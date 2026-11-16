# Space Apps 2026 submission text (draft)

Paste each section into the matching field on the team's Project page (Edit, then Save Progress often). Submit for Judging before 23:59 local; you can edit and resubmit until then.

## Project name

firecal

## High-level summary

firecal turns 26 years of NASA fire detections from two generations of satellites (MODIS on Terra and Aqua, VIIRS on S-NPP and NOAA-20) into one unbroken burning calendar, so a change in satellites is no longer mistaken for a change in fire. VIIRS sees far more hotspots than MODIS for the same fires, so a raw count jumps in 2012. We count burning cell-days instead, convert MODIS to VIIRS-equivalent counts with day and night multipliers fitted where both satellites observed the same places at the same times, and test every change against rules written down before seeing the results. A web app lets anyone draw an area or enter coordinates, pick dates, and see at once how busy this month is against the usual, a years × months calendar, the season so far, a long-term trend, and downloads of the numbers, the charts and the hotspots themselves. It runs for the whole globe and for an Argentina study region, through two days ago.

## Link to Project Demo

https://github.com/strychemi/firecal/blob/3a19569c0e129595f9301fd1a22e89ee05866f76/docs/firecal-demo.pdf (7-slide PDF)

## Link to Final Project

https://github.com/strychemi/firecal (the repository must be public; check the link in a private window).

## Detailed Project Description

**What it does**
- Map: draw a box or polygon, or type latitude/longitude (box, or point and radius), and choose a date range.
- Answer card first: e.g. "2.4× the usual October, 3rd highest of 26 years", with the month still in progress compared like for like (days 1–D against days 1–D of earlier years), and a trend (Theil–Sen slope with a Mann–Kendall test) for the selected month.
- Burning calendar: years × months heatmap; fire season year by year (per month or season so far); yearly totals; per-satellite raw hotspot counts beside the harmonized series.
- Anomalies against the multi-year median or mean (toggle, always labelled), with colour-blind-safe sequential and diverging ramps and values on hover.
- Downloads: monthly series and per-hexagon CSVs, charts as PNG/SVG carrying their title, area, dates and legend, and a CSV of the hotspots detected in the search (Argentina app; up to 250,000 rows).

**How it works**
- Python + DuckDB pipeline reads the FIRMS yearly archives and recent days from the FIRMS API, counts burning cell-days on an H3 grid (local solar date, day/night), fits the MODIS → VIIRS conversion per area on 2013–2022, validates by leaving one year out, and publishes versioned Parquet.
- One satellite per day, never summed: Terra from November 2000, Aqua from August 2002, S-NPP from February 2012, then NOAA-20.
- Fit only where both satellites actually observed, using NASA's granule (swath) records from the Common Metadata Repository; MODIS labels for 2000–2017 come from the producer's version-3 files.
- Globally, each continent is fitted and judged as its own study area.
- Rust (axum) API reads only the published data, answers in milliseconds for cached areas, and serves a SvelteKit app with a MapLibre map.
- Every computation in the Rust API has an independent Python reference, and a parity test compares their full responses.

**Results (Argentina, leave-one-year-out):** typical error of the converted monthly count 9.95 % for the whole area and 22.2 % for 2° × 2° blocks. Day and night multipliers are about 3.05 and 10.3.

**Benefits and impact:** emergency responders, land managers, firefighters and scientists can ask "is this fire season unusual, here?" across the full satellite record, without the 2012 jump misleading them, and take the numbers and hotspots away for their own work.

**Tools:** Python, DuckDB, H3, Rust (axum, tokio), SvelteKit, MapLibre GL, Playwright, mise. Everything is open source.

## NASA data

- FIRMS (Fire Information for Resource Management System) MODIS Collection 6.1 and VIIRS 375 m (S-NPP, NOAA-20) active fire archives, and the FIRMS API for recent days.
- MCD14ML MODIS Collection 6 monthly fire location product (version 3 labels), University of Maryland MODIS fire team.
- Common Metadata Repository (CMR) granule records for MODIS and VIIRS swaths.

## Use of Super Intelligence (SI)

Yes. The team chose the approach to the challenge; an SI coding assistant (Anthropic's Claude, via Claude Code) then helped write and review code, documentation, tests and analysis, while the team set the goals, made the decisions and checked the results. Every session is recorded in AI_LOG.md in the repository: what was asked, what the AI did, what was checked. AI-generated code and data are identified as such in the repository's README and AI_LOG.md. No NASA logos or branding appear in AI-generated content.

## Space Agency Partner Data and Other References

No Space Agency Partner data was used.


- NASA FIRMS: https://firms.modaps.eosdis.nasa.gov/
- MODIS Collection 6/6.1 Active Fire Product User's Guide (Giglio et al.).
- VIIRS 375 m Active Fire Product User's Guide (Schroeder et al.).
- H3 hexagonal grid: https://h3geo.org/
- Open-source software: Python, DuckDB, H3, Rust (axum, tokio, tower-http), SvelteKit, MapLibre GL JS, Playwright, mise, and their dependencies, under their own licenses.
- Basemap: OpenFreeMap tiles (https://openfreemap.org/), OpenStreetMap data © OpenStreetMap contributors.
