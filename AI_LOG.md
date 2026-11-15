# AI-use log

The Space Apps rules ask every team to describe how it used AI. This file records what AI tools did in this project, what people decided, and where AI output was wrong and corrected. New entries go at the bottom of the log. Times are UTC.

## Tools

| Tool | Models | Used for |
|---|---|---|
| Claude Code (Claude desktop app, Code tab) | Claude Opus 5.5 (`claude-opus-5-5`), Claude Fable 5.2 (`claude-fable-5-2`) | Method design, data analysis scripts, the explainer page, project documents, the pipeline, API and app code, git and GitHub operations |
| GitHub Copilot pull request reviewer | GitHub's choice | Automatic review comments on pull requests #5–#9; Claude Code fixed the valid ones and replied on each thread |

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

**04:20–04:29 · This log and the architecture** (#10)
- *Asked:* do the important follow-ups in the suggested order, checking in along the way. The AI began preparing a public demo. *Decided by the team:* set the demo aside for later.
- *AI did:* added the build-out entry above, listed the Copilot reviewer as a tool, and corrected the key-handling note. In `ARCHITECTURE.md` it updated file and step names and marked where the prototype differs from the global design.

**04:20–04:29 · NOAA-20 against S-NPP** (#11)
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
