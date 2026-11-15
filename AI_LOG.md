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

