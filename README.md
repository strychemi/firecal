# firecal

Harmonizing 26 years of NASA MODIS & VIIRS satellite fire records into an unbroken, cross-calibrated burning activity calendar.

NASA Space Apps 2026 · *Harmonization of MODIS and VIIRS Hot Spots*. Prototype: Argentina study region, November 2000 to two days ago (recent days from the FIRMS API).

| Document | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design |
| [PREREGISTRATION.md](PREREGISTRATION.md) | Rules for judging any change to the method, fixed in advance |
| [docs/api.md](docs/api.md) | API contract |
| [AI_LOG.md](AI_LOG.md) | How AI tools were used |

## Run it

Requirements: [mise](https://mise.jdx.dev), which installs the pinned Node, pnpm, Rust, uv and Python from `mise.toml`, plus the FIRMS yearly "all countries" archives (`modis_YYYY_all_countries.zip`, `viirs-snpp_…`, `viirs-jpss1_…`) in `data/`.

```bash
mise install        # the pinned tools
mise run setup      # frontend and pipeline dependencies
mise run data       # build the published data (about a minute for Argentina)
mise run web:build  # build the frontend
mise run api        # build and run the API, which serves the app: http://127.0.0.1:8080
```

`mise tasks` lists every task. The pipeline steps behind `data` are `ingest` (zips, plus any recent days from `download` → `data/bronze/`), `cells` (burning cell-days → `data/silver/`), `fit` (multipliers and validation → `data/model/`), `publish` (→ `data/gold/vN/`, and `data/gold/CURRENT`) and `example` (example API responses → `web/static/example/`).

**Recent data (optional).** The zips end with `last_year` in `firecal.toml`. To add the days since, up to two days ago:
1. Get a free [FIRMS MAP_KEY](https://firms.modaps.eosdis.nasa.gov/api/map_key/).
2. Put it in `.env` at the repo root (`cp .env.example .env`; `.env` is git-ignored).
3. Run `mise run refresh`. It downloads the new days, rebuilds and publishes a new data version (a running API switches to it within 10 seconds), and deletes all but the newest three versions (`keep_versions` in `firecal.toml`; each is about 190 MB). Each run's log is in `data/logs/`.

`download` writes one CSV per product and UTC day to `data/firms_api/`: standard-processing data where FIRMS has it, near-real-time after that. Running `refresh` again brings the series up to date. It fetches only new days, the last few near-real-time days again, and days whose standard-processing version has since appeared. The key is used only in the requests to FIRMS; mise does not load `.env`. When the series ends partway through a month, the app compares that month so far with the same days in earlier years.

**Frontend work without the API:** `mise run web:examples`.

**Without mise:** each task in `mise.toml` is a plain command you can run yourself, for example `cd pipeline && uv run python -m firecal_pipeline all`.

## Checks

With the API running, `mise run parity` sends the same requests to the Rust API and to the Python reference implementation and compares the answers.

Before a pull request, run all checks:

```bash
mise run check      # or scripts/check.sh
```

It runs everything on this machine, in about half a minute:
1. Type-checks and builds the frontend.
2. Builds the API.
3. Runs the whole pipeline on a small sample, then compares the API with the reference on it.
4. Compares them again on the full published data.

The sample is real FIRMS rows for a small box near the Paraná Delta, including recent near-real-time days. It's built from your local `data/` the first time (`--fresh-sample` rebuilds it) and is git-ignored, so no fire data goes into the repo. The pipeline and the API both read `FIRECAL_ROOT` to find it (`pipeline/tests/fixture/`). The script exits non-zero if any check fails.

## Data credits

Fire data: NASA FIRMS active-fire archives, MODIS Collection 6.1 (MCD14ML, Terra and Aqua) and VIIRS 375 m (S-NPP and NOAA-20).

Basemap: [OpenFreeMap](https://openfreemap.org/) tiles, © [OpenMapTiles](https://openmaptiles.org/), data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors. Map libraries: MapLibre GL JS (BSD-3-Clause), deck.gl (MIT), Terra Draw (MIT), h3-js (Apache-2.0).
