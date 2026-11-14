# AI-use log

The Space Apps rules ask every team to describe how it used AI. This file records what AI tools did in this project, what people decided, and where AI output was wrong and corrected. New entries go at the bottom of the log. Times are UTC.

## Tools

| Tool | Models | Used for |
|---|---|---|
| Claude Code (Claude desktop app, Code tab) | Claude Opus 5.5 (`claude-opus-5-5`), Claude Fable 5.2 (`claude-fable-5-2`) | Method design, data analysis scripts, the explainer page, project documents, git and GitHub operations |

Commits written with AI help carry a `Co-Authored-By: Claude …` line naming the model.

## How we use AI

- **People decide; AI proposes and does the work.** The team chose the challenge, the scientific priorities, the data and the technology stack, and approves every commit, push, pull request and merge. Where a decision was proposed by the AI and accepted, the log says so.
- **Every number comes from code run on our data.** Results quoted in our documents are produced by scripts in this repo, not written from the model's memory.
- **AI mistakes are logged, not hidden.** Each session's entry lists errors the AI made and how they were caught.
- **No secrets shared.** The FIRMS MAP_KEY has not been given to any AI tool.

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
