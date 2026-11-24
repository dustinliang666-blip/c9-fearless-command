"""Offline tests using synthetic teams, champions, games and feed fragments."""

from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from tracks.bounties.cloud9_jetbrains.contracts import (
    Action, BLUE, DRAFT_ORDER, Game, HARD_FEARLESS, RED, STANDARD, UNKNOWN, fearless_contexts,
    prior_locks,
)
from tracks.bounties.cloud9_jetbrains.engine.calibration import fit_historical, gamma_for_stage, series_bootstrap
from tracks.bounties.cloud9_jetbrains.engine.draft_engine import (
    FEATURES, STAGES, DraftState, History, Predictor, SeriesDraft, chronological_split, draft_examples,
    historical_board, how_to_win, probability, rolling_examples, series_windows, train_and_validate,
)
from tracks.bounties.cloud9_jetbrains.etl.build_lol_aggregates import (
    aggregate, align_draft, consume_feed, format_mode,
)


CHAMPIONS = frozenset(f"c{i:02d}" for i in range(80))
NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)
ORDER = (
    "bB rB bB rB bB rB bP rP rP bP bP rP rB bB rB bB rP bP bP rP"
).split()


def synthetic_game(series, start_day, won, *, duration_hours=1, number=1, offset=0):
    start = NOW + timedelta(days=start_day, hours=2 * (number - 1))
    game = Game(
        str(series), f"{series}-{number}", 1, number, "15.1", start, "a", "b",
        won, end=start + timedelta(hours=duration_hours), best_of=5, format_mode=HARD_FEARLESS,
    )
    game.actions = tuple(
        Action(side, kind, f"c{offset + index:02d}")
        for index, (side, kind, _) in enumerate(DRAFT_ORDER)
    )
    game.roster = {
        team: {
            f"{team}{i}": action.champion
            for i, action in enumerate(game.actions) if action.kind == "pick" and action.side == side
        }
        for team, side in (("a", BLUE), ("b", RED))
    }
    return game


def complete(series):
    while series.current.turn:
        state = series.current
        side, action, _ = state.turn
        series.apply(side, action, min(state.available))


def model_for(stats, first_weight=0):
    return {
        "as_of": NOW.isoformat(),
        "serving": {"pre": {"intercept": 0.0, "slope": 1.0},
                    "weights": [first_weight] + [0] * (len(FEATURES) - 1),
                    "gamma": {str(stage): 1 for stage in STAGES}},
        "history": vars(stats),
    }


class DraftTests(TestCase):
    def test_twenty_step_order_and_validation(self):
        series = SeriesDraft("a", "b", CHAMPIONS)
        with self.assertRaisesRegex(ValueError, "complete"):
            series.finish_game("a")
        with self.assertRaisesRegex(ValueError, "Expected blue ban"):
            series.apply(RED, "ban", "c00")
        with self.assertRaisesRegex(ValueError, "unavailable"):
            series.apply(BLUE, "ban", "unknown")
        for index, expected in enumerate(ORDER):
            side = BLUE if expected[0] == "b" else RED
            action = "ban" if expected[1] == "B" else "pick"
            self.assertEqual(series.current.turn, (side, action, 1 if index < 12 else 2))
            if index == 6:
                with self.assertRaisesRegex(ValueError, "Only a ban"):
                    series.apply(side, action, None)
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    series.apply(side, action, "c01")
            series.apply(side, action, f"c{index:02d}" if index else None)
        self.assertIsNone(series.current.turn)
        self.assertEqual(len(series.current.picks(BLUE)), 5)
        self.assertEqual(len(series.current.picks(RED)), 5)
        with self.assertRaisesRegex(ValueError, "complete"):
            series.apply(BLUE, "ban", "c45")

    def test_hard_fearless_locks_carry_to_game_five_across_side_swaps(self):
        series = SeriesDraft("a", "b", CHAMPIONS)
        locks = set()
        for index, winner in enumerate(("a", "b", "a", "b", "a"), 1):
            self.assertEqual(series.current.number, index)
            self.assertEqual(series.current.fearless_locks, locks)
            if locks:
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    series.apply(BLUE, "ban", min(locks))
            complete(series)
            finished = series.current
            locks.update(finished.picks(BLUE) + finished.picks(RED))
            passed_ban = next(a.champion for a in finished.actions if a.kind == "ban")
            following = series.finish_game(winner, next_blue=finished.red)
            if index < 5:
                self.assertEqual(following.blue, finished.red)
                self.assertIn(passed_ban, following.available)
            else:
                self.assertIsNone(following)
        self.assertEqual(series.winner, "a")
        with self.assertRaisesRegex(ValueError, "complete"):
            series.apply(BLUE, "ban", "c79")

    def test_standard_bo3_resets_champions_and_stops_at_two_wins(self):
        series = SeriesDraft("a", "b", CHAMPIONS, best_of=3, format_mode=STANDARD)
        complete(series)
        champion = series.current.picks(BLUE)[0]
        self.assertIn(champion, series.finish_game("a").available)
        complete(series)
        self.assertIsNone(series.finish_game("a"))

    def test_unknown_does_not_infer_fearless_from_unique_picks_or_length(self):
        self.assertEqual(format_mode("unlisted", "Playoffs", 5), UNKNOWN)
        self.assertEqual(format_mode("unlisted", "", 3, "standard"), STANDARD)
        self.assertEqual(format_mode("LEC - Winter 2025", "Regular Season", 1), STANDARD)
        self.assertEqual(format_mode("LEC - Winter 2025", "Playoffs", 5), HARD_FEARLESS)
        first = replace(synthetic_game("s", 0, 1), format_mode=UNKNOWN)
        second = replace(synthetic_game("s", 0, 0, number=2, offset=20), format_mode=UNKNOWN)
        self.assertFalse(list(fearless_contexts([first, second], retrospective=True)))
        series = SeriesDraft("a", "b", CHAMPIONS, format_mode=UNKNOWN)
        complete(series)
        champion = series.current.picks(BLUE)[0]
        following = series.finish_game("a")
        self.assertIn(champion, following.available)
        self.assertEqual(following.format_mode, UNKNOWN)

    def test_red_can_draft_first_without_switching_map_sides(self):
        series = SeriesDraft("a", "b", CHAMPIONS, first_pick_side=RED)
        self.assertEqual(series.current.blue, "a")
        self.assertEqual(series.current.turn, (RED, "ban", 1))
        complete(series)
        state = series.current
        self.assertEqual(state.actions[6].side, RED)
        self.assertEqual(state.actions[12].side, BLUE)
        self.assertEqual(state.actions[-1].side, BLUE)
        game = synthetic_game("s", 0, 1)
        game.actions = tuple(replace(action, side=RED if action.side == BLUE else BLUE)
                             for action in game.actions)
        game.roster["a"], game.roster["b"] = game.roster["b"], game.roster["a"]
        game.first_pick_side = RED
        self.assertTrue(game.complete_draft)

    def test_delta_uses_acting_side_and_is_bounded_and_monotone_in_strength(self):
        stats = History()
        stats.champion.update({"c10": [100, 100], "c20": [100, 0]})
        predictor = Predictor(model_for(stats, first_weight=1000))
        state = DraftState("a", "b", CHAMPIONS, fearless_locks=frozenset({"c78"}))
        for _ in range(6):
            side, kind, _ = state.turn
            state = state.apply(side, kind, None)
        before = predictor.predict(state)
        self.assertEqual(before, 0.5)
        ranks = predictor.recommend(state, limit=len(CHAMPIONS))
        self.assertEqual((ranks[0]["champion"], ranks[-1]["champion"]), ("c10", "c20"))
        self.assertNotIn("c78", {row["champion"] for row in ranks})
        for row in ranks:
            self.assertTrue(0 < row["blue_probability"] < 1)
            self.assertAlmostEqual(row["delta_pp"], 100 * (row["blue_probability"] - before))
        state = state.apply(BLUE, "pick", "c30")
        red_best = predictor.recommend(state, limit=1)[0]
        self.assertEqual(red_best["champion"], "c10")
        self.assertGreater(red_best["delta_pp"], 0)
        self.assertLess(red_best["blue_probability"], predictor.predict(state))

    def test_stage_calibration_is_monotone_and_suppresses_unsupported_delta(self):
        labels = np.array([0, 1] * 32)
        base = np.zeros(len(labels))
        useful = labels * 2 - 1.0
        self.assertEqual(gamma_for_stage(labels, base, -useful), 0)
        gamma = gamma_for_stage(labels, base, useful)
        self.assertGreater(gamma, 0)
        self.assertLessEqual(gamma, 1)
        model = model_for(History(), 2)["serving"]
        model["gamma"]["6"] = 0
        model["gamma"]["12"] = gamma
        self.assertEqual(probability(model, 0, [5], 6), 0.5)
        probabilities = [probability(model, 0, [value], 12) for value in (-1, 0, 1)]
        self.assertLess(probabilities[0], probabilities[1])
        self.assertLess(probabilities[1], probabilities[2])


class TimeSplitTests(TestCase):
    def test_series_boundary_is_purged_and_past_results_use_completion_time(self):
        games = [synthetic_game(i, i, i % 2) for i in range(10)]
        games[7].end += timedelta(days=2)
        train, test, cutoff = chronological_split(series_windows(games))
        self.assertEqual((len(train), len(test)), (7, 2))
        self.assertTrue(all(end < cutoff for _, end, _ in train))
        self.assertTrue(all(start >= cutoff for start, _, _ in test))
        self.assertFalse({g.series for _, _, group in train for g in group}
                         & {g.series for _, _, group in test for g in group})
        features = {game.series: rows for game, rows in rolling_examples(series_windows(games))}
        modified = [replace(game, blue_won=1 - game.blue_won) if game.series == "7" else game for game in games]
        new = {game.series: rows for game, rows in rolling_examples(series_windows(modified))}
        self.assertEqual(new["8"], features["8"])
        self.assertEqual(new["9"], features["9"])

    def test_draft_start_is_preferred_to_game_start(self):
        game = synthetic_game("s", 0, 1)
        game.first_draft_at = game.start - timedelta(minutes=5)
        self.assertEqual(series_windows([game])[0][0], game.first_draft_at)

    def test_held_out_results_do_not_change_prediction_or_cohort_priors(self):
        games = [synthetic_game(i, i, i % 2) for i in range(10)]
        changed = [replace(game, blue_won=1 - game.blue_won) if int(game.series) >= 8 else game for game in games]
        predictions = []
        with patch(
            "tracks.bounties.cloud9_jetbrains.engine.calibration.series_bootstrap",
            side_effect=lambda labels, probs, series: predictions.append((list(labels), list(probs))) or {},
        ):
            train_and_validate(games, fit_serving=False)
            train_and_validate(changed, fit_serving=False)
        halfway = len(predictions) // 2
        self.assertNotEqual(predictions[0][0], predictions[halfway][0])
        self.assertEqual([p for _, p in predictions[:halfway]], [p for _, p in predictions[halfway:]])

    def test_same_series_features_exclude_earlier_game_results(self):
        first = synthetic_game("s", 0, 1)
        second = synthetic_game("s", 0, 0, number=2, offset=20)
        original = list(draft_examples([first, second], History()))
        first.blue_won = 0
        repeated = list(rolling_examples(series_windows([first, second])))
        self.assertEqual(original[1][1], repeated[1][1])

    def test_current_future_picks_do_not_change_earlier_prefix_features(self):
        first = synthetic_game("s", 0, 1)
        second = synthetic_game("s", 0, 0, number=2, offset=20)
        stats = History()
        stats.add(first)
        initial = dict((g.number, rows) for g, (_, rows) in draft_examples([first, second], stats))[2]
        champion = first.picks[RED][-1]
        second.actions = second.actions[:-1] + (replace(second.actions[-1], champion=champion),)
        last_player = next(reversed(second.roster["b"]))
        second.roster["b"][last_player] = champion
        changed = dict((g.number, rows) for g, (_, rows) in draft_examples([first, second], stats))[2]
        self.assertEqual(initial[:-1], changed[:-1])
        self.assertIsNotNone(initial[-1])
        self.assertIsNone(changed[-1])

    def test_overlap_or_equal_timestamp_never_reveals_prior_locks(self):
        first = synthetic_game("s", 0, 1)
        second = synthetic_game("s", 0, 0, number=2, offset=20)
        self.assertEqual(len(prior_locks([first, second], second)), 10)
        for overlap in (timedelta(0), timedelta(milliseconds=1)):
            first.end = second.draft_start + overlap
            self.assertIsNone(prior_locks([first, second], second))
            rated = list(draft_examples([first, second], History()))
            self.assertTrue(all(value is None for value in rated[1][1][1]))
            with self.assertRaisesRegex(ValueError, "Prior Hard Fearless"):
                historical_board([first, second], second, CHAMPIONS, as_of=second.start, step=0)

    def test_historical_replay_rejects_future_turns_and_serving_model(self):
        games = [synthetic_game(i, i, i % 2) for i in range(12)]
        target = games[8]
        target.first_draft_at = target.start - timedelta(minutes=5)
        target.action_times = tuple(target.first_draft_at + timedelta(seconds=i) for i in range(20))
        as_of = target.action_times[3]
        with self.assertRaisesRegex(ValueError, "not verified"):
            historical_board([target], target, CHAMPIONS, as_of=as_of, step=5)
        state = historical_board([target], target, CHAMPIONS, as_of=as_of, step=4)
        with self.assertRaisesRegex(ValueError, "Serving models"):
            Predictor(model_for(History())).curve(state, as_of=as_of)
        fitted = fit_historical(games, as_of)
        self.assertEqual(fitted["history"]["games"], 8)
        changed = [replace(game, blue_won=1 - game.blue_won) if int(game.series) >= 8 else game for game in games]
        self.assertEqual(fitted, fit_historical(changed, as_of))
        self.assertEqual(len(Predictor(fitted).curve(state, as_of=as_of)), 5)

    def test_bootstrap_resamples_whole_series(self):
        # Each series contains one win and one loss. Any whole-series sample
        # preserves AUC, log loss and Brier for this constant prediction.
        report = series_bootstrap([1, 0, 1, 0], [0.6] * 4, ["a", "a", "b", "b"], replicates=100)
        self.assertEqual(report["auc"], {"value": 0.5, "ci95": [0.5, 0.5]})
        self.assertAlmostEqual(report["brier"]["ci95"][0], report["brier"]["ci95"][1])


class AggregateTests(TestCase):
    def test_feed_session_filter_and_gold_closest_before_15(self):
        game = synthetic_game("a", 0, 1)

        def event(kind, second, team="a", gold=(22000, 20000)):
            return {
                "type": kind, "actor": {"state": {"teamId": team}}, "target": {"id": game.game_id},
                "seriesState": {"games": [{
                    "id": game.game_id, "clock": {"currentSeconds": second},
                    "teams": [{"id": t, "totalMoneyEarned": v} for t, v in zip(("a", "b"), gold)],
                }]},
            }

        envelopes = [{
            "occurredAt": (NOW + timedelta(seconds=i)).isoformat(),
            "events": [entry],
        } for i, entry in enumerate((
            {"type": "grid-started-feed", "seriesState": {"format": "best-of-5"}},
            event("player-completed-slayDragon", 450, "a"),
            event("player-completed-slayOceanDrake", 450, "a"),
            event("player-killed-player", 500, "b"),
            event("player-completed-slayVoidGrub", 540, "a"),
            event("player-completed-slayVoidGrub", 548, "a"),
            event("player-!completed-slayVoidGrub", 550, "a"),
            event("player-completed-increaseLevel", 899),
            event("player-completed-slayRiftHerald", 905, "b", (30000, 20000)),
            event("series-ended-game", 1700),
            {"type": "grid-started-feed"},
            event("player-completed-slayDragon", 360, "b"),
        ))]
        seen = Counter()
        consume_feed(envelopes, {(1, game.game_id): game}, seen)
        self.assertTrue(game.early_observed)
        self.assertEqual(game.gold_diff, 2000)
        self.assertEqual(game.first, {"dragon": "a", "first_blood": "b", "grubs": "a"})
        self.assertEqual(game.grubs, {"a": 1})
        self.assertEqual(seen["player-completed-slayDragon"], 1)
        self.assertEqual(game.best_of, 5)

    def test_transition_denominator_and_repeated_pick_break(self):
        first = synthetic_game("s", 0, 1)
        second = synthetic_game("s", 0, 0, number=2, offset=20)
        repeated = synthetic_game("s", 0, 1, number=3)
        group = [first, second, repeated]
        self.assertEqual([g.number for g, _ in fearless_contexts(group, retrospective=True)], [1, 2])
        self.assertEqual(len(list(fearless_contexts(group))[-1][1]), 20)
        cohorts = aggregate([first, second, repeated])["fearless"]["a"]
        blocked = first.picks[RED][0]
        replacement = cohorts["2"]["transitions"]["prior_pick"][blocked]
        self.assertEqual(replacement["n"], 5)
        self.assertEqual(replacement["distinct_games"], 1)
        self.assertEqual(sum(replacement["next"].values()), 5)
        self.assertNotIn("3", cohorts)

    def test_late_undo_matches_event_before_macro_clock_filter_and_stale_snapshot(self):
        first = synthetic_game("s", 0, 1)
        second = synthetic_game("s", 0, 0, number=2, offset=20)
        first.end = second.start

        def event(kind, clock, team, actor):
            return {"type": kind, "actor": {"id": actor, "state": {"teamId": team}},
                    "seriesStateDelta": {"games": [{"id": second.game_id}]},
                    "seriesState": {"games": [
                        {"id": first.game_id, "finished": True, "clock": {"currentSeconds": 899}},
                        {"id": second.game_id, "clock": {"currentSeconds": clock}},
                    ]}}

        envelopes = [{"occurredAt": second.start.isoformat(), "events": [
            event("player-completed-slayDragon", 895, "a", "early-player"),
            event("player-completed-slayDragon", 898, "b", "other-team-player"),
            event("player-completed-slayDragon", 901, "a", "late-player"),
            event("player-!completed-slayDragon", 902, "a", "early-player"),
        ]}]
        seen = Counter()
        consume_feed(envelopes, {(1, first.game_id): first, (1, second.game_id): second}, seen)
        self.assertEqual(seen["player-completed-slayDragon"], 3)
        self.assertEqual(first.first, {})
        self.assertEqual(second.first, {"dragon": "b"})

    def test_first_session_can_begin_after_feed_marker(self):
        game = synthetic_game("s", 0, 1)
        observed = game.start + timedelta(minutes=30)
        game.end = None
        consume_feed([{
            "occurredAt": observed.isoformat(),
            "events": [{
                "type": "series-ended-game",
                "target": {"id": game.game_id},
                "seriesState": {"games": [{"id": game.game_id}]},
            }],
        }], {(1, game.game_id): game}, Counter())
        self.assertEqual(game.end, observed)

    def test_unique_missing_ban_can_be_aligned(self):
        game = synthetic_game("s", 0, 1)
        self.assertIsNone(align_draft(game.actions[2:]))
        game.actions = align_draft(game.actions[1:])
        self.assertEqual(game.actions[0], Action(BLUE, "ban", None))
        self.assertTrue(game.complete_draft)

    def test_coaching_advice_has_sample_counts(self):
        game = synthetic_game("s", 0, 1)
        game.early_observed = True
        game.first["dragon"] = "b"
        scouting = aggregate([game])
        stats = History()
        stats.add(game)
        predictor = Predictor(model_for(stats))
        cache = {"names": {"teams": {"b": "Opponent"}, "characters": {}}, "scouting": scouting}
        advice = how_to_win(cache, predictor, DraftState("a", "b", CHAMPIONS), "b")
        self.assertEqual({row["kind"] for row in advice}, {"draft_tendency", "macro"})
        for row in advice:
            self.assertEqual(row["evidence"]["denominator"], 1)
            self.assertEqual(row["evidence"]["distinct_games"], 1)
            self.assertIn("n=1", row["text"])
