"""Reference implementation of the API contract (docs/api.md), in Python.

Two uses: it writes example responses the frontend is built against (web/static/example/), and it
is the oracle the Rust API is tested against (tests compare both on the same requests).
"""
import calendar
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


def days_label(mname: str, days: int) -> str:
    return f"{mname} 1" if days == 1 else f"{mname} 1–{days}"


def month_range(start: str, end: str) -> list[str]:
    y, m = map(int, start.split("-"))
    ye, me = map(int, end.split("-"))
    out = []
    while (y, m) <= (ye, me):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


EXPORT_HEADER = ("hex_id,latitude,longitude,acq_date,acq_time,local_solar_date,satellite,instrument,daynight,"
                 "confidence,frp,in_calendar")


class TooManyHotspots(Exception):
    def __init__(self, rows: int, limit: int):
        super().__init__(f"This search has {rows:,} hotspots; one file holds at most {limit:,}. Narrow the dates or the area.")
        self.rows, self.limit = rows, limit


def csv_field(s: str) -> str:
    return '"' + s.replace('"', '""') + '"' if any(c in s for c in ',"\n') else s


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
        # Older manifests have no `through`: the series then ends on its last month's last day.
        ey, em = map(int, self.manifest["series_end"].split("-"))
        self.through = self.manifest.get("through") or f"{ey:04d}-{em:02d}-{calendar.monthrange(ey, em)[1]:02d}"
        self.in_progress = self.manifest.get("in_progress")

    def meta(self) -> dict:
        m = self.manifest
        v = {}
        for k, d in self.validation.items():
            # A conversion the pre-registered rule rejected is not used: report the scores of what is (no conversion).
            if d.get("decision", {}).get("kept", True):
                v[k] = {"whole_area_typical_error_pct": d["leave_one_year_out"]["whole_area"]["median"],
                        "small_area_typical_error_pct": d["leave_one_year_out"]["small_area_2deg"]["median"],
                        "backward_join_gap_pct": d["backward_join"]["gap_pct"]["all"], "converted": True}
            else:
                n = d["no_conversion"]["leave_one_year_out"]
                v[k] = {"whole_area_typical_error_pct": n["whole_area"]["median"],
                        "small_area_typical_error_pct": n["small_area_2deg"]["median"],
                        "backward_join_gap_pct": n["gap_pct"]["all"], "converted": False}
        return {"data_version": self.version, "series_start": m["series_start"], "series_end": m["series_end"],
                "through": self.through, "in_progress": m.get("in_progress"),
                "unit": m["unit"], "region": m["region"], "eras": m["eras"], "gaps": m["gaps"],
                "days_filled_by": m["days_filled_by"], "validation": v,
                "presets": [{k: p[k] for k in ("id", "name", "note", "bbox")} for p in self.presets.values()],
                "export_limit": int(self.cfg["api"].get("max_export_rows", 250000))}

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
        start = req.get("start") or self.manifest["series_start"]
        end = req.get("end") or self.manifest["series_end"]
        selected = req.get("month") or end
        ym = lambda m: int(m[:4]) * 100 + int(m[5:])
        per_cell = con.execute(f"""
            SELECT cell, coalesce(sum(value) FILTER (WHERE year::INTEGER * 100 + month = ?), 0) AS in_month,
                   coalesce(sum(value) FILTER (WHERE year::INTEGER * 100 + month BETWEEN ? AND ?), 0) AS in_range
            FROM '{self.dir}/monthly_res{res}.parquet' JOIN sel USING (cell) GROUP BY cell""",
            [ym(selected), ym(start), ym(end)]).fetchall()
        hexes = sorted(({"h3": h3.int_to_str(c), "month": round(float(m), 2), "range": round(float(r), 2)}
                        for c, m, r in per_cell if m > 0 or r > 0), key=lambda h: h["h3"])
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
                           "complete": bool(s.days_with_data == s.days),
                           "in_progress": bool(self.in_progress and mo == self.in_progress["month"])})

        # The in-progress month is compared on days 1..D: every year's same-month value becomes its month to date.
        compared, to_date = series, None
        if self.in_progress and selected == self.in_progress["month"]:
            mtd = dict(con.execute(f"SELECT year, sum(value) FROM '{self.dir}/mtd_res{res}.parquet' JOIN sel USING (cell) GROUP BY year").fetchall())
            compared = [{**m, "value": round(float(mtd.get(int(m["month"][:4]), 0.0)), 2)} if m["month"][5:] == selected[5:] else m
                        for m in series]
            to_date = (self.through, int(self.in_progress["days"]))

        baseline = req.get("baseline", "median")
        shown = [m for m in series if start <= m["month"] <= end]
        return {"data_version": self.version,
                "area": {"resolution": res, "hexagons": len(ids), "active_hexagons": int(active),
                         "ring": [[round(x, 5), round(y, 5)] for x, y in ring]},
                "start": start, "end": end, "months": shown,
                "stats": self.stats(compared, selected, baseline, to_date), "cells": hexes}

    def export(self, req: dict) -> str:
        """POST /api/export.csv: the filtered hotspots behind a search, as CSV text."""
        api = self.cfg["api"]
        ring = area_ring(req["area"], self.presets)
        res, cells = area_cells(ring, self.manifest["resolutions"], int(api["max_hexagons"]))
        start = req.get("start") or self.manifest["series_start"]
        end = req.get("end") or self.manifest["series_end"]
        ey, em = int(end[:4]), int(end[5:])
        upto = f"{ey + 1:04d}-01-01" if em == 12 else f"{ey:04d}-{em + 1:02d}-01"
        con = duckdb.connect()
        con.execute("CREATE TABLE sel(cell UBIGINT)")
        con.executemany("INSERT INTO sel VALUES (?)", [[h3.str_to_int(c)] for c in cells])
        frm = (f"FROM '{self.dir}/hotspots.parquet' h JOIN sel ON h.cell{res} = sel.cell "
               "WHERE h.local_date >= CAST(? AS DATE) AND h.local_date < CAST(? AS DATE)")
        n = con.execute(f"SELECT count(*) {frm}", [f"{start}-01", upto]).fetchone()[0]
        limit = int(api.get("max_export_rows", 250000))
        if n > limit:
            raise TooManyHotspots(n, limit)
        rows = con.execute(f"""
            SELECT h.cell{res}, h.lat, h.lon, strftime(h.acq_utc, '%Y-%m-%d'), strftime(h.acq_utc, '%H%M'),
                   strftime(h.local_date, '%Y-%m-%d'), h.sat, h.dn, h.confidence, h.frp, h.in_calendar
            {frm} ORDER BY h.acq_utc, h.lat, h.lon, h.sat""", [f"{start}-01", upto]).fetchall()
        out = [EXPORT_HEADER]
        for cell, lat, lon, d, t, ld, sat, dn, conf, frp, used in rows:
            hex_id = h3.int_to_str(cell)
            if not h3.is_valid_cell(hex_id):
                raise ValueError(f"hotspots.parquet has an invalid H3 cell {cell}")
            inst = "MODIS" if sat in ("terra", "aqua") else "VIIRS"
            out.append(f"{hex_id},{lat:.5f},{lon:.5f},{d},{t},{ld},{sat},{inst},{csv_field(dn)},"
                       f"{csv_field(conf or '')},{'' if frp is None else f'{frp:.1f}'},{'true' if used else 'false'}")
        return "\n".join(out) + "\n"

    def stats(self, series, selected: str, baseline: str, to_date=None) -> dict:
        """to_date = (through, D) when series values are days 1..D of the in-progress month."""
        cur = next(m for m in series if m["month"] == selected)
        mon = selected[5:]
        others = [m for m in series if m["month"][5:] == mon and m["month"] != selected and m["complete"]]
        vals = np.array([m["value"] for m in others])
        base = float(np.median(vals) if baseline == "median" else vals.mean()) if len(vals) else 0.0
        ratio = cur["value"] / base if base > 0 else None
        rank = 1 + int((vals > cur["value"]).sum())
        pct = round(float((vals < cur["value"]).mean() * 100), 1) if len(vals) else None
        category = None if ratio is None else next(c for t, c in CATEGORIES if ratio < t)
        mname = MONTHS[int(mon) - 1]
        if to_date:
            usual, same = days_label(mname, to_date[1]), "the same days are"
            name = f"{usual}, {selected[:4]}"
        else:
            usual, same, name = mname, "the same month is", f"{mname} {selected[:4]}"
        word = "median" if baseline == "median" else "average"
        if cur["value"] == 0 and base == 0:
            sentence = f"No fire was detected in {name}, and {same} usually fire-free here."
        elif ratio is None:
            sentence = f"{name} had {cur['value']:,.0f} fire-days; {same} usually fire-free here."
        else:
            sentence = (f"{name} had {cur['value']:,.0f} fire-days, {ratio:.1f}× the usual "
                        f"{usual} ({word} of {len(vals)} years), "
                        f"{ordinal(rank)} highest of {len(vals) + 1} years.")
        return {"month": selected, "value": cur["value"], "lower": cur["lower"], "upper": cur["upper"],
                "source": cur["source"], "baseline": baseline, "baseline_value": round(base, 2),
                "baseline_years": [int(m["month"][:4]) for m in others],
                "ratio": None if ratio is None else round(ratio, 3), "rank": rank, "of": len(vals) + 1,
                "percentile": pct, "category": category, "sentence": sentence,
                "through": to_date[0] if to_date else None}


def write_examples(cfg: Config) -> None:
    ref = Reference(cfg)
    out = ROOT / "web" / "static" / "example"
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps(ref.meta(), indent=1))
    for pid in ref.presets:
        resp = ref.query({"area": {"preset": pid}})
        if ref.in_progress:
            # The browser cannot redo the days-1..D comparison from monthly totals, so save it for both baselines.
            month = ref.in_progress["month"]
            resp["to_date_stats"] = {b: ref.query({"area": {"preset": pid}, "month": month, "baseline": b})["stats"]
                                     for b in ("median", "mean")}
        (out / f"query-{pid}.json").write_text(json.dumps(resp))
    print("examples written to", out, flush=True)
