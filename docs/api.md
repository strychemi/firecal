# API contract (v0, prototype)

The Rust API (`api/`) serves this contract. `pipeline/firecal_pipeline/reference.py` implements the same contract in Python: it writes the example responses in `web/static/example/` and is the oracle the Rust tests compare against.

All counts are **burning cell-days**: one H3 resolution-8 cell (about 0.74 km²), on one local solar date, for one day or night pass, with at least one hotspot, so a cell can count twice a day. `value` is in **VIIRS-equivalent burning cell-days**: observed by VIIRS from February 2012 (S-NPP, with NOAA-20 on S-NPP outage days) and converted from MODIS before that; `raw`, `detections` and `frp` are the satellite's own numbers, never converted.

## `GET /api/meta`

```json
{
  "data_version": "v2",
  "series_start": "2000-11",
  "series_end": "2025-12",
  "unit": "VIIRS-equivalent burning cell-days (...)",
  "region": { "bbox": [-76, -56, -50, -20], "countries": ["Argentina", "..."] },
  "eras": [{ "start": "2000-11-01", "end": "2002-07-31", "source": "terra_harmonized", "chain": ["terra", "aqua"] }],
  "gaps": [{ "start": "2001-06-15", "end": "2001-07-02", "days": 18 }],
  "days_filled_by": { "noaa20": 36, "terra": 9 },
  "validation": { "aqua": { "whole_area_typical_error_pct": 9.95, "small_area_typical_error_pct": 22.23, "backward_join_gap_pct": 2.0 } },
  "presets": [{ "id": "parana-delta", "name": "Paraná Delta", "note": "...", "bbox": [-60.8, -34.3, -58.3, -32.0] }]
}
```

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

The area becomes the H3 hexagons whose centres fall inside it, at the finest published level (6, 5, then 4) that keeps it at or under `max_hexagons` (3,000). If even level 4 is over, level 4 is used anyway. An area too small to contain any centre uses the single level-6 hexagon at its centre.

`start` and `end` limit the `months` returned. They default to the series start and end. `month` is the month the stats describe (default: `end`). `baseline` is `median` (default) or `mean`.

Response:

```json
{
  "data_version": "v2",
  "area": { "resolution": 6, "hexagons": 2247, "active_hexagons": 2046,
            "ring": [[-60.8, -34.3], [-58.3, -34.3], [-58.3, -32.0], [-60.8, -32.0], [-60.8, -34.3]] },
  "start": "2000-11",
  "end": "2025-12",
  "months": [
    {
      "month": "2008-04", "source": "aqua_harmonized",
      "value": 13156.95, "lower": 11076.25, "upper": 15491.89,
      "raw": 2730, "detections": 2757, "frp": 135875.8,
      "days": 30, "days_with_data": 30, "complete": true
    }
  ],
  "stats": {
    "month": "2025-12", "value": 49.0, "lower": null, "upper": null, "source": "viirs",
    "baseline": "median", "baseline_value": 162.0, "baseline_years": [2000, 2001, "..."],
    "ratio": 0.302, "rank": 22, "of": 26, "percentile": 16.0,
    "category": "much lower than usual",
    "sentence": "December 2025 had 49 fire-days, 0.3× the usual December (median of 25 years), 22nd highest of 26 years."
  },
  "cells": [
    { "h3": "86b2a6c07ffffff", "month": 2.0, "range": 311.47 }
  ]
}
```

Field rules:

- `months` lists every month from `start` to `end`, including months with no fire (zeros).
- `area.ring` is the outline the hexagons were chosen from, as a closed ring of `[lon, lat]` rounded to 5 decimals: the box corners, the polygon as sent (closed), or the circle's 64-sided polygon. The map draws this, so it always shows the area the numbers cover.
- `cells` has one entry per hexagon in the area with any fire in the selected `month` or from `start` to `end`, sorted by `h3` (the H3 index as a hex string, at `area.resolution`). `month` is its fire-days in the selected month and `range` its fire-days from `start` to `end`, both rounded to 2 decimals.
- `source` is `terra_harmonized`, `aqua_harmonized` or `viirs`.
- `lower` and `upper` form the 80 % range for converted months: `value × e^q10` to `value × e^q90`, with `q10` and `q90` taken from `misses.parquet` for that satellite's model and the bin containing `value`. They are `null` for VIIRS months (observed, not converted) and for months with `value` 0.
- `complete` is false when the study box had days with no satellite data that month; such months are left out of baselines.
- `stats` compares the selected month with the same calendar month in every other complete year of the whole series (not limited by `start`/`end`):
  - `baseline_value` is the median or mean of those years;
  - `ratio` is `value / baseline_value` (`null` if the baseline is 0);
  - `rank` is 1 + the number of those years with a higher value; `of` is their count + 1;
  - `percentile` is the share of those years with a lower value (`null` if there are no such years);
  - `category` comes from `ratio`: below 0.5 "much lower than usual", below 0.8 "lower than usual", below 1.25 "about usual", below 2 "higher than usual", otherwise "much higher than usual" (`null` when `ratio` is `null`);
  - when there are no other complete years, `baseline_value` is 0, `baseline_years` is empty and `rank` and `of` are both 1.
- Numbers are rounded: `value`, `lower`, `upper`, `baseline_value` to 2 decimals, `frp` to 1, `ratio` to 3, `percentile` to 1.

Errors return HTTP 400 with `{ "error": "message" }`.
