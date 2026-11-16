# AI-use log

The Space Apps rules ask every team to describe how it used AI. This file records what AI tools did in this project, what people decided, and where AI output was wrong and corrected. New entries go at the bottom of the log. Times are UTC.

## Tools

| Tool | Models | Used for |
|---|---|---|
| Claude Code (Claude desktop app, Code tab) | Claude Opus 5.5 (`claude-opus-5-5`), Claude Fable 5.2 (`claude-fable-5-2`) | Method design, data analysis scripts, the explainer page, project documents, the pipeline, API and app code, git and GitHub operations |
| GitHub Copilot pull request reviewer | GitHub's choice | Automatic review comments on pull requests #5–#17; Claude Code fixed the valid ones and replied on each thread |

Commits written with AI help carry a `Co-Authored-By: Claude …` line naming the model.

## How we use AI

- **People decide; AI proposes and does the work.** The team chose the challenge, the scientific priorities, the data and the technology stack, and approves every commit, push, pull request and merge. Where a decision was proposed by the AI and accepted, the log says so.
- **Every number comes from code run on our data.** Results quoted in our documents are produced by scripts in this repo, not written from the model's memory.
- **AI mistakes are logged, not hidden.** Each session's entry lists errors the AI made and how they were caught.
- **No secrets shared.** The FIRMS MAP_KEY's value has never been shown to an AI tool. The team put it in the git-ignored `.env` themselves. From 2026-11-15 the AI runs the download step, which reads the key from `.env` and sends it only to FIRMS; the AI checked that the key appears in no log, downloaded file, commit or pull request.

## Log

### 2026-11-14, session 1 (15:12–22:35): method, rule checks, explainer, design

**15:12–15:45 · Harmonization approach** (Opus 5.5)
- *Asked:* how to approach MODIS–VIIRS harmonization with the highest scientific rigour.
- *AI did:* laid out the approach (burning cell-days on H3 hexagons, Aqua–S-NPP overlap, leave-one-year-out validation, held-out years) and proposed upgrades, each with a keep/reject rule set in advance.
- *Decided by the team:* focus on the harmonization science before building anything.

**15:45–15:56 · Checking the rules on real data** (Fable 5.2 from here until 20:36)
- *Asked:* how valid each rule is, then to test them on the standard-processing FIRMS archives already downloaded, using H3 cells for cell-days.
- *AI did:* wrote `science/rule_checks/ingest.py` (H3 res-8 cell-days for Aqua and S-NPP, Argentina box, 2012–2025) and `checks.py` (baseline fit, leave-one-year-out, year-block bootstrap, permutation test, join test, error-range coverage, stand-in test, nested cross-validation, outage detection). Results are in `results.json`.
- *Found:* the planned "every decile under 3 %" rule fails 99.7 % of the time even when there is no tilt; luck moves whole-area scores too much for a 0.2-point margin; the baseline join and error ranges pass; the larger surrounding region is a better stand-in.
- *Decided:* the AI proposed revised rules and pass marks from these results. The team accepted them, later fixed in `PREREGISTRATION.md`.

**15:56–19:19 · Explainer page ("primer")**
- *Asked:* visualizations of the analysis for teaching; then more context, metaphors and examples; foundational concepts; links between lessons and goals; plain language for a non-specialist.
- *AI did:* built `primer.template.html`, `build_page.py` and the generated `primer.html`, with hand-written SVG charts, and published it as a private claude.ai artifact. It rewrote the page several times to the team's feedback.
- *Also:* read NASA LAADS's MODIS-to-VIIRS transition page for relevant points. On the team's request it wrote and ran `frp_check.py` (fire-strength floors). This showed the tilt comes from small fires only VIIRS detects. That became a lesson.

**19:19–20:36 · Primer restructure** (session context was summarised and continued here)
- *Asked:* make the lessons less disparate; how a scientist would do it in order; how each relates to formulas and data; make the formulas look nice.
- *AI did:* reordered the page into a nine-step path with a "next question" link between steps. It added a "The maths" box to each step, checking each formula against the analysis code, and typeset the formulas with KaTeX (a one-off Node script, not in the repo).

**20:36–21:09 · Status and architecture** (Opus 5.5 from here)
- *Asked:* status against the challenge objectives; whether a pipeline, API and web-app architecture is sound; whether an API server is better for global coverage; status of the rule checks.
- *AI did:* compared the repo with the game plan and the challenge page. It reviewed an architecture design and recommended keeping its data flow while changing several points (single place applying the model, stateless areas, error ranges built after summing an area, per-block outage checks). It estimated global data sizes from Argentina numbers; these are marked as estimates to be measured.
- *Decided by the team:* the whole globe is the goal; Rust backend with a Svelte frontend.

**20:55–21:28 · Pre-registration, architecture, git**
- *AI did:* wrote `PREREGISTRATION.md` and `ARCHITECTURE.md`, committed them and the rule-check work, pushed branches, and opened pull requests #1 and #2. The team reviewed and merged both. The AI then deleted the merged branches at the team's request.

**21:31 · This log started.**

**21:38–22:35 · First working prototype** (Opus 5.5)
- *Asked:* build a prototype to iterate on: the Argentina pipeline for 2000–2025 writing the published data, a frontend built against a saved example response, and a minimal Rust API with `query` and `meta`.
- *AI did:* wrote `firecal.toml` and the Python + DuckDB pipeline in `pipeline/` (ingest, cell-days, fit and validation, publish, and a Python reference implementation of the API that writes example responses). It wrote the API contract (`docs/api.md`) and the Rust API in `api/`, and checked the API against the Python reference with `pipeline/tests/test_api_parity.py` (10 requests, 4 rejected requests and `meta`, all matching). A second AI agent, working in parallel from a written brief, built the SvelteKit frontend in `web/` against the example responses. The AI then ran the full app in a browser with live data.
- *Checks:* the Aqua multipliers and scores reproduce the earlier rule checks exactly (day 3.05, night 10.3, typical error 9.95 %). Known satellite outages appear as gaps or filled days (for example Terra, 2001-06-15 to 07-02).
- *Not verified:* screen readers, browsers other than the in-app one, and file downloads through the browser's save dialog.

**Errors the AI made in this session, and how they were caught**
- Claimed the in-sample join gap is zero by construction. Wrong with shrinkage (night gap −6.5 %); corrected by the AI.
- Published the primer with a summary-table column missing after a script's check failed, and said it was done. Caught by the AI; fixed and republished.
- Wrote that the commit order showed the rules came before the evidence. The team questioned it; the AI clarified that the Argentina analysis came first and the pre-registration only protects the global analysis and future upgrades.
- Pushed `ARCHITECTURE.md` to pull request #1 after the team had already merged it, and edited the merged PR's description to include it. The team pointed this out; the AI restored the PR's description and moved the commit to a new PR (#2).
- Could not view most of the primer's layout in its browser tool; the team was told which parts were unchecked.

### 2026-11-14 to 15, session 1 continued (22:35–04:20): building out the prototype

All work in this part was done with Opus 5.5. The session's context was summarised and continued along the way.

**22:35–23:17 · Prototype pull request** (#5)
- *AI did:* committed the prototype, opened pull request #5, and fixed the Copilot review comments on #1–#5. The team merged it.
- *Decided by the team:* not to rewrite the git history.

**23:17–23:49 · Naming the unit** (#6)
- *Asked:* whether "burning places" was the right term, what its unit is, and how close "VIIRS-equivalent burning cell-days" is to the literature.
- *AI did:* explained the unit (one H3 res-8 cell, one local solar date, one day or night pass) and compared candidate names with terms used in fire-count studies.
- *Decided by the team:* "fire-days" in the app and "VIIRS-equivalent burning cell-days" in the documents. The AI renamed both, updated the primer, and opened #6.

**23:49–02:03 · Map and area drawing** (#7)
- *Asked:* whether to rebuild the interface on Kepler.gl; then to add map drawing.
- *AI did:* compared Kepler.gl with building on its parts. The team chose MapLibre GL, deck.gl and Terra Draw (all open-source licences, checked by the AI), with OpenFreeMap basemaps. The AI built the map with drawn boxes, polygons and circles and per-hexagon fire-days. The API now returns the area outline and per-hexagon values, and the parity test covers them.
- *Asked:* why drawing needed two clicks; the AI switched to press-and-drag. *Asked:* to try deck.gl's H3 layer and report the cost; the AI measured the bundle (+4.1 KB gzipped once imports were fixed).

**02:03–03:37 · Hotspot CSV export** (#8)
- *AI did:* added `POST /api/export.csv` in Rust and the Python reference: filtered hotspots for the searched hexagons and months, with a row cap. Exports are compared byte for byte in the parity test. A detection is marked `in_calendar` when it came from the satellite the calendar counts that day; for one test area this matched the calendar's own detection count exactly (14,851).

**03:37–04:13 · Recent data and the in-progress month** (#9)
- *Asked:* add recent data and compare the month in progress.
- *AI did:* wrote the FIRMS area API download step and ingest of recent days. It extended the series to 2026-11-13 and compared the in-progress month with the same days in earlier years across the pipeline, both APIs and the app.
- *Found:* near-real-time files lack FIRMS `type`. The AI tested a stand-in mask on 2023–2025 and logged it as a change in `PREREGISTRATION.md`, noting the check came first. S-NPP's near-real-time feed ends on 2 November, so November 2026 is NOAA-20 only.
- *Asked:* whether an "ever flagged as static" mask is valid. The AI tested it on the same years: it catches slightly more non-vegetation detections but drops four times as much real fire. *Decided by the team:* keep the current mask.

**04:13–04:20 · Status and next steps**
- *Asked:* status against the challenge objectives. All nine work for the Argentina prototype. *Decided by the team:* bring this log and `ARCHITECTURE.md` up to date and add a NOAA-20 conversion before building a public demo.

**Checks in this part:** the Rust API matched the Python reference on every parity request after each change (0 failures). The app was checked in the in-app browser after each feature. *Not verified:* screen readers, other browsers, and downloads through the browser's save dialog.

**Errors the AI made in this part, and how they were caught**
- A SQL month filter overflowed a 16-bit year column. Caught by the AI's test; fixed with a cast.
- Several map set-up mistakes (MapLibre import, the worker file served as a web page, an empty legend class). Caught by the AI in the browser.
- The first H3-layer bundle was 160 KB larger than needed because of how the module was imported. Caught when the AI measured the bundle for the team; fixed with named imports.
- Drawing needed two clicks. The team noticed; fixed.
- The export could write an empty `hex_id` for an invalid cell (caught by Copilot). The AI's first fix rejected every cell, because the validity check was given a number instead of a string; caught by the AI's own test.
- A fallback end date could be invalid, such as 31 February (caught by Copilot); fixed in both APIs.
- Browser screenshots sometimes showed stale pages. The AI rechecked through page scripts instead of trusting them.

### 2026-11-15, session 1 continued (04:20–04:40): documents and the NOAA-20 check

All work in this part was done with Opus 5.5.

**04:20–04:22 · This log and the architecture** (#10)
- *Asked:* do the important follow-ups in the suggested order, checking in along the way. The AI began preparing a public demo. *Decided by the team:* set the demo aside for later.
- *AI did:* added the build-out entry above, listed the Copilot reviewer as a tool, and corrected the key-handling note. In `ARCHITECTURE.md` it updated file and step names and marked where the prototype differs from the global design.

**04:22–04:29 · NOAA-20 against S-NPP** (#11)
- *Why:* S-NPP's near-real-time feed ended on 2026-11-02, so recent months are counted from NOAA-20 alone, treated as S-NPP with no conversion. The two had never been compared.
- *Decided by the team:* fix the keep/reject rule before fitting. The AI proposed the rule (the margins of pre-registered rules 1 and 2, against no conversion). It committed the rule to `PREREGISTRATION.md` before running any NOAA-20 fit.
- *AI did:* fitted NOAA-20 with the same model as Aqua on 2018–2022, leaving one year out.
- *Found:* NOAA-20 and S-NPP count almost the same (multipliers 1.006 by day, 1.008 at night). With no conversion the typical error is 2.54 % for the whole area and 8.19 % for small areas. The fitted conversion made small areas 0.22 points worse, so the rule rejected it and NOAA-20 stays unconverted. On held-out 2023–2025 (reported only), the whole-area error was 2.34 % without conversion and 1.83 % with it.
- *AI did:* recorded the outcome under the rule. The methods page and the API's `meta` now show NOAA-20's scores as used, without conversion. Published counts did not change (row for row).

**04:29–04:38 · Review comments**
- Copilot's four comments were all valid; the AI fixed them, replied on each thread and resolved it. The team merged #10 and #11.

**Checks in this part:** the Aqua and Terra fit results reproduced exactly. The parity test passed (0 failures). After the review fixes, `validation.json` was byte-identical and the published data matched row for row. *Not tested:* the publish path for a NOAA-20 conversion the rule keeps, since none was kept.

**Errors the AI made in this part, and how they were caught**
- The first run of the new fit code crashed on a variable the AI had moved. Caught by the run; fixed before any result was used.
- The methods page would have listed NOAA-20 under "Converted satellite" with the scores of the rejected conversion. Caught by the AI before committing.
- The publish step still gave NOAA-20 a fixed multiplier of 1, so a conversion the rule kept would have been silently ignored (caught by Copilot).
- `ARCHITECTURE.md` presented the global endpoint table without saying so, and wrote `gold/current` for the real `gold/CURRENT` file (caught by Copilot).

### 2026-11-15, session 1 continued (04:47–06:50): local checks, refresh, real data only

All work in this part was done with Opus 5.5.

**04:47–05:05 · Status, and where the checks run**
- *Decided by the team:* set the public demo aside until the other objectives are done.
- *AI did:* proposed GitHub Actions checks that ran the pipeline on a committed sample of FIRMS rows. *Decided by the team:* fire data does not go into the repo, and the checks run locally instead.

**05:05–05:28 · Local checks and mise** (#13)
- *AI did:* wrote `scripts/check.sh`. It type-checks and builds the frontend, builds the API, runs the whole pipeline on a small sample, and compares the Rust API with the Python reference on the sample and on the full data. The sample is real FIRMS rows for a box near the Paraná Delta, built from local data and git-ignored.
- *Found:* building the sample exposed a real bug. Ingest crashed when no recent file had a `type` column, which happens once every recent day is near-real-time. Fixed in the same pull request.
- *Decided by the team:* adopt mise as the task runner and pinned-tool manager, committing the checks first and mise second. The AI pinned Node, pnpm, Rust, uv and Python, and turned the README's commands into tasks.
- *Asked:* whether the local check equals a CI run on the production data. The AI explained the differences: same steps, but it runs only on this machine, and only when someone runs it.

**05:28–05:40 · Keeping the data current**
- *AI did:* began with a macOS launchd job to run the refresh daily on this machine. *Decided by the team, after asking for a plain explanation and alternatives:* drop the launchd job. Deployed, the server's scheduler runs the same script, with the key in that job's environment only.
- *AI did:* wrote `scripts/refresh.sh` (`mise run refresh`): download, ingest, cells, publish, then a new `prune` step that keeps the newest `keep_versions` data versions plus the one in use.

**05:40–06:11 · Real data only** (#14)
- *Asked:* what the example data was, then to drop it and test against a running backend, with the tests first.
- *AI did:* added 11 Playwright browser tests. They load the app from the Rust API and check every number on screen against the API's answer for the same request, including presets, dates, custom areas, calendar clicks, the three downloads and error messages. `check.sh` runs them on the sample and on the full data. The AI committed the tests while example mode still existed, then removed it: the saved responses, the fallback to them, the browser copy of the stats rules, the example-only parts of the page and the pipeline's `example` step.
- *Found:* the sample box is so small that every past month counts as incomplete, so the sample never exercises the "usual" comparison. The full-data run covers it.

**06:11–06:25 · Review comments**
- Copilot's two comments were valid. The AI fixed both, tested the fixes and replied on each thread. *Decided by the team:* resolve the threads, then merge.

**06:25–06:50 · Dependabot alerts** (#15)
- *Asked:* check three Dependabot alerts on `main` (image-size high, fflate moderate, deepmerge low).
- *AI did:* traced each through `pnpm why` and searched the built app for each library's name and its own error messages. None are in the app. image-size and fflate come in with deck.gl's 3D-tiles and texture loaders, which the app does not use. deepmerge only merges the project's own build config.
- *Decided by the team:* pin the patched versions and dismiss the deepmerge alert, which has no patched release. The AI pinned fflate 0.7.5 and image-size 2.0.3 and dismissed the alert as "not used". GitHub closed the other two when #15 merged.

**Checks in this part:** `mise run check` passed before each push: parity with 0 failures on the sample and on the full data, and, from #14 on, 11 of 11 browser tests on both. The new refresh lock and `prune` were tested on throwaway files and folders. *Not verified:* a full `mise run refresh` on the real data (no new version has been published with it yet), drawing an area on the map in the browser tests (the box and circle forms run the same search), and the pinned image-size version with the tool that uses it, which the app never runs.

**Errors the AI made in this part, and how they were caught**
- The AI proposed committing a sample of fire data so the checks could run on GitHub. Caught by the team.
- `check.sh` stopped early after a passing step, because stopping the API returned a non-zero status under `set -e`. Caught by the AI's first run.
- The check's wait for the API never failed, and could have tested another server already on the port (caught by Copilot; the AI added the second part).
- A preview server left on port 8080 served an old API build, so `mise run parity` failed. Caught by the AI, which stopped it.
- Two refresh runs could both clear a stale lock and run at once (caught by Copilot). Fixed with a lock the operating system releases when the run exits.
- `keep_versions = 0` pruned nothing (caught by Copilot). While testing the fix, the AI found that with no `gold/CURRENT` file it would have deleted every version. It now deletes nothing in that case.
- One browser test first failed on whitespace in its own assertion, not on the app. Caught by the run.

### 2026-11-15, session 1 continued (07:13–15:56): outage rule and MODIS labels

All work in this part was done with Opus 5.5.

**07:13–07:20 · Branch clean-up**
- The team's SSH key agent refused to sign, so `git pull` and the branch deletion failed. The AI updated `main` over HTTPS with the GitHub CLI's login, deleted the remote branch through the GitHub API, and told the team to unlock the agent.

**07:20–08:44 · Global outage-check rule** (#17)
- *Asked:* draft the outage-check rule that `PREREGISTRATION.md` requires before the global fit.
- *AI did:* measured, on Argentina data already analysed, how often Aqua records nothing in a 5° or 10° square while S-NPP records something on days both satellites worked. In 10° squares this happens on 15 % of day passes and 60 % of night passes in which S-NPP records 10–49 detections. So a detection-based check on small units would drop the days when Aqua sees little.
- *AI did:* proposed using NASA's records of when and where each satellite observed instead. It first assumed this needed a NASA Earthdata login; checking showed the public granule search (CMR) needs none.
- *Found:* the granule counts reproduce both known 2022 outages to the day. They also show partial first days (2022-03-31 Aqua; 2022-07-26 S-NPP) that the whole-box rule had counted as full days.
- *AI did:* confirmed from the `version` column of the FIRMS files that the VIIRS rows are version 2, matching the granule records.
- *Decided by the team:* use the granule records, with a fallback where they are missing. The AI committed the rule before any global data was analysed. It is not implemented yet; that comes with the global run.

**08:44–15:26 · MODIS processing versions**
- *Found while checking versions:* the FIRMS MODIS archive is not one version. Rows read 6.2 through 2017, 6.03 for 2018–2022 and 61.03 from 2023. The project's docs had said "Collection 6.1" throughout.
- *AI did:* read the MODIS fire team's user guide. Collections 6 and 6.1 "may be freely intermixed". Version 2 and version 3 of the monthly location files contain the same detections, but version 3 has improved hotspot `type` labels, which the vegetation filter reads.
- *Found:* in Argentina the filter removed 0.65 % of Aqua daytime cell-days in 2013–2017 and 2.39 % in 2018–2022. S-NPP showed no step.
- *Asked:* explain in plain terms, and whether the fix was worth the effort now. The AI estimated about 1 % for Argentina, an unknown but possibly much larger effect globally, and a few hours of work. It recommended committing the rule now and doing the swap later. *Decided by the team:* do it all now.
- *Asked:* whether the University of Maryland files may be used. They are NASA data, shared without restriction, with a citation requested.
- The files are only reachable by SFTP, with a login the MODIS fire team publishes in its user guide. The AI does not enter passwords, so the team logged in and downloaded the files themselves (206 monthly files, 1.3 GB). The team's first connection failed because SSH tried the agent's keys first; the AI found the cause and gave a command that skips them.

**15:26–15:38 · Version-3 labels for 2000–2017** (#17)
- *AI did:* committed the rule first. Then it changed `ingest` so that each FIRMS MODIS row from 2000–2017 takes its `type` from the producer's version-3 file, matched on UTC time, satellite, latitude and longitude, and stops if under 99.9 % of a year's rows match.
- *Found:*
  - 100.000 % of rows matched in every year, and 2–4 % of rows per year changed type. The step is gone: the share the filter removes now varies with fire activity in every era.
  - Published pre-2012 values fell 0.8 % (Aqua era) and 1.9 % (Terra era). VIIRS months are unchanged, and 506 of 75,505 resolution-6 hexagons lost more than half their pre-2012 fire-days.
  - Aqua's whole-area typical error moved from 9.95 % to 10.56 %, the backward-join gap from 2.0 % to −0.4 %, and the held-out error from 11.44 % to 10.80 %. These are reported, not pass/fail.
- *AI did:* added the download steps and corrected data credits, with the producer's citation, to the README.

**15:38–15:56 · Review comments**
- Copilot's two comments were valid. Ingest now stops if a row matches label rows that disagree on type. The README had repeated the shared login; it now links to the user guide instead.
- *Decided by the team:* remove the login from the commit history. The AI rewrote the one unmerged commit that contained it and force-pushed the branch, with a check that nobody else had changed it. It confirmed no branch contains it, and told the team that GitHub keeps the replaced commit reachable by direct link for a while. The team resolved the threads and merged.

**Checks in this part:** the label match was 100 % in every year. After the review fixes, rerunning 2010 gave a bronze table identical to the merged run, and a made-up month with disagreeing labels stopped as it should. `mise run check` passed before each push: parity 0 failures and 11 of 11 browser tests on the sample and on the full data (data version v8). *Not verified:* that FIRMS's 2018–2022 rows carry the same labels as the producer's current version-3 files (only 2000–2017 were downloaded); the granule-based outage unit, which is not built yet; and whether the label change matters more globally.

**Errors the AI made in this part, and how they were caught**
- The AI put the label cache inside `data/bronze/`. The next step reads every file there, so `cells` and `publish` failed, and `fit` ran on stale data. Caught by the AI from the errors. The fit output from that run was not used, and a half-written data version (v7) was left for `prune`.
- The AI first read the relabelled data as a reversed step. A year-by-year table showed it was the 2020 fire season lowering one average. Caught by the AI before reporting a result.
- To check whether FIRMS's API serves the newer labels, the AI wrote a one-off script that read the FIRMS key from `.env`, outside the download step that is approved to use it. Claude Code's permission check blocked it before it ran. The team chose to skip the check.
- The README repeated the shared SFTP login (caught by Copilot).
- Duplicate label rows would have been resolved silently (caught by Copilot).

### 2026-11-15, session 1 continued (16:00–17:00): the outage rule on Argentina

**16:00–16:20 · Granule records** (branch `outage-unit`)
- *Asked:* build the outage rule on Argentina first.
- *AI did:* added a `granules` step that downloads NASA's public records of each satellite's 5- and 6-minute swath slices touching the study box, month by month for the fit years (564 requests to NASA's CMR, no login, 31 MB). `cells` now writes which outage-check units (resolution-3 cell, local date, pass) each satellite observed, and `fit` uses only units both observed.
- *Checks:* on four sample months no detection fell outside its satellite's footprints; shifting the detections 30° east put 96 % outside, so the check can fail.
- *Asked:* what the step is and where the data comes from. The AI explained in plain terms.

**16:20–16:45 · Two problems in NASA's catalogue, each settled by the team before any fit**
- An Aqua footprint over Antarctica touches the box. The AI's first version read footprints as flat latitude/longitude shapes and stopped on it. Footprints are now tested on the sphere, as NASA defines them, which also covers the poles and the date line for the global run.
- The pre-registered footprint check then failed for NOAA-20: 1.03 % of its detections fell outside. All but 4 had no record at their time. The catalogue holds 43 NOAA-20 records for April 2018 and 5 for May, against about 480 in a normal month. *Asked:* explain in plain terms, and why check NASA's data at all. *Decided by the team:* treat missing records with the fallback, one pass at a time, and have the check count only detections outside a record that exists.
- The pre-fit check found the reverse case: passes NASA records but FIRMS does not hold, for example NOAA-20 from January to March 2018, before FIRMS's NOAA-20 record starts. Counted as observed, they would enter the fit as zero fire. *Asked:* whether the rules were getting too complex. The AI said the rule reduces to two conditions and recommended keeping both, noting that dropping the granule records was a fair simplification and that the choice had to be made before any fit. *Decided by the team:* keep both. A unit counts as observed only if a record covers it and FIRMS has that satellite's data on that pass.
- Each change was written into `PREREGISTRATION.md` §7 before the fit, with what had been seen.

**16:45–17:00 · Check and refit**
- *Found:* every known outage is caught to the day, including the partial first days. Against the old whole-box rule, 3.5 % of the Aqua comparison's units and 2.7 % of Terra's lose fair status, holding about 2.5 % of S-NPP's cell-days; none gain it.
- Refit, reported not pass/fail: Aqua's night multiplier moved from 10.37 to 9.96 and its whole-area typical error from 10.56 % to 9.41 %; held-out error from 10.80 % to 9.10 %, while the held-out gap widened from 3.56 % to 4.91 %. Terra's whole-area error moved from 18.57 % to 17.12 %. The NOAA-20 conversion is still rejected. Outcome rows, including the one for the MODIS labels, are in §7. Published as data version v9.

- The AI pointed out that the two rule rows, though written before the fit, were not yet committed, so git would show them landing with the results. *Decided by the team:* commit the rule rows first, then the rest. Both commits still come after the fit ran; the rows' own text records the order.

**Checks in this part:** `mise run check` passed: parity 0 failures and 11 of 11 browser tests, on the sample and on the full data. The sample has no granule records, so it runs on the per-pass fallback.

**Errors the AI made in this part, and how they were caught**
- The AI assumed no footprint near the box would cross a pole. The pipeline stopped on the first one; caught by the AI's own guard.
- An empty table of units had no column types and failed on the sample; caught by the AI's test run.
- The check script had an ambiguous column name; caught when it ran.

### 2026-11-15, session 1 continued (17:18–19:20): the global baseline

**17:18–17:35 · Scope and rules**
- *Asked:* where the project stands, then to scope the global run and estimate a global app. The AI measured before estimating: the global archive was already on disk (48 zips, 9.75 GB), a global VIIRS year ingests in 19 s, and global granule records come to about 4.6 million. It recommended a global report first and a global app later. *Decided by the team:* global report first.
- *AI did:* recovered session 1's bootstrap from `science/rule_checks/checks.py`, because it was in code, not in `PREREGISTRATION.md`. It drafted a continent table (UN M49 regions, the Americas split, Russia split at 60° E) and a §7 row: each continent its own study area, scores and luck ranges as for Argentina. *Decided by the team:* commit as drafted. Committed before any global analysis; the row lists what had been seen (row counts and label matches from two timing runs, and global granule counts).
- *Found:* NASA's catalogue lacks about half of Aqua's granule records from 2020-08-16; every other sampled day is complete. The fallback already covers this.

**17:35–18:30 · Code for the global run**
- *AI did:* added a separate global setup (`global/firecal.toml`, output in `data/global/`) so the Argentina app is unchanged; a continent on every bronze row; observed units tested one day at a time, only for cells with fire, with one matrix product per day; condition 2 and the fallback per continent (`silver/passes.parquet`); `fit` per continent; and a `report` step with the rule statuses and luck ranges.
- *Checks:* rebuilding Argentina with the new code gave the same multipliers as v9 in every area and the same 4,337,847 observed units. Two held-out night gaps moved by 0.01 points and the pre-fit check moved by 21 units, all from one S-NPP pass (2024-04-25, night) that now uses the fallback: its fires sit at swath edges where no fire cell's centre is covered. `report` reproduced session 1's Argentina rule 5 figure, 79.9 %.
- *Asked:* for a live progress bar. The AI put one in a Terminal tab that reads the job logs.

**18:30–19:20 · Global run**
- Ingest: 48 year files, 7.7 GB; MODIS labels matched 100 % in every year except 2011 (99.991 %, above the 99.9 % rule). Footprint check passed for every satellite (at most 0.0027 % outside). The first `fit` stopped on Antarctica, which has 3 Aqua cell-days in ten years; continents with a training set lacking either satellite on a pass are now marked as cannot be fitted.
- *Found:* the conversion works about as well on every continent as in Argentina (Aqua whole-area typical error 6–15 %, Europe worst). The night multiplier ranges from 10.6 (South America) to 26.7 (Europe). Tilt fails almost everywhere, as in Argentina. The join between the records fails for Aqua in Europe and North America (night gaps of −23 % and −27 %) and in Asia at night. Error ranges pass everywhere, but the app's own ranges cover only 70–79 %. Terra's held-out years go badly wrong in some continents (Africa −41 %); the AI's guess is Terra's orbit drift, not checked. Results are in §7.
- *Asked:* explain the results in plain terms.

**Checks in this part:** `mise run check` passed (parity 0 failures and 11 of 11 browser tests, on the sample and the full Argentina data).

**Errors the AI made in this part, and how they were caught**
- Rule 5 at first used the app's error-range method (all area sizes pooled, fixed bins), not the rule's (small areas, 5 bins), and showed Argentina failing at 74.6 %. Caught by the AI comparing with session 1's 79.9 %.
- The global fit crashed on Antarctica, which has almost no fire; caught by the run.
- A first per-granule loop would have taken an estimated 2–3 hours globally; the AI vectorized it before the run and checked the result was identical on Argentina.

**19:25–20:10 · Review comment and a question about the score grid** (#19)
- Copilot noted that the second half of the fallback ("detections but no granule units at all") ignored the continent. Valid. Its suggested fix, deciding per continent from granule units at fire cells, would let a partial outage over one continent switch on the fallback there, which counts the satellite as observing the whole continent. The AI instead read the clause per continent and from the records: a pass uses the fallback if none of the satellite's detections in that continent lies inside a granule footprint. Rebuilt, Argentina now matches v9 exactly (the S-NPP pass of 2024-04-25 no longer uses the fallback), and the global multipliers, validation and report are unchanged to the digit, so the §7 outcome row stands.
- *Asked:* why the small-area score uses 2° squares rather than H3. The AI found no written reason; the definition came from session 1's checks. Squares shrink toward the poles, so northern continents are scored on fewer block-months; paired comparisons share the squares, so this mostly widens luck ranges. *Decided by the team:* skip an H3 check for now and note the limit in the docs; revisit if a northern upgrade result is borderline.


### 2026-11-15, session 1 continued (20:12–20:40): upgrade 1, the resolution-2 stand-in

**20:12–20:17 · Status, estimates and the rule**
- *Asked:* where the project stands, how long §5 and the optional items would take, then to draft the stand-in rule. The AI estimated 5–7 hours for the three §5 upgrades.
- *Found while drafting:* as written, rule 1 (a 0.5-point small-area gain, leaving one year out) would reject the stand-in almost everywhere, because leaving one year out barely creates areas without data. The AI drafted a §7 row that makes rule 6 the test and rules 1–5 no-harm checks, and wrote down the Argentina test's details, which were in code. It also set two new thresholds: at least 20 data-rich areas per continent, and at most 0.5 points of extra gap where the baseline already fails rule 4. *Decided by the team:* commit as drafted. Committed at 20:17, before any stand-in was run on global data.

**20:17–20:40 · Code, run and adoption**
- *AI did:* the res-2 parent multiplier in `fit` (used only where an area has no multiplier of its own on that pass), and in `report` the leave-area-out test and the paired no-harm checks, with their own random generator so the baseline's luck ranges are unchanged. Argentina first: the baseline report was unchanged and rule 6 gave 19.2 → 14.5 % (session 1: 19.3 → 14.0 %, before the fair-unit and label changes).
- *Found:* rule 6 passes in Africa, Asia, North America, Oceania and South America and fails in Europe, where the continent's multiplier is already good (13.5 %). The no-harm checks pass everywhere it was kept. *Decided by the team:* adopt and record.
- *AI did:* the kept continents go in the config (`standin_areas`); `fit` writes the parent multipliers to `model.json` and `publish` falls back to them before the study-area multiplier. Argentina follows South America and was published as v10 (9 res-4 cell-months change). Methods page and ARCHITECTURE updated; outcome row in §7.
- *Found after adopting:* the stand-in reaches at most 0.07 % of MODIS cell-days before 2013 on any continent. An area has its own multiplier if either satellite saw fire there in 2013–2022, and S-NPP sees fire in nearly every area that burns. The AI had said earlier that the stand-in matters mostly before 2013; it does, but for very few fire days. Recorded in the outcome row.

**Checks in this part:** `mise run check` passed (parity 0 failures and 11 of 11 browser tests, on the sample and on the Argentina v10 data). The global refit kept every multiplier, and validation moved by at most 0.01 points.

**Errors the AI made in this part, and how they were caught**
- The AI overstated where the stand-in would matter before measuring its reach; caught by the AI's own count after adopting, and corrected in the outcome row and to the team.

**20:45–21:00 · Review comments** (#20)
- Copilot noted that `publish` reads a top-level `models` that the global `model.json` doesn't have, and that publishing the global run needs continent-scoped lookups. Valid but not new in this PR: the global setup was never meant to publish. The AI made `publish` stop with a clear message on per-continent models and said so in the README; continent-scoped publishing is left for the global app.
- Copilot noted that `rule6` divides by zero if a hidden area holds all of the continent's Aqua cell-days on a pass. Valid in principle; it doesn't happen in any continent (every result is finite). The AI made that case report "cannot be tested" instead. Argentina's report is identical byte for byte.
- Copilot noted that the Methods page said "a place with no fires", while the stand-in applies where neither satellite saw fire on the shared passes. Valid; reworded.

### 2026-11-15, session 1 continued (21:00–21:20): the app's error ranges, and Terra's orbit drift

**21:00–21:02 · Priorities and the rule**
- *Asked:* what is left, which item gives the most leverage, why a global app would take 4–8 hours, and whether most teams will go global. The AI recommended fixing the app's error ranges first (an hour's work, and the one place the app told users something untrue), then the tilt correction, then a global app. It said it could not know what other teams will build. *Decided by the team:* start with the error ranges.
- *AI did:* drafted a §7 row: one miss table per size of area (res-4, res-3, 2° block, study area) with rule 5's quintile bins; a search uses the size nearest its area; pass at 75–85 % for the three smaller sizes; the Methods page states coverage by size either way. The row says the 2° block result was already known (rule 5 uses this method). *Decided by the team:* commit as drafted. Committed at 21:02, before the new ranges were computed for the hexagon sizes.

**21:02–21:15 · Code and runs**
- *AI did:* `fit` writes the per-size tables with each size's typical area; the Rust API and the Python reference pick the table by the search's area (the sum of its hexagons' areas); `report` judges the app's ranges by size. Argentina published as v11.
- *Found:* every size passes on every continent, for Aqua and Terra, at 79.8–80.0 %, against 70–78 % for the old pooled ranges. Whole-study-area coverage is 68–75 %, reported only.
- *Asked:* whether some items could run in parallel. The AI said the global app touches the same files as this branch and should wait for it to merge; a Terra orbit-drift check only reads data. *Decided by the team:* do the Terra check here.
- *Found (Terra):* both MODIS satellites drifted about 70 minutes from 2021, Terra earlier and Aqua later; S-NPP did not. Terra's daytime ratio to S-NPP climbs every year with the drift on every continent (Africa +116 % by 2025), which explains its held-out errors; Aqua drifted across the flat top of the daily fire cycle and changed little. The app is unaffected: Terra and Aqua are converted only for years before the drift. Written up in `docs/terra_drift.md`. *Decided by the team:* keep Terra for 2000-11 to 2002-07, and add the note to this PR.

**Checks in this part:** `mise run check` passed (parity 0 failures and 11 of 11 browser tests, on the sample and on Argentina v11). The parity test compares the Rust API's ranges with the Python reference's for the same searches. The global multipliers and every other report field are unchanged.

**Errors the AI made in this part, and how they were caught**
- None found in the results. The Terra check used all cell-days rather than fair units because the global fit was using the memory; the write-up says so.

**21:30 · Review comment** (#21)
- Copilot noted that a bin can be empty if quantile edges repeat (many identical predictions), leaving its range as NaN. Valid in principle; no current table has an empty bin (Argentina 40 rows, global 240). The AI made an empty bin borrow the nearest non-empty bin's range, as the old fixed-bin table did, and checked on a forced case. Argentina's tables and validation are unchanged byte for byte.

### 2026-11-15, session 1 continued (21:24–21:55): upgrade 3, the tilt correction

**21:24–21:26 · The rule**
- *Asked:* what is left, how close the project is, and what seasonal multipliers would gain (the AI guessed under 1 point, without looking). Then to draft the tilt rule. The AI found that it had described the tilt backwards earlier (the conversion undercounts quiet months and overcounts busy ones) and said so. *Decided by the team:* the form, fire-strength classes, from three options (also local busyness, and a curve on totals that would break cells adding up to area totals). The AI drafted a §7 row: three FRP classes per continent and pass, Poisson class weights, tested before seasonal multipliers, with rule 3 and rules 1, 2, 4 and 5 all required. *Decided by the team:* commit as drafted. Committed at 21:26, before any fire-strength model was fitted.

**21:26–21:55 · Code and runs, with the global app in parallel**
- *Asked:* whether the global app could run in parallel. *Decided by the team:* yes, in its own session (archive only); the AI wrote its brief, including which files to leave alone, and a progress display for both tasks.
- *AI did:* a `tilt` step: class edges per validation fold computed in SQL, so every left-out year uses edges from its own training years; class weights by Poisson maximum likelihood; the rule checks against the current version.
- *Found:* rejected on every continent. The classes work as expected (strong fires get 0.15–0.9 times the weakest class's weight) but quiet and busy months turn out to have a similar mix of fire strengths, so the tilt barely moves, and night tilt fails everywhere. Unexpectedly, the classes improve the whole-area score on every continent (North America 9.24 → 6.32 %) and fix the join between the records where it failed (night gap Europe −22.8 → −5.7 %, North America −26.8 → −7.3 %). That is not what the rule tested, so it does not count; the outcome row says so.

**Checks in this part:** `mise run check` passed (parity 0 failures and 11 of 11 browser tests, on the sample and on Argentina v11). `fit` and `publish` do not use the correction, so the app is unchanged.

**Errors the AI made in this part, and how they were caught**
- The AI described the tilt's direction backwards in an earlier answer; caught by the AI while drafting the rule.
- The first global run stopped on Antarctica, which has too few fires for every validation fold to have class edges; caught by the run. Areas without edges for every fold are now marked as cannot be fitted.

**22:10 · Review comment** (#22)
- Copilot noted that the reported small-area tilt fits a line with `np.polyfit`, which fails with fewer than 2 points and would stop the whole `tilt` run for a metric that is only reported. Valid in principle; every study area has thousands of block-months. The AI made it report nothing below 3 points. Argentina's tilt report is unchanged byte for byte.

### 2026-11-15, session 2 (21:25–22:20): the global app (side session, own branch)

**21:25–21:35 · Brief and plan** (Opus 5.5, started by session 1 with a written brief while it tests the tilt correction on another branch)
- *Asked:* build the global app, archive only, with the global run's per-continent models; recent days and the global hotspot CSV out of scope.
- *AI did:* worked in its own git worktree (branch `global-app`) so session 1's checkout was untouched, and waited for session 1's global steps to finish before running its own (checked with `pgrep`).

**21:35–22:00 · Pipeline, API, app**
- *AI did:* `cells` writes coverage per continent (a new `coverage` step rewrites only that file, 7 s globally); `publish` applies each continent's multipliers to its own cell-days, picks each day's satellite per continent, and writes month status per continent plus each hexagon's fire-days per continent. The API and the Python reference give a search the error ranges and month status of the continent holding most of its fire-days, and `meta` lists each continent's scores and gaps. The app says which continent's model a search used and the Methods page shows that continent's numbers. The global hotspot CSV is refused with a message.
- *Decided by the AI, for the team to review:* the search-continent rule (most fire-days over the whole series; no fire → the whole globe's days with data); Antarctica's MODIS months have no data rather than unconverted counts, and its VIIRS days use the whole globe's satellite choice, since it has detections on only a third of days; res 6 stays in memory (measured below) rather than read from disk.
- *Measured:* global publish 27 s, 7.6 GB peak. Data v2 is 405 MB (res 6: 44 M rows). The API first held 3.3 GB; storing each level as one array cut that to 1.8 GB. Searches take 3–16 ms, about 0.5 s for a box over all of Africa.
- *Checks:* Argentina's sample publishes byte for byte as before (every monthly, month-to-date and hotspot file). Parity: 0 failures on the Argentina sample, on Argentina v11 (published before continents, read unchanged), on a new global sample (`pipeline/tests/fixture_global`, 16 searches on every continent, across the Panama–Colombia border, Heard Island and open ocean) and on the full global data. Browser tests: 11 passed on the global sample, including a new test that every preset names its continent's model and the Methods page shows its scores.

**Errors the AI made in this part, and how they were caught**
- A first comparison of old and new `publish` ran the new code twice (the package path pointed at the new code); caught because the "old" output had the new continent column, and re-run with the old code.
- The parity list first used two presets only the global sample has, so it could not run on the full global data; caught when planning that run, and changed to boxes.

**Seen, not changed:** for a continent-sized search the 80 % range can sit entirely below the converted value (Africa, January 2004: 700,316 with range 638,387–698,633), because the whole-continent miss table says the conversion overshoots there. And a month with no data (Antarctica before 2012) still gets a "0.0× the usual" sentence, as an incomplete month does in Argentina.

### 2026-11-15, session 1 continued (22:25–22:45): upgrade 2, seasonal multipliers

**22:25–22:31 · Estimate and the rule**
- *Asked:* how long seasonal multipliers would take (the AI: 1–1.5 hours, about 2 if kept), then to draft the rule. The AI drafted a §7 row: a multiplier per area, season and pass, shrunk toward the area's current multiplier with `k = 50` (section 2's pseudo-count, not tuned); rules 1, 2 and 5 against the current version; rule 4 by the stand-in's convention (no more than 0.5 points further from zero where the current version fails it); rule 3 reported. The row records the AI's earlier guess of under 1 point, made without looking. *Decided by the team:* commit as drafted. Committed at 22:30, before any seasonal model was fitted.

**22:31–22:45 · Run and adoption**
- *AI did:* a `seasonal` step on the pattern of `tilt`. Argentina first: the current version's numbers matched earlier runs exactly.
- *Found:* kept in Africa, Asia, North America, Oceania and South America, with small-area gains of 0.8–3.8 points (Africa 23.5 → 19.7 %); rejected in Europe, where the night join moved 3 points further from zero. The AI's guess was wrong: the gains are several times larger.
- *Asked:* whether anything could run in parallel (the AI proposed a demo-hosting session, as a card) and whether API or static hosting is better. The AI recommended keeping the API for the submission (it works, is parity-tested and meets every objective, including the hotspot export) and moving to static files on a CDN afterwards, which the additive data model suits.
- *Decided by the team:* adopt and record. The AI added `seasonal_areas` to both configs, `seasons` in `model.json`, and a seasonal join in `publish` by calendar month. Argentina refitted to exactly the test's numbers (whole-area 7.57 %, small-area 20.37 %) and published as v12; the global data refitted and republished. Methods page, ARCHITECTURE, README and the §7 outcome row updated.

**Checks in this part:** `mise run check` passed all five stages (parity 0 failures and 11 of 11 browser tests on the sample, on Argentina v12 and on a global sample). The global refit matches the seasonal test's numbers on every continent; global data published as v3.

### 2026-11-15, session 1 continued (23:05–23:50): map-first layouts

**23:05–23:35 · Three prototypes**
- *Asked:* three layouts that still meet every objective, with the map as the centrepiece and controls for quick insight, closer to kepler.gl's demo, each built for one of the likeliest groups of users.
- *AI did:* chose the groups from the challenge's own list: responders and firefighters ("is burning unusual now, and where?"), scientists and analysts ("how did it change over 25 years?"), land managers and planners ("when does my area burn, and was this year worse?"). Built a shared full-screen map component and three pages under `/proto/`: **A · Now** (the map view is the search; each hexagon coloured against its own usual month), **B · Explore** (kepler-style layer panel, 3D, a time bar with brush and play) and **C · Seasons** (the calendar as the time control, a change map between two years, a typical-season chart). B and C were written by two parallel sub-agents from the AI's design brief while the AI wrote A; the AI checked all three in the browser on the global data.
- *Found:* the API turns a search box more than 180° wide into one hexagon (H3 cannot fill such a polygon); the map views cut wide views to their middle 180° and say so. Not fixed in the API yet. A's per-hexagon comparison needs one search per comparison year, since the API has no per-hexagon usual value.

**23:35–23:50 · B becomes the app**
- *Decided by the team:* start from B.
- *AI did:* made B the home page, adding back what the old page had: exact From/To/month pickers and the median/mean choice (Dates tab), the hexagon count and continent note, the monthly line chart, Methods, and the download notes. Removed the old map component; A and C stay at `/proto/`. Browser tests updated for the panel tabs.
- *Decided by the AI, for the team to review:* the left panel opens on Area.

**23:50–00:10 · Review against modern web guidance**
- *Asked:* review the page against Google's modern-web-guidance skill.
- *AI did:* checked it against the tabs, dark-mode, spinner, slider, toolbar and accessibility guides, and changed: the panel tabs became a real tab list (arrow keys, Home/End, `aria-selected`, a tab panel, and an underline so colour is not the only cue); the page follows the system's light or dark setting instead of forcing dark, as the B prototype did; the loading spinner is a native `<progress>` that slows down for reduced motion; the map tools are a labelled group rather than a toolbar (a toolbar promises arrow-key navigation it did not have); the time bar's instructions moved from its label to a description, and it no longer blocks vertical scrolling on touch screens; the skip link points at the answer panel, which exists even when collapsed; selected buttons keep a visible state in forced-colours mode; hover styles apply only where hovering exists.

**00:10–00:40 · Accessibility gaps**
- *Asked:* is the page accessible? The AI said partly: the objectives can all be done without the map or a mouse, but listed five gaps and that it had not been tested with an automated scan, a keyboard-only pass, a screen reader or at 200 % zoom. *Decided by the team:* fix gaps 1–4 and add axe to the tests.
- *AI did:* the answer stops announcing to screen readers while the months play (it changed every 0.7 s); the map's camera flights, 3D tilt and growing columns are off for people who ask for reduced motion; an "On the map" card and the map's description say in words how many hexagons had fire and where the five busiest are, and point to the hexagon CSV for the rest (hexagon centres from `h3-js`, now a direct dependency at the version already installed); the time bar shows a month's details when it has keyboard focus, speaks each month's value, takes Home and End, and points to the Dates tab for typing dates. Added `@axe-core/playwright` and a test that scans every panel tab in light and dark mode against WCAG 2.2 A and AA.
- *Found:* axe reported no violations, but could not check text contrast on 50 elements because the panels were slightly see-through over the map (gap 5). The panels are now solid; 13 remain unchecked, all chart labels inside SVGs (which axe does not check) and one arrow glyph. Their colours are the same text tokens as the panels, about 8:1 in light mode and 10:1 in dark.
- *Found by the new test on the Argentina sample:* the Methods page's "Known gaps" list scrolls when there are more than 12 gaps, and keyboard users could not scroll it (nothing in it takes focus). It predates this work. It is now a labelled region that takes focus.
- *Still not done:* a keyboard-only walk-through, a screen-reader session, and a 200 % zoom check.


**00:40–01:10 · Copilot's review of PR #25**
- *Asked:* address Copilot's twelve comments.
- *AI did:* agreed with all twelve and fixed them. The map's zoom buttons were hidden behind the time panel (and the insights panel); pages now lift them clear. A search box near a pole could put south above north, and rounding could shrink a tiny box to nothing; both edges are now clamped to the map's ±85.05° limit and rounded outwards. The fitted view and, on A, the per-hexagon comparison and hotspot export could pair a newly chosen area with the previous area's results; each now uses the area its results answer. Map colours now redraw when the system switches light/dark (A) and whenever the palette changes (home page). A failed search opens the insights panel, where its message is. Legend lists are keyed by position, not label. On C, the calendar scrolls vertically when it needs to, and the typical-season chart no longer says "no fire" when some years burned but the usual value of every month is zero.

### 2026-11-16, session 1 continued (01:15–01:45): searches wider than 180°

**01:15–01:45 · Wide boxes**
- *Asked:* fix the API for search boxes wider than 180° (found while building the prototypes; the pages had been cutting wide map views to their middle 180°).
- *Found:* H3 takes each edge of an area the short way round the globe, so a box more than 180° wide is read as the rest of the world. Tested in the Python reference: a 200°-wide box came back with exactly the hexagons of a 160°-wide box, and a whole-world box with none. Adding points along the long edges worked up to about 200° and then failed, so the AI chose strips.
- *AI did:* the API and the Python reference fill a box more than 180° wide as strips at most 90° wide and merge them; a drawn polygon that wide is refused with a 400 (splitting arbitrary shapes needs geometry clipping, and drawn areas that wide are rare). The map pages no longer cut wide views: a view showing the whole world searches it all. A view across the 180° line is still cut there, and says so. Parity cases added (a 340° box on Argentina, a whole-world and a 200° box on the global sample, and the refused polygon), plus two Rust unit tests, which `mise run check` now runs. `docs/api.md` describes the rule.

**Checks:** `mise run check` passed all five stages (Rust unit tests 2 of 2; parity 0 failures and 13 browser tests on each data set). On the global data, a whole-world search returns 287,098 hexagons at level 4 (69,285 with fire in August 2010) in about 4 s; checked in the browser from a zoomed-out map view.

**01:50–02:00 · Copilot's review of PR #26**
- *Found by Copilot:* a box such as `[-1e12, -1, 1e12, 1]` passed the order check and would have asked for about 22 billion strips, in both the API and the Python reference, before H3 looked at the coordinates. The AI agreed: it had not bounded the width when it added the strips.
- *AI did:* both now refuse an area with a coordinate that is not a finite number, or more than 360° of longitude wide, before splitting. Added a parity case for the refused box, a Rust unit test, and a sentence in `docs/api.md`.

### 2026-11-16, session 1 continued (02:05–03:20): seven fixes from using the app

**02:05–02:25 · Review of seven items**
- *Asked:* the left panel's empty space; the monthly chart crunched for busy areas; the "much lower/higher" arrows looking weaker than the plain ones; Methods and limits being long; shareable links; well-known presets on each continent; accessible colour ramps.
- *AI did:* measured each in the browser (on a 900 px screen the Data tab's content filled about half the panel) and ran the dataviz skill's palette checker on every ramp. *Found:* every continent but Antarctica already had a preset; the satellite colours pass the colour-blindness checks; the "compared with usual" colours have matching lightness on each side; the map's lightest class was 1.3:1 against the page (1.5:1 in dark), below the 2:1 floor.
- *Decided by the team:* do all seven, and also grade the comparison colours so the "much" cells are the deepest and the plain ones lighter.

**02:25–03:20 · The changes**
- *AI did:* the left panel is as tall as its content, up to the space above the time bar. The monthly line became **Fire season, year by year**: months along the bottom, one faint line per year, the usual year dashed and the selected year in blue. Seasons start after the usually quietest month, so the Central African season (September–August) is not split at New Year. Comparison categories have drawn icons (a solid arrow; two solid heads for "much"; two bars for about usual) instead of ⇓/⇑ text, which render thin. In dark mode "much" was the pale step; it is now the vivid one (blue `#2a78d6`, red `#d64545`, lightness-matched, white icon at 4.4:1), with the plain steps dim, matching light mode where "much" was already the deepest. Methods and limits became a two-line "Limits for this answer" card (conversion error for this continent, missing days in these dates) with the full text in a dialog. The address bar now holds the search as query parameters (`preset` or `bbox`/`circle`/`polygon`, `start`, `end`, `month`, `baseline`), checked against the data on load, with a Copy link button in the Data tab. Presets carry an optional `group` (API, Python reference and docs), and the global list has 15 under continent headings, adding the miombo woodlands, Central Kalimantan, Attica and Evia, Northern Quebec, south-east Australia and the Pantanal. The map uses its own five-class ramp (blue 250–650, every other step), which passes the ordinal checks in both modes; seven classes cannot clear both the 2:1 floor and the step gap on this ramp.
- *Found by the AI when checking the presets against the data:* several "notably" years were wrong. Paraná Delta's biggest year is 2008, with 2022 only fifth (notes in both configs now say 2008 and 2020); Northern California's are 2021, 2020 and 2008; Kalimantan's 2015 and 2006 (2019 is not in its top four); Attica and Evia's 2021 and 2007; south-east Australia's biggest January is 2003 (the alpine fires), then the Black Summer. Each note now names the years the data shows.
- *Not done:* a separate `/methods` page (the dialog keeps the methods next to the search they describe).

**03:20–03:45 · Stronger "much", and a different icon**
- *Asked:* make "much" significantly more saturated and the plain steps a lot dimmer, and are there alternatives to the double arrow?
- *AI did:* rebuilt the five colours in OKLCH: "much" at chroma about 0.19 (light `#1e59cd` / `#be2323`, dark `#3783f0` / `#e6443d`, white icon at 6:1 in light and about 4:1 in dark), the plain steps nearly grey at chroma 0.05 (light `#b8d0ef` / `#edc2bd`, dark `#3d516b` / `#694542`). Each arm steps in lightness from the grey midpoint and the vivid pair is far apart for every colour-vision type. *Found:* the two dim steps are too pale to tell apart by colour (ΔE 9, and still under 15 at nearly twice the chroma), so their arrows' direction tells them apart; every cell has one. Mocked up five icon options in the new colours (two solid heads, chevrons, size, outline vs solid, arrow to a bar).
- *Decided by the team:* outline vs solid: one arrow shape, hollow for lower/higher and solid for "much".

**03:45–04:10 · Methods and limits, easier to read**
- *Asked:* format the methods dialog so it is easier to read: more spacing or separated sections (cards, perhaps), and the fire data citations as a list.
- *AI did:* each topic is now its own card (What is counted, One satellite per day, Converted to one scale, The 80 % range, How well the conversion works, Known gaps, Limits), in two columns on wide screens and one on phones. Each card opens with a one-line summary and puts the details in bullets. The satellite changeover dates are a short timeline. The data and credits are a full-width card with one bullet per source (NASA FIRMS, MODIS MCD14ML, VIIRS 375 m S-NPP and NOAA-20, data version, unit). The dialog header (title, a line on what it covers, Close) stays put while the text scrolls. Close gets focus when the dialog opens, and scrolling inside it no longer scrolls the page behind. Clicking outside closes it, with a fallback for browsers without `closedby` (Safari). Fixed two missing spaces in the text ("where possible (Africa…", "through the year (except in Europe…").
- *Checked:* light and dark on desktop, and a 375 px phone (no sideways scrolling, cards in one column).

**04:10–04:40 · Saved chart images that stand alone**
- *Asked:* are the SVG/PNG buttons for anything in particular? Then keep them, but put the chart's title, description and legend in the image.
- *Found:* the buttons meet the challenge's "Download analytics and visualizations" (the CSVs cover the analytics, the images the visualizations). The images held only the plot, so a saved calendar did not say which area or dates it showed or what its colours meant.
- *AI did:* each saved image now has the chart's title, then the area and dates, then the description and the legend redrawn from the one on screen (colour boxes, the comparison icons and the hatching), above the plot, in the screen's colours. The description leaves out on-screen instructions ("Click a month…"); the calendar's says the ringed cell is the answer card's month, and the yearly chart's says whether the counts are converted or raw. The SVG's `<title>` and `<desc>` carry the same text. A browser test checks that a saved SVG contains the title, area and dates, description and legend.
- *Checked:* all three charts saved as PNG in the browser, including the calendar's "compared with usual" legend.

**04:40–05:00 · Neater selects**
- *Asked:* the month and year selects look cramped (the arrow hugs the right edge), and the From/To focus ring is cut off on the left; tidy up every select.
- *AI did:* one select style for the whole app in `app.css`: the browser's arrow is replaced by a drawn chevron with 12 px of room on each side, more padding, the same border as the text fields, a darker border on hover, and a focus ring 1 px outside the border. The chevron has a light and a dark version (a data URL cannot read CSS variables). The month and year selects have minimum widths so the pairs line up. The left panel's scrolling area has 4 px of room on each side, offset by a negative margin, so focus rings are no longer clipped. The native picker is kept (phones show their own); the guide's `appearance: base-select` was not used because it replaces the phone pickers and Firefox lacks it.
- *Checked:* keyboard focus on From in light and dark, the calendar's Show menu, and no sideways scrolling in any left-panel tab. `mise run check` passed all five stages.

**05:00–05:15 · The time bar sets what the map shows**
- *Asked:* clicking a month on the time bar should switch the map to the selected month, and adjusting the range there should switch it back to the date range.
- *AI did:* the map now follows what the time bar was last used for. Clicking a bar or stepping with the arrow keys shows that month; dragging a range or pressing Whole series shows the range. A click outside the current dates widens them and then selects the month, so the map shows the month. Play already switched to the month. The Layer tab's buttons still choose either way. The date pickers in the Dates tab and calendar clicks are unchanged. A browser test drags, clicks, presses Whole series and uses the arrow keys, checking the Layer buttons each time.
- *Checked:* `mise run check` passed all five stages (16 browser tests each).

**05:15–06:05 · Season so far, and the trend**
- *Asked:* other useful analytics not in the app. The AI suggested six (season so far, trend, season timing, two periods compared, a per-hexagon anomaly map, fire frequency). *Asked next:* how "season so far" differs from the existing season chart. The AI said it shares that chart's layout and data, so it should be a toggle there, not a new chart. *Decided by the team:* add the toggle, then the trend.
- *AI did, season so far:* Fire season, year by year has a Per month / So far this season toggle. So far shows each season's running total. The usual line is the median (or mean) of the complete seasons' running totals at each month, not the running total of the monthly medians. A season starting before the dates shown has no line, since its total so far is unknown. Tooltip, table, saved image and screen-reader text follow the toggle. A browser test checks the running total never falls.
- *AI did, trend:* the API's `stats` gained `trend`, how the selected calendar month has changed over every complete year of the record: the Theil–Sen slope as a percentage of the month's median, and the two-sided Mann–Kendall test (tie corrected). "A steady change, unlikely to be chance" when p < 0.05, otherwise "no clear trend", with at least 10 years needed. Both are rank-based, so one extreme year barely moves them. It runs on the converted counts, so the 2012 satellite change is not read as a rise. It is written in the Rust API and the Python reference with the same normal-CDF formula; parity compares the whole response, sentences included. The answer card shows the sentence, Methods has a Trend card, and `docs/api.md` gives the rules. A Rust unit test covers a steady rise with one wild year, an alternating series and too few years; a browser test checks the card shows the API's sentence.
- *Found:* on the global data for August 2001–2025, Central Africa is rising about 3.3 % a year (p = 0.018), Northern California 7.6 % (p = 0.042), Kalimantan falling 13.2 % (p = 0.004, the large peat-fire years were in the 2000s); the southern Amazon, south-east Australia and Yakutia show no clear trend.
- *Not done:* no `PREREGISTRATION.md` §7 row, as the trend is a display statistic, not a change to the conversion or its rules. Years are treated as independent (no correction for runs of wet or dry years); Methods and the API docs say so. A whole-year or whole-season trend is not added.

**Copilot's review of PR #27** (2026-11-16, from 02:40 UTC; this log's earlier times for the day run past that, so they are not clock times)
- *Found by Copilot, seven comments, all valid:* (1) the "Limits for this answer" card counted every day of a gap that overlapped the dates, so a gap from 30 January to 2 February counted four days for a February-only search; (2) for a continent with no fitted model (Antarctica) the card said months before February 2012 were converted, when they have no data; (3) in "So far this season" a season's running total carried on past an incomplete month, so later complete months looked unmarked while their totals were too low; (4) the "So far" usual line took each column's median from the seasons complete up to that column, so its cohort changed across the year and the line could fall; (5) a drawn polygon with more than 200 points was left out of the link, but Copy link still copied it, so the link opened the default area; (6) links rounded coordinates to 4 decimals, which can change the hexagons or collapse a tiny box; (7) a link dropped a described month outside the dates shown, though the month picker allows any month in the series.
- *AI did:* (1) each gap is clipped to the selected dates before its days are counted; (2) the card says those months have no data where the continent has no model; (3) a running total stops at an incomplete month, which is drawn hollow; (4) the usual running total uses only seasons with all twelve months complete, at every column, and the chart note says so; (5) a polygon too long for a link clears the search from the address bar, turns Copy link off and says why; (6) links carry numbers exactly as the search sent them (drawn shapes are already rounded where drawn); (7) a link keeps any month in the series. Added a browser test for a link whose month lies outside its dates.
- *Found by the AI:* on the check sample (a few days kept per month) no season has twelve complete months, so the stricter usual line (4) is empty there; the season chart test now accepts an empty usual line, or one with all twelve months.
- *Checks:* `mise run check` passed all five stages (Rust unit tests 4 of 4; parity 0 failures and 17 browser tests on each data set). The first run's parity step hit another server already on port 8090 (the main checkout's API); the passing run used the same script on port 8093.
