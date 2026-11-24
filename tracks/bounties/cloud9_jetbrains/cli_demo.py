"""Replay a hypothetical Cloud9 Kia vs FlyQuest Hard Fearless series."""

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tracks.bounties.cloud9_jetbrains.contracts import BLUE, HARD_FEARLESS, RED, runtime_paths
from tracks.bounties.cloud9_jetbrains.engine.draft_engine import (
    Predictor, SeriesDraft, how_to_win, key, load_cache,
)


def format_options(rows, names):
    return " | ".join(
        f"{names.get(row['champion'], row['champion'])} {row['delta_pp']:+.2f} pp (n={row['n']})"
        for row in rows
    )


def lineup_candidates(state, side, players, stats):
    """Keep picks that can be assigned to distinct players with prior games."""
    def assign(champions, remaining):
        if not champions:
            return True
        champion, *rest = champions
        return any(
            key(player, champion) in stats.player_champion and assign(rest, remaining - {player})
            for player in remaining
        )

    picks = state.picks(side)
    available = frozenset(players)
    return {champion for champion in state.available if assign(picks + (champion,), available)}


def play(cache, patch):
    names = cache["names"]["characters"]
    teams = cache["names"]["teams"]
    by_name = {name: team for team, name in teams.items()}
    c9, opponent = by_name["Cloud9 Kia"], by_name["FlyQuest"]
    predictor = Predictor(cache["model"])
    lineups = predictor.stats.lineups
    matchup = SeriesDraft(c9, opponent, names, best_of=5, format_mode=HARD_FEARLESS)
    print(f"Cloud9 Kia vs FlyQuest | Hypothetical Hard Fearless Bo5 | Patch {patch}")
    print("Delta is the acting side's modeled change from the current board, in percentage points.")
    print("Candidate n counts historical picks by the selecting team or, for bans, by its opponent.")
    print("Demo shortlist: bans with 3+ opponent picks and picks with a viable historical player assignment.")

    for number in range(1, 4):
        state = matchup.current
        probability = predictor.predict(state, patch=patch, lineups=lineups)
        print(
            f"\nGame {number} | {teams[state.blue]} blue, {teams[state.red]} red | "
            f"{len(state.fearless_locks)} prior picks locked | {state.first_pick_side} first | Blue {probability:.1%}"
        )
        if number == 3:
            for advice in how_to_win(cache, predictor, state, opponent, patch=patch, lineups=lineups):
                if advice["kind"] != "model_option":
                    print(f"  How to Win | {advice['text']}")
        while state.turn:
            side, kind, phase = state.turn
            team = state.blue if side == BLUE else state.red
            candidates = lineup_candidates(state, side, lineups.get(team, ()), predictor.stats) if kind == "pick" else None
            limit = 3 if number == 3 else 1
            rows = predictor.recommend(state, patch=patch, lineups=lineups, candidates=candidates,
                                       min_sample=3 if kind == "ban" else 0, limit=limit)
            if not rows:
                print(f"  Step {len(state.actions) + 1} has no supported shortlist. Showing all legal options.")
                rows = predictor.recommend(state, patch=patch, lineups=lineups, limit=limit)
            step = len(state.actions)
            if number == 3 and step in (0, 6, 12, 16, 19):
                print(f"  Step {len(state.actions) + 1:2} {side} {kind} (phase {phase}) | {format_options(rows, names)}")
            if number == 3 and step == 6:
                for advice in how_to_win(cache, predictor, state, opponent, patch=patch, lineups=lineups,
                                         candidates=candidates):
                    if advice["kind"] == "model_option":
                        print(f"  How to Win | {advice['text']}")
            state = matchup.apply(side, kind, rows[0]["champion"])
        probability = predictor.predict(state, patch=patch, lineups=lineups)
        print(f"  Final draft | Blue {probability:.1%} / Red {1 - probability:.1%}")
        for side, team in ((BLUE, state.blue), (RED, state.red)):
            print(f"  {teams[team]}: {', '.join(names[hero] for hero in state.picks(side))}")
        if number < 3:
            winner = c9 if number == 1 else opponent
            print(f"  Scenario result: {teams[winner]} wins. Series {matchup.wins[c9] + (winner == c9)}"
                  f"-{matchup.wins[opponent] + (winner == opponent)}.")
            matchup.finish_game(winner, next_blue=state.red if number == 1 else c9,
                                next_first_pick=RED if number == 1 else BLUE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch", help="Patch context (defaults to the latest patch in Cloud9 Kia's profile)")
    args = parser.parse_args()
    _, output = runtime_paths()
    cache = load_cache(output)
    c9 = next(team for team, name in cache["names"]["teams"].items() if name == "Cloud9 Kia")
    c9_groups = cache["scouting"]["teams"][c9]
    patches = (value.removeprefix("patch:") for value in c9_groups if value.startswith("patch:") and "/" not in value)
    patch = args.patch or max(patches, key=lambda value: tuple(int(part) for part in value.split(".")))
    play(cache, patch)


if __name__ == "__main__":
    main()
