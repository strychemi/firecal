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

   Steps: `ingest` (zips → `data/bronze/`), `cells` (burning cell-days → `data/silver/`), `fit` (multipliers and validation → `data/model/`), `publish` (→ `data/gold/vN/`, and `data/gold/CURRENT`), `example` (example API responses → `web/static/example/`).

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

## Data credits

Fire data: NASA FIRMS active-fire archives, MODIS Collection 6.1 (MCD14ML, Terra and Aqua) and VIIRS 375 m (S-NPP and NOAA-20).
