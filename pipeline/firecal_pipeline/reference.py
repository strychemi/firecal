"""Reference implementation of the API contract (docs/api.md), in Python.

It is the oracle the Rust API is tested against: tests/test_api_parity.py sends the same requests to both
and compares the answers.
"""
import calendar
import json
import math

import duckdb
import h3
import numpy as np

from .config import Config

CATEGORIES = [(0.5, "much lower than usual"), (0.8, "lower than usual"), (1.25, "about usual"),
              (2.0, "higher than usual"), (math.inf, "much higher than usual")]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
MODEL_OF = {"terra_harmonized": "terra", "aqua_harmonized": "aqua"}
# Data published before continents (Argentina up to v11) is one continent, named as its cell-days are.
SINGLE = "study_area"


class NoExport(Exception):
    """The published data has no hotspot file (the global run): the export is refused."""
    MESSAGE = "The hotspot CSV is not available for this data yet; download hotspots from NASA FIRMS instead."

    def __init__(self):
        super().__init__(self.MESSAGE)


def validation_entries(v: dict) -> dict:
    """validation.json for one study area -> meta's per-satellite scores. A satellite that could not be fitted
    (Antarctica) has no entry."""
    out = {}
    for k, d in v.items():
        if "leave_one_year_out" not in d:
            continue
        # A conversion the pre-registered rule rejected is not used: report the scores of what is (no conversion).
        if d.get("decision", {}).get("kept", True):
            out[k] = {"whole_area_typical_error_pct": d["leave_one_year_out"]["whole_area"]["median"],
                      "small_area_typical_error_pct": d["leave_one_year_out"]["small_area_2deg"]["median"],
                      "backward_join_gap_pct": d["backward_join"]["gap_pct"]["all"], "converted": True}
        else:
            n = d["no_conversion"]["leave_one_year_out"]
            out[k] = {"whole_area_typical_error_pct": n["whole_area"]["median"],
                      "small_area_typical_error_pct": n["small_area_2deg"]["median"],
                      "backward_join_gap_pct": n["gap_pct"]["all"], "converted": False}
    return out


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


def fill_pieces(ring) -> list[list[tuple[float, float]]]:
    """The ring as pieces H3 can fill. H3 takes each edge the short way round the globe, so an area more than
    180 degrees of longitude wide would be filled as the rest of the world. A box that wide is split into strips
    at most 90 degrees wide; a polygon that wide is refused (docs/api.md)."""
    xs = [p[0] for p in ring]
    x0, x1 = min(xs), max(xs)
    # Checked before splitting, so an absurd box cannot ask for billions of strips.
    if not all(math.isfinite(c) for p in ring for c in p) or x1 - x0 > 360:
        raise ValueError("area must have finite coordinates and be at most 360 degrees of longitude wide")
    if x1 - x0 <= 180:
        return [ring]
    y0, y1 = ring[0][1], ring[2][1]
    if ring != [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]:
        raise ValueError("polygon is more than 180 degrees of longitude wide; use a box, or draw it in parts")
    k = math.ceil((x1 - x0) / 90)
    edges = [x0 + (x1 - x0) * i / k for i in range(k)] + [x1]
    return [[(a, y0), (b, y0), (b, y1), (a, y1), (a, y0)] for a, b in zip(edges, edges[1:])]


def area_cells(ring, resolutions, max_hex):
    polys = [h3.LatLngPoly([(lat, lon) for lon, lat in piece[:-1]]) for piece in fill_pieces(ring)]

    def fill(res):
        return set().union(*(h3.polygon_to_cells(poly, res) for poly in polys))

    for res in sorted(resolutions, reverse=True):  # finest first
        cells = fill(res)
        if 0 < len(cells) <= max_hex:
            return res, cells
    finest, coarsest = max(resolutions), min(resolutions)
    cells = fill(coarsest)
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
        if "continent" not in self.misses:
            self.misses["continent"] = SINGLE
        st = duckdb.sql(f"SELECT * FROM '{self.dir}/month_status.parquet'").df()
        if "continent" not in st:
            st["continent"] = SINGLE
        self.status = {(r.continent, f"{r.year:04d}-{r.month:02d}"): r for r in st.itertuples()}
        self.areas = sorted(st.continent.unique())
        # Older manifests have no `through`: the series then ends on its last month's last day.
        ey, em = map(int, self.manifest["series_end"].split("-"))
        self.through = self.manifest.get("through") or f"{ey:04d}-{em:02d}-{calendar.monthrange(ey, em)[1]:02d}"
        self.in_progress = self.manifest.get("in_progress")

    def continents(self) -> dict:
        """meta `continents`: per continent (Argentina: the one study area), whether it has a fitted model, its
        validation scores, and its own gaps and filled days. "World" (several continents only) has no model of
        its own: it is the month status used for a search with no fire."""
        m = self.manifest
        nested = self.validation.get("continents")
        out = {}
        for c in self.areas:
            info = m.get("continents", {}).get(c, {"fitted": True, "gaps": m["gaps"], "days_filled_by": m["days_filled_by"]})
            v = validation_entries(nested.get(c, {}) if nested is not None else self.validation)
            out[c] = {"fitted": bool(info["fitted"]) and (c == "World" or bool(v)), "validation": v,
                      "gaps": info["gaps"], "days_filled_by": info["days_filled_by"]}
        return out

    def meta(self) -> dict:
        m = self.manifest
        nested = "continents" in self.validation
        return {"data_version": self.version, "series_start": m["series_start"], "series_end": m["series_end"],
                "through": self.through, "in_progress": m.get("in_progress"),
                "unit": m["unit"], "region": m["region"], "eras": m["eras"], "gaps": m["gaps"],
                "days_filled_by": m["days_filled_by"],
                "validation": {} if nested else validation_entries(self.validation),
                "continents": self.continents(),
                "presets": [{k: p[k] for k in ("id", "name", "note", "bbox", "group") if k in p} for p in self.presets.values()],
                "export_limit": int(self.cfg["api"].get("max_export_rows", 250000)) if self.has_export else None}

    @property
    def has_export(self) -> bool:
        return (self.dir / "hotspots.parquet").exists()

    def continent_of(self, con, res: int):
        """The search's continent: the one holding most of its fire-days over the whole series (ties: the first
        name), whose model, error ranges and month status the search uses (docs/api.md). A search with no fire
        uses "World" (several continents) or the one study area. Returns (continent, its share or None)."""
        path = self.dir / f"continents_res{res}.parquet"
        if not path.exists():
            return self.areas[0], None
        rows = con.execute(f"""SELECT continent, sum(value)::DOUBLE FROM '{path}' JOIN sel USING (cell)
                               GROUP BY continent""").fetchall()
        total = sum(v for _, v in rows)
        if total <= 0:
            return ("World" if "World" in self.areas else self.areas[0]), None
        name, top = min(rows, key=lambda r: (-r[1], r[0]))
        return name, round(top / total, 3)

    def range_for(self, continent: str, source: str, value: float, area_km2: float):
        """80 % range: the search's continent's miss table of the size of area nearest the search's area on a
        log scale (PREREGISTRATION.md §7, 2026-11-15), and the bin containing value."""
        model = MODEL_OF.get(source)
        if model is None or value <= 0:
            return None, None
        m = self.misses[(self.misses.continent == continent) & (self.misses.model == model)]
        if m.empty:
            return None, None
        sizes = m.drop_duplicates("size")
        size = sizes.iloc[int(np.argmin(np.abs(np.log(sizes.area_km2.to_numpy()) - math.log(area_km2))))]["size"]
        t = m[(m["size"] == size) & (m.lo <= value) & (value < m.hi)].iloc[0]
        return value * math.exp(t.q10), value * math.exp(t.q90)

    def query(self, req: dict) -> dict:
        api = self.cfg["api"]
        ring = area_ring(req["area"], self.presets)
        res, cells = area_cells(ring, self.manifest["resolutions"], int(api["max_hexagons"]))
        ids = [h3.str_to_int(c) for c in cells]
        area_km2 = sum(h3.cell_area(c, unit="km^2") for c in cells)
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
        continent, share = self.continent_of(con, res)

        series = []
        for mo in month_range(self.manifest["series_start"], self.manifest["series_end"]):
            s, r = self.status[(continent, mo)], by_month.get(mo)
            value = float(r.value) if r is not None else 0.0
            lo, hi = self.range_for(continent, s.source, value, area_km2)
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
                "continent": continent, "continent_share": share,
                "start": start, "end": end, "months": shown,
                "stats": self.stats(compared, selected, baseline, to_date), "cells": hexes}

    def export(self, req: dict) -> str:
        """POST /api/export.csv: the filtered hotspots behind a search, as CSV text."""
        api = self.cfg["api"]
        ring = area_ring(req["area"], self.presets)
        res, cells = area_cells(ring, self.manifest["resolutions"], int(api["max_hexagons"]))
        if not self.has_export:
            raise NoExport()
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
                "through": to_date[0] if to_date else None, "trend": trend(series, selected)}


TREND_MIN_YEARS = 10


def norm_cdf(z: float) -> float:
    """Standard normal CDF through erf by Abramowitz and Stegun 7.1.26, as in the Rust API."""
    x = abs(z) / math.sqrt(2.0)
    t = 1.0 / (1.0 + 0.3275911 * x)
    poly = ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t
    erf = 1.0 - poly * math.exp(-x * x)
    return 0.5 * (1.0 + erf) if z >= 0 else 0.5 * (1.0 - erf)


def trend(series, selected: str) -> dict:
    """The selected calendar month over the complete years: Theil-Sen slope as a share of the median,
    and the two-sided Mann-Kendall test with the tie correction. Mirrors `trend` in api/src/query.rs."""
    mon = selected[5:]
    mname = MONTHS[int(mon) - 1]
    pts = [(float(m["month"][:4]), m["value"]) for m in series if m["month"][5:] == mon and m["complete"]]
    n = len(pts)

    def none(sentence):
        return {"years": n, "first": None, "last": None, "slope": None, "pct_per_year": None, "p": None,
                "direction": None, "clear": False, "sentence": sentence}

    if n < TREND_MIN_YEARS:
        return none(f"Too few complete years of {mname} here ({n}) to judge a trend; it needs {TREND_MIN_YEARS}.")
    first, last = int(pts[0][0]), int(pts[-1][0])
    if all(v == 0 for _, v in pts):
        return none(f"No fire was detected here in {mname} in any of the {n} years from {first} to {last}.")
    slopes, s_stat = [], 0
    for i in range(n):
        for j in range(i + 1, n):
            d = pts[j][1] - pts[i][1]
            slopes.append(d / (pts[j][0] - pts[i][0]))
            s_stat += (d > 0) - (d < 0)
    slope = float(np.median(slopes))
    vals = sorted(v for _, v in pts)
    typical = float(np.median(vals))
    ties = 0.0
    k = 0
    while k < n:
        e = k
        while e + 1 < n and vals[e + 1] == vals[k]:
            e += 1
        t = e - k + 1
        ties += t * (t - 1) * (2 * t + 5)
        k = e + 1
    var = (n * (n - 1) * (2 * n + 5) - ties) / 18.0
    z = 0.0 if var <= 0 else (s_stat - 1) / math.sqrt(var) if s_stat > 0 else (s_stat + 1) / math.sqrt(var) if s_stat < 0 else 0.0
    p = min(1.0, max(0.0, 2.0 * (1.0 - norm_cdf(abs(z)))))
    pct = slope / typical * 100.0 if typical > 0 else None
    rate = f"about {abs(pct):.1f} % a year" if pct is not None else f"about {abs(slope):.1f} fire-days a year"
    clear = p < 0.05 and slope != 0
    direction = "rising" if slope > 0 else "falling" if slope < 0 else "flat"
    ps = "p\u00a0<\u00a00.001" if p < 0.001 else f"p\u00a0=\u00a0{p:.3f}"  # non-breaking: one line
    span = f"From {first} to {last}"
    if clear:
        verb = "risen" if slope > 0 else "fallen"
        sentence = f"{span}, {mname} fire-days here have {verb} {rate}: a steady change, unlikely to be chance ({n} years, {ps})."
    elif slope == 0:
        sentence = f"{span}, {mname} fire-days here show no trend ({n} years, {ps})."
    else:
        way = "up" if slope > 0 else "down"
        sentence = (f"{span}, {mname} fire-days here show no clear trend: a drift of {rate} {way} "
                    f"is within normal year-to-year variation ({n} years, {ps}).")
    return {"years": n, "first": first, "last": last, "slope": round(slope, 2),
            "pct_per_year": None if pct is None else round(pct, 2), "p": round(p, 4), "direction": direction,
            "clear": clear, "sentence": sentence}
