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

Requirements: [mise](https://mise.jdx.dev), which installs the pinned Node, pnpm, Rust, uv and Python from `mise.toml`, plus the FIRMS yearly "all countries" archives (`modis_YYYY_all_countries.zip`, `viirs-snpp_…`, `viirs-jpss1_…`) in `data/`, plus the MODIS labels and granule records below.

**MODIS labels.** FIRMS's MODIS archive carries older (version-2) hotspot type labels through 2017, so the pipeline takes the labels for 2000–2017 from the producer's version-3 monthly files (PREREGISTRATION.md §7). They are NASA data from the MODIS fire team's server at the University of Maryland, about 1.3 GB, reached by SFTP with the login the team publishes in its [user guide](https://www.earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf). Section 4.3, "University of Maryland SFTP Server", gives the login:

```bash
mkdir -p data/mcd14ml
sftp -o IdentityAgent=none -o PubkeyAuthentication=no fire@fuoco.geog.umd.edu
# at sftp>:  cd data/MODIS/C6/MCD14ML   lcd data/mcd14ml
#            get MCD14ML.200*.006.03.txt.gz   get MCD14ML.201[0-7]*.006.03.txt.gz   bye
```

`ingest` stops with an error if a year's files are missing, or if under 99.9 % of FIRMS rows find their label.

**Granule records.** The fit uses only places and times both satellites actually observed (PREREGISTRATION.md §7). Which ones those are comes from NASA's public records of each satellite's 5- and 6-minute swath slices ("granules"), downloaded once with `mise run granules`: about 600 requests to NASA's Common Metadata Repository, no login, roughly 10 minutes, saved to `data/granules/`. `cells` stops with an error if a month is missing, or if more than 0.1 % of a satellite's detections fall outside its recorded footprints.

```bash
mise install        # the pinned tools
mise run setup      # frontend and pipeline dependencies
mise run granules   # NASA granule records for the fit (once)
mise run data       # build the published data (about a minute for Argentina)
mise run web:build  # build the frontend
mise run api        # build and run the API, which serves the app: http://127.0.0.1:8080
```

`mise tasks` lists every task. The pipeline steps behind `data` are `ingest` (zips, plus any recent days from `download` → `data/bronze/`), `cells` (burning cell-days, and the places and times each satellite observed → `data/silver/`), `fit` (multipliers and validation → `data/model/`) and `publish` (→ `data/gold/vN/`, and `data/gold/CURRENT`).

**Recent data (optional).** The zips end with `last_year` in `firecal.toml`. To add the days since, up to two days ago:
1. Get a free [FIRMS MAP_KEY](https://firms.modaps.eosdis.nasa.gov/api/map_key/).
2. Put it in `.env` at the repo root (`cp .env.example .env`; `.env` is git-ignored).
3. Run `mise run refresh`. It downloads the new days, rebuilds and publishes a new data version (a running API switches to it within 10 seconds), and deletes all but the newest three versions (`keep_versions` in `firecal.toml`; each is about 190 MB). Each run's log is in `data/logs/`.

`download` writes one CSV per product and UTC day to `data/firms_api/`: standard-processing data where FIRMS has it, near-real-time after that. Running `refresh` again brings the series up to date. It fetches only new days, the last few near-real-time days again, and days whose standard-processing version has since appeared. The key is used only in the requests to FIRMS; mise does not load `.env`. When the series ends partway through a month, the app compares that month so far with the same days in earlier years.

**Frontend work:** `mise run web:dev` serves the app with live reload and sends its API requests to the API on :8080, so run `mise run api` alongside it. The app has no data of its own.

**Without mise:** each task in `mise.toml` is a plain command you can run yourself, for example `cd pipeline && uv run python -m firecal_pipeline all`.

## Checks

With the API running, `mise run parity` sends the same requests to the Rust API and to the Python reference implementation and compares the answers. `mise run web:test` runs the browser tests against it (after `mise run web:build`): they load the app and check every number on screen against the API's answer for the same request.

Before a pull request, run all checks:

```bash
mise run check      # or scripts/check.sh
```

It runs everything on this machine, in about half a minute:
1. Type-checks and builds the frontend.
2. Builds the API.
3. Runs the whole pipeline on a small sample, then compares the API with the reference on it and runs the browser tests against the API serving the app.
4. Does both again on the full published data.

The sample is real FIRMS rows for a small box near the Paraná Delta, including recent near-real-time days. It's built from your local `data/` the first time (`--fresh-sample` rebuilds it) and is git-ignored, so no fire data goes into the repo. The pipeline and the API both read `FIRECAL_ROOT` to find it (`pipeline/tests/fixture/`). The script exits non-zero if any check fails.

## Data credits

Fire data: NASA FIRMS active-fire archives: MODIS MCD14ML Collection 6 and 6.1 (Terra and Aqua) and VIIRS 375 m Collection 2 (S-NPP and NOAA-20). MODIS hotspot types for 2000–2017 from the MCD14ML Collection 6 version 3 files of the MODIS fire team, University of Maryland (Giglio, L., Schroeder, W. & Justice, C. O. (2016), The Collection 6 MODIS active fire detection algorithm and fire products, *Remote Sensing of Environment* 178, 31–41). NASA data, shared without restriction under the [EOSDIS Data Use and Citation Guidance](https://www.earthdata.nasa.gov/data/catalog/lancemodis-mcd14dl-6.1nrt).

Basemap: [OpenFreeMap](https://openfreemap.org/) tiles, © [OpenMapTiles](https://openmaptiles.org/), data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors. Map libraries: MapLibre GL JS (BSD-3-Clause), deck.gl (MIT), Terra Draw (MIT), h3-js (Apache-2.0).
