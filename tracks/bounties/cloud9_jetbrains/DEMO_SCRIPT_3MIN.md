# C9 Fearless Command | Three-minute recording plan

**Question for the viewer:** When an opponent's Game 1 pick is no longer legal, what can a coach prepare instead, and how much evidence supports it? Record the running workbench. The clock below is the edit timeline: finish speech by 2:58, then trim the silent tail so the public YouTube export is **under** three minutes. Use English narration or captions and original visuals; no unlicensed music or logos.

| Clock | Picture and operator action | English voice-over |
| --- | --- | --- |
| 0:00–0:12 | From the repository root, run `python -B tracks/bounties/cloud9_jetbrains/app/server.py --demo`. Open `http://127.0.0.1:8000/`. Hold on **Synthetic demo** and Northstar vs. Redshift. | “What happens to Redshift's draft when its opening pick disappears next game? Let's play that out. These teams, champions and matches are synthetic.” |
| 0:12–0:32 | In **Macro scouting**, select patch **2.2**, scout side **Red**. Zoom to **First dragon** and its fraction, then **Most picked**. Restore **All patches** and **Both** before drafting. | “Redshift secured the first dragon by minute fifteen in eight of fifteen observed red-side games on this practice patch. That's a reason to review early objective setups, not a prediction for the next match.” |
| 0:32–0:55 | In **Next-turn options**, click the top option and hold on the new point in **Win-rate impact**. Repeat with the top option through Redshift's first pick; note that pick and the first ban for the Game 2 comparison. | “The option estimates the change for the team acting now. The line uses a different reference: blue's change since before the draft, in percentage points. Watch it update after a ban and again after a pick.” |
| 0:55–1:14 | Continue choosing the first recommendation until turn 20 is complete. Speed up intervening clicks with a visible **time compressed** label. Pause over a point on the finished curve; leave Northstar selected as **Scenario winner**. | “Each point uses only the actions on the board so far. This is a scenario, not a forecast of who actually won. I'm recording Northstar as the winner so we can prepare the next draft.” |
| 1:14–1:36 | Click **Record result**. In **Game 2**, open **Series locks**; find the Game 1 pick. Open **Choose champion**: the old pick is absent; the old ban is available. Do not apply a move yet. | “Ten picks, from both teams, are unavailable to either side. Bans do not carry. We can threaten the old ban again, but neither team can take that first pick.” |
| 1:36–1:58 | Hold on **How to win → Replacement watch**. Highlight the fraction, then **distinct games**, then its scope. Cut briefly to Game 1 and back to show its board is still reviewable. | “Here the replacement appeared on two of twenty-five eligible pick turns, across five distinct games. The card says Game Two, Hard Fearless, all patches. Twenty-five turns is not twenty-five matches, and a replacement is not a guaranteed win.” |
| 1:58–2:22 | Cut to the command and final rows from a completed **licensed local evaluation** (setup below). Highlight Elo, then the full draft, including intervals. Do not film feeds or cache contents. | “Does pick/ban add information beyond team strength? On 377 held-out drafts, log loss went from 0.6714 for pre-draft Elo to 0.6701 after the draft. The intervals are wide. That's a small change, not proof that following a recommendation wins games.” |
| 2:22–2:48 | Show the **licensed local replay** command using variables, followed by its exit status and prefix length only. Cut to the passing synthetic replay test named below. Label the cut **pre-run; scan omitted**. | “For a historical replay, I ask for seven retained actions at a timestamp when all seven were known. The CLI refits without this series or later results. I get a baseline and seven turn values. The test also asks one turn too early and checks that the engine refuses.” |
| 2:48–3:00 | Return to Game 2 in **Synthetic demo**. End on **Series locks** beside **Replacement watch**. Add the tested public demo address only once available. No speech after 2:58. | “Try a different Game One. Check what's legal in Game Two, then read the denominator before trusting the advice.” |

### Operator preflight (off camera)

- Rehearse from a fresh page. The fractions above are from the synthetic defaults and this click path; if you change sides, patch, opponent or choices, read the new card rather than dubbing in the old number. The demo coefficients illustrate the UI, not the fitted model.
- Pre-run both licensed commands **locally**, from the repository root, with the dependencies in [README.md](README.md). Set `STL_DATA_DIR` to your authorized source checkout and `C9_CACHE_DIR` to a separate external cache directory. Never point the public host at these directories. A full scan need not finish on camera.

```powershell
$engine = 'tracks/bounties/cloud9_jetbrains/engine/draft_engine.py'
python -B $engine --revalidate
```

Privately choose a complete Game 1 with earlier completed training series. Use its licensed series ID and a timezone-aware time in the draft window when the first seven retained actions have been observed. Enter both values off camera; do not publish the ID, timestamp, picks, per-game predictions or raw JSON. Capture a real run:

```powershell
$series = Read-Host 'Local series ID'
$asOf = Read-Host 'Verified prefix timestamp (ISO 8601 with offset)'
$replay = python -B $engine --as-of $asOf --series $series --game 1 --step 7
$rc = $LASTEXITCODE
if ($rc -ne 0) { throw "Replay failed: $rc" }
$points = ($replay[-1] | ConvertFrom-Json).blue_probabilities.Count
"Replay exit $rc; $points points (including pre-draft)"
```

The independent negative check needs no licensed input: `python -B -m unittest discover -s tracks/bounties/cloud9_jetbrains/tests -p test_cloud9_lol.py -k historical_replay -v`. In this synthetic test four turns are verified; a request for the fifth is rejected. It is a different case from the seven-turn local replay.

### Publish checklist (not yet performed)

1. Publish only the project sources and synthetic assets to a dedicated public repository. Preserve the `tracks/bounties/cloud9_jetbrains/` import layout and include the project MIT license and run instructions at the repository root. Test from a clean checkout; do not publish the surrounding workspace or mount any licensed directories.
2. On a Python-capable host behind HTTPS, use `python -B tracks/bounties/cloud9_jetbrains/app/server.py --demo --host 0.0.0.0 --port 8000` (set the port to the host's assigned listener). From a signed-out browser, check `/api/health` reports `mode: synthetic`, complete a draft and confirm Game 2 locks. Keep the URL free and accessible through judging.
3. Export the English cut under three minutes, upload it publicly to YouTube and test the watch link signed out. Complete the genuine JetBrains activity and disclosure in [AI_SHOWCASE.md](AI_SHOWCASE.md) before using the project text or bonus link on Devpost.
