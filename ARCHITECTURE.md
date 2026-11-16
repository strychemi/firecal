# firecal architecture

**Challenge:** NASA Space Apps 2026, *Harmonization of MODIS and VIIRS Hot Spots*.
**Shape:** offline Python + DuckDB pipeline → versioned Parquet → Rust (axum) API → SvelteKit static frontend.
**Status:** prototype for Argentina, 2026-11-15. The method is tested in `science/rule_checks/` with its keep/reject rules fixed in `PREREGISTRATION.md`; the pipeline (`pipeline/`), API (`api/`) and app (`web/`) run end to end, for Argentina and for the whole globe, including recent days from the FIRMS API and the in-progress month comparison. The rest of this document is the design for the global version.

## 1. Challenge objectives → where they are met

| The challenge asks for | Component | How |
|---|---|---|
| Harmonize MODIS and VIIRS so the sensor of origin no longer matters | Pipeline: `fit`, `publish` | Count burning cell-days (H3 res 8, local solar date, day/night). Convert MODIS to VIIRS-equivalent counts with per-area day/night multipliers fitted on 2013–2022. Validate by leaving one year out. Judge every change by `PREREGISTRATION.md`. |
| Consistent series from the early 2000s to the present | Pipeline, recent-data job | Terra from 2000-11, Aqua from 2002-08, S-NPP as observed from 2012-02, then NOAA-20 after S-NPP's last day. One satellite per day, never summed. Recent months from the FIRMS API. |
| Web app taking harmonized data as input | API + frontend | The app reads only the published `gold/` data. |
| Select a region and a date range | Frontend map and form → `POST /api/query` | Draw a box or polygon, or enter latitude/longitude (box, or point and radius). Date-range picker. |
| Burning calendar: busier months, busier years, current fire vs previous | Frontend calendar and stats card | Years × months heatmap; answer card comparing the selected month with the same month in earlier years. |
| Current month against the historical median | `mtd_res{4,5,6}.parquet` + stats | A month still in progress is compared like for like (days 1–D against days 1–D of earlier years). |
| Download analytics and visualizations | Frontend downloads, chart export | Monthly series and per-hexagon values as CSV, built in the browser from the query response; charts as PNG/SVG with their title, area and dates, description and legend. |
| CSV of hotspots detected during a search | `POST /api/export.csv` | Filtered hotspot rows for the area and months; a search over the row cap is refused with its row count. |
| Colour ramps showing similarities and differences across months | Frontend | Sequential ramp for counts, diverging ramp for anomalies, both colour-blind safe, with values on hover. |

**Potential considerations**

| Consideration | Design |
|---|---|
| Audience: emergency responders, scientists, land managers, firefighters | Answer card first ("2.4× the usual October, 3rd highest of 26 years"), detail charts below, methods page for scientists |
| Draw an area or enter latitude/longitude | Both, in one area input |
| Accessible colour ramps | Validated palettes; colour never carries meaning alone |
| Anomalies against multi-year averages | Toggle between mean (as the challenge words it) and median (steadier against extreme years); median by default, always labelled |
| Number of fires detected | Each satellite's raw hotspot count shown beside the harmonized calendar |

**Hotspots vs burning cell-days.** The challenge speaks of "number of hotspots". We harmonize VIIRS-equivalent burning cell-days instead, because a raw hotspot count mostly reflects pixel size: VIIRS reports about 5× as many hotspots as Aqua for the same fires. The app shows the harmonized calendar as the main view, labelled "fire-days", and each satellite's raw hotspot count as "fires detected", and explains the difference in one line.

## 2. System overview

```
OFFLINE  (Python + DuckDB; run on demand)
──────────────────────────────────────────
FIRMS zips ──▶ ingest ──▶ cell-days ──▶ fit + validate ──▶ publish
               bronze/    silver/        model/              gold/vN/

SCHEDULED  (daily; the only process that holds the FIRMS key. Prototype: run by hand)
──────────────────────────────────────────────────────────────
FIRMS API ──▶ recent cell-days ──▶ republish recent months ──▶ gold/vN+1/

ONLINE
──────
Rust API (axum) ── reads the version named in gold/CURRENT ── swaps when it changes
     │  small JSON, streamed CSV
     ▼
SvelteKit static build (served by the same Rust binary) ── MapLibre map + charts
```

**Rules that hold across the system**

- **Python writes `gold/`; Rust only reads it.** The folder layout and schemas in section 4 are the contract.
- **The model is applied once, in `publish`.** The API never multiplies by a ratio, so the app cannot disagree with the validation.
- **Statistics are computed after summing an area.** The median of an area's totals is not the sum of per-cell medians.
- **One configuration file** (`firecal.toml`) sets the region, filters, years and model options for every step.
- **The FIRMS key is never in the repo, the API or the browser.** It lives in a git-ignored `.env` read only by the download and recent-data steps.

## 3. Offline pipeline (Python 3.13, DuckDB, `uv`)

| Step | Input | Output | Notes |
|---|---|---|---|
| `download` | FIRMS area API | `firms_api/{product}/{date}.{sp,nrt}.csv` | Days after the yearly zips, one file per UTC day; standard processing where available, near-real-time after. The only step that reads the FIRMS key. Requests run in parallel, paced by the key's transaction count (FIRMS charges about 36 per world-day, limit 5,000 per 10 minutes). The global run fetches the whole world, VIIRS only. |
| `ingest` | FIRMS yearly zips, `firms_api/` | `bronze/{product}/{year}.parquet`, `bronze/{product}/recent.parquet` | One schema for all products. Clipped to the configured box. Idempotent, one year at a time. Near-real-time rows have no FIRMS `type`; a static-cell mask from the archive stands in (`PREREGISTRATION.md` §7). Recent rows have no country: in the global run each takes the continent its res-6 cell (or a coarser parent) had most often in the archive (`bronze/continent_cells.parquet`; §7). |
| `cells` | bronze | `silver/cell_day/…` | Filters (`type = 0`; MODIS confidence ≥ 30; VIIRS nominal/high), local solar date, H3 res 8, day/night. One row per cell, date, satellite and day/night, with hotspot count and FRP. |
| `granules` | NASA CMR granule records (public, no login) | `granules/{sat}/{YYYY-MM}.parquet` | When and where each satellite observed (5- and 6-minute swath slices with footprints and day/night flag), for the fit years. Downloaded once; recent months fetched again. |
| `outages` | bronze, granules | `silver/coverage.parquet`, `silver/observed.parquet` | Written by `cells`. Coverage: which satellite had any detection in the box on each day; `publish` uses it to pick each day's satellite. Observed: which outage-check units (H3 res-3 cell, local solar date, pass) each satellite observed, from granule footprints (`PREREGISTRATION.md` §7, 2026-11-15), with the whole box per pass as the fallback where records are missing. Stops if over 0.1 % of a satellite's detections fall outside its footprints. |
| `fit` | silver | `model/model.json`, `model/validation.json`, `model/misses.parquet` | Fitted and tested only on units both satellites observed. Per-area day/night multipliers with shrinkage; an area with no data uses its res-2 parent's multiplier where the stand-in was kept (`standin_areas` in the config; `PREREGISTRATION.md` §7); leave-one-year-out predictions; rule checks from `PREREGISTRATION.md`. |
| `report` | silver | `model/report.json` | The baseline's rule statuses (rules 3–5) and the luck ranges of its scores, per study area or continent, and the test of each upgrade (rule 6 and no-harm checks for the resolution-2 stand-in), with the year-block bootstrap of `PREREGISTRATION.md` §7. The small-area score uses 2° blocks, which shrink toward the poles, so northern continents are scored on fewer block-months (see `report.py`). |
| `tilt` | silver | `model/tilt_report.json` | The tilt correction by fire strength (`PREREGISTRATION.md` §7, upgrade 3), tested per study area or continent against the current version. Rejected everywhere: kept as a record and for re-runs; `fit` and `publish` do not use it. |
| `seasonal` | silver | `model/seasonal_report.json` | Seasonal multipliers (`PREREGISTRATION.md` §7, upgrade 2), tested per study area or continent against the current version. Kept where listed in `seasonal_areas` (all fitted continents except Europe; Argentina); `fit` writes `seasons` to `model.json` and `publish` applies them by calendar month. |
| `publish` | silver + model | `gold/vN/` | Applies the model, picks one satellite per day with fallbacks, builds the hexagon levels, writes the manifest. |

**Going global.** `global/firecal.toml` runs the same steps over every country, with a continent on every row and each continent fitted as its own study area; granule footprints are tested only for cells with fire, one day at a time. Every step runs on a box from config: Argentina first (minutes), checked against the known numbers, then the globe. Large aggregations stay in DuckDB over Parquet split by year and satellite; nothing loads the full record into pandas.

## 4. Published data (`gold/vN/`)

| File | Contents |
|---|---|
| `monthly_res4.parquet`, `monthly_res5.parquet`, `monthly_res6.parquet` | One row per hexagon per month with any fire, sorted by cell: `cell, year, month, source, value, raw, detections, frp`. `value` is VIIRS-equivalent burning cell-days; `raw` is the source satellite's own count; `detections` is its hotspot count. |
| `mtd_res4.parquet`, `mtd_res5.parquet`, `mtd_res6.parquet` | `cell, year, value` for days 1–D of the in-progress month, in every year. Absent when no month is in progress. |
| `month_status.parquet` | Per month: source, days in the month, days with satellite data, days filled by a fallback satellite. Marks incomplete and in-progress months. |
| `misses.parquet` | 80 % ranges from leave-one-year-out misses `ln(V / V̂)`: one table per size of area (res-4 cell, res-3 cell, 2° block, study area) with its typical area, 5 bins of predicted count each (`PREREGISTRATION.md` §7). |
| `hotspots.parquet` | Filtered hotspot rows with their level 4–6 hexagons and an `in_calendar` flag, for the CSV export. Prototype: one file (161 MB for Argentina); split by year and coarse parent hexagon before going global. |
| `model.json`, `validation.json` | Multipliers and test results, shown on the methods page. |
| `manifest.json` | Data version, coverage dates (including `through`, the last day with data, and `in_progress`), satellites and outages filled, input file checksums, model version. |

`source` is one of `terra_harmonized`, `aqua_harmonized`, `viirs` (S-NPP, or NOAA-20 as its successor).

`continents_res{4,5,6}.parquet` holds each hexagon's fire-days per continent, from which the API picks a search's continent; `month_status.parquet` and `misses.parquet` have a `continent` column (Argentina: `study_area`).

**Sizes** (global data v2): `monthly_res6` 249 MB (44 M rows), `monthly_res5` 110 MB, `monthly_res4` 43 MB. The API holds all three in memory, about 1.8 GB (README, global app).

## 5. Rust API (`api/`)

Crates: `axum`, `tokio`, `duckdb` (bundled), `h3o`, `geo`, `serde`, `tower-http` (compression, static files).

Endpoints in the global design. The prototype exposes only `meta`, `query` and `export.csv`; see the prototype status below and `docs/api.md`.

| Endpoint | Request | Response |
|---|---|---|
| `POST /api/query` | area, metric (`cell_days`, `detections`, `frp`), harmonized or raw, date range, comparison (mean or median) | Monthly series with 80 % ranges, calendar grid, stats card for the selected month |
| `POST /api/map` | area, month, metric | Hexagons with value, multi-year average and difference |
| `POST /api/summary.csv` | area, date range | Monthly series as CSV |
| `POST /api/export.csv` | area, date range | Streamed hotspot rows; capped by area and date span |
| `GET /api/presets` | | Preset regions from `firecal.toml` |
| `GET /api/meta` | | Data version, coverage, satellites, last date, month-in-progress flag |

**Prototype status** (`docs/api.md` is the contract as built): `query`, `meta` and `export.csv` exist. `query` takes area, dates, selected month and mean or median, and returns every metric (converted, raw, hotspots, FRP) for each month rather than taking a metric choice. It also returns per-hexagon values, which the map uses in place of `/api/map`. Presets come with `meta`, and the monthly CSV is built in the browser. The export builds the file in memory; streaming is for the global version.

An **area** is a GeoJSON polygon, a box, or a point and radius.

**How a query runs**

1. Turn the area into hexagons. Use the finest level that keeps it under about 3,000 hexagons (res 6 for a province, res 4 for a continent). Cache the result keyed by a hash of the shape.
2. Sum those hexagons' rows into one monthly series.
3. Compute the stats on that series: same month in earlier years, median or mean, rank, ratio.
4. Build the 80 % range from `misses.parquet`: the table for the size of area nearest the search's area, and the bin of the area's own predicted total.

**Design choices**

- **Stateless.** Every request carries its area; nothing is stored per user, so restarts and extra instances are harmless.
- **Coarse levels in memory, fine levels from disk.** Res 4 and 5 are loaded at start-up. Res 6 and hotspot rows are read through DuckDB from cell-sorted Parquet.
- **Cacheable.** A response depends only on the request and the data version, so the data version is the HTTP cache key (`ETag`). Prototype: not yet implemented, and neither is the per-shape hexagon cache.
- **Version swap.** `gold/CURRENT` names one version. When it changes, the API loads the new version and swaps atomically.

## 6. Frontend (`web/`, SvelteKit with `adapter-static`)

The map fills the window, as in kepler.gl. Panels float over it: on the left, area, dates, layer style and downloads; on the right, the answer, charts and methods; along the bottom, a time bar (the whole series as a histogram coloured by satellite era: drag to set the dates, click to pick the month, play to step through the months). Light or dark follows the system setting. Two other layouts, for responders (`/proto/now`) and land managers (`/proto/seasons`), are kept as prototypes.

| View | Purpose |
|---|---|
| Area input | Map drawing (box, polygon or circle), a latitude/longitude form (box, or point and radius), and presets grouped by continent |
| Answer card | "Is this month unusual?", with the error range and the comparison used, and whether this month has been rising or falling over the record (Theil–Sen slope, Mann–Kendall test, computed by the API) |
| Calendar heatmap | Years × months; sequential ramp for counts, diverging for anomalies ("much" the most intense step, with a drawn icon for each category) |
| Yearly totals | Raw-to-harmonized toggle that removes the 2012 jump (the demo moment) |
| Fire season, year by year | Months along the bottom, one faint line per year, the usual year dashed and the selected year highlighted. Seasons start after the usually quietest month, so a season is not split at New Year. "So far this season" shows each season's running total instead, so a season running ahead or behind sits above or below the usual line (the median of the complete seasons' totals). The full monthly series is in its table and the CSV |
| Map | Hexagons for the selected month against the average. Prototype: fire-days per hexagon for the selected month or the whole date range in five classes, flat or in 3D (height = date-range fire-days) |
| Time bar | The whole series for the area; sets the dates and the month, and plays through the months (one search per month, cached). The map follows its last use: a month clicked or stepped to shows that month, a range dragged or Whole series shows the range. A month clicked in the calendar also shows that month |
| Downloads and links | Monthly CSV, hotspot CSV, per-hexagon CSV (opens in Kepler.gl), PNG/SVG of each chart (with its title, area and dates, description and legend, so the image stands alone). The address bar holds the search (area, dates, month, "usual") as query parameters, so a link reproduces it |
| Methods and limits | Two lines on the limits of this answer (conversion error for its continent, missing days in its dates); the full methods (how the conversion works, test results from `validation.json`, known weaknesses, data credits) in a dialog |

The frontend always reads the API; it has no saved data of its own. Browser tests (`web/e2e`, Playwright) load the built app from a running API and check every number on screen against the API's answer for the same request.

## 7. Operations

- **One container:** the Rust binary serves the API and the built frontend; `gold/` is mounted as a volume.
- **Recent data:** a daily job fetches new FIRMS days with the key from its own environment, then runs `cells` → `publish` for the affected months and updates `gold/CURRENT`. Prototype: `scripts/refresh.sh` (`mise run refresh`), run by hand. It republishes the whole series and keeps the newest three versions. Deployed, the server's scheduler runs the same script daily, with the key in that job's environment only.
- **Snapshots:** a frozen, checksummed copy of `gold/` is used for the submission, so the demo, slides and video show the same numbers.

## 8. Repository layout

```
firecal.toml          configuration for every step
pipeline/             Python package: download, ingest, cells, fit, publish, and the reference API
science/              analysis, rule checks, primer
api/                  Rust crate (axum)
web/                  SvelteKit app; e2e/ holds the browser tests
docs/api.md           API contract
data/                 git-ignored: FIRMS zips, firms_api/, bronze/, silver/, model/, gold/
PREREGISTRATION.md    fixed keep/reject rules
ARCHITECTURE.md       this file
AI_LOG.md             how AI was used
```

## 9. Build order and fallbacks

1. ✅ **Pipeline on Argentina, end to end**, checked against the known numbers (day multiplier about 3.05, night about 10.3, typical error about 10 %).
2. ✅ **API pass 1:** `query` and `meta`, enough for the calendar and answer card. Frontend built against a saved response in parallel.
3. ✅ **Global pipeline run**, with per-continent validation, including recent days.
4. ✅ **API pass 2:** map data (per-hexagon values in `query`). **Pass 3:** the hotspot CSV export (the monthly CSV is built in the browser).
5. ✅ **Recent-data job** (by hand for now) and month-in-progress comparison.

| Risk | Fallback |
|---|---|
| Global run not ready or wrong | Ship Argentina plus showcase regions from the same pipeline |
| Hosting fails during judging | Local run plus the recorded video |
| Hotspot export too slow globally | Cap the area and date span, or limit export to preset regions |

## 10. Known limits

- Pre-2012 values are a conversion that cannot be checked directly; the backward test (fit on later years, predict earlier ones) is the best available evidence.
- The conversion overshoots in busy months and undershoots in quiet ones (the tilt in `PREREGISTRATION.md`, rule 3). The cause is small fires that only VIIRS detects.
- Small areas are noisy; error ranges widen accordingly.
- High latitudes, where satellite passes overlap several times a day, are untested.

## 11. Future improvements

Not built for the submission, in rough order of value.

- **A res-3 level for continent and world searches.** Res 4 is the coarsest level published, and a search uses it however large it is: the whole world is 287,000 hexagons (69,000 with fire), 4 s the first time. Publishing res 3 (about 12,400 km², a config line in `app_resolutions`) and using it only above about 50,000 res-4 hexagons would cut that about sevenfold. At world zoom a res-4 hexagon is smaller than a pixel, so res 3 is also easier to read, and it is the scale the conversion is fitted and scored at. Box totals are unchanged; a drawn polygon's edge shifts slightly. Needs the API rule and Python reference, parity cases and a republish.
- **Global hotspot CSV.** The global archive holds about 580 M detections (MODIS 111 M, S-NPP 297 M, NOAA-20 173 M), a 6–8 GB file, too large to bake into the demo's image, so it is not published; the hosted Argentina app serves the hotspot CSV. To add it: set `hotspot_export = true`, add a range filter on the search's cells so DuckDB skips row groups (the file is sorted by hexagon), and host the file on a disk volume. Or split it by year and by res-2 cell so a search reads only its own pieces, keep the 250,000-row cap, and point larger requests to the FIRMS archive download.
- **Stream the hotspot CSV.** It is built in memory (about 24 MB at the cap); streaming it would bound the server's memory per export.
- **An HTTP `ETag`** from the data version, so browsers and proxies can reuse answers.
- **More analytics** (each about 1–3 hours):
  - Season timing: the date by which half of each season's fire-days had happened, over the years, to show seasons starting earlier or later.
  - Two periods compared, for example 2001–2010 against 2016–2025, as season curves or a difference calendar.
  - Where a month is unusual: each hexagon coloured by its month against its own usual (needs a per-hexagon baseline in the API).
  - Fire frequency: how many years each hexagon burned, separating yearly burning from one-off fires (needs a per-hexagon count in the API).
  - A whole-year or whole-season trend next to the month's.
- **Trend serial correlation.** The trend test treats years as independent; a version that allows for runs of wet or dry years (pre-whitening) would make its "unlikely to be chance" more conservative.
- **Manual accessibility checks:** a screen reader walk-through, keyboard only, and 200 % zoom; the browser tests do not cover them.
