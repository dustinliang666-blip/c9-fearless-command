"""Stream GRID League of Legends feeds and write the local aggregate cache."""

from collections import Counter, defaultdict
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tracks.bounties.cloud9_jetbrains.contracts import (
    Action, BLUE, CACHE_VERSION, DRAFT_ORDER, FORMAT_MODES, Game, HARD_FEARLESS,
    OBJECTIVES, RED, STANDARD, UNKNOWN, fearless_contexts,
    order_for, runtime_paths, series_groups,
)

try:
    from orjson import loads
except ImportError:
    from json import loads


DRAFT_EVENTS = ("team-picked-character", "team-banned-character")
MACRO_EVENTS = {
    "player-killed-player": "first_blood",
    "player-completed-slayVoidGrub": "grubs",
    "player-completed-slayRiftHerald": "herald",
    "player-completed-slayDragon": "dragon",
    "player-completed-slayElderDragon": "dragon",
}


def format_mode(event, stage, best_of, explicit=None):
    """Resolve format from published competition rules and optional explicit metadata."""
    if explicit in FORMAT_MODES:
        return explicit
    if best_of == 1:
        return STANDARD
    if best_of not in (3, 5):
        return UNKNOWN
    if event == "LEC - Winter 2025":
        return HARD_FEARLESS if stage == "Playoffs" else UNKNOWN
    if event in {"LCK - LCK Cup 2025", "LTA North - Split 1 2025", "LTA South - Split 1 2025",
                 "LTA Cross-Conference - Split 1 2025"}:
        return HARD_FEARLESS
    if event in {
        "LCK - Split 2 2025", "LCK - Split 3 2025", "LEC - Spring 2025", "LEC - Summer 2025",
        "LTA North - Split 2 2025", "LTA South - Split 2 2025", "LTA North - Split 3 2025",
        "LTA South - Split 3 2025", "LTA Cross-Conference - Regional Championship 2025",
        "LCS - Promotion 2026", "LCS - Split 1 2026", "LCS - Split 2 2026", "LCS - Split 3 2026",
        "LEC - LEC Versus 2026", "LEC - Spring 2026",
    }:
        return HARD_FEARLESS
    return UNKNOWN


def objective_for(event_type):
    if event_type.startswith("player-completed-slay") and event_type.endswith("Drake"):
        return "dragon"
    return MACRO_EVENTS.get(event_type)


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream)


def lol_metadata(data, stem):
    return (row for row in csv_rows(data / "meta" / f"{stem}.csv") if row["title"] == "lol")


def read_metadata(data):
    names = {
        stem: {row[f"{entity}_id"]: row["name"] for row in lol_metadata(data, stem)}
        for stem, entity in (("teams", "team"), ("players", "player"), ("characters", "character"))
    }
    games = defaultdict(dict)
    invalid = set()
    dropped = 0
    for row in lol_metadata(data, "games"):
        series, session = row["series_id"], int(row["session"])
        if row["session_valid"] != "True":
            invalid.add((series, session))
            continue
        sides = {row[f"team{i}_side"]: row[f"team{i}_id"] for i in (1, 2)}
        winner = row["winner_team_id"]
        if (
            row["finished"] != "True" or not row["started_at"]
            or set(sides) != {BLUE, RED} or not winner or winner not in sides.values()
        ):
            dropped += 1
            continue
        game_id = row["game_id"]
        games[series][session, game_id] = Game(
            series, game_id, session, int(row["game_number"]), row["patch"],
            datetime.fromisoformat(row["started_at"]), sides[BLUE], sides[RED],
            int(winner == sides[BLUE]),
        )
    for row in lol_metadata(data, "rosters"):
        game = games.get(row["series_id"], {}).get((int(row["session"]), row["game_id"]))
        if game and row["participation_status"] == "active" and row["character_id"]:
            team = row["team_id"]
            if team in (game.blue, game.red):
                game.roster.setdefault(team, {})[row["player_id"]] = row["character_id"]
    return names, games, invalid, dropped


def zstd_open(path):
    try:
        from compression import zstd
    except ImportError:
        import zstandard as zstd
    return zstd.open(path, "rt", encoding="utf-8")


def is_present(champion):
    return bool(champion and champion.lower() not in {"none", "null", "no-ban", "0"})


def unpack_action(entry, game):
    team = entry.get("drafter", {}).get("id")
    side = BLUE if team == game.blue else RED if team == game.red else None
    draftable = entry.get("draftable") or {}
    champion = draftable.get("id")
    if side and entry.get("type") in {"pick", "ban"}:
        return Action(side, entry["type"], champion if is_present(champion) else None)
    return None


class GameFeed:
    def __init__(self, game):
        self.game = game
        self.draft = {}
        self.draft_times = {}
        self.macro = defaultdict(list)
        self.gold_at = -1
        self.gold_diff = None
        self.max_clock = -1

    def load_draft(self, entries, stamp, replace=False):
        draft, times = ({}, {}) if replace else (self.draft.copy(), self.draft_times.copy())
        for entry in entries:
            sequence = entry.get("sequenceNumber")
            action = unpack_action(entry, self.game)
            if isinstance(sequence, int) and action:
                draft[sequence] = action
                times[sequence] = (self.draft_times[sequence] if self.draft.get(sequence) == action
                                   else stamp)
        self.draft, self.draft_times = draft, times

    def observe(self, event, state, stamp, seen):
        kind = event["type"]
        entries = state.get("draftActions")
        is_draft_action = kind in DRAFT_EVENTS
        if is_draft_action:
            seen[kind] += 1
        if is_draft_action or (entries and not self.draft):
            first = datetime.fromisoformat(stamp)
            if self.game.first_draft_at is None or first < self.game.first_draft_at:
                self.game.first_draft_at = first
        if event.get("includesFullState") and entries:
            self.load_draft(entries, stamp, replace=True)
        elif is_draft_action:
            self.load_draft(entries or (), stamp)
        elif kind in ("team-!picked-character", "team-!banned-character"):
            team = event["actor"].get("id")
            side = BLUE if team == self.game.blue else RED
            action = Action(side, "pick" if "picked" in kind else "ban", event["target"].get("id"))
            for seq in sorted(self.draft, reverse=True):
                if self.draft[seq] == action:
                    del self.draft[seq]
                    del self.draft_times[seq]
                    break

        if kind == "series-ended-game" and event.get("target", {}).get("id") == self.game.game_id:
            self.game.end = datetime.fromisoformat(stamp)
        elif self.game.end is None and state.get("finished") is True:
            self.game.end = datetime.fromisoformat(stamp)

        undo = "-!" in kind
        original = kind.replace("-!", "-", 1) if undo else kind
        objective = objective_for(original)
        if objective:
            seen[kind] += 1
        clock = (state.get("clock") or {}).get("currentSeconds")
        if objective:
            actor, target = event.get("actor", {}), event.get("target", {})
            team = (actor.get("state") or {}).get("teamId")
            if team in (self.game.blue, self.game.red):
                claims = self.macro[objective]
                identity = (actor.get("id"), target.get("id"))
                if undo:
                    for index in range(len(claims) - 1, -1, -1):
                        _, owner, event_type, recorded = claims[index]
                        if (owner, event_type) == (team, original) and all(
                            a is None or b is None or a == b for a, b in zip(identity, recorded)
                        ):
                            del claims[index]
                            break
                elif isinstance(clock, (int, float)):
                    claims.append((clock, team, original, identity))
        if not isinstance(clock, (int, float)):
            return
        self.max_clock = max(self.max_clock, clock)
        if 870 <= clock <= 900 and clock >= self.gold_at:
            gold = {
                team["id"]: team["totalMoneyEarned"]
                for team in state.get("teams", ())
                if isinstance(team.get("totalMoneyEarned"), (int, float))
            }
            if self.game.blue in gold and self.game.red in gold:
                self.gold_at = clock
                self.gold_diff = int(gold[self.game.blue] - gold[self.game.red])

    def finish(self):
        sequences = sorted(self.draft)
        ordered = tuple(self.draft[i] for i in sequences)
        # Feed ordinals can be compacted when a team forfeits a ban. Restore a
        # pass only on a unique alignment of the published turns.
        self.game.actions = ordered
        for first in (BLUE, RED):
            aligned = align_draft(ordered, order_for(first))
            if aligned is not None:
                self.game.actions = aligned
                self.game.first_pick_side = first
                observed = iter(datetime.fromisoformat(self.draft_times[i]) for i in sequences)
                last = max(datetime.fromisoformat(self.draft_times[i]) for i in sequences)
                cursor = 0
                times = []
                for action in aligned:
                    if cursor < len(ordered) and action == ordered[cursor]:
                        times.append(next(observed))
                        cursor += 1
                    else:
                        times.append(last)
                self.game.action_times = tuple(times)
                break
        self.game.early_observed = self.max_clock >= 900
        self.game.gold_diff = self.gold_diff if self.game.early_observed else None
        early = {key: [claim for claim in claims if 0 < claim[0] <= 900]
                 for key, claims in self.macro.items()}
        self.game.first = {
            key: min(claims, key=lambda claim: claim[0])[1]
            for key, claims in early.items() if claims
        }
        self.game.grubs = dict(Counter(claim[1] for claim in early.get("grubs", ())))


def align_draft(actions, order=DRAFT_ORDER):
    if len(actions) == len(DRAFT_ORDER):
        return actions if all((a.side, a.kind) == turn[:2] for a, turn in zip(actions, order)) else None

    def align(turn, offset, prefix):
        if turn == len(order):
            if offset == len(actions):
                yield prefix
            return
        if len(actions) - offset > len(order) - turn:
            return
        side, kind, _ = order[turn]
        if offset < len(actions) and (actions[offset].side, actions[offset].kind) == (side, kind):
            yield from align(turn + 1, offset + 1, prefix + (actions[offset],))
        if kind == "ban":
            yield from align(turn + 1, offset, prefix + (Action(side, kind, None),))

    possibilities = align(0, 0, ())
    first = next(possibilities, None)
    return first if next(possibilities, None) is None else None


def consume_feed(envelopes, games, seen):
    collectors = {key: GameFeed(game) for key, game in games.items()}
    valid_sessions = {session for session, _ in games}
    formats = {}
    session = 0
    for envelope in envelopes:
        events = envelope["events"]
        if any(event["type"] == "grid-started-feed" for event in events):
            session += 1
        elif session == 0:
            # Some valid files begin after sequence 1 and omit the first marker.
            session = 1
        if session not in valid_sessions:
            continue
        for event in events:
            state = event.get("seriesState", {})
            fmt = state.get("format")
            if fmt in ("best-of-1", "best-of-3", "best-of-5"):
                formats[session] = int(fmt[-1])
            game_states = state.get("games", ())
            if not game_states:
                continue
            target, actor = event.get("target", {}), event.get("actor", {})
            direct = next((entity.get("id") for entity in (target, actor) if entity.get("type") == "game"), None)
            if direct is None and event["type"] in {"series-started-game", "series-ended-game"}:
                direct = target.get("id")
            delta = {game.get("id") for game in event.get("seriesStateDelta", {}).get("games", ())}
            if direct:
                active = {direct}
            elif len(delta) == 1:
                active = delta
            elif len(game_states) == 1 and not delta:
                active = {game_states[0].get("id")}
            else:
                unfinished = {game.get("id") for game in game_states if game.get("finished") is not True}
                active = unfinished if len(unfinished) == 1 and (not delta or unfinished <= delta) else set()
            for game_state in game_states:
                key = (session, game_state.get("id"))
                collector = collectors.get(key)
                if collector is not None and key[1] in active:
                    collector.observe(event, game_state, envelope["occurredAt"], seen)
    for (session, _), collector in collectors.items():
        collector.game.best_of = formats.get(session)
        collector.finish()


def scan_corpus(data, *, progress=False):
    names, series, invalid, dropped = read_metadata(data)
    event_ids = {row["event"]: row["event_tournament_id"] for row in lol_metadata(data, "tournaments")}
    indexes = list(csv_rows(data / "lol" / "series.csv"))
    seen = Counter()
    streamed = set()
    event_coverage = {}
    for index, row in enumerate(indexes, 1):
        series_id = row["series_id"]
        feed = data / row["file"]
        games = series.get(series_id, {})
        if not feed.is_file():
            raise FileNotFoundError(feed)
        if games:
            with zstd_open(feed) as stream:
                consume_feed((loads(line) for line in stream), games, seen)
            streamed.add(series_id)
            event = row["event"]
            for game in games.values():
                game.format_mode = format_mode(event, row["stage"], game.best_of, row.get("format_mode"))
                game.competition = event.partition(" - ")[0]
            totals = event_coverage.setdefault(event, {"event_id": event_ids.get(event), "series": 0, "games": 0})
            totals["series"] += 1
            totals["games"] += len(games)
        if progress and (index % 100 == 0 or index == len(indexes)):
            print(f"Indexed {index}/{len(indexes)} series (streamed {len(streamed)} valid feeds)", flush=True)

    missing = set(series) - streamed
    if missing:
        raise ValueError(f"{len(missing)} valid series missing from the LoL index")
    games = [game for rows in series.values() for game in rows.values()]
    counts = {
        "indexed_series": len(indexes),
        "valid_series": len(streamed),
        "invalid_sessions": len(invalid),
        "valid_games": len(games),
        "unusable_valid_metadata_rows": dropped,
        "complete_drafts": sum(game.complete_draft for game in games),
        "red_first_drafts": sum(game.complete_draft and game.first_pick_side == RED for game in games),
        "early_observed_games": sum(game.early_observed for game in games),
        "gd15_games": sum(game.gold_diff is not None for game in games),
        "events": dict(sorted(seen.items())),
        "competition_coverage": event_coverage,
        "format_games": dict(Counter(game.format_mode for game in games)),
        "adjacent_draft_overlaps": sum(
            earlier.end is not None and earlier.end >= later.draft_start
            for group in series_groups(games) for earlier, later in zip(group, group[1:])
        ),
    }
    return games, names, counts


def new_profile():
    return {
        "n": 0, "wins": 0, "picks": {}, "draft_n": {}, "draft": {},
    }


def count_result(table, key, won):
    count = table.setdefault(key, [0, 0])
    count[0] += 1
    count[1] += won


def record_draft(profile, game, side, won):
    if not game.complete_draft:
        return
    picks = 0
    for action, (_, _, phase) in zip(game.actions, order_for(game.first_pick_side)):
        if action.side != side:
            continue
        group = f"{action.kind}{phase}"
        if action.kind == "pick":
            picks += 1
        for key in (group, "first_pick") if action.kind == "pick" and picks == 1 else (group,):
            stats = profile["draft"].setdefault(key, {})
            if action.champion:
                count_result(stats, action.champion, won)
    for key in profile["draft"]:
        profile["draft_n"][key] = profile["draft_n"].get(key, 0) + 1


def record_macro(profile, game, team, won, side):
    macro = profile.setdefault("macro", {"gold": [0, 0, 0, 0, 0], "grubs": [0, 0], "first": {}})
    if game.early_observed:
        for objective in OBJECTIVES:
            owner = game.first.get(objective)
            status = "secured" if owner == team else "conceded" if owner else "none"
            count_result(macro["first"].setdefault(objective, {}), status, won)
        macro["grubs"][0] += 1
        macro["grubs"][1] += game.grubs.get(team, 0)
    if game.gold_diff is not None:
        diff = game.gold_diff if side == BLUE else -game.gold_diff
        stats = macro["gold"]
        stats[0] += 1
        stats[1] += diff
        stats[2] += diff > 0
        stats[3] += won if diff > 0 else 0
        stats[4] += won


def profile_groups(index, entity, patch, side):
    groups = index.setdefault(entity, {})
    for key in ("all", f"patch:{patch}", f"side:{side}", f"patch:{patch}/side:{side}"):
        yield groups.setdefault(key, new_profile())


def add_transitions(game, side, prior, cohort):
    if not game.complete_draft:
        return
    bans, opposing_picks, seen = set(), set(), set()
    for action in game.actions:
        champion = action.champion
        if champion is None:
            continue
        if action.kind == "ban":
            bans.add(champion)
        elif action.side != side:
            opposing_picks.add(champion)
        else:
            cohorts = ("prior_pick", prior), ("draft_ban", bans - prior), ("opponent_pick", opposing_picks)
            for reason, unavailable in cohorts:
                matrix = cohort["transitions"].setdefault(reason, {})
                for blocked in unavailable:
                    stats = matrix.setdefault(blocked, {"n": 0, "distinct_games": 0, "next": {}})
                    stats["n"] += 1
                    if (reason, blocked) not in seen:
                        stats["distinct_games"] += 1
                        seen.add((reason, blocked))
                    stats["next"][champion] = stats["next"].get(champion, 0) + 1


def aggregate(games):
    teams, players, fearless = {}, {}, {}
    lineups = {}
    for game in sorted(games, key=lambda g: g.start):
        for side, team, won in ((BLUE, game.blue, game.blue_won), (RED, game.red, 1 - game.blue_won)):
            roster = game.roster.get(team, {})
            if len(roster) == 5:
                lineups[team] = sorted(roster)
            for profile in profile_groups(teams, team, game.patch, side):
                profile["n"] += 1
                profile["wins"] += won
                for champion in set(roster.values()):
                    count_result(profile["picks"], champion, won)
                record_draft(profile, game, side, won)
                record_macro(profile, game, team, won, side)
            for player, champion in roster.items():
                for profile in profile_groups(players, player, game.patch, side):
                    profile["n"] += 1
                    profile["wins"] += won
                    count_result(profile["picks"], champion, won)
                    if game.complete_draft:
                        for key in ("ban1", "ban2"):
                            profile["draft_n"][key] = profile["draft_n"].get(key, 0) + 1
                        for action, (_, _, phase) in zip(game.actions, order_for(game.first_pick_side)):
                            if action.kind == "ban" and action.side == side and action.champion:
                                bans = profile["draft"].setdefault(f"ban{phase}", {})
                                count_result(bans, action.champion, won)
    for group in series_groups(games):
        for game, prior in fearless_contexts(group, retrospective=True):
            for side, team, won in ((BLUE, game.blue, game.blue_won), (RED, game.red, 1 - game.blue_won)):
                cohort = fearless.setdefault(team, {}).setdefault(str(game.number), {
                    "n": 0, "wins": 0, "pool_size_sum": 0, "remaining_pool_sum": 0,
                    "picks": {}, "transitions": {},
                })
                pool = set(teams[team]["all"]["picks"])
                cohort["n"] += 1
                cohort["wins"] += won
                cohort["pool_size_sum"] += len(pool)
                cohort["remaining_pool_sum"] += len(pool - prior)
                for champion in game.picks[side]:
                    count_result(cohort["picks"], champion, won)
                add_transitions(game, side, prior, cohort)
    competitions = defaultdict(set)
    for game in games:
        if game.competition:
            competitions[game.blue].add(game.competition)
            competitions[game.red].add(game.competition)
    return {"teams": teams, "players": players, "fearless": fearless, "lineups": lineups,
            "competitions": {team: sorted(regions) for team, regions in competitions.items()}}


def write_cache(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def print_summary(cache):
    counts = cache["coverage"]
    print(
        f"LoL: {counts['valid_series']}/{counts['indexed_series']} valid series, "
        f"{counts['valid_games']} valid games, {counts['invalid_sessions']} invalid sessions excluded"
    )
    print(
        f"Ordered drafts: {counts['complete_drafts']} ({counts['red_first_drafts']} red-first); "
        f"clock through 15:00: {counts['early_observed_games']}; GD@15: {counts['gd15_games']}"
    )
    print("Observed draft and early macro event types:", ", ".join(counts["events"]))
    team = next((team for team, name in cache["names"]["teams"].items() if name == "Cloud9 Kia"), None)
    if team not in cache["scouting"]["teams"]:
        return
    profile = cache["scouting"]["teams"][team]["all"]
    print(f"Cloud9 Kia: {profile['wins']}/{profile['n']} wins; {len(profile['picks'])} distinct picks.")
    for objective, results in profile["macro"]["first"].items():
        secured = results.get("secured", (0, 0))[0]
        print(f"  {objective} secured by 15:00: {secured}/{sum(cell[0] for cell in results.values())}")
    n, total, *_ = profile["macro"]["gold"]
    if n:
        print(f"  Mean GD@15: {total / n:+.0f} gold (n={n})")


def main():
    from tracks.bounties.cloud9_jetbrains.engine.draft_engine import train_and_validate

    data, output = runtime_paths()
    games, names, coverage = scan_corpus(data, progress=True)
    cache = {
        "version": CACHE_VERSION, "coverage": coverage, "names": names,
        "scouting": aggregate(games), "model": train_and_validate(games),
    }
    write_cache(output, cache)
    print_summary(cache)
    print(f"Local aggregate cache: {output}")


if __name__ == "__main__":
    main()
