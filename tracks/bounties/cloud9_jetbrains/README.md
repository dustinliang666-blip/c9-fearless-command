# C9 Fearless Command

A League of Legends draft and macro scouting workbench. Scout an opponent by patch and map side, play a legal Hard Fearless best-of-five, and track the percentage-point change in blue-side win probability at each turn. The coach brief attaches sample counts and scopes to its scouting advice.

## Start the workbench

Judge materials: [Devpost project story](DEVPOST_SUBMISSION.md) · [engineering and AI workflow](AI_SHOWCASE.md) · [three-minute recording plan](DEMO_SCRIPT_3MIN.md).

From the repository root, run either command and open `http://127.0.0.1:8000/`. Python 3.11 or newer can serve the workbench with its standard library. The browser uses local HTML, CSS and JavaScript and requires no build step.

~~~powershell
python -B tracks/bounties/cloud9_jetbrains/app/server.py --demo
~~~

Demo mode uses original generated teams, champions and matches, with illustrative coefficients. It runs without a GRID checkout, fitted cache or network connection.

~~~powershell
$env:C9_CACHE_DIR = '/external/authorized-cache'
python -B tracks/bounties/cloud9_jetbrains/app/server.py
~~~

Licensed mode reads `$C9_CACHE_DIR/lol_aggregates.json` once, binds locally, and defaults to Cloud9 Kia vs. FlyQuest. Use the synthetic mode for public demos. The licensed source and cache stay outside the repository. [GRID data license](https://github.com/cloud9esports/stl-hackathon-2026-grid-starter/blob/main/LICENSE.md)

In the draft board, use the champion menu or click a recommendation to apply the current turn. After the 20th turn, record a scenario winner to carry both teams' picks into the next game as locks. Games already played remain available for review. Map side and first pick can be chosen independently before each draft starts.

## Build and verify the licensed cache

~~~powershell
python -m pip install numpy scipy zstandard orjson
$env:STL_DATA_DIR = '/external/authorized-source'
$env:C9_CACHE_DIR = '/external/authorized-cache'
python -B tracks/bounties/cloud9_jetbrains/etl/build_lol_aggregates.py
python -B tracks/bounties/cloud9_jetbrains/engine/draft_engine.py --revalidate
python -B tracks/bounties/cloud9_jetbrains/cli_demo.py
python -B -m unittest discover -s tracks/bounties/cloud9_jetbrains/tests -v
~~~

`orjson` is optional. Python 3.14 can use its built-in Zstandard reader. The HTTP smoke tests use a temporary server with an operating-system-assigned port. Install Playwright and Chromium (Edge on Windows) to also run the browser smoke test.

The ETL checks `session_valid`, streams each compressed feed, and replaces the external cache atomically. The verified cache covers 728 valid series, 1,697 games and 1,695 complete ordered drafts. Event routing uses the explicit game ID or the changed game in the feed delta. Macro aggregation reconciles reversals before applying the 15-minute clock cutoff, and GD@15 uses the latest snapshot within the preceding 30 seconds.

Historical drafts use `standard`, `hard_fearless` or `unknown`. The rules table uses the published format for known events and stages. A standalone Bo1 is standard by default, and unverified multi-game formats remain unknown. Only confirmed Hard Fearless games contribute lock-conditioned replacement evidence. A prior game must have ended strictly before the next draft, and the prior board must replay legally.

- 2025 rules. [Season format](https://lolesports.com/news/lol-esports-in-2025) · [LCK Cup](https://lolesports.com/ko-KR/news/2025-lck-new-format/) · [LEC Winter](https://lolesports.com/en-GB/news/2025-lec-winter-split-primer) · [Fearless extension](https://lolesports.com/en-SG/news/fearless-draft-takes-over-2025)
- 2026 rules. [Season format](https://lolesports.com/en-GB/news/season-start-2026-lol-esports) · [LEC rulebook](https://static.wikia.nocookie.net/lolesports_gamepedia_en/images/c/cf/LEC_2026_Rulebook.pdf/revision/latest?cb=20260202160035) · [LCS rulebook](https://static.wikia.nocookie.net/lolesports_gamepedia_en/images/2/22/LCS_2026_Rulebook.pdf/revision/latest?cb=20260502170501) · [LCS Promotion](https://lolesports.com/en-US/news/lcs-promotion-tournament-wsci)

The read-only HTTP endpoints are `GET /api/health`, `GET /api/teams`, `GET /api/scouting?team=…&patch=…&side=…`, and `POST /api/draft/evaluate`. The draft endpoint accepts team IDs, an optional patch, and one to five game objects. Each game can specify `blue`, `first_pick_side`, `actions` (ordered champion IDs or a null pass for a ban), and `winner`. Each brief sample returns `numerator`, `denominator`, `unit`, `scope`, and `distinct_games`. A replacement sample counts eligible pick turns and the distinct games that contributed them.

## Chronological calibration

Each stage uses `logit(p_s) = z_pre + gamma_s * delta_z_BP,s`. The pre-draft component uses time-decayed Elo with an observed blue-side prior and nonnegative-slope Platt scaling. Elo, lineup estimates and sparse, sample-size-shrunken statistics are released after series completion. Model weights are fitted against the pre-draft logit as a fixed offset with L2 regularization. Five forward training folds supply out-of-fold estimates for stage shrinkage. A stage with no forward log-loss improvement gets a zero weight, returning the pre-draft probability at every turn in that stage.

The holdout begins at `2026-02-02T15:46:17.180000+00:00` and contains 377 drafts across 146 series. All model parameters and historical priors are frozen from the 582 training series (1,318 drafts). Parentheses show 95% percentile intervals from 2,000 series-cluster bootstrap replicates.

| Model | AUC | LogLoss | Brier |
| --- | --- | --- | --- |
| 50% | 0.5000 (0.5000–0.5000) | 0.6931 (0.6931–0.6931) | 0.2500 (0.2500–0.2500) |
| Training blue-side prior | 0.5000 (0.5000–0.5000) | 0.6897 (0.6858–0.6935) | 0.2483 (0.2463–0.2502) |
| Pre-draft Elo | 0.6166 (0.5527–0.6796) | 0.6714 (0.6484–0.6945) | 0.2392 (0.2281–0.2501) |
| Complete calibrated draft | 0.6168 (0.5526–0.6797) | 0.6701 (0.6456–0.6944) | 0.2386 (0.2269–0.2501) |

The full draft has lower LogLoss and Brier than the blue-side prior. Compared with Elo, the change is small; these are intervals for each model, not a paired interval for the gain. A draft delta describes a model estimate on this board, not the causal effect of the pick. The fresh `--revalidate` run and the 25-test suite both exited 0 on 2026-11-24; see [all draft stages](AI_SHOWCASE.md#validation-receipt).

Running `draft_engine.py` without flags prints the stored validation report, not a refit. The existing external cache differs in the last decimal of some AUC fields. Use `--revalidate` for the published table; it does not rewrite the cache.

## Historical replay

Run `engine/draft_engine.py --as-of <ISO-8601 timestamp> --series <series-id> --game <number> --step <0–20>` with the licensed source available. Use a timezone-aware timestamp between that game's draft start and game start. A replay fits a fresh model from series completed before the target draft and exposes only the requested prefix verified at that timestamp. The workbench serves hypothetical boards using a separate all-history model. Historical timestamps are accepted by the replay CLI.
