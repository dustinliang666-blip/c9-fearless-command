# C9 Fearless Command

A League of Legends draft and macro scouting workbench. Scout by patch and side, play a legal Hard Fearless best-of-five, and read the evidence behind replacement suggestions before trusting them.

## Quickstart

From this repository root, run with Python 3.11 or newer:

```sh
python -B tracks/bounties/cloud9_jetbrains/app/server.py --demo --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`. `--demo` starts a synthetic scenario with illustrative coefficients. No dataset, credentials, package install, or network access is needed. `--host` and `--port` select the listener; defaults are `127.0.0.1` and `8000`.

Complete Game 1 with the recommendation buttons or champion chooser, select a scenario winner, and click **Record result**. Both teams' picks become unavailable for Game 2; bans do not carry over. Check **Series locks** and **How to win → Replacement watch** for the eligible pick-turn and distinct-game counts.

## Tests

```sh
python -m pip install -r requirements.txt
python -m playwright install chromium
python -B -m unittest discover -s tracks/bounties/cloud9_jetbrains/tests -v
```

On Windows the browser smoke test uses Microsoft Edge. The licensed-cache smoke test skips when no authorized external cache is configured. Run the public demo and synthetic tests without licensed data environment overrides.

## JetBrains PyCharm inspection

Shared PyCharm inspection configuration lives in `.idea/inspectionProfiles/Project_Default.xml`. The release codebase was audited and refactored with JetBrains PyCharm Community Edition `2025.2.6.1` (`inspect.bat`), resolving 16 static-analysis findings across `app/server.py`, `engine/draft_engine.py`, `etl/build_lol_aggregates.py`, and `tests/test_workbench.py`; see [AI_SHOWCASE.md](tracks/bounties/cloud9_jetbrains/AI_SHOWCASE.md) for the exact before/after receipt.

## Data and license

Only synthetic demo assets and MIT-licensed source are distributed here. The reported historical metrics come from a separate licensed evaluation; they do not describe the synthetic demo. For methodology and licensed-local setup, see the [project README](tracks/bounties/cloud9_jetbrains/README.md) and [validation receipt](tracks/bounties/cloud9_jetbrains/AI_SHOWCASE.md#validation-receipt). See [LICENSE](LICENSE).
