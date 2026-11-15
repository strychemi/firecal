# Terra's held-out errors and orbit drift

Reported only (PREREGISTRATION.md §6). Checked 2026-11-15 on the global run (`data/global/`).

**Question.** Terra's conversion to S-NPP goes badly wrong in the held-out years 2023–2025 on some continents
(whole-area typical error: Africa 37 %, gap −41 %; Oceania 27 %; Asia 24 %), while Aqua's held-out errors stay
small. Is Terra's orbit drift the cause?

**Answer: yes, mostly.** Terra now passes over about an hour earlier than in the calibration years. Fires build
up through the morning, so an earlier Terra sees fewer of them by day, and the fitted multiplier (from 2013–2022)
undercounts what S-NPP sees. The effect grows each year, in step with the drift, on every continent. It does not
affect the app: Terra is converted only for 2000-11 to 2002-07, when its orbit was held in place.

## 1. Overpass time

Median local solar time of filtered detections within 10° of the equator (hours; local time = UTC + lon/15):

| Year | Terra day | Terra night | Aqua day | Aqua night | S-NPP day | S-NPP night |
|---|---|---|---|---|---|---|
| 2013–2020 | 10.56–10.58 | 22.47–22.50 | 13.56–13.57 | 1.56–1.59 | 13.45–13.55 | 1.35–1.49 |
| 2021 | 10.52 | 22.44 | 13.57 | 1.57 | 13.45 | 1.38 |
| 2022 | 10.38 | 22.28 | 13.63 | 1.63 | 13.47 | 1.40 |
| 2023 | 10.16 | 22.05 | 13.82 | 1.82 | 13.48 | 1.41 |
| 2024 | 9.85 | 21.75 | 14.16 | 2.18 | 13.46 | 1.38 |
| 2025 | 9.46 | 21.32 | 14.71 | 2.68 | 13.49 | 1.42 |

Both MODIS satellites stopped holding their orbits around 2020–2021 and have drifted by about 70 minutes:
Terra earlier, Aqua later. S-NPP has not moved.

## 2. S-NPP / MODIS ratio by year

Yearly S-NPP burning cell-days divided by the MODIS satellite's, as % change from the 2013–2019 mean.
All cell-days, not only fair units, so outages add some noise (for example Aqua in 2022).

| Continent | Terra day 2022 / 23 / 24 / 25 | Terra night 2022 / 23 / 24 / 25 | Aqua day 2022 / 23 / 24 / 25 |
|---|---|---|---|
| Africa | +9 / +34 / +48 / +116 | +1 / −16 / −27 / −31 | −4 / −2 / −12 / +2 |
| Asia | −1 / +7 / +2 / +31 | −1 / −9 / −28 / 0 | +15 / −6 / −7 / −2 |
| Europe | +1 / +1 / +12 / +33 | −33 / −9 / −25 / −45 | −5 / −6 / −18 / −20 |
| North America | −3 / +5 / +13 / +24 | −5 / −26 / −34 / −28 | +2 / −8 / −19 / −13 |
| Oceania | +24 / −7 / +24 / +32 | +4 / −18 / −32 / −29 | +10 / −3 / −11 / +2 |
| South America | +2 / +3 / +13 / +50 | −7 / −24 / −25 / −33 | −6 / −3 / −18 / −11 |

- **Terra by day:** the ratio climbs year by year on every continent, most in Africa (+116 % in 2025), where
  savanna fires have a strong afternoon peak. An earlier pass sees fewer fires, so S-NPP sees relatively more.
- **Terra at night:** the ratio falls by about 25–35 %. The night pass moved from about 22:30 to 21:20, earlier
  in the evening, when more of the day's fires are still burning, so Terra sees relatively more.
- **Aqua by day:** changes are smaller and less regular (mostly −20 % to +15 %). Aqua drifted as far, but
  from 13:34 to 14:43, across the flat top of the daily fire cycle, so the number of fires it sees changes
  little. This matches Aqua's small held-out errors.

Year-to-year swings of ±15–25 % happen before the drift too (Asia and Oceania, 2019–2021), so single years
are noisy; the Terra trend is consistent across continents and grows with the drift.

## What follows

- The app is unaffected: Terra is converted only for 2000-11 to 2002-07, Aqua only for 2002-08 to 2012-01,
  both before any drift.
- The calibration years end in 2022, when Terra had drifted about 12 minutes and Aqua about 4. A refit with a
  later calibration window would mix orbits; 2013–2021 or 2013–2020 would be cleaner. Any such change needs a
  rule in PREREGISTRATION.md §7 first.
- Held-out 2023–2025 results for Terra (and, increasingly, Aqua) measure drift as well as the conversion, so
  they are a poor test of how the conversion works on the early years, as §1 already says for Aqua.
