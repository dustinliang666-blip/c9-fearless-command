"""Original practice fixtures. No GRID input, cache, or training dependencies."""

from datetime import datetime, timedelta, timezone
from random import Random

from ..contracts import Action, BLUE, CACHE_VERSION, DRAFT_ORDER, Game, HARD_FEARLESS, RED
from ..engine.draft_engine import History, key
from ..etl.build_lol_aggregates import aggregate


def demo_cache():
    teams = {"north": "Northstar", "shift": "Redshift", "tide": "Tidemark", "ember": "Emberline"}
    characters = {
        f"{family.lower()}-{role.lower()}": f"{family} {role}"
        for family in ("Ash", "Cinder", "Dusk", "Frost", "Gale", "Iron", "Lunar", "Moss", "Rift", "Solar")
        for role in ("Blade", "Seer", "Warden", "Sage", "Hunter", "Knight", "Drake", "Rider", "Oracle")
    }
    hero_pool = list(characters)
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    random = Random(90)
    history = History()
    games = []
    for index in range(32):
        first = list(teams)[index % 4]
        second = list(teams)[(index + 1 + index // 4 % 3) % 4]
        locks = set()
        wins = {first: 0, second: 0}
        for number in range(1, 6):
            blue, red = (first, second) if number % 2 else (second, first)
            start = now + timedelta(days=index, hours=number)
            won = int(random.random() < (0.66 if blue == "north" else 0.48))
            game = Game(
                f"practice-{index}", f"practice-{index}-{number}", 1, number,
                "2.1" if index < 16 else "2.2", start, blue, red, won, end=start + timedelta(minutes=40),
                best_of=5, early_observed=True, format_mode=HARD_FEARLESS,
                competition="Practice circuit", gold_diff=random.randrange(-3600, 3600),
            )
            actions = []
            for side, kind, _ in DRAFT_ORDER:
                team = blue if side == BLUE else red
                position = list(teams).index(team)
                preferred = hero_pool[position * 12:position * 12 + 18]
                allowed = [hero for hero in hero_pool if hero not in locks]
                current = {action.champion for action in actions}
                pool = [hero for hero in preferred if hero in allowed and hero not in current]
                if kind == "ban" or not pool or random.random() < 0.46:
                    pool = [hero for hero in allowed if hero not in current]
                champion = random.choice(pool)
                actions.append(Action(side, kind, champion))
                if kind == "pick":
                    players = game.roster.setdefault(team, {})
                    players[key(team, str(len(players)))] = champion
            game.actions = tuple(actions)
            locks.update(game.picks[BLUE] + game.picks[RED])
            for objective in ("dragon", "grubs", "herald", "first_blood"):
                if random.random() > 0.18:
                    game.first[objective] = blue if random.random() < (0.64 if won else 0.39) else red
            if "grubs" in game.first:
                game.grubs[game.first["grubs"]] = random.choice((2, 3, 5))
            history.add(game)
            games.append(game)
            wins[blue if won else red] += 1
            if max(wins.values()) == 3:
                break
    return {
        "version": CACHE_VERSION, "names": {"teams": teams, "characters": characters},
        "coverage": {"valid_games": len(games), "valid_series": 32},
        "scouting": aggregate(games),
        "model": {
            "as_of": games[-1].end.isoformat(), "history": vars(history),
            "serving": {
                "pre": {"intercept": 0.06, "slope": 0.85},
                "weights": [5.0, 3.5, 2.3, 2.0, 3.4, 4.5, 1.8, 1.25],
                "gamma": {"6": 0.5, "12": 0.75, "16": 0.8, "20": 0.9},
            },
        },
    }
