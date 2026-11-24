# Engineering C9 Fearless Command: when the board should stay flat

The useful question was not “can an AI suggest a champion?” It was “can a coach tell a legal alternative, a historical observation and a model estimate apart?” We used AI assistants to build and challenge the software. We did **not** put a chat model in the recommendation path: the same board and evidence produce the same kind of auditable answer.

## What each tool actually did

| Role | Work performed | How to check the result |
| --- | --- | --- |
| Build — GPT-6.2 Sol / Codex | Implemented the Phase 2 engine and interactive workbench. The team brief specified a legal series, evidence counts and separate synthetic and licensed modes. | Follow one action from `app/static/workbench.js` to `Workbench.evaluate` in `app/server.py` and `SeriesDraft` in `engine/draft_engine.py`. |
| Cross-family review — Claude Fable 5.2 | Reviewed Phase 2; the build went through a fix-and-recheck cycle. A review sign-off is not a performance measurement. | `tests/test_cloud9_lol.py` checks time boundaries and turn legality. `tests/test_workbench.py` exercises HTTP, carried picks, evidence denominators and the browser. |
| Independent fact-check — GPT-6.2 Astra / Codex | Compared documentation with source, reran the refit and tests, and rehearsed the synthetic evidence and licensed replay. | The full-draft AUC in an earlier README did not match the fresh run. The corrected receipt below comes from `--revalidate`, not the cached report or a model's recollection. |
| Static analysis & refactoring — JetBrains PyCharm Community Edition `2025.2.6.1` (`PC-252.28539.58`) | Ran headless project inspection (`inspect.bat` with `.idea/inspectionProfiles/Project_Default.xml`) across `tracks/bounties/cloud9_jetbrains/`, resolved 16 true-positive Python findings across 4 files, consciously rejected 8 stdlib/namespace false positives, and re-verified with both `inspect.bat` and `unittest`. | Inspect `.idea/inspectionProfiles/Project_Default.xml`, the `PyCharm static inspection receipt` below, and run `python -B -m unittest discover -s tracks/bounties/cloud9_jetbrains/tests -v`. |

**JetBrains tool disclosure:** This entry uses **JetBrains PyCharm Community Edition `2025.2.6.1` (build `PC-252.28539.58`)** (`inspect.bat` + shared `.idea/inspectionProfiles/Project_Default.xml`) to run Python static type checking, unused-symbol analysis, and scope-shadowing inspections prior to release. We did **not** use JetBrains Junie or Air in this build record and do not claim Junie/Air workflow automation.

### PyCharm static inspection receipt (2026-11-24)

Command run from the standalone repository root with PyCharm Community `2025.2.6.1`:

```powershell
& "C:\Program Files\JetBrains\PyCharm Community Edition 2025.2.6.1\bin\inspect.bat" `
  . .idea\inspectionProfiles\Project_Default.xml out_inspect `
  -d tracks\bounties\cloud9_jetbrains -v1 -format json
```

- **Accepted and fixed (16 Python warnings → 0 in those categories):**
  - `app/server.py` (`PyTypeCheckerInspection`: 6 → 0; `PyShadowingNamesInspection`: 3 → 0): explicitly typed `Handler.send` and `Handler.send_json` with `status: HTTPStatus | int = HTTPStatus.OK` (PyCharm flagged `HTTPStatus.FORBIDDEN`, `BAD_REQUEST`, and `NOT_FOUND` against an inferred `Literal[HTTPStatus.OK]`), and renamed inner helper variables (`count`, `blue_team`, `first_pick`) to avoid shadowing outer names.
  - `engine/draft_engine.py` (`PyTypeCheckerInspection`: 1 → 0; `PyRedundantParenthesesInspection`: 2 → 0): annotated `rows: list[tuple[float, ...] | None] = [None] * (len(DRAFT_ORDER) + 1)` in `draft_examples` so tuple assignments type-check cleanly, and removed redundant tuple parentheses on two `yield` statements in `prefix_features`.
  - `etl/build_lol_aggregates.py` (`PyUnusedLocalInspection`: 1 → 0): removed the unused `team` parameter from `add_transitions(game, side, prior, cohort)` and updated its caller in `aggregate`.
  - `tests/test_workbench.py` (`PyUnusedImportsInspection`: 2 → 0; `PyTypeCheckerInspection`: 1 → 0): replaced `self.skipTest` fallthrough with explicit `raise SkipTest(...) from exc` and typed `ViewportSize(width=1440, height=900)`.
- **Consciously rejected (8 stdlib/layout warnings retained):**
  - `PyPep8NamingInspection` (2): `BaseHTTPRequestHandler.do_GET` and `do_POST` require exact stdlib method casing.
  - `PyRelativeImportInspection` (4): namespace-package imports (`from ..contracts ...`, `from .draft_engine ...`) work across CLI and `unittest` discovery without empty `__init__.py` boilerplate.
  - `PyTypeCheckerInspection` (1) & `PyUnresolvedReferencesInspection` (1): stdlib `ThreadingHTTPServer(..., Handler)` generic stub variance and `BaseServer.server_port` attribute stub.
- **Post-fix verification:** Re-running `inspect.bat` exited `0` with all 16 accepted issues eliminated, and `python -B -m unittest discover -s tracks/bounties/cloud9_jetbrains/tests -v` passed `24/24` synthetic tests (1 licensed-cache test skipped outside authorized cache).

## One board, two clocks

**The coach's clock.** `contracts.py` defines the pick/ban sequence; map side and first-pick priority are separate. `SeriesDraft.finish_game` requires a complete draft and a scenario winner. In Hard Fearless it carries both sides' **picks**, not bans, into the next game regardless of a side swap. Historical standard games reset; unknown series do not supply lock-conditioned replacements. For a historical Hard Fearless board, required prior games must have legally reconstructible drafts and must have ended **strictly before** the target draft. Equality is not “before.”

**The model's clock.** `etl/build_lol_aggregates.py` streams each eligible feed and reconciles reversals before counting early objectives. `engine/draft_engine.py` groups games by series, orders by draft start, and releases results, estimated lineups and player/champion statistics only after series completion. Earlier legal picks can impose locks without revealing that series' outcomes to the rating model. Prefix features use picks and bans observed so far, not the final lineup from the game being scored.

`engine/calibration.py` estimates a nonnegative-slope Platt transform of time-decayed Elo with a blue-side prior. Draft features (including player familiarity, ally synergy, opposing matchups and demand for locked picks) are fitted with an L2 penalty and a fixed pre-draft logit offset. Five forward validation folds within training supply out-of-fold estimates. At each fold, earlier calibration rows are eligible only when their series ended before that fold's start. Each stage learns a weight between zero and one; no forward log-loss gain means zero. The reported holdout uses frozen training statistics and parameters, never the all-history model served for hypothetical games.

## Validation receipt

Fresh licensed source scan and local suite, 2026-11-24 (Asia/Shanghai), Python 3.13.13. From the repository root, after installing the [licensed dependencies](README.md):

```powershell
$env:STL_DATA_DIR = '/external/authorized-source'
$env:C9_CACHE_DIR = '/external/authorized-cache'
python -B tracks/bounties/cloud9_jetbrains/engine/draft_engine.py --revalidate
python -B -m unittest discover -s tracks/bounties/cloud9_jetbrains/tests -v
```

- **Coverage:** 728 valid series, 1,697 games and 1,695 complete ordered drafts (external cache coverage fields). The fresh source scan streamed 728 valid feeds from an index of 745 series.
- **Time split:** last training result `2026-02-02T00:59:35.749000+00:00`; cutoff `2026-02-02T15:46:17.180000+00:00`. Train: 582 series / 1,318 drafts. Holdout: 146 series / 377 drafts. Overlapping series purged: 0; untimed games: 0. Training out-of-fold: 1,146 drafts, 1,145 with pick/ban features. Holdout pre-only fallbacks: 0.
- **Verification:** `--revalidate` exited 0. `unittest` ran 25 tests and exited 0, with no skips; these include the licensed-cache read-only check and the synthetic Playwright browser smoke test.

Each cell is the printed point estimate and 95% percentile interval from 2,000 whole-series bootstrap resamples. Games from a sampled series stay together. Higher AUC is better; lower LogLoss and Brier are better.

| Model | AUC [95% CI] | LogLoss [95% CI] | Brier [95% CI] |
| --- | --- | --- | --- |
| 50% baseline | 0.5000 [0.5000, 0.5000] | 0.6931 [0.6931, 0.6931] | 0.2500 [0.2500, 0.2500] |
| Blue prior 51.7% | 0.5000 [0.5000, 0.5000] | 0.6897 [0.6858, 0.6935] | 0.2483 [0.2463, 0.2502] |
| Pre-draft Elo | 0.6166 [0.5527, 0.6796] | 0.6714 [0.6484, 0.6945] | 0.2392 [0.2281, 0.2501] |
| Draft after 6 steps | 0.6166 [0.5527, 0.6796] | 0.6714 [0.6484, 0.6945] | 0.2392 [0.2281, 0.2501] |
| Draft after 12 steps | 0.6183 [0.5554, 0.6797] | 0.6704 [0.6460, 0.6943] | 0.2387 [0.2270, 0.2501] |
| Draft after 16 steps | 0.6181 [0.5549, 0.6798] | 0.6705 [0.6460, 0.6944] | 0.2387 [0.2270, 0.2501] |
| Draft after 20 steps | 0.6168 [0.5526, 0.6797] | 0.6701 [0.6456, 0.6944] | 0.2386 [0.2269, 0.2501] |

The first stage's fitted weight was zero: moving the line there would have implied information the validation did not support. Step 12 ranked outcomes slightly better than the full draft on this split; more actions did not monotonically improve AUC. The full draft's loss and Brier were slightly lower than Elo's. These are per-model intervals, not a paired test of the difference. None of these numbers measures the effect of following a particular pick recommendation.

## What the judge can inspect

- **The evidence unit.** `how_to_win` returns a numerator, denominator, unit, scope and distinct-game count. A replacement frequency counts eligible pick turns, not matches or wins. A first-dragon comparison counts games. Patch-specific advice can fall back to a wider cohort; the card labels the scope actually used.
- **The forecast boundary.** The right-hand curve is blue's cumulative change from pre-draft. A candidate is scored against the current board using the *same next-stage weight* for both alternatives, then signed for the acting side. Crossing a calibration stage therefore need not make the option delta equal the next movement of the curve.
- **The zero-build interface.** `app/static/` contains local HTML, CSS, JavaScript and an SVG curve. One Python standard-library HTTP server serves them and evaluates boards. The synthetic browser test drives a full draft, checks the next game's locks, revisits the completed game and checks that the page made no external requests.
- **The data boundary.** In licensed mode `app/server.py` restricts the bind address to loopback and checks the HTTP `Host` against local names and the listener port on GET and POST. This guards against foreign Host headers; it is not authentication. Never reverse-proxy licensed mode to the internet. `--demo` creates its own fixtures and illustrative coefficients in memory instead of loading the licensed cache.
- **The replay boundary.** The workbench rejects historical `as_of` requests. The CLI excludes the target series and fits on series completed strictly before the target draft. A replay accepts only retained actions verified by the requested time; it is not a tick-for-tick reconstruction of later-retracted actions. A licensed seven-turn replay exited 0 with eight curve values including the baseline. The [recording plan](DEMO_SCRIPT_3MIN.md) shows how to demonstrate this without publishing a licensed board.
