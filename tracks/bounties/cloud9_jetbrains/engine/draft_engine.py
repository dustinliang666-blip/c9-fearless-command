"""LoL draft rules, chronological validation and evidence-backed coaching."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from math import exp, log
from pathlib import Path
import argparse
import json
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tracks.bounties.cloud9_jetbrains.contracts import (
    Action, BLUE, CACHE_VERSION, DRAFT_ORDER, FORMAT_MODES, HARD_FEARLESS, RED, STANDARD,
    advance_locks, legal_actions, order_for, prior_locks, runtime_paths, series_groups, validate_action,
)


def other(side):
    if side not in (BLUE, RED):
        raise ValueError("Side must be blue or red")
    return RED if side == BLUE else BLUE


@dataclass(frozen=True)
class DraftState:
    blue: str
    red: str
    champions: frozenset[str]
    number: int = 1
    fearless_locks: frozenset[str] = frozenset()
    actions: tuple[Action, ...] = ()
    first_pick_side: str = BLUE
    format_mode: str = HARD_FEARLESS

    def __post_init__(self):
        if self.format_mode not in FORMAT_MODES:
            raise ValueError(f"Unsupported format mode: {self.format_mode}")
        if self.format_mode != HARD_FEARLESS and self.fearless_locks:
            raise ValueError("Prior champion locks require Hard Fearless")

    @property
    def turn(self):
        return order_for(self.first_pick_side)[len(self.actions)] if len(self.actions) < len(DRAFT_ORDER) else None

    @property
    def available(self):
        return self.champions - self.fearless_locks - {
            action.champion for action in self.actions
        }

    def apply(self, side, kind, champion):
        action = Action(side, kind, champion)
        validate_action(self.turn, action, self.champions - self.available, self.champions)
        return replace(self, actions=self.actions + (action,))

    def picks(self, side):
        return tuple(a.champion for a in self.actions if a.side == side and a.kind == "pick")


class SeriesDraft:
    def __init__(self, team1, team2, champions, *, best_of=5, format_mode=None, fearless=None,
                 first_pick_side=BLUE):
        if best_of not in (1, 3, 5):
            raise ValueError("Supported formats are Bo1, Bo3 and Bo5")
        if team1 == team2:
            raise ValueError("A series requires two different teams")
        other(first_pick_side)
        self.best_of = best_of
        if format_mode is not None and fearless is not None:
            raise ValueError("Specify format_mode or fearless")
        self.format_mode = format_mode if format_mode is not None else (
            STANDARD if fearless is False else HARD_FEARLESS
        )
        self.wins = {team1: 0, team2: 0}
        self.current = DraftState(team1, team2, frozenset(champions), first_pick_side=first_pick_side,
                                  format_mode=self.format_mode)
        self.history = []

    @property
    def winner(self):
        return next((team for team, wins in self.wins.items() if wins > self.best_of // 2), None)

    def apply(self, side, kind, champion):
        if self.winner:
            raise ValueError("Series is complete")
        self.current = self.current.apply(side, kind, champion)
        return self.current

    def finish_game(self, winner, *, next_blue=None, next_first_pick=BLUE):
        if self.winner or self.current.turn is not None:
            raise ValueError("A complete and unresolved draft is required")
        if winner not in self.wins or (next_blue is not None and next_blue not in self.wins):
            raise ValueError("Teams must belong to this series")
        other(next_first_pick)
        game = self.current
        self.wins[winner] += 1
        self.history.append((game, winner))
        if self.winner:
            return None
        locks = advance_locks(self.format_mode, game.fearless_locks, game.picks(BLUE), game.picks(RED))
        blue = game.blue if next_blue is None else next_blue
        red = next(team for team in self.wins if team != blue)
        self.current = DraftState(blue, red, game.champions, game.number + 1, locks,
                                  first_pick_side=next_first_pick, format_mode=self.format_mode)
        return self.current


def shrunk(cell, strength, prior=0.5):
    n, wins = cell
    return (wins + strength * prior) / (n + strength)


def key(*parts):
    return "|".join(parts)


def record(table, name, won):
    cell = table.setdefault(name, [0, 0])
    cell[0] += 1
    cell[1] += won


@dataclass
class History:
    team: dict = field(default_factory=dict)
    champion: dict = field(default_factory=dict)
    patch_champion: dict = field(default_factory=dict)
    player: dict = field(default_factory=dict)
    player_champion: dict = field(default_factory=dict)
    team_champion: dict = field(default_factory=dict)
    synergy: dict = field(default_factory=dict)
    counter: dict = field(default_factory=dict)
    games: int = 0
    blue_wins: int = 0
    ratings: dict = field(default_factory=dict)
    lineups: dict = field(default_factory=dict)

    def rating(self, team, at):
        value, last = self.ratings.get(team, (0.0, at.timestamp()))
        return value * 2 ** (-max(0, at.timestamp() - last) / (180 * 86400))

    def rating_difference(self, blue, red, at):
        return self.rating(blue, at) - self.rating(red, at)

    def add(self, game, *, available_at=None):
        at = available_at or game.end or game.start
        blue, red = (self.rating(team, at) for team in (game.blue, game.red))
        side_logit = log((self.blue_wins + 25) / (self.games - self.blue_wins + 25))
        change = 0.14 * (game.blue_won - sigmoid(side_logit + blue - red))
        self.ratings[game.blue] = (blue + change, at.timestamp())
        self.ratings[game.red] = (red - change, at.timestamp())
        self.games += 1
        self.blue_wins += game.blue_won
        picks = {}
        for side, team, won in ((BLUE, game.blue, game.blue_won), (RED, game.red, 1 - game.blue_won)):
            record(self.team, team, won)
            roster = game.roster.get(team, {})
            if len(roster) == 5:
                self.lineups[team] = sorted(roster)
            picks[side] = sorted(set(roster.values()))
            for player, champion in roster.items():
                record(self.player, player, won)
                record(self.player_champion, key(player, champion), won)
            for index, champion in enumerate(picks[side]):
                record(self.champion, champion, won)
                record(self.patch_champion, key(game.patch, champion), won)
                record(self.team_champion, key(team, champion), won)
                for ally in picks[side][index + 1:]:
                    record(self.synergy, key(champion, ally), won)
        for blue in picks[BLUE]:
            for red in picks[RED]:
                first, second = sorted((blue, red))
                if first != second:
                    record(self.counter, key(first, second), game.blue_won if first == blue else 1 - game.blue_won)


EMPTY = (0, 0)
FEATURES = (
    "champion_strength", "team_champion_form", "player_mastery", "player_familiarity",
    "synergy", "counter", "ban_pressure", "fearless_pick_demand",
)
STAGES = (6, 12, 16, 20)


def sigmoid(value):
    return 1 / (1 + exp(-max(-35, min(35, value))))


def champion_form(stats, champion, patch):
    overall = shrunk(stats.champion.get(champion, EMPTY), 16)
    return shrunk(stats.patch_champion.get(key(patch, champion), EMPTY), 12, overall)


def team_pick_rate(stats, team, champion):
    games = stats.team.get(team, EMPTY)[0]
    times = stats.team_champion.get(key(team, champion), EMPTY)[0]
    return times / games if games else 0.0


def player_features(stats, roster, champion, champion_wr):
    # An unresolved flex pick has no known assignment. Weight players by
    # their historical games on the champion plus one for each active player.
    total = mastery = familiarity = 0.0
    for player in roster:
        cell = stats.player_champion.get(key(player, champion), EMPTY)
        played = stats.player.get(player, EMPTY)[0]
        weight = 1 + cell[0]
        mastery += weight * (shrunk(cell, 10, champion_wr) - champion_wr)
        familiarity += weight * cell[0] / (played + 10)
        total += weight
    return (mastery / total, familiarity / total) if total else (0.0, 0.0)


def prefix_features(stats, blue, red, patch, lineups, actions, locks):
    """Return homogeneous features so a marginal comparison uses one scorer."""
    teams = {BLUE: blue, RED: red}
    picks = {BLUE: [], RED: []}
    form = {
        side: shrunk(stats.team.get(team, EMPTY), 12)
        for side, team in teams.items()
    }
    locked_demand = {
        side: sum(team_pick_rate(stats, team, champion) for champion in sorted(locks)) / 5
        for side, team in teams.items()
    }
    strength = team_champ = mastery = familiarity = synergy = counter = ban_pressure = depth = 0.0
    yield strength, team_champ, mastery, familiarity, synergy, counter, ban_pressure, depth
    for action in actions:
        side, kind, champion = action.side, action.kind, action.champion
        if champion is not None:
            opponent = other(side)
            team = teams[side]
            sign = 1 if side == BLUE else -1
            champ_form = champion_form(stats, champion, patch)
            if kind == "ban":
                demand = team_pick_rate(stats, teams[opponent], champion)
                ban_pressure += sign * demand * (0.5 + champ_form) / 5
            else:
                strength += sign * (champ_form - 0.5) / 5
                cell = stats.team_champion.get(key(team, champion), EMPTY)
                team_champ += sign * (shrunk(cell, 10, form[side]) - form[side]) / 5
                experience, frequent = player_features(stats, lineups.get(team, ()), champion, champ_form)
                mastery += sign * experience / 5
                familiarity += sign * frequent / 5
                depth += sign * locked_demand[side] * team_pick_rate(stats, team, champion) / 5
                for ally in picks[side]:
                    pair = key(*sorted((champion, ally)))
                    synergy += sign * (shrunk(stats.synergy.get(pair, EMPTY), 12) - 0.5) / 10
                for enemy in picks[opponent]:
                    first, second = sorted((champion, enemy))
                    matchup = shrunk(stats.counter.get(key(first, second), EMPTY), 16) - 0.5
                    counter += (sign if first == champion else -sign) * matchup / 25
                picks[side].append(champion)
        yield strength, team_champ, mastery, familiarity, synergy, counter, ban_pressure, depth


def series_windows(games):
    windows = []
    for group in series_groups(games):
        if all(game.end is not None and game.end > game.start for game in group):
            windows.append((min(g.draft_start for g in group), max(g.end for g in group), group))
    return sorted(windows, key=lambda window: (window[0], window[2][0].series))


def chronological_split(windows):
    if len(windows) < 2:
        raise ValueError("Validation requires at least two timestamped series")
    cutoff = windows[int(len(windows) * 0.8)][0]
    train = [window for window in windows if window[1] < cutoff]
    test = [window for window in windows if window[0] >= cutoff]
    if not train or not test:
        raise ValueError("Validation requires observations on both sides of the cutoff")
    return train, test, cutoff


def draft_examples(group, stats):
    for game in group:
        if game.complete_draft:
            locks = prior_locks(group, game)
            rows: list[tuple[float, ...] | None] = [None] * (len(DRAFT_ORDER) + 1)
            if locks is not None:
                try:
                    actions = legal_actions(game.actions, first_pick_side=game.first_pick_side, locks=locks)
                    features = prefix_features(stats, game.blue, game.red, game.patch, stats.lineups,
                                               actions, locks)
                    for index, features_at_step in enumerate(features):
                        rows[index] = features_at_step
                except ValueError:
                    # The invalid action and all later turns have no usable BP
                    # estimate. Earlier legal prefixes retain their score.
                    pass
            yield game, (stats.rating_difference(game.blue, game.red, game.draft_start), rows)


def rolling_examples(windows):
    """Build historical features using only series finished before each draft."""
    completed = sorted(windows, key=lambda window: window[1])
    stats = History()
    next_result = 0
    for start, _, group in windows:
        while next_result < len(completed) and completed[next_result][1] < start:
            _, end, past = completed[next_result]
            for game in past:
                stats.add(game, available_at=end)
            next_result += 1
        yield from draft_examples(group, stats)


def results_history(windows):
    stats = History()
    for _, end, group in sorted(windows, key=lambda window: (window[1], window[2][0].series)):
        for game in group:
            stats.add(game, available_at=end)
    return stats


def pre_logit(model, rating_difference):
    return model["pre"]["intercept"] + model["pre"]["slope"] * rating_difference


def probability(model, rating_difference, features, step):
    base = pre_logit(model, rating_difference)
    if not step or features is None:
        return sigmoid(base)
    stage = next(stage for stage in STAGES if step <= stage)
    delta = sum(weight * value for weight, value in zip(model["weights"], features))
    return sigmoid(base + model["gamma"][str(stage)] * delta)


def train_and_validate(games, *, fit_serving=True):
    from tracks.bounties.cloud9_jetbrains.engine.calibration import train_and_validate as train

    return train(games, fit_serving=fit_serving)


def load_cache(path):
    with path.open(encoding="utf-8") as stream:
        cache = json.load(stream)
    if cache["version"] != CACHE_VERSION:
        raise ValueError("Aggregate cache version mismatch. Rebuild with the ETL.")
    return cache


def historical_board(group, game, champions, *, as_of, step):
    """Replay final retained draft actions up to step (retracted mid-draft actions are excluded)."""
    if as_of.tzinfo is None or not game.draft_start <= as_of <= game.start:
        raise ValueError("as_of must be a timezone-aware timestamp between draft start and game start")
    if not 0 <= step <= len(DRAFT_ORDER):
        raise ValueError("step must be between 0 and 20")
    locks = prior_locks(group, game)
    if locks is None:
        raise ValueError("Prior Hard Fearless drafts could not be verified before this draft")
    if step and (len(game.action_times) < step or max(game.action_times[:step]) > as_of):
        raise ValueError("The requested draft prefix was not verified at as_of")
    state = DraftState(game.blue, game.red, frozenset(champions), game.number, locks,
                       first_pick_side=game.first_pick_side, format_mode=game.format_mode)
    for action in game.actions[:step]:
        state = state.apply(action.side, action.kind, action.champion)
    return state


class Predictor:
    def __init__(self, aggregate_model):
        self.model = aggregate_model["serving"]
        self.stats = History(**aggregate_model["history"])
        self.as_of = datetime.fromisoformat(aggregate_model["as_of"])
        self.historical = aggregate_model.get("historical", False)

    def curve(self, state, *, patch="", lineups=None, as_of=None):
        if self.historical and as_of != self.as_of:
            raise ValueError("Historical prediction requires the fitted as_of timestamp")
        if not self.historical and as_of is not None:
            raise ValueError("Serving models cannot score historical as_of requests")
        rating = self.stats.rating_difference(state.blue, state.red, self.as_of)
        rows = prefix_features(self.stats, state.blue, state.red, patch, lineups or self.stats.lineups,
                               state.actions, state.fearless_locks)
        return [probability(self.model, rating, row, step) for step, row in enumerate(rows)]

    def predict(self, state, *, patch="", lineups=None, as_of=None):
        return self.curve(state, patch=patch, lineups=lineups, as_of=as_of)[-1]

    def recommend(self, state, *, patch="", lineups=None, as_of=None, candidates=None, min_sample=0, limit=10):
        if state.turn is None:
            return []
        if self.historical and as_of != self.as_of:
            raise ValueError("Historical prediction requires the fitted as_of timestamp")
        if not self.historical and as_of is not None:
            raise ValueError("Serving models cannot score historical as_of requests")
        side, kind, _ = state.turn
        rating = self.stats.rating_difference(state.blue, state.red, self.as_of)
        effective_lineups = lineups or self.stats.lineups
        current_row = list(prefix_features(
            self.stats, state.blue, state.red, patch, effective_lineups,
            state.actions, state.fearless_locks,
        ))[-1]
        # Compare candidates against the current board under the SAME target stage gamma
        # so stage transitions do not inject artificial delta_pp shifts on zero-delta picks.
        next_step = len(state.actions) + 1
        same_stage_base = probability(self.model, rating, current_row, next_step)
        team = state.blue if side == BLUE else state.red
        target = (state.red if side == BLUE else state.blue) if kind == "ban" else team
        result = []
        available = state.available if candidates is None else state.available.intersection(candidates)
        for champion in available:
            sample = self.stats.team_champion.get(key(target, champion), EMPTY)[0]
            if sample < min_sample:
                continue
            updated = self.predict(state.apply(side, kind, champion), patch=patch, lineups=lineups, as_of=as_of)
            result.append({
                "champion": champion, "delta_pp": (updated - same_stage_base) * (100 if side == BLUE else -100),
                "blue_probability": updated, "n": sample, "team": target,
            })
        return sorted(result, key=lambda row: (-row["delta_pp"], -row["n"], row["champion"]))[:limit]


def scouting_profile(cache, team, *, patch="", side=None):
    groups = cache["scouting"]["teams"].get(team, {})
    scope = "/".join(part for part in (f"patch:{patch}" if patch else "", f"side:{side}" if side else "") if part)
    return groups.get(scope or "all", {})


def evidence(numerator, denominator, unit, scope, *, distinct_games=None):
    return {
        "numerator": numerator, "denominator": denominator, "unit": unit, "scope": scope,
        "distinct_games": denominator if distinct_games is None else distinct_games,
    }


def how_to_win(cache, predictor, state, opponent, *, patch="", lineups=None, candidates=None):
    """Build deterministic advice with denominators and a declared evidence scope."""
    if opponent not in (state.blue, state.red):
        raise ValueError("Opponent must belong to the current draft")
    names = cache["names"]["characters"]
    opponent_name = cache["names"]["teams"].get(opponent, opponent)
    side = BLUE if state.blue == opponent else RED
    profile = scouting_profile(cache, opponent, patch=patch, side=side)
    scope = f"patch {patch}, {side} side" if patch else f"{side} side, all patches"
    if profile.get("n", 0) < 5:
        profile = scouting_profile(cache, opponent, side=side)
        scope = f"{side} side, all patches"
    if profile.get("n", 0) < 5:
        profile = scouting_profile(cache, opponent)
        scope = "both sides, all patches"
    advice = []
    tendency = profile.get("draft", {}).get("first_pick", {})
    n = profile.get("draft_n", {}).get("first_pick", 0)
    if n and tendency:
        hero, (count, _) = min(tendency.items(), key=lambda row: (-row[1][0], names.get(row[0], row[0])))
        name = names.get(hero, hero)
        preparation = f"Prepare an answer to {name}." if hero in state.available else (
            f"Review alternatives to {name}, which is unavailable on this board."
        )
        advice.append({
            "kind": "draft_tendency", "evidence": evidence(count, n, "drafts", scope),
            "instruction": preparation,
            "text": f"{preparation} "
            f"{opponent_name} opened with it in {count}/{n} drafts ({scope}; n={n}).",
        })
    cohort = cache["scouting"]["fearless"].get(opponent, {}).get(str(state.number), {})
    matrix = cohort.get("transitions", {}).get("prior_pick", {})
    available = state.available
    supported = [
        (hero, matrix[hero]) for hero in state.fearless_locks
        if hero in matrix and available.intersection(matrix[hero]["next"])
    ]
    if state.format_mode == HARD_FEARLESS and supported:
        blocked, data = min(supported, key=lambda row: (-row[1]["n"], names.get(row[0], row[0])))
        options = ((hero, count) for hero, count in data["next"].items() if hero in available)
        hero, count = min(options, key=lambda row: (-row[1], names.get(row[0], row[0])))
        n = data["n"]
        scope_text = f"Game {state.number}, verified Hard Fearless, all patches"
        preparation = f"Prepare for {names.get(hero, hero)} when {names.get(blocked, blocked)} is locked."
        advice.append({
            "kind": "fearless_replacement",
            "evidence": evidence(count, n, "pick_turns", scope_text, distinct_games=data["distinct_games"]),
            "instruction": preparation,
            "text": f"{preparation} "
            f"{opponent_name} took it on {count}/{n} eligible pick turns across {data['distinct_games']} games.",
        })
    results = profile.get("macro", {}).get("first", {}).get("dragon", {})
    secured, wins = results.get("secured", EMPTY)
    conceded, conceded_wins = results.get("conceded", EMPTY)
    n = sum(cell[0] for cell in results.values())
    if n:
        comparison = (
            f" They won {wins}/{secured} when securing it and {conceded_wins}/{conceded} when conceding it."
            if secured and conceded else ""
        )
        advice.append({
            "kind": "macro",
            "instruction": "Review bot and mid priority before first dragon.",
            "evidence": evidence(secured, n, "games", f"{scope}, first dragon by 15:00"),
            "comparison": [
                evidence(wins, secured, "games", f"{scope}, wins after securing first dragon"),
                evidence(conceded_wins, conceded, "games", f"{scope}, wins after conceding first dragon"),
            ],
            "text": f"Review bot and mid priority before first dragon. {opponent_name} secured first dragon "
            f"by 15:00 in {secured}/{n} observed games ({scope}; n={n}).{comparison}",
        })
    if state.turn and state.turn[0] != side:
        kind = state.turn[1]
        supported = predictor.recommend(
            state, patch=patch, lineups=lineups, candidates=candidates, min_sample=1, limit=1,
        )
        if supported:
            candidate = supported[0]
            hero, n = candidate["champion"], candidate["n"]
            evidence_team = cache["names"]["teams"].get(candidate["team"], candidate["team"])
            total = predictor.stats.team[candidate["team"]][0]
            if candidate["delta_pp"] > 0:
                preparation = f"Consider {names.get(hero, hero)} for this {kind} (model {candidate['delta_pp']:+.2f} pp)."
                advice.append({
                    "kind": "model_option",
                    "instruction": preparation,
                    "evidence": evidence(n, total, "games", f"{evidence_team} picks, both sides, all patches"),
                    "text": f"{preparation} "
                    f"{evidence_team} picked it in {n}/{total} historical games (n={n} picks).",
                })
    return advice


def print_validation(report):
    print(
        f"Chronological cutoff {report['cutoff']}; last training result {report['last_train_end']}\n"
        f"Train {report['train_series']} series / {report['train_games']} drafts; "
        f"test {report['test_series']} series / {report['test_games']} drafts; "
        f"purged overlapping series {report['purged_series']}; untimed games {report['untimed_games']}.\n"
        f"Training OOF {report['oof_games']} drafts ({report['oof_legal_drafts']} with BP); "
        f"holdout pre-only fallbacks {report['pre_only_fallback_games']}; gamma {report['gamma']}."
    )
    print(f"{'Model':25} {'AUC [95% CI]':>25} {'LogLoss [95% CI]':>25} {'Brier [95% CI]':>25}")
    baselines = (
        ("50% baseline", report["coin_flip"]),
        (f"Blue prior {report['blue_prior']:.1%}", report["side_baseline"]),
    )
    for name, row in (*baselines, *(("Pre-draft Elo" if n == "0" else f"Draft after {n} steps", s)
                                    for n, s in report["draft"].items())):
        cells = []
        for metric in ("auc", "log_loss", "brier"):
            value, ci = row[metric]["value"], row[metric]["ci95"]
            cells.append(f"{value:.4f} [{ci[0]:.4f}, {ci[1]:.4f}]" if ci else "N/A")
        print(f"{name:25}" + "".join(f"{cell:>25}" for cell in cells))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--revalidate", action="store_true", help="Rescan GRID and refit the chronological holdout")
    mode.add_argument("--as-of", type=datetime.fromisoformat, help="Replay at a timezone-aware draft timestamp")
    parser.add_argument("--series", help="Series ID for historical replay")
    parser.add_argument("--game", type=int, default=1)
    parser.add_argument("--step", type=int, default=0, help="Number of observed actions to replay")
    args = parser.parse_args()
    data, output = runtime_paths()
    if args.as_of is not None:
        from tracks.bounties.cloud9_jetbrains.engine.calibration import fit_historical
        from tracks.bounties.cloud9_jetbrains.etl.build_lol_aggregates import scan_corpus

        if not args.series or args.as_of.tzinfo is None:
            parser.error("--as-of requires --series and a timezone-aware timestamp")
        games, names, _ = scan_corpus(data, progress=True)
        group = [game for game in games if game.series == args.series]
        group.sort(key=lambda game: game.number)
        game = next((game for game in group if game.number == args.game), None)
        if game is None:
            parser.error("No matching game found")
        try:
            state = historical_board(group, game, names["characters"], as_of=args.as_of, step=args.step)
        except ValueError as error:
            parser.error(str(error))
        predictor = Predictor(fit_historical(games, args.as_of, before=game.draft_start, exclude=game.series))
        print(json.dumps({"format_mode": state.format_mode, "as_of": args.as_of.isoformat(),
                          "fearless_locks": sorted(state.fearless_locks),
                          "blue_probabilities": predictor.curve(state, patch=game.patch, as_of=args.as_of)}))
        return
    if args.revalidate:
        from tracks.bounties.cloud9_jetbrains.etl.build_lol_aggregates import scan_corpus

        games, _, _ = scan_corpus(data, progress=True)
        report = train_and_validate(games, fit_serving=False)["validation"]
    else:
        report = load_cache(output)["model"]["validation"]
    print_validation(report)


if __name__ == "__main__":
    main()
