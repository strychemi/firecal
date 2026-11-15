# firecal

Harmonizing 26 years of NASA MODIS & VIIRS satellite fire records into an unbroken, cross-calibrated burning activity calendar.

NASA Space Apps 2026 · *Harmonization of MODIS and VIIRS Hot Spots*. Prototype: Argentina study region, November 2000 to December 2025.

| Document | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design |
| [PREREGISTRATION.md](PREREGISTRATION.md) | Rules for judging any change to the method, fixed in advance |
| [docs/api.md](docs/api.md) | API contract |
| [AI_LOG.md](AI_LOG.md) | How AI tools were used |

## Run it

Requirements: [uv](https://docs.astral.sh/uv/), Rust (cargo), Node 24 with pnpm, and the FIRMS yearly "all countries" archives (`modis_YYYY_all_countries.zip`, `viirs-snpp_…`, `viirs-jpss1_…`) in `data/`.

1. Build the data (about a minute for Argentina):

   ```bash
   cd pipeline && uv run python -m firecal_pipeline all
   ```

   Steps: `ingest` (zips, plus any recent days from `download` → `data/bronze/`), `cells` (burning cell-days → `data/silver/`), `fit` (multipliers and validation → `data/model/`), `publish` (→ `data/gold/vN/`, and `data/gold/CURRENT`), `example` (example API responses → `web/static/example/`).

   Recent data (optional): the zips end with `last_year` in `firecal.toml`. To add the days since, up to two days ago, get a free [FIRMS MAP_KEY](https://firms.modaps.eosdis.nasa.gov/api/map_key/), put it in `.env` at the repo root (`cp .env.example .env`; `.env` is git-ignored), then download and rebuild:

   ```bash
   cd pipeline && uv run python -m firecal_pipeline download && uv run python -m firecal_pipeline all
   ```

   `download` writes one CSV per product and UTC day to `data/firms_api/`, using standard-processing data where FIRMS has it and near-real-time after that. Re-run it to bring the series up to date: it fetches only new days, the last few near-real-time days again, and days whose standard-processing version has since appeared. The key is used only in the requests to FIRMS. When the series ends partway through a month, the app compares that month so far with the same days in earlier years.

2. Build the frontend:

   ```bash
   cd web && pnpm install && pnpm build
   ```

3. Run the API, which also serves the built frontend:

   ```bash
   cargo run --release --manifest-path api/Cargo.toml
   ```

   Open http://127.0.0.1:8080.

For frontend work without the API: `cd web && VITE_EXAMPLES=1 pnpm dev`.

## Check the API against the reference

```bash
cd pipeline && uv run python tests/test_api_parity.py
```

With the API running, this sends the same requests to the Rust API and to the Python reference implementation and compares the answers.

## Run all checks before a pull request

```bash
scripts/check.sh
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
