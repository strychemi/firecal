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
