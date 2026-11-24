"""Shared draft and runtime data contracts."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import os

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DEFAULT = Path.home() / ".fearless-command" / "licensed-input"
CACHE_DEFAULT = Path.home() / ".fearless-command" / "licensed-cache"
CACHE_VERSION = 3
BLUE, RED = "blue", "red"
STANDARD, HARD_FEARLESS, UNKNOWN = "standard", "hard_fearless", "unknown"
FORMAT_MODES = (STANDARD, HARD_FEARLESS, UNKNOWN)
DRAFT_ORDER = tuple(
    (side, kind, phase)
    for kind, phase, sides in (
        ("ban", 1, (BLUE, RED) * 3),
        ("pick", 1, (BLUE, RED, RED, BLUE, BLUE, RED)),
        ("ban", 2, (RED, BLUE) * 2),
        ("pick", 2, (RED, BLUE, BLUE, RED)),
    )
    for side in sides
)
RED_FIRST_ORDER = tuple((RED if side == BLUE else BLUE, kind, phase) for side, kind, phase in DRAFT_ORDER)
OBJECTIVES = ("dragon", "grubs", "herald", "first_blood")


def order_for(first_pick_side):
    if first_pick_side not in (BLUE, RED):
        raise ValueError("Side must be blue or red")
    return DRAFT_ORDER if first_pick_side == BLUE else RED_FIRST_ORDER


@dataclass(frozen=True)
class Action:
    side: str
    kind: str
    champion: str | None


@dataclass
class Game:
    series: str
    game_id: str
    session: int
    number: int
    patch: str
    start: datetime
    blue: str
    red: str
    blue_won: int
    end: datetime | None = None
    first_draft_at: datetime | None = None
    best_of: int | None = None
    roster: dict[str, dict[str, str]] = field(default_factory=dict)
    actions: tuple[Action, ...] = ()
    first_pick_side: str = BLUE
    early_observed: bool = False
    first: dict[str, str] = field(default_factory=dict)
    grubs: dict[str, int] = field(default_factory=dict)
    gold_diff: int | None = None
    format_mode: str = UNKNOWN
    competition: str = ""
    action_times: tuple[datetime, ...] = ()

    @property
    def draft_start(self):
        return min(self.first_draft_at, self.start) if self.first_draft_at else self.start

    @property
    def picks(self):
        return {
            side: tuple(self.roster.get(team, {}).values())
            for side, team in ((BLUE, self.blue), (RED, self.red))
        }

    @property
    def lineups(self):
        return {team: tuple(sorted(players)) for team, players in self.roster.items()}

    @property
    def complete_draft(self):
        picks = self.picks
        if any(len(set(picks[side])) != 5 for side in (BLUE, RED)):
            return False
        if len(self.actions) != len(DRAFT_ORDER):
            return False
        try:
            replay_actions(self.actions, first_pick_side=self.first_pick_side)
        except ValueError:
            return False
        return all(
            {a.champion for a in self.actions if a.side == side and a.kind == "pick"}
            == set(picks[side])
            for side in (BLUE, RED)
        )


def runtime_paths():
    data = Path(os.environ.get("STL_DATA_DIR", DATA_DEFAULT)).resolve()
    cache = Path(os.environ.get("C9_CACHE_DIR", CACHE_DEFAULT)).resolve()
    output = cache / "lol_aggregates.json"
    for path in (data, cache, output.resolve()):
        if path.is_relative_to(REPO_ROOT):
            raise ValueError(f"GRID input and cache must be outside the repository ({path})")
    if cache.is_relative_to(data) or output.resolve().is_relative_to(data):
        raise ValueError("The cache must be outside the read-only GRID source directory")
    return data, output


def series_groups(games):
    groups = defaultdict(list)
    for game in games:
        groups[game.series].append(game)
    return [sorted(group, key=lambda g: (g.number, g.start)) for group in groups.values()]


def validate_action(turn, action, unavailable, champions=None):
    if turn is None:
        raise ValueError("Draft is complete")
    if (action.side, action.kind) != turn[:2]:
        raise ValueError(f"Expected {turn[0]} {turn[1]}")
    if action.champion is None:
        if action.kind != "ban":
            raise ValueError("Only a ban may be passed")
    elif action.champion in unavailable or (champions is not None and action.champion not in champions):
        raise ValueError(f"Champion unavailable: {action.champion}")


def replay_actions(actions, *, first_pick_side=BLUE, locks=()):
    for _ in legal_actions(actions, first_pick_side=first_pick_side, locks=locks):
        pass


def legal_actions(actions, *, first_pick_side=BLUE, locks=()):
    order = order_for(first_pick_side)
    unavailable = set(locks)
    for index, action in enumerate(actions):
        validate_action(order[index] if index < len(order) else None, action, unavailable)
        if action.champion is not None:
            unavailable.add(action.champion)
        yield action


def advance_locks(mode, locks, blue_picks, red_picks):
    if mode not in FORMAT_MODES:
        raise ValueError(f"Unsupported format mode: {mode}")
    return frozenset(locks).union(blue_picks, red_picks) if mode == HARD_FEARLESS else frozenset()


def prior_locks(group, current):
    """Use only completed drafts that precede the current draft, strictly."""
    if current.format_mode != HARD_FEARLESS:
        return frozenset()
    earlier = tuple(game for game in group if game.number < current.number)
    if len(earlier) != current.number - 1:
        return None
    locks = frozenset()
    for number, game in enumerate(earlier, 1):
        if (game.number != number or game.session != current.session or game.format_mode != HARD_FEARLESS
                or not game.end or game.end <= game.start or game.end >= current.draft_start
                or any(stamp >= current.draft_start for stamp in game.action_times)
                or not game.complete_draft):
            return None
        try:
            replay_actions(game.actions, first_pick_side=game.first_pick_side, locks=locks)
        except ValueError:
            return None
        locks = advance_locks(HARD_FEARLESS, locks, game.picks[BLUE], game.picks[RED])
    return locks


def fearless_contexts(group, *, retrospective=False):
    for game in group:
        if game.format_mode != HARD_FEARLESS:
            continue
        locks = prior_locks(group, game)
        if locks is None:
            continue
        if retrospective:
            if not game.complete_draft:
                continue
            try:
                replay_actions(game.actions, first_pick_side=game.first_pick_side, locks=locks)
            except ValueError:
                continue
        yield game, locks
