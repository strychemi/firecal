# API contract (v0, prototype)

The Rust API (`api/`) serves this contract. `pipeline/firecal_pipeline/reference.py` implements the same contract in Python and is the oracle the Rust API is compared against (`pipeline/tests/test_api_parity.py`).

All counts are **burning cell-days**: one H3 resolution-8 cell (about 0.74 km²), on one local solar date, for one day or night pass, with at least one hotspot, so a cell can count twice a day. `value` is in **VIIRS-equivalent burning cell-days**: observed by VIIRS from February 2012 (S-NPP, with NOAA-20 on S-NPP outage days) and converted from MODIS before that; `raw`, `detections` and `frp` are the satellite's own numbers, never converted.

## `GET /api/meta`

```json
{
  "data_version": "v2",
  "series_start": "2000-11",
  "series_end": "2026-11",
  "through": "2026-11-13",
  "in_progress": { "month": "2026-11", "days": 13 },
  "unit": "VIIRS-equivalent burning cell-days (...)",
  "region": { "bbox": [-76, -56, -50, -20], "countries": ["Argentina", "..."] },
  "eras": [{ "start": "2000-11-01", "end": "2002-07-31", "source": "terra_harmonized", "chain": ["terra", "aqua"] }],
  "gaps": [{ "start": "2001-06-15", "end": "2001-07-02", "days": 18 }],
  "days_filled_by": { "noaa20": 36, "terra": 9 },
  "validation": { "aqua": { "whole_area_typical_error_pct": 9.95, "small_area_typical_error_pct": 22.23, "backward_join_gap_pct": 2.0, "converted": true } },
  "continents": { "study_area": { "fitted": true, "validation": { "aqua": { "...": "..." } }, "gaps": [], "days_filled_by": {} } },
  "presets": [{ "id": "parana-delta", "name": "Paraná Delta", "note": "...", "bbox": [-60.8, -34.3, -58.3, -32.0] }],
  "export_limit": 250000
}
```

- `through` is the last local solar date with data. Days after the yearly FIRMS archive come from the FIRMS area API: standard-processing data where FIRMS has it, near-real-time after that. A local date counts only once the UTC morning after it is in, so `through` is two days before the newest UTC date FIRMS has. The global data has recent days too (VIIRS only); each recent detection takes the continent its place had most often in the archive, since the API gives no country.
- `validation` has one entry per satellite tested against S-NPP (leaving one calibration year out). `converted` is false when the pre-registered rule rejected the fitted conversion (NOAA-20): the scores are then for counting it as S-NPP unchanged, which is what the data uses, and `backward_join_gap_pct` is that version's overall gap.
- `continents` has one entry per continent with its own model and month status: the global data has `Africa`, `Antarctica`, `Asia`, `Europe`, `North_America`, `Oceania`, `South_America` and `World`; Argentina has the one entry `study_area`. Each holds `fitted` (false for Antarctica, too sparse to fit, and so without MODIS months), `validation` (as above, for that continent), and `gaps` and `days_filled_by` from that continent's own satellite choice. `World` is the whole run's satellite choice, used only for a search with no fire. With several continents the top-level `validation` is empty and `gaps` and `days_filled_by` are `World`'s; with one they are that continent's.
- `export_limit` is `null` when the data has no hotspot file (the global data): `/api/export.csv` is then refused.
- `in_progress` is set when the series ends partway through a month (`series_end`): that month and how many of its days (1..`days`) have data. It is `null` when `through` is a month's last day.

## `POST /api/query`

Request (only `area` is required):

```json
{
  "area": { "preset": "parana-delta" },
  "start": "2000-11",
  "end": "2025-12",
  "month": "2025-12",
  "baseline": "median"
}
```

`area` is one of:

| Form | Example |
|---|---|
| Preset | `{ "preset": "parana-delta" }` |
| Box | `{ "bbox": [minLon, minLat, maxLon, maxLat] }` |
| Polygon | `{ "polygon": [[lon, lat], [lon, lat], ...] }` (closed or not) |
| Circle | `{ "point": [lon, lat], "radius_km": 50 }` (64-sided polygon) |

H3 takes each edge of an area the short way round the globe, so an area more than 180° of longitude wide would be read as the rest of the world. A box that wide (up to the whole world) is therefore filled as strips at most 90° wide. A polygon that wide is refused with a 400; use a box, or draw it in parts. An area more than 360° wide, or with a coordinate that is not a finite number, is refused.

The area becomes the H3 hexagons whose centres fall inside it, at the finest published level (6, 5, then 4) that keeps it at or under `max_hexagons` (3,000). If even level 4 is over, level 4 is used anyway. An area too small to contain any centre uses the single level-6 hexagon at its centre.

`start` and `end` limit the `months` returned. They default to the series start and end. `month` is the month the stats describe (default: `end`). `baseline` is `median` (default) or `mean`.

Response:

```json
{
  "data_version": "v2",
  "area": { "resolution": 6, "hexagons": 2247, "active_hexagons": 2046,
            "ring": [[-60.8, -34.3], [-58.3, -34.3], [-58.3, -32.0], [-60.8, -32.0], [-60.8, -34.3]] },
  "continent": "South_America",
  "continent_share": 1.0,
  "start": "2000-11",
  "end": "2025-12",
  "months": [
    {
      "month": "2008-04", "source": "aqua_harmonized",
      "value": 13156.95, "lower": 11076.25, "upper": 15491.89,
      "raw": 2730, "detections": 2757, "frp": 135875.8,
      "days": 30, "days_with_data": 30, "complete": true, "in_progress": false
    }
  ],
  "stats": {
    "month": "2025-12", "value": 49.0, "lower": null, "upper": null, "source": "viirs",
    "baseline": "median", "baseline_value": 162.0, "baseline_years": [2000, 2001, "..."],
    "ratio": 0.302, "rank": 22, "of": 26, "percentile": 16.0,
    "category": "much lower than usual",
    "sentence": "December 2025 had 49 fire-days, 0.3× the usual December (median of 25 years), 22nd highest of 26 years.",
    "through": null
  },
  "cells": [
    { "h3": "86b2a6c07ffffff", "month": 2.0, "range": 311.47 }
  ]
}
```

Field rules:

- `continent` is the continent whose model the search uses: the one holding most of the search's fire-days (`value`) over the whole series, summed over its hexagons (ties: the first name alphabetically); `continent_share` is that continent's share, rounded to 3 decimals. Each fire-day was already converted with its own continent's multipliers when the data was published; the search's continent decides the 80 % ranges and the month status (`days_with_data`, `complete`). A search with no fire uses `World` (several continents) or the one study area, with `continent_share` `null` (also `null` for data published before continents).
- `months` lists every month from `start` to `end`, including months with no fire (zeros).
- `area.ring` is the outline the hexagons were chosen from, as a closed ring of `[lon, lat]` rounded to 5 decimals: the box corners, the polygon as sent (closed), or the circle's 64-sided polygon. The map draws this, so it always shows the area the numbers cover.
- `cells` has one entry per hexagon in the area with any fire in the selected `month` or from `start` to `end`, sorted by `h3` (the H3 index as a hex string, at `area.resolution`). `month` is its fire-days in the selected month and `range` its fire-days from `start` to `end`, both rounded to 2 decimals.
- `source` is `terra_harmonized`, `aqua_harmonized` or `viirs`.
- `lower` and `upper` form the 80 % range for converted months: `value × e^q10` to `value × e^q90`, with `q10` and `q90` taken from `misses.parquet` for the search's `continent` and that satellite's model, the size of area (`size`: res-4 cell, res-3 cell, 2° block or study area) whose typical `area_km2` is nearest the searched area on a log scale (the sum of the areas of the search's hexagons), and the bin containing `value`. They are `null` for VIIRS months (observed, not converted), for months with `value` 0, and for a continent without error tables (Antarctica, `World`).
- `days` is the number of days in the calendar month and `days_with_data` the days with satellite data in the search's `continent` (Argentina: the study box): a satellite with no detection anywhere in the continent that day has no data there. In Antarctica, MODIS days (before February 2012) have no data. `complete` is false when they differ: days with no data, or the in-progress month. Such months are left out of baselines.
- `in_progress` is true only for the in-progress month (meta `in_progress`).
- `stats` compares the selected month with the same calendar month in every other complete year of the whole series (not limited by `start`/`end`):
  - `baseline_value` is the median or mean of those years;
  - `ratio` is `value / baseline_value` (`null` if the baseline is 0);
  - `rank` is 1 + the number of those years with a higher value; `of` is their count + 1;
  - `percentile` is the share of those years with a lower value (`null` if there are no such years);
  - `category` comes from `ratio`: below 0.5 "much lower than usual", below 0.8 "lower than usual", below 1.25 "about usual", below 2 "higher than usual", otherwise "much higher than usual" (`null` when `ratio` is `null`);
  - when there are no other complete years, `baseline_value` is 0, `baseline_years` is empty and `rank` and `of` are both 1;
  - when the selected month is the in-progress month, every year is counted on days 1..D only (D = meta `in_progress.days`): `value` is the month so far, the other years' values are their own days 1..D, and `through` is meta `through`. The sentence names the days: "November 1–13, 2026 had 7,312 fire-days, 1.1× the usual November 1–13 (median of 26 years), 13th highest of 27 years." Otherwise `through` is `null`.
- Numbers are rounded: `value`, `lower`, `upper`, `baseline_value` to 2 decimals, `frp` to 1, `ratio` to 3, `percentile` to 1.

Errors return HTTP 400 with `{ "error": "message" }`.

## `POST /api/export.csv`

The filtered hotspots behind a search, one row per detection, as CSV.

Request: `{ "area": ..., "start": "YYYY-MM", "end": "YYYY-MM" }`. The area forms, hexagon choice and month defaults are the same as `/api/query`, so the export covers exactly the hexagons and months the counts cover. Dates are local solar dates: a detection belongs to the month of its local solar date.

Response: `200`, `text/csv; charset=utf-8`, with `Content-Disposition: attachment; filename="firecal-hotspots-START_END.csv"`. Rows are sorted by UTC time, then latitude, longitude and satellite.

```
hex_id,latitude,longitude,acq_date,acq_time,local_solar_date,satellite,instrument,daynight,confidence,frp,in_calendar
86c2c5007ffffff,-33.63694,-58.37142,2020-08-01,0433,2020-08-01,snpp,VIIRS,N,n,0.9,true
```

| Column | Meaning |
|---|---|
| `hex_id` | H3 index (hex string) of the detection's hexagon at the response level, the same hexagons as `cells` in `/api/query` |
| `latitude`, `longitude` | Detection centre, 5 decimals |
| `acq_date`, `acq_time` | UTC date and time (`HHMM`), as FIRMS reports them |
| `local_solar_date` | UTC + longitude / 15 hours, the date used for counting |
| `satellite` | `terra`, `aqua`, `snpp` or `noaa20` |
| `instrument` | `MODIS` (Terra, Aqua) or `VIIRS` (S-NPP, NOAA-20) |
| `daynight` | `D` or `N`, FIRMS's flag |
| `confidence` | FIRMS's value: 0–100 for MODIS, `n` or `h` for VIIRS |
| `frp` | Fire radiative power, MW, 1 decimal |
| `in_calendar` | `true` if the detection is from the satellite the calendar counts that day; summing these by month gives the `detections` field of `/api/query` |

Only detections that pass the filters are included (`type = 0`; MODIS confidence ≥ 30; VIIRS nominal or high), from every satellite, including those not used for the calendar that day.

A search with more than `max_export_rows` (`export_limit` in `/api/meta`, 250,000) detections is refused with HTTP 413 and `{ "error": "message", "rows": 11465418, "limit": 250000 }`. Bad requests return HTTP 400 as for `/api/query`. Data published without a hotspot file (the global data, meta `export_limit` `null`) refuses every export with HTTP 404 and `{ "error": "The hotspot CSV is not available for this data yet; download hotspots from NASA FIRMS instead." }`.
