# Pre-registration: MODIS–VIIRS harmonization rules

Written and committed 2026-11-14, before any global data has been analysed and before any upgrade to the baseline model has been tested. The commit timestamp is the record of when these rules were fixed.

**Purpose.** Each rule below says in advance what result would make us keep or reject a change to the method. Writing them down first stops us from choosing the test after seeing the answer.

**What has already been looked at.** These rules were checked on the Argentina study box only: FIRMS standard-processing archives for Aqua MODIS (MCD14ML C6.1) and S-NPP VIIRS (375 m), 2012–2025, clipped to `[-76.0, -56.0, -50.0, -20.0]`, using the baseline model below. The global archives are downloaded but have not been analysed. NOAA-20, NOAA-21 and Terra have not been analysed. Because the pass marks were tuned on Argentina, Argentina is not an independent test of them.

The evidence for each number is in `science/rule_checks/results.json` and `science/rule_checks/frp_results.json`, produced by `ingest.py`, `checks.py` and `frp_check.py` in that folder. The plain-language explanation is the primer (`science/rule_checks/primer.html`).

## 1. Definitions

| Term | Definition |
|---|---|
| Hotspot filters | FIRMS `type = 0` (presumed vegetation fire). MODIS `confidence ≥ 30`. VIIRS `confidence` in {nominal, high}. |
| Local solar date | UTC acquisition time + longitude / 15 hours, then take the date. |
| Burning cell-day | One H3 resolution-8 cell, on one local solar date, for one satellite and one day/night flag, with at least one hotspot. |
| `M`, `V` | Burning cell-days counted by Aqua MODIS (`M`) and S-NPP VIIRS (`V`), summed over an area and a month. |
| Fair day | A day on which both satellites have at least one detection in the outage-check unit (section 4, rule 7). Only fair days are used to fit or test the conversion. |
| Calibration years | 2013–2022. 2012 is partial (S-NPP starts 2012-01-20). |
| Held-out years | 2023–2025. Never used for fitting or for choosing between versions. Aqua's orbit drift makes them a poor test of the pre-2012 conversion, so they are reported, not used as pass/fail. |
| `V̂` | The prediction of `V` from `M`. In validation, always made by a model that did not see the predicted year. |
| Miss | `ln(V / V̂)` for one area-month. |
| Typical error | Median over area-months of `|V̂ − V| / V`. |
| Whole-area score | Typical error over study-area months (120 months in Argentina, 2013–2022). Area-months with `V < 100` are excluded. |
| Small-area score | Typical error over 2° × 2° block-months with `V ≥ 50`. The main score for comparing versions, because it moves far less by luck (section 3). |
| Luck range | 95 % interval from a year-block bootstrap: resample the 10 calibration years with replacement, recompute, 4,000 times. For a comparison between two versions, both are scored on the same resampled years (paired). |

## 2. Baseline model

The version every upgrade is compared against.

- Separate conversion for day and night passes.
- Study-area multiplier: `r = ΣV / ΣM` over the calibration years on fair days.
- Per-area multiplier for each H3 resolution-3 parent cell `s`, shrunk toward `r`: `r_s = (V_s + k·r) / (M_s + k)` with `k = 50`.
- Areas with no calibration data use `r`.
- Prediction: `V̂ = r_s × M`.
- Validation: leave one calibration year out; fit on the other nine; predict the hidden year.

Argentina results for the baseline: `r` = 3.05 by day and 10.3 at night; whole-area typical error 9.95 %; small-area typical error 22.2 %.

## 3. Rules for keeping an upgrade

An upgrade is kept only if it passes every rule that applies to it. If two versions are within the margins below, keep the simpler one.

### Rule 1. Accuracy gain (small-area score)

- **Keep** only if the small-area typical error improves by **at least 0.5 percentage points**, and the paired luck range of the difference lies entirely on the improving side of zero.
- **Why this margin.** On Argentina, luck alone moves the small-area score by about 0.4 points (bootstrap SD), and moves a paired difference between two similar versions by 0.13 points (SD; 95 % range −0.57 to −0.05 for r3 k50 against r3 k200). So 0.5 points is several times the noise.

### Rule 2. No worse overall (whole-area score)

- **Reject** if the whole-area typical error gets worse by **more than 2 percentage points**.
- **Why not tighter.** Luck alone moves the paired whole-area difference by 0.35–1.0 points (SD), and its 95 % range spans about 1.3–4 points. A 0.2-point limit, which we first planned, cannot be measured at this scale.

### Rule 3. Tilt (replaces the "every decile under 3 %" rule)

- **Measure** the tilt `b` as the slope of a straight line through the misses: `ln(V / V̂) = a + b·ln(V̂)`, over whole-area months in the left-out years.
- **Pass** if `|b| ≤ 0.03` by day and `|b| ≤ 0.06` at night. Roughly two bootstrap SDs of the baseline's tilt (0.014 by day, 0.028 at night).
- **Baseline status.** It fails: `b` = −0.087 (−0.115 to −0.059) by day, −0.30 (−0.355 to −0.249) at night. It stays the baseline because no alternative has been tested yet. Any upgrade that claims to fix the tilt must pass this rule.
- **Why the old rule was dropped.** "Every decile of activity has mean bias under 3 %" fails 99.7 % of the time on Argentina whole-area months when the misses are shuffled so that there is no tilt at all. On small areas it still fails 43 % of the time by day. A rule that a perfect model fails cannot judge a fix.
- **Context.** On small areas the tilt is steeper (−0.17 by day, −0.40 at night). The fire-strength check shows the tilt disappears once fires below about 10–20 MW by day and 5 MW at night are ignored, so its cause is small fires that only VIIRS detects. Ignoring small fires is not itself an accepted fix: the multiplier keeps falling below 1 as the floor rises, and small fires are part of what the calendar is for.

### Rule 4. The join between the records

- **Measure** the gap `100 × ln(ΣV̂ / ΣV)` on the **backward test**: fit on 2018–2022, predict 2013–2017. This copies the real task, which is predicting earlier years from later ones.
- **Pass** if the gap is within **±7 %** for day and night combined and for day alone, and within **±10 %** at night.
- **Baseline status.** Passes. Combined +2.0 % (−1.7 to +6.7); day +0.2 % (−3.8 to +2.8); night +7.4 % (−3.6 to +20.3). The night luck range is wide, so the night result is weak evidence either way.
- **Also reported, not pass/fail.** Leave-one-year-out gap (−0.03 %), forward test (−0.7 %), held-out 2023–2025.
- **Not a test.** The gap on the years the model was fitted on. With shrinkage it is not zero (night −6.5 %), but it does not measure how the model does on unseen years.

### Rule 5. Error ranges

- **Build** an 80 % range for each prediction from past misses: take the 10th and 90th percentiles of `ln(V / V̂)` from the other calibration years, for predictions of similar size (5 bins by predicted count). Range = `[V̂·e^q10, V̂·e^q90]`.
- **Pass** if, averaged over left-out years, **75–85 %** of small-area months fall inside the range. Each year's coverage is also reported.
- **Baseline status.** Passes: 79.9 % mean, 76–82 % in every year.
- **Not used for pass/fail.** Whole-area coverage, which jumps between 58 % and 100 % by year simply because 12 months a year is too few to measure a percentage.
- **For areas larger than one block,** the range is built from the area's own totals, not by adding up per-cell ranges.

### Rule 6. Stand-in multiplier for areas without history

- **Test** by leave-stratum-out: take a resolution-3 area with plenty of fires, remove its own data, predict it using only the stand-in, and score the typical error. Compare stand-ins with a paired bootstrap.
- **Adopt** a stand-in only if it beats the current one with a paired luck range that excludes zero.
- **Not used.** Scoring stand-ins on the quietest areas: only 0.3 % of their block-months had enough fires to score.
- **Argentina result, to be confirmed globally.** The larger surrounding region (resolution-2 parent) beats the study-area average: 14.0 % against 19.3 % typical error over 113 areas, difference 5.3 points (2.6 to 7.7). This is the first upgrade to test globally.

### Rule 7. Days without data

- **Full-day outages.** A satellite with no detection at all in an outage-check unit on a day is treated as having **no data** that day, not zero fire. Fitting and testing use only days when both satellites have data.
- **Argentina status.** With the whole study box as the unit, this caught every known outage (S-NPP 2022-07-27 to 08-10; Aqua 2022-04-01 to 16; shorter S-NPP gaps in 2024).
- **Before the global fit,** the outage-check unit and a rule for partial-day outages must be added to this file and committed. A small unit is not safe on its own, because VIIRS normally detects fires that Aqua misses, so "VIIRS saw something and Aqua saw nothing" is ordinary in a small area. That decision is made without looking at fit results.

### Dropped for now: choosing and scoring on separate years

Nested cross-validation (choosing the version on nine years and scoring on the tenth) picked the same version (r3, k = 50) in all 10 folds, so the reported score was not flattered. Re-run it if the candidate list grows well beyond the current seven versions.

## 4. Going global

The pass marks above are calibrated on Argentina's noise. Quieter regions have wider luck ranges. For each continent:

1. Recompute every luck range with the same bootstrap.
2. Apply rules 1, 4 and 5 unchanged.
3. For rule 2, the margin is the larger of 2 points and twice the continent's paired bootstrap SD.
4. For rule 3, if the luck range of `b` is wider than the pass mark on either side, report the continent as **too noisy to test**, not as passing.
5. Report each continent's results separately. A pass in one continent does not carry to another.

## 5. Order of upgrades to test

Each is tested against the current accepted version, one at a time:

1. Stand-in: resolution-2 parent instead of the study-area average (rule 6, then rules 1–5).
2. Seasonal multipliers per area (DJF, MAM, JJA, SON), shrunk toward the area's multiplier.
3. A correction for the tilt (rule 3 must pass, as well as rules 1, 2, 4 and 5).

## 6. Reported but not pass/fail

- NOAA-20 against S-NPP on matched days: the noise floor between two satellites of the same design.
- Held-out 2023–2025 results.
- Terra conversion for 2000-11 to 2002-07, with its own error ranges.
- High-latitude regions where passes overlap several times a day.

## 7. Changes after this commit

Any change to a rule, pass mark or definition is added below with the date, the reason, and whether it was made before or after seeing the results it affects. Earlier text is not edited.

| Date | Change | Reason | Before or after seeing affected results |
|---|---|---|---|
| 2026-11-14 | Near-real-time (NRT) hotspots, used only for days after the yearly archive, have no FIRMS `type`. For those rows the `type = 0` filter is replaced by a stand-in: drop detections in H3 res-8 cells where at least half of the archive detections had `type` ≠ 0. Standard-processing rows keep the `type = 0` filter. | FIRMS NRT files omit `type`. Built from 2012–2022 and applied to 2023–2025 VIIRS, the stand-in removes 83 % of the detections `type` removes and wrongly drops 0.2 % of vegetation detections. | After: the 2023–2025 check above was run to choose the 50 % threshold. No pass/fail test uses NRT data. |
| 2026-11-15 | **NOAA-20 conversion rule, fixed before fitting.** NOAA-20 days (used when S-NPP has no data) are currently counted as S-NPP with no conversion (multiplier 1). Proposed: convert them with the baseline model of section 2, fitting NOAA-20 in place of Aqua, on fair days with both S-NPP and NOAA-20 detections, calibration years 2018–2022 (NOAA-20 data starts 2018-04-01). Compare it with no conversion (`V̂ = M`) by leaving one calibration year out. **Keep** the conversion only if its small-area typical error is at least 0.5 percentage points lower than no conversion's, and its whole-area typical error is not more than 2 points higher (the margins of rules 1 and 2). With five calibration years there is no luck-range requirement. Otherwise keep multiplier 1. Held-out years 2023–2025, tilt and gap are reported, not pass/fail. VIIRS months keep no error range either way. | S-NPP's near-real-time feed ended on 2026-11-02, so recent months are counted from NOAA-20 alone. NOAA-20 has not been compared with S-NPP before. | Before: written and committed before any NOAA-20 fit was run. |
| 2026-11-15 | **Outcome of the NOAA-20 rule above: conversion rejected, multiplier 1 kept.** Leaving one year out (2018–2022), no conversion scores 2.54 % whole-area and 8.19 % small-area typical error; the fitted conversion (study-area multipliers 1.006 by day, 1.008 at night) scores 2.35 % and 8.41 %. The small-area score gets 0.22 points worse, short of the required 0.5-point gain. Held-out 2023–2025 whole-area error: 2.34 % without conversion, 1.83 % with it (reported only). Numbers in `data/model/validation.json` (`noaa20`). | Applying the rule as written. | After: this records the result. |
| 2026-11-15 | **Outage-check unit and partial-day outages for the global fit (rule 7), fixed before any global data is analysed.** (1) Whether a satellite observed comes from NASA's granule records, not from detections: the public CMR records of the fire products FIRMS is built from, MOD14 and MYD14 version 061 (the only MODIS swath records in CMR; they record when and where the instrument observed, which does not depend on the processing version of the hotspot rows) and VNP14IMG and VJ114IMG version 002 (the FIRMS VIIRS archive rows are version 2). (2) Unit: one H3 resolution-3 cell, one local solar date, one pass. A satellite has data in a unit if one of its granules for that pass covers the cell's centre during that local solar date. The pass comes from the granule's day/night flag; a granule flagged as both counts for both. (3) A **fair unit** is one where both satellites have data. Only fair units are used to fit or test the conversion; this replaces the fair day over the whole study box. (4) Partial-day outages need no separate rule: a missing granule removes exactly the cells it would have covered. (5) Consistency check: if more than 0.1 % of a satellite's detections fall outside its granule footprints, stop and investigate before fitting. (6) Check before fitting, using no fit result: on Argentina 2013–2022 the new unit must catch the known outages (S-NPP 2022-07-27 to 08-10; Aqua 2022-04-01 to 16; the shorter S-NPP gaps in 2024). Report how many Argentina units change fair status. The Argentina baseline refitted on the new unit is reported, not pass/fail, because Argentina has already been looked at. (7) Fallback: where granule records are missing for a period in which FIRMS has detections, that period uses one continent, one local solar date and one pass as the unit, with any unfiltered detection meaning data; partial-day outages are then not detected, and the results say so. | In Argentina's 10° squares on fair days (2013–2022), Aqua records no detection on 15 % of day passes and 60 % of night passes in which S-NPP records 10–49, and on 2 % of night passes in which S-NPP records 200–499. Detection-based checks on small units would therefore drop the days when Aqua sees little, which skews the conversion. Granule counts per day reproduce both 2022 outages to the day and show partial first days the box rule counted as full: 2022-03-31 Aqua (193 of 289 granules; 5 Argentina detections against 96 the day before) and 2022-07-26 S-NPP (161 of 241; 271 detections against Aqua's 665). | Before: no global data has been analysed. The Argentina detection counts and the 2022 granule counts above were looked at; no fit was run. |
| 2026-11-15 | **MODIS hotspot types for 2000-11 to 2017-12 come from the producer's version-3 labels.** The FIRMS yearly MODIS archive mixes MCD14ML product versions: rows are version 2 (`version` 6.2) through 2017 and version 3 (6.03, then 61.03) from 2018. Version 3 keeps the same detections and changes only the hotspot `type` labels ("significantly improved typing of hot spots", MODIS Collection 6/6.1 Active Fire User's Guide, section 5.5.2), and the `type = 0` filter reads those labels. Collection 6 and 6.1 fire products may be freely intermixed (same guide, section 2.1). From now on, each FIRMS MODIS row dated 2000-11 to 2017-12 takes its `type` from the matching row of the producer's MCD14ML Collection 6 version 3 monthly files (University of Maryland), matched on UTC date and time, satellite, latitude and longitude. Detections, the country selection and every other field still come from FIRMS; rows from 2018 on are unchanged. **Check:** in each year at least 99.9 % of the FIRMS rows must find a match; otherwise stop and investigate before using the labels. The near-real-time static-cell stand-in (row of 2026-11-14) is rebuilt from the relabelled archive. Applies to the Argentina prototype and to the global run. | In Argentina the `type` filter removes 0.65 % of Aqua daytime burning cell-days in 2013–2017 and 2.39 % in 2018–2022 (night 3.29 % and 3.37 %); S-NPP, whose processing version did not change, shows no step. The step lies inside the calibration years, and every year before 2012 would keep static sources that version 3 removes. | After, for Argentina: the step above was measured, and the backward-join result had been seen. Before, for global data: no global data has been analysed. |
| 2026-11-15 | **Rule 7, parts 5 and 7 (outage-check unit, row above of the same date): missing granule records.** (5) The consistency check counts a detection as outside only if a granule record of its satellite exists at its acquisition time (within a minute, as FIRMS times are whole minutes) and the detection lies outside that record's footprint. Detections with no granule record at their time are missing records, not footprint errors; they are counted and reported. The 0.1 % limit is unchanged. (7) The fallback applies per pass: on any local solar date and pass where a satellite has a detection with no granule record at its time, or detections but no granule units at all, the whole study box (globally, the continent) is that satellite's unit for that pass, with any unfiltered detection meaning data, in place of its granule units for that pass. (Detail of method, settled at the same time: footprints are CMR's 4-corner polygons with great-circle edges, tested on the sphere, so polar and antimeridian footprints need no special case.) | As first written, the check failed for NOAA-20: 35,817 of 3,478,929 Argentina detections in 2013–2025 (1.03 %) fell outside its footprints. All but 4 had no granule record at their time, and they lie in April–June 2018, NOAA-20's first months in FIRMS: CMR holds 43 VJ114IMG version-2 granules touching the box in April 2018 and 5 in May, against about 480 in a normal month, while FIRMS has NOAA-20 detections on those days. Where a record exists the footprints match: detections outside them are Terra 0 of 593,413, Aqua 0 of 1,001,578, S-NPP 3 of 5,542,365, NOAA-20 4 of 3,478,929. The fallback covers 127 NOAA-20 passes (2018-04 to 06), 9 Terra (2025) and 1 S-NPP (2025). | Before any fit on the new unit: the check's failure and the counts above were seen; no fit or pre-fit outage comparison had been run. Before, for global data: no global data has been analysed. |
| 2026-11-15 | **Rule 7, part 2 (outage-check unit): FIRMS must hold the pass.** A satellite has data in a unit only if both (a) one of its granules for that pass covers the cell's centre during that local solar date (part 2 as written), and (b) FIRMS has at least one of its detections, unfiltered, on that local solar date and pass in the study box (globally, the continent). Fair units are still those where both satellites have data. Parts 5 and 7 (row above) are unchanged. | Granule records show when a satellite observed, not whether FIRMS holds the result. In Argentina 2013–2025 the records show passes with no FIRMS detection anywhere in the box: NOAA-20 on 98 passes (every pass from 2018-01-15, when its records start, to February 2018, many in March 2018, before FIRMS's NOAA-20 record begins on 2018-04-01; and 2023-07-19 to 22), S-NPP on 3 (2024-07-10 night, 2024-11-03), Aqua on 11 day passes and Terra on 31. Counted as observed, these would enter the fit as zero fire for that satellite: S-NPP has 23,713 burning cell-days on the NOAA-20 passes. Condition (b) also drops passes on which a satellite truly saw no fire in the whole box, mostly Aqua (473) and Terra (181) night passes, holding 0.6 % of S-NPP's cell-days on the Aqua comparison; on a continent this is expected to be rare, because unfiltered detections include gas flares and other persistent sources. Considered and not chosen: condition (b) alone, which keeps the box or continent rule per pass and drops the granule records (simpler, but gives up partial-day outages and the gaps between swaths, 2 % of S-NPP's Argentina cell-days). | Before any fit on the new unit: the per-day and per-pass counts above and the pre-fit outage comparison were seen; no fit had been run. Before, for global data: no global data has been analysed. |
| 2026-11-15 | **Outcome of the MODIS labels rule (row of 2026-11-15 above): check passed, labels used.** In every year 2000–2017, 100.000 % of FIRMS MODIS rows in the Argentina box matched a version-3 row, with no ambiguous match; 2–4 % of rows per year changed `type`. The 2018 step in the `type` filter disappears. Pre-2012 totals fall 0.8 % (Aqua era) and 1.9 % (Terra era). Refit on Argentina (reported, not pass/fail): Aqua study-area multipliers 3.0505 → 3.0839 by day and 10.3018 → 10.3723 at night; leave-one-year-out whole-area typical error 9.95 → 10.56 %, small-area 22.23 → 22.47 %; backward-join gap 2.0 → −0.4 %; held-out whole-area 11.44 → 10.80 %. Terra whole-area 19.79 → 18.57 %, held-out 18.21 → 20.21 %. | Applying the rule as written. | After: this records the result. |
| 2026-11-15 | **Outcome of the pre-fit check of the outage-check unit (rule 7 part 6, with the two rows above of the same date).** Argentina, granule records for 2013–2025 (`pipeline/tests/outage_check.py`). (a) Known outages caught: no S-NPP unit observed on 2022-07-27 to 08-09, with the day pass already missing on 07-26 and part of the night pass back on 08-10; no Aqua unit on 2022-04-01 to 14, with the day pass missing on 03-31; no S-NPP unit on any of the 19 days in 2024 the whole-box rule marked as outages. (b) Units (res-3 cell, local date, pass, with a burning cell-day of either satellite) that change fair status against the old whole-box day rule: Aqua comparison 22,052 of 626,820 lose it (3.5 %; 0.60 % of Aqua's and 2.58 % of S-NPP's cell-days), none gain it; Terra 17,293 of 646,025 (2.7 %; 0.49 % and 2.53 %); NOAA-20 2,422 of 717,735 (0.3 %; 0.53 % and 0.03 %). (c) Argentina baseline refitted on fair units (reported, not pass/fail), before → after: Aqua multipliers 3.0839 → 3.0493 by day, 10.3723 → 9.9577 at night; leave-one-year-out whole-area typical error 10.56 → 9.41 %, small-area 22.47 → 22.16 %; tilt at night −0.311 → −0.243; backward-join gap −0.40 → −0.28 %; held-out whole-area 10.80 → 9.10 %, held-out gap 3.56 → 4.91 %. Terra multipliers 6.8217 → 6.7142 and 5.5690 → 5.4157; whole-area 18.57 → 17.12 %, small-area 32.50 → 32.72 %; held-out 20.21 → 18.92 %. NOAA-20: conversion still rejected (small-area gain −0.24 points, whole-area loss −0.26). Numbers in `data/model/validation.json`. | Applying the rule as written. | After: this records the result. |
| 2026-11-15 | **Global run: continents, study areas and luck ranges (sections 2 and 4), fixed before any global data is analysed.** (1) **Continents** are listed in `global/continents.toml`: the UN M49 regions, with the Americas split into North America (Northern America, Central America, the Caribbean) and South America, Antarctica and the far southern islands as their own group, and one exception, the Russian Federation split at 60° E (west to Europe, east to Asia). Each detection takes the continent of its FIRMS country file (Russia by its longitude). Detections outside every country file (open ocean) are not in the FIRMS country files and are not used. The continent is the fallback unit of rule 7. (2) **Each continent is its own study area.** The baseline of section 2 is fitted separately for each continent: study-area multipliers `r` per continent and pass, resolution-3 multipliers shrunk toward the continent's `r` with `k = 50`; a resolution-3 cell that spans two continents gets a multiplier in each, from that continent's detections. Calibration years 2013–2022 and held-out years 2023–2025, as for Argentina. (3) **Scores** as defined for Argentina, within each continent: whole-area typical error over continent-months with at least 100 S-NPP cell-days; small-area typical error over 2° blocks with at least 50. (4) **Luck ranges** (section 4, item 1) repeat the Argentina method in `science/rule_checks/checks.py`: resample the 10 calibration years with replacement, 4,000 times, seed 20261114, recompute the score on the pooled years, and take the 2.5th–97.5th percentiles; for rule 6, resample the data-rich resolution-3 areas (at least 2,000 Aqua cell-days in the calibration years) 1,000 times, with `k = 200` for the resolution-2 stand-in, as in the Argentina test. (5) The baseline's rule statuses (rules 3, 4 and 5) are reported for each continent before any upgrade is tested; upgrades then follow section 5, kept or rejected per continent. | Section 4 says how to judge each continent but not what a continent is, how the study-area multiplier is defined outside Argentina, or how the bootstrap was run (the method was in code, not in this file). Fixing them now keeps them independent of global results. The Russian split keeps the Siberian boreal fires, most of Russia's, from dominating Europe. | Before: no global data has been analysed. Two global years (S-NPP 2020, MODIS 2010) were ingested only to time the step; their row counts and label-match rate (100 %) were seen, nothing else. Global granule counts per day were seen (an Aqua gap in CMR from 2020-08-16). |
