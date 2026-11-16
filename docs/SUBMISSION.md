# Space Apps 2026 submission text (draft)

Paste each section into the matching field on the team's Project page (Edit, then Save Progress often). Submit for Judging before 23:59 local; you can edit and resubmit until then.

## Project name

firecal

## High-level summary

firecal turns 26 years of NASA fire detections from two generations of satellites, MODIS (Terra and Aqua, since 2000) and VIIRS (S-NPP and NOAA-20, since 2012), into one unbroken burning calendar. VIIRS sees about five times as many hotspots as MODIS for the same fires, so raw counts jump in 2012 and a change of instrument is easily mistaken for a change in fire. We count burning cell-days on a hexagon grid instead, convert MODIS to VIIRS-equivalent counts with day and night multipliers fitted only where both satellites observed the same place at the same time, validate on years the model never saw, and judge every method change by rules written down before seeing the results.

A public web app lets anyone draw an area or enter coordinates, pick dates, and get the answer first: how this month compares with the usual (e.g. "9.9× the usual August, 2nd highest of 26 years"), a years × months burning calendar, the month in progress against the same days of past years, the season so far, and a long-term trend test. Numbers, hexagon maps, charts and the hotspots themselves can be downloaded. It runs for the whole globe and for an Argentina study region, from November 2000 through 13 November 2026.

This matters because responders, land managers and scientists need to know whether a fire season is unusual where they work, across the full satellite record, without the switch of satellites misleading them.

Live app: https://firecal-709583608801.us-central1.run.app

## Link to Project Demo

https://github.com/strychemi/firecal/blob/3a19569c0e129595f9301fd1a22e89ee05866f76/docs/firecal-demo.pdf (7-slide PDF)

## Link to Final Project

https://firecal-709583608801.us-central1.run.app

## Detailed Project Description

Live app: https://firecal-709583608801.us-central1.run.app · Code and methods: https://github.com/strychemi/firecal · The first visit may take ~15 s to wake up.

WHAT IT DOES
- Choose an area: draw a box or polygon on the map, type latitude/longitude (a box, or a point and radius), or pick one of 15 preset fire regions. Choose dates from November 2000 through 13 November 2026.
- Answer first: e.g. "August 2020 had 14,280 fire-days, 9.9× the usual August, 2nd highest of 26 years". A month still in progress is compared like for like: days 1 to D against days 1 to D of earlier years.
- Trend: whether the selected month has changed over the record (Theil–Sen slope with a Mann–Kendall test), run on the converted counts so the 2012 satellite change is not read as a rise.
- Burning calendar: a years × months heatmap, the fire season year by year (per month, or the season's running total so far), yearly totals, and each satellite's raw hotspot count beside the harmonized series.
- Anomalies against the multi-year median or mean (a toggle, always labelled), with colour-blind-safe ramps and values on hover. A time bar animates the map month by month; clicking a month on it or in the calendar maps that month.
- Downloads: the monthly series and per-hexagon values as CSV, and charts as PNG/SVG carrying their title, area, dates and legend. Every search can be shared as a link. A CSV of the hotspots detected in a search (up to 250,000 rows) works on the Argentina study region when run locally.

HOW IT WORKS
- A Python + DuckDB pipeline reads the NASA FIRMS yearly archives and recent days from the FIRMS API, and counts burning cell-days on an H3 hexagon grid (local solar date, day and night separately). Counting cell-days instead of hotspots removes most of the pixel-size difference between the sensors.
- One satellite per day, never summed: Terra from November 2000, Aqua from August 2002, S-NPP from February 2012, then NOAA-20.
- MODIS is converted to VIIRS-equivalent counts with day and night multipliers fitted on 2013–2022, using only places and times both satellites actually observed, taken from NASA's granule (swath) records in the Common Metadata Repository. MODIS labels for 2000–2017 come from the producer's version-3 files.
- Validation leaves one year out: fit on nine years, predict the hidden one. Every change to the method is kept or rejected by rules fixed in advance (PREREGISTRATION.md): seasonal multipliers passed and are used everywhere except Europe; a tilt correction was tested and rejected.
- Globally, each continent is fitted and judged as its own study area.

BUILT TO BE FAST AND CHECKED
- A Rust (axum) API serves the published data to a SvelteKit + MapLibre web app. A whole-world search takes about 4 s the first time and about 0.05 s for another month or dates after that; heavy searches share a fixed number of slots so the server stays responsive.
- Every API calculation has an independent Python reference, and a parity test compares their full responses. 17 browser tests run against both data sets. Hosted on Google Cloud Run.

RESULTS
Argentina, on years the model did not see: typical error of the converted monthly count 9.95 % for the whole study area, and 22.2 % for 2° × 2° blocks. Day and night multipliers are about 3.05 and 10.3.

BENEFITS
Emergency responders, land managers, firefighters and scientists can ask "is this fire season unusual, here?" across the full satellite record, without the 2012 jump misleading them, and take the numbers, charts and hotspots away for their own work.

WHAT WE HOPE TO ACHIEVE
A fire record people can trust anywhere on Earth back to 2000, updated daily from FIRMS. Next: coarser hexagons for continent and world views, a global hotspot CSV, fire-season timing, and per-hexagon anomaly maps.

TOOLS
Python, DuckDB, H3, Rust (axum, tokio), SvelteKit, MapLibre GL JS, Playwright, Docker, Google Cloud Run. All open source. AI assistance (Claude Code) is disclosed in AI_LOG.md.

## NASA data

- NASA FIRMS (Fire Information for Resource Management System): the source of all fire detections. https://firms.modaps.eosdis.nasa.gov/
  - FIRMS yearly archive downloads (MODIS Collection 6.1; VIIRS 375 m from S-NPP and NOAA-20), November 2000 to December 2025: https://firms.modaps.eosdis.nasa.gov/download/
  - FIRMS API, for the days since (through 13 November 2026): https://firms.modaps.eosdis.nasa.gov/api/
- MODIS active fire product (MCD14ML, Collection 6, version 3 monthly files from the University of Maryland MODIS fire team): hotspot type labels for 2000–2017. User guide: https://www.earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf
- NASA Common Metadata Repository (CMR) granule records: the footprint and time of every MODIS and VIIRS swath, so the conversion is fitted only where both satellites actually observed. https://cmr.earthdata.nasa.gov/search/
- Data use follows NASA's open data guidance: https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance

## Use of Super Intelligence (SI)

Yes. The team chose the approach to the challenge; an SI coding assistant (Anthropic's Claude, via Claude Code) then helped write and review code, documentation, tests and analysis, while the team set the goals, made the decisions and checked the results. Every session is recorded in AI_LOG.md in the repository: what was asked, what the AI did, what was checked. AI-generated code and data are identified as such in the repository's README and AI_LOG.md. No NASA logos or branding appear in AI-generated content.

## Space Agency Partner Data and Other References

Space Agency Partner data: none used. All fire data comes from NASA (see NASA Data).

Data and map
- Basemap: OpenFreeMap tiles (https://openfreemap.org/), OpenMapTiles schema, map data © OpenStreetMap contributors (https://www.openstreetmap.org/copyright).
- H3 hexagonal grid system: https://h3geo.org/

Methods and references
- Giglio, L., Schroeder, W., Justice, C. O. (2016). The collection 6 MODIS active fire detection algorithm and fire products. Remote Sensing of Environment 178, 31–41.
- Schroeder, W., Oliva, P., Giglio, L., Csiszar, I. A. (2014). The New VIIRS 375 m active fire detection data product: Algorithm description and initial assessment. Remote Sensing of Environment 143, 85–96.
- Theil, H. (1950) and Sen, P. K. (1968): Theil–Sen slope estimator.
- Mann, H. B. (1945) and Kendall, M. G. (1975): Mann–Kendall trend test.
- Abramowitz, M., Stegun, I. A. (1964). Handbook of Mathematical Functions, formula 7.1.26 (normal distribution approximation).

Software (all open source, used under their own licenses)
- Python, DuckDB (https://duckdb.org/), uv
- Rust: axum, tokio, tower-http, h3o, geo, duckdb-rs
- SvelteKit (https://svelte.dev/), MapLibre GL JS (https://maplibre.org/)
- Playwright (testing), mise (tool versions), Docker, Google Cloud Run and Cloud Build (hosting)

AI assistance
- Claude Code (Anthropic) helped write and review code, documentation, tests and analysis; the team set goals, made decisions and checked results. Every session is recorded in AI_LOG.md: https://github.com/strychemi/firecal/blob/main/AI_LOG.md

No copyrighted images, text or code from others are included; all app code was written for this project.
