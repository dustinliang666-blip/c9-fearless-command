"""Run the C9 Fearless Command local workbench or the synthetic public demo."""

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tracks.bounties.cloud9_jetbrains.app.demo import demo_cache
from tracks.bounties.cloud9_jetbrains.contracts import (
    BLUE, CACHE_VERSION, FORMAT_MODES, HARD_FEARLESS, OBJECTIVES, RED, order_for, runtime_paths,
)
from tracks.bounties.cloud9_jetbrains.engine.draft_engine import (
    EMPTY, STAGES, Predictor, SeriesDraft, evidence, how_to_win, load_cache, scouting_profile,
)


STATIC = Path(__file__).with_name("static")
MAX_BODY = 64 * 1024


class Workbench:
    def __init__(self, cache, *, demo=False):
        self.cache = cache
        self.demo = demo
        self.predictor = Predictor(cache["model"])
        self.teams = {
            team: cache["names"]["teams"].get(team, team)
            for team in cache["scouting"]["teams"]
        }
        self.champions = cache["names"]["characters"]
        self.patches = sorted({
            scope.removeprefix("patch:") for scopes in cache["scouting"]["teams"].values()
            for scope in scopes if scope.startswith("patch:") and "/" not in scope
        }, key=lambda patch: tuple((0, int(part)) if part.isdecimal() else (1, part)
                                   for part in patch.split(".")), reverse=True)

    def check_team(self, team):
        if not isinstance(team, str) or team not in self.teams:
            raise ValueError("Select a known team")
        return team

    def check_patch(self, patch):
        if patch != "" and patch not in self.patches:
            raise ValueError("Select a known patch or all patches")
        return patch

    def health(self):
        return {"status": "ok", "mode": "synthetic" if self.demo else "licensed_local",
                "cache_version": CACHE_VERSION, "model_as_of": self.predictor.as_of.isoformat(),
                "coverage": self.cache["coverage"]}

    def catalog(self):
        regions = self.cache["scouting"]["competitions"]
        roster = [{"id": team, "name": self.teams[team], "competitions": regions.get(team, [])}
                  for team in sorted(self.teams, key=self.teams.get)]
        by_name = {name: team for team, name in self.teams.items()}
        return {
            "teams": roster, "patches": self.patches,
            "default_team": by_name.get("Northstar" if self.demo else "Cloud9 Kia", roster[0]["id"]),
            "default_opponent": by_name.get("Redshift" if self.demo else "FlyQuest", roster[1]["id"]),
        }

    def scouting(self, team, patch, side):
        self.check_team(team)
        self.check_patch(patch)
        if side not in ("", BLUE, RED):
            raise ValueError("Select blue, red, or both sides")
        scope = f"{side + ' side' if side else 'both sides'}, {('patch ' + patch) if patch else 'all patches'}"
        profile = scouting_profile(self.cache, team, patch=patch, side=side or None)

        def top(table, total, description):
            rows = sorted(table.items(), key=lambda row: (-row[1][0], self.champions.get(row[0], row[0])))
            return [{"name": self.champions.get(hero, hero), "champion": hero, "wins": wins,
                     "evidence": evidence(count, total, "games", f"{scope}, {description}")}
                    for hero, (count, wins) in rows[:5]]

        macro = profile.get("macro", {})
        objectives = []
        for kind in OBJECTIVES:
            outcomes = macro.get("first", {}).get(kind, {})
            n = sum(cell[0] for cell in outcomes.values())
            objectives.append({"objective": kind, "evidence": evidence(
                outcomes.get("secured", EMPTY)[0], n, "games", f"{scope}, first {kind} by 15:00",
            )})
        gold_n, gold_sum, *_ = macro.get("gold", [0, 0])
        return {
            "team": self.teams[team], "scope": scope, "games": profile.get("n", 0),
            "wins": profile.get("wins", 0), "first_objectives": objectives,
            "gold_at_15": {"mean": gold_sum / gold_n if gold_n else None, "games": gold_n},
            "picks": top(profile.get("picks", {}), profile.get("n", 0), "played games"),
            "opening_bans": top(profile.get("draft", {}).get("ban1", {}),
                                profile.get("draft_n", {}).get("ban1", 0), "ordered drafts"),
        }

    def evaluate(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        if "as_of" in payload:
            raise ValueError("This endpoint simulates with serving data. Use the historical replay CLI for as_of.")
        team = self.check_team(payload.get("team"))
        opponent = self.check_team(payload.get("opponent"))
        patch = self.check_patch(payload.get("patch", ""))
        mode = payload.get("format_mode", HARD_FEARLESS)
        if mode not in FORMAT_MODES:
            raise ValueError("Unsupported format_mode")
        games = payload.get("games", [{}])
        view = payload.get("view_game", len(games) if isinstance(games, list) else None)
        if (not isinstance(games, list) or not 1 <= len(games) <= 5 or type(view) is not int
                or not 1 <= view <= len(games) or not all(isinstance(game, dict) for game in games)):
            raise ValueError("Send one to five game objects and a valid view_game")

        def sides(game):
            blue_team = game.get("blue", team)
            first_pick = game.get("first_pick_side", BLUE)
            if blue_team not in (team, opponent) or first_pick not in (BLUE, RED):
                raise ValueError("Invalid map side or first pick")
            return blue_team, first_pick

        blue, priority = sides(games[0])
        series = SeriesDraft(blue, opponent if blue == team else team, self.champions,
                             best_of=5, format_mode=mode, first_pick_side=priority)
        states = []
        for index, game in enumerate(games):
            actions = game.get("actions", [])
            if not isinstance(actions, list) or len(actions) > 20:
                raise ValueError("Each game accepts up to 20 draft actions")
            for champion in actions:
                if champion is not None and not isinstance(champion, str):
                    raise ValueError("A draft action must name a champion or pass a ban")
                if series.current.turn is None:
                    raise ValueError("Draft is complete")
                side, kind, _ = series.current.turn
                series.apply(side, kind, champion)
            states.append(series.current)
            winner = game.get("winner")
            if winner is not None and winner not in (team, opponent):
                raise ValueError("Invalid game winner")
            if index + 1 < len(games):
                blue, priority = sides(games[index + 1])
                if series.finish_game(winner, next_blue=blue, next_first_pick=priority) is None:
                    raise ValueError("No games may follow a series winner")
            elif winner is not None:
                series.finish_game(winner)

        state = states[view - 1]
        curve = self.predictor.curve(state, patch=patch)
        slots = [
            {"side": side, "kind": kind, "phase": phase,
             "champion": self.champions.get(state.actions[index].champion) if index < len(state.actions) else None}
            for index, (side, kind, phase) in enumerate(order_for(state.first_pick_side))
        ]
        recommendations = self.predictor.recommend(state, patch=patch, limit=10)
        for row in recommendations:
            target = row["team"]
            row["name"] = self.champions[row["champion"]]
            row["evidence"] = evidence(row["n"], self.predictor.stats.team.get(target, EMPTY)[0],
                                       "games", f"{self.teams[target]} picks, all patches")
        step = len(state.actions)
        stage = next((stage for stage in STAGES if step <= stage), None) if step else None
        upcoming_stage = next((stage for stage in STAGES if step + 1 <= stage), None)
        return {
            "format_mode": mode, "game": view, "blue": state.blue, "red": state.red, "step": step,
            "model_as_of": self.predictor.as_of.isoformat(),
            "turn": state.turn, "slots": slots, "wins": series.wins, "series_winner": series.winner,
            "blue_probability": curve[-1], "curve": [{"step": index, "blue_probability": value,
                "delta_pp": 100 * (value - curve[0])} for index, value in enumerate(curve)],
            "stage_gamma": self.predictor.model["gamma"][str(stage)] if stage else None,
            "next_stage_gamma": self.predictor.model["gamma"][str(upcoming_stage)] if upcoming_stage else None,
            "locks": self.named(state.fearless_locks), "available": self.named(state.available),
            "recommendations": recommendations,
            "brief": how_to_win(self.cache, self.predictor, state, opponent, patch=patch),
            "can_finish": view == len(games) and state.turn is None and not series.winner
                and games[-1].get("winner") is None,
        }

    def named(self, champions):
        return [{"id": hero, "name": self.champions[hero]}
                for hero in sorted(champions, key=self.champions.get)]


def create_server(host="127.0.0.1", port=8000, *, demo=False, cache_path=None, quiet=False):
    if not demo and host not in ("127.0.0.1", "localhost"):
        raise ValueError("Licensed scouting runs on the local loopback interface")
    cache = demo_cache() if demo else load_cache(cache_path if cache_path is not None else runtime_paths()[1])
    app = Workbench(cache, demo=demo)
    index_html = (STATIC / "index.html").read_bytes()
    script = (STATIC / "workbench.js").read_bytes()
    styles = (STATIC / "workbench.css").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            if not quiet:
                super().log_message(*args)

        def send(self, body: bytes, kind: str, status: HTTPStatus | int = HTTPStatus.OK):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, payload, status: HTTPStatus | int = HTTPStatus.OK):
            self.send(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                      "application/json; charset=utf-8", status)

        def allowed_host(self):
            if demo:
                return True
            raw = (self.headers.get("Host") or "").strip().lower()
            actual_port = self.server.server_port
            allowed = {
                f"127.0.0.1:{actual_port}", f"localhost:{actual_port}", f"[::1]:{actual_port}",
            }
            if actual_port == 80:
                allowed |= {"127.0.0.1", "localhost", "[::1]"}
            return raw in allowed

        def do_GET(self):
            if not self.allowed_host():
                self.send_json({"error": "Forbidden Host header"}, HTTPStatus.FORBIDDEN)
                return
            url = urlsplit(self.path)
            if url.path == "/":
                self.send(index_html, "text/html; charset=utf-8")
            elif url.path == "/workbench.css":
                self.send(styles, "text/css; charset=utf-8")
            elif url.path == "/workbench.js":
                self.send(script, "text/javascript; charset=utf-8")
            elif url.path == "/api/health":
                self.send_json(app.health())
            elif url.path == "/api/teams":
                self.send_json(app.catalog())
            elif url.path == "/api/scouting":
                try:
                    query = parse_qs(url.query, max_num_fields=12)
                    self.send_json(app.scouting(*(query.get(key, [""])[0] for key in ("team", "patch", "side"))))
                except ValueError as error:
                    self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            else:
                self.send_json({"error": "Page not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self):
            if not self.allowed_host():
                self.send_json({"error": "Forbidden Host header"}, HTTPStatus.FORBIDDEN)
                return
            if urlsplit(self.path).path != "/api/draft/evaluate":
                self.send_json({"error": "Page not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= MAX_BODY:
                    raise ValueError("Expected a JSON body of up to 64 KiB")
                payload = json.loads(self.rfile.read(size))
                self.send_json(app.evaluate(payload))
            except (ValueError, RecursionError) as error:
                self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Use original synthetic practice fixtures")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        server = create_server(args.host, args.port, demo=args.demo)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    with server:
        print(f"Fearless Command | http://{args.host}:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
