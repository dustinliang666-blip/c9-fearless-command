"""HTTP and optional headless browser smoke tests with deterministic fixtures."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
from threading import Thread
from unittest import SkipTest, TestCase
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tracks.bounties.cloud9_jetbrains.app.server import create_server
from tracks.bounties.cloud9_jetbrains.contracts import runtime_paths


@contextmanager
def running_server(**options):
    with create_server(port=0, quiet=True, **options) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=5)
            if thread.is_alive():
                raise AssertionError("Temporary HTTP server failed to shut down")


def get_json(base, path, payload=None):
    request = Request(base + path)
    if payload is not None:
        request.data = json.dumps(payload).encode("utf-8")
        request.add_header("Content-Type", "application/json")
    with urlopen(request, timeout=10) as response:
        return json.load(response)


class WorkbenchTests(TestCase):
    def check_endpoints(self, base, mode):
        health = get_json(base, "/api/health")
        self.assertEqual((health["status"], health["mode"]), ("ok", mode))
        self.assertGreater(health["coverage"]["valid_games"], 0)
        teams = get_json(base, "/api/teams")
        team, opponent = teams["default_team"], teams["default_opponent"]
        query = urlencode({"team": opponent})
        profile = get_json(base, f"/api/scouting?{query}")
        self.assertGreater(profile["games"], 0)
        self.assertEqual(len(profile["first_objectives"]), 4)
        self.assertEqual(profile["picks"][0]["evidence"]["unit"], "games")
        payload = {"team": team, "opponent": opponent, "games": [{}]}
        board = get_json(base, "/api/draft/evaluate", payload)
        self.assertEqual((board["game"], board["step"], len(board["slots"])), (1, 0, 20))
        self.assertEqual(board["curve"][0]["delta_pp"], 0)
        self.assertTrue(0 < board["blue_probability"] < 1)
        self.assertTrue(board["recommendations"])
        self.assertTrue(board["brief"])
        for card in board["brief"]:
            self.assertEqual(set(card["evidence"]), {"numerator", "denominator", "unit", "scope", "distinct_games"})
        return payload, board

    def test_synthetic_http_and_frontend_assets(self):
        with running_server(demo=True, cache_path=Path("missing-cache-file.json")) as base:
            payload, board = self.check_endpoints(base, "synthetic")
            for asset, expected_type, token in (
                ("/", "text/html", b'id="game-tabs"'),
                ("/workbench.css", "text/css", b".workspace"),
                ("/workbench.js", "text/javascript", b"/api/draft/evaluate"),
            ):
                with urlopen(base + asset, timeout=5) as response:
                    self.assertEqual(response.headers.get_content_type(), expected_type)
                    self.assertIn(token, response.read())
            with self.assertRaises(HTTPError) as invalid:
                get_json(base, "/api/draft/evaluate", payload | {"as_of": "2030-01-02T00:00:00Z"})
            self.assertEqual(invalid.exception.code, 400)
            self.assertIn("historical", json.load(invalid.exception)["error"])
            with self.assertRaises(HTTPError) as invalid:
                get_json(base, "/api/draft/evaluate", payload | {"games": [{"actions": [123]}]})
            self.assertEqual(invalid.exception.code, 400)
            self.assertEqual(board["format_mode"], "hard_fearless")
        with self.assertRaises(URLError):
            urlopen(base + "/api/health", timeout=1)

    def test_http_game_five_carries_only_picks_and_exposes_turn_counts(self):
        with running_server(demo=True) as base:
            payload, board = self.check_endpoints(base, "synthetic")
            locks = set()
            for number in range(1, 6):
                self.assertEqual(len(board["locks"]), 10 * (number - 1))
                pool = [hero["id"] for hero in board["available"]]
                actions = pool[:20]
                current = payload["games"][-1]
                current["actions"] = actions
                curve = get_json(base, "/api/draft/evaluate", payload)["curve"]
                self.assertEqual(len(curve), 21)
                locks.update(actions[i] for i, slot in enumerate(board["slots"]) if slot["kind"] == "pick")
                current["winner"] = payload["team"] if number % 2 else payload["opponent"]
                if number == 5:
                    break
                payload["games"].append({"blue": payload["opponent"], "first_pick_side": "red"})
                board = get_json(base, "/api/draft/evaluate", payload)
                self.assertEqual({row["id"] for row in board["locks"]}, locks)
                self.assertIn(actions[0], {row["id"] for row in board["available"]})
                transition = next((card for card in board["brief"] if card["kind"] == "fearless_replacement"), None)
                if number == 1:
                    self.assertIsNotNone(transition)
                    sample = transition["evidence"]
                    self.assertEqual(sample["unit"], "pick_turns")
                    self.assertEqual(sample["denominator"], 5 * sample["distinct_games"])
            complete = get_json(base, "/api/draft/evaluate", payload)
            self.assertEqual((complete["game"], complete["series_winner"]), (5, payload["team"]))
            self.assertIsNone(complete["turn"])
            payload["games"][1]["actions"][0] = payload["games"][0]["actions"][6]
            with self.assertRaises(HTTPError) as illegal:
                get_json(base, "/api/draft/evaluate", payload)
            self.assertEqual(illegal.exception.code, 400)
            self.assertIn("unavailable", json.load(illegal.exception)["error"])
            self.assertEqual(get_json(base, "/api/draft/evaluate", payload | {"format_mode": "unknown"})["locks"], [])

    def test_licensed_http_reads_external_cache_without_rewriting_it(self):
        _, path = runtime_paths()
        if not os.environ.get("C9_CACHE_DIR") and not path.is_file():
            self.skipTest("Licensed cache is unavailable")
        before = path.stat()
        with running_server(cache_path=path) as base:
            payload, _ = self.check_endpoints(base, "licensed_local")
            teams = get_json(base, "/api/teams")
            self.assertIn("Cloud9 Kia", {team["name"] for team in teams["teams"] if team["id"] == payload["team"]})
        self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(path.stat().st_size, before.st_size)

    def test_browser_smoke(self):
        try:
            from playwright.sync_api import ViewportSize, expect, sync_playwright
        except ImportError as exc:
            raise SkipTest("Playwright is unavailable") from exc

        viewport = ViewportSize(width=1440, height=900)
        with running_server(demo=True) as base, sync_playwright() as playwright:
            settings = {"channel": "msedge"} if os.name == "nt" else {}
            browser = playwright.chromium.launch(**settings)
            try:
                page = browser.new_page(viewport=viewport)
                errors, external = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: external.append(request.url) if not request.url.startswith(base) else None)
                page.goto(base)
                expect(page.get_by_role("heading", name="Draft workbench")).to_be_visible()
                expect(page.locator("#scouting")).to_contain_text("First dragon")
                expect(page.locator("#turn")).to_contain_text("Turn 1/20")
                expect(page.locator(".brief-card")).not_to_have_count(0)
                page.locator("#swap").click()
                expect(page.locator("#turn")).to_contain_text("Redshift")
                page.locator("#priority").select_option("red")
                expect(page.locator("#turn")).to_contain_text("Northstar")
                page.locator("#pass").click()
                expect(page.locator("#curve circle")).to_have_count(2)
                page.locator("#undo").click()
                expect(page.locator("#curve circle")).to_have_count(1)
                for step in range(20):
                    page.locator(".recommendation").first.click()
                    expect(page.locator("#curve circle")).to_have_count(step + 2)
                page.get_by_role("button", name="Record result").click()
                expect(page.get_by_role("button", name="Game 2")).to_have_attribute("aria-pressed", "true")
                expect(page.locator("#lock-count")).to_have_text("10")
                page.get_by_role("button", name="Game 1").click()
                expect(page.locator("#curve circle")).to_have_count(21)
                page.set_viewport_size({"width": 390, "height": 844})
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
                self.assertEqual(errors, [])
                self.assertEqual(external, [])
            finally:
                browser.close()
