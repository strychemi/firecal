"""Reference implementation of the API contract (docs/api.md), in Python.

Two uses: it writes example responses the frontend is built against (web/static/example/), and it
is the oracle the Rust API is tested against (tests compare both on the same requests).
"""
import json
import math

import duckdb
import h3
import numpy as np

from .config import ROOT, Config

CATEGORIES = [(0.5, "much lower than usual"), (0.8, "lower than usual"), (1.25, "about usual"),
              (2.0, "higher than usual"), (math.inf, "much higher than usual")]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
MODEL_OF = {"terra_harmonized": "terra", "aqua_harmonized": "aqua"}


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def area_ring(area: dict, presets: dict) -> list[tuple[float, float]]:
    """Area -> closed ring of (lon, lat)."""
    if "preset" in area:
        area = {"bbox": presets[area["preset"]]["bbox"]}
    if "bbox" in area:
        x0, y0, x1, y1 = area["bbox"]
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    if "polygon" in area:
        ring = [tuple(p) for p in area["polygon"]]
        return ring if ring[0] == ring[-1] else ring + [ring[0]]
    if "point" in area:
        lon, lat = area["point"]
        r = float(area["radius_km"])
        dlat = r / 111.32
        dlon = r / (111.32 * math.cos(math.radians(lat)))
        ring = [(lon + dlon * math.cos(2 * math.pi * i / 64), lat + dlat * math.sin(2 * math.pi * i / 64)) for i in range(64)]
        return ring + [ring[0]]
    raise ValueError("area needs one of: preset, bbox, polygon, point + radius_km")


def area_cells(ring, resolutions, max_hex):
    poly = h3.LatLngPoly([(lat, lon) for lon, lat in ring[:-1]])
    for res in sorted(resolutions, reverse=True):  # finest first
        cells = h3.polygon_to_cells(poly, res)
        if 0 < len(cells) <= max_hex:
            return res, cells
    finest, coarsest = max(resolutions), min(resolutions)
    cells = h3.polygon_to_cells(poly, coarsest)
    if cells:
        return coarsest, cells
    lon = sum(p[0] for p in ring[:-1]) / (len(ring) - 1)
    lat = sum(p[1] for p in ring[:-1]) / (len(ring) - 1)
    return finest, {h3.latlng_to_cell(lat, lon, finest)}


def month_range(start: str, end: str) -> list[str]:
    y, m = map(int, start.split("-"))
    ye, me = map(int, end.split("-"))
    out = []
    while (y, m) <= (ye, me):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


class Reference:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        gold = cfg.out / "gold"
        self.version = (gold / "CURRENT").read_text().strip()
        self.dir = gold / self.version
        self.manifest = json.loads((self.dir / "manifest.json").read_text())
        self.validation = json.loads((self.dir / "validation.json").read_text())
        self.presets = {p["id"]: p for p in cfg.raw.get("presets", [])}
        self.misses = duckdb.sql(f"SELECT * FROM '{self.dir}/misses.parquet'").df()
        st = duckdb.sql(f"SELECT * FROM '{self.dir}/month_status.parquet'").df()
        self.status = {f"{r.year:04d}-{r.month:02d}": r for r in st.itertuples()}

    def meta(self) -> dict:
        m = self.manifest
        v = {k: {"whole_area_typical_error_pct": d["leave_one_year_out"]["whole_area"]["median"],
                 "small_area_typical_error_pct": d["leave_one_year_out"]["small_area_2deg"]["median"],
                 "backward_join_gap_pct": d["backward_join"]["gap_pct"]["all"]} for k, d in self.validation.items()}
        return {"data_version": self.version, "series_start": m["series_start"], "series_end": m["series_end"],
                "unit": m["unit"], "region": m["region"], "eras": m["eras"], "gaps": m["gaps"],
                "days_filled_by": m["days_filled_by"], "validation": v,
                "presets": [{k: p[k] for k in ("id", "name", "note", "bbox")} for p in self.presets.values()]}

    def range_for(self, source: str, value: float):
        model = MODEL_OF.get(source)
        if model is None or value <= 0:
            return None, None
        t = self.misses[(self.misses.model == model) & (self.misses.lo <= value) & (value < self.misses.hi)].iloc[0]
        return value * math.exp(t.q10), value * math.exp(t.q90)

    def query(self, req: dict) -> dict:
        api = self.cfg["api"]
        ring = area_ring(req["area"], self.presets)
        res, cells = area_cells(ring, self.manifest["resolutions"], int(api["max_hexagons"]))
        ids = [h3.str_to_int(c) for c in cells]
        con = duckdb.connect()
        con.execute("CREATE TABLE sel(cell UBIGINT)")
        con.executemany("INSERT INTO sel VALUES (?)", [[i] for i in ids])
        sums = con.execute(f"""
            SELECT year, month, sum(value) AS value, sum(raw) AS raw, sum(detections) AS detections,
                   sum(frp) AS frp, count(DISTINCT cell) AS hexes
            FROM '{self.dir}/monthly_res{res}.parquet' JOIN sel USING (cell) GROUP BY ALL""").df()
        active = con.execute(f"SELECT count(DISTINCT cell) FROM '{self.dir}/monthly_res{res}.parquet' JOIN sel USING (cell)").fetchone()[0]
        by_month = {f"{r.year:04d}-{r.month:02d}": r for r in sums.itertuples()}

        series = []
        for mo in month_range(self.manifest["series_start"], self.manifest["series_end"]):
            s, r = self.status[mo], by_month.get(mo)
            value = float(r.value) if r is not None else 0.0
            lo, hi = self.range_for(s.source, value)
            series.append({"month": mo, "source": s.source, "value": round(value, 2),
                           "lower": None if lo is None else round(lo, 2), "upper": None if hi is None else round(hi, 2),
                           "raw": int(r.raw) if r is not None else 0,
                           "detections": int(r.detections) if r is not None else 0,
                           "frp": round(float(r.frp), 1) if r is not None else 0.0,
                           "days": int(s.days), "days_with_data": int(s.days_with_data),
                           "complete": bool(s.days_with_data == s.days)})

        start = req.get("start") or self.manifest["series_start"]
        end = req.get("end") or self.manifest["series_end"]
        selected = req.get("month") or end
        baseline = req.get("baseline", "median")
        shown = [m for m in series if start <= m["month"] <= end]
        return {"data_version": self.version,
                "area": {"resolution": res, "hexagons": len(ids), "active_hexagons": int(active)},
                "start": start, "end": end, "months": shown,
                "stats": self.stats(series, selected, baseline)}

    def stats(self, series, selected: str, baseline: str) -> dict:
        cur = next(m for m in series if m["month"] == selected)
        mon = selected[5:]
        others = [m for m in series if m["month"][5:] == mon and m["month"] != selected and m["complete"]]
        vals = np.array([m["value"] for m in others])
        base = float(np.median(vals) if baseline == "median" else vals.mean()) if len(vals) else 0.0
        ratio = cur["value"] / base if base > 0 else None
        rank = 1 + int((vals > cur["value"]).sum())
        pct = round(float((vals < cur["value"]).mean() * 100), 1) if len(vals) else None
        category = None if ratio is None else next(c for t, c in CATEGORIES if ratio < t)
        name = f"{MONTHS[int(mon) - 1]} {selected[:4]}"
        word = "median" if baseline == "median" else "average"
        if cur["value"] == 0 and base == 0:
            sentence = f"No fire was detected in {name}, and the same month is usually fire-free here."
        elif ratio is None:
            sentence = f"{name} had {cur['value']:,.0f} fire-days; the same month is usually fire-free here."
        else:
            sentence = (f"{name} had {cur['value']:,.0f} fire-days, {ratio:.1f}× the usual "
                        f"{MONTHS[int(mon) - 1]} ({word} of {len(vals)} years), "
                        f"{ordinal(rank)} highest of {len(vals) + 1} years.")
        return {"month": selected, "value": cur["value"], "lower": cur["lower"], "upper": cur["upper"],
                "source": cur["source"], "baseline": baseline, "baseline_value": round(base, 2),
                "baseline_years": [int(m["month"][:4]) for m in others],
                "ratio": None if ratio is None else round(ratio, 3), "rank": rank, "of": len(vals) + 1,
                "percentile": pct, "category": category, "sentence": sentence}


def write_examples(cfg: Config) -> None:
    ref = Reference(cfg)
    out = ROOT / "web" / "static" / "example"
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps(ref.meta(), indent=1))
    for pid in ref.presets:
        (out / f"query-{pid}.json").write_text(json.dumps(ref.query({"area": {"preset": pid}})))
    print("examples written to", out, flush=True)
