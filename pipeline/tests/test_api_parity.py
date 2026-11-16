"""Compare the Rust API with the Python reference implementation on the same requests.

Needs the API running (cargo run --release --manifest-path api/Cargo.toml).
Run: uv run python tests/test_api_parity.py [http://127.0.0.1:8080]
"""
import json
import math
import sys
import urllib.error
import urllib.request

from firecal_pipeline.config import Config
from firecal_pipeline.reference import NoExport, Reference, TooManyHotspots

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"

REQUESTS = [
    {"area": {"preset": "argentina-box"}},
    {"area": {"preset": "parana-delta"}, "month": "2008-04"},
    {"area": {"preset": "chaco"}, "month": "2020-09", "baseline": "mean", "start": "2010-01", "end": "2021-12"},
    {"area": {"preset": "patagonia-andes"}, "month": "2002-02"},
    {"area": {"bbox": [-65.0, -30.0, -60.0, -26.0]}, "month": "2004-09"},
    {"area": {"bbox": [-58.6, -34.7, -58.3, -34.5]}, "month": "2012-08"},
    {"area": {"bbox": [-58.45, -34.62, -58.44, -34.61]}},
    {"area": {"point": [-71.3, -41.13], "radius_km": 40}, "month": "2021-03"},
    {"area": {"point": [-60.0, -24.0], "radius_km": 250}, "month": "2001-06"},
    {"area": {"polygon": [[-62, -32], [-59, -31], [-58, -34], [-61.5, -35]]}, "month": "2011-08"},
    # The in-progress month (the series' last; compared on days 1..D) and the same month a year earlier.
    {"area": {"preset": "chaco"}, "baseline": "mean"},
    {"area": {"bbox": [-58.6, -34.7, -58.3, -34.5]}, "start": "2026-01"},
    {"area": {"point": [-71.3, -41.13], "radius_km": 40}},
    {"area": {"preset": "parana-delta"}, "month": "2025-11"},
    # Boxes more than 180 degrees wide are filled as strips (H3 alone would fill the rest of the world).
    {"area": {"bbox": [-170.0, -60.0, 170.0, 60.0]}, "month": "2010-08"},
]
# The global sample: one or more searches per continent, searches spanning two continents (the continent
# with most of the fire-days decides the ranges and month status), Antarctica (no model) and open ocean (no fire).
GLOBAL_REQUESTS = [
    {"area": {"preset": "central-africa"}, "month": "2004-01"},
    {"area": {"preset": "central-africa"}, "month": "2001-12", "baseline": "mean"},
    {"area": {"preset": "parana-delta"}, "month": "2008-04"},
    {"area": {"bbox": [-59.5, -33.8, -58.8, -33.0]}, "month": "2011-08"},
    {"area": {"preset": "mainland-se-asia"}, "month": "2007-03"},
    {"area": {"point": [100.5, 19.0], "radius_km": 30}, "month": "2010-04"},
    {"area": {"preset": "northern-california"}, "month": "2008-06"},
    {"area": {"preset": "central-portugal"}, "month": "2005-08", "start": "2003-01", "end": "2012-12"},
    {"area": {"bbox": [-8.5, 40.0, -8.0, 40.5]}, "month": "2003-08"},
    {"area": {"preset": "top-end"}, "month": "2009-09"},
    {"area": {"preset": "panama-colombia"}, "month": "2007-03"},
    {"area": {"polygon": [[-79.5, 8.0], [-77.0, 7.0], [-76.0, 9.0]]}, "month": "2003-04"},
    {"area": {"bbox": [73.2, -53.3, 73.9, -52.9]}, "month": "2005-01"},
    {"area": {"bbox": [73.2, -53.3, 73.9, -52.9]}, "month": "2020-01"},
    {"area": {"bbox": [-150.0, -10.0, -145.0, -5.0]}, "month": "2010-06"},
    {"area": {"preset": "central-africa"}},
    # Boxes more than 180 degrees wide, up to the whole map, are filled as strips.
    {"area": {"bbox": [-180.0, -85.0, 180.0, 85.0]}, "month": "2010-08"},
    {"area": {"bbox": [-100.0, -20.0, 100.0, 20.0]}, "month": "2004-01"},
]
GLOBAL_EXPORTS = [
    {"area": {"preset": "parana-delta"}, "start": "2020-08", "end": "2020-08"},  # no hotspot file: refused
]

BAD = [
    {"area": {"bbox": [-60, -30, -65, -26]}},
    {"area": {"preset": "nowhere"}},
    {"area": {"bbox": [-65.0, -30.0, -60.0, -26.0]}, "start": "1999-01"},
    {"area": {"bbox": [-65.0, -30.0, -60.0, -26.0]}, "baseline": "mode"},
    {"area": {"polygon": [[-100, 0], [100, 0], [0, 10]]}},  # more than 180 degrees wide and not a box
    {"area": {"bbox": [-1e12, -1, 1e12, 1]}},  # more than 360 degrees wide: refused before splitting
]

EXPORTS = [
    {"area": {"preset": "parana-delta"}, "start": "2020-08", "end": "2020-08"},
    {"area": {"bbox": [-58.6, -34.7, -58.3, -34.5]}},
    {"area": {"point": [-71.3, -41.13], "radius_km": 40}, "start": "2015-01", "end": "2015-03"},
    {"area": {"polygon": [[-62, -32], [-59, -31], [-58, -34], [-61.5, -35]]}, "start": "2004-09", "end": "2004-09"},
    {"area": {"preset": "parana-delta"}, "start": "2026-08", "end": "2026-11"},  # near-real-time rows
    {"area": {"preset": "argentina-box"}},  # over the cap: must be refused with the same row count
]


def post_raw(path, req):
    r = urllib.request.Request(BASE + path, json.dumps(req).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def post(req):
    r = urllib.request.Request(BASE + "/api/query", json.dumps(req).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def close(a, b, path, problems, tol=0.02):
    if isinstance(a, dict):
        if set(a) != set(b):
            problems.append(f"{path}: keys differ {sorted(set(a) ^ set(b))}")
        for k in a.keys() & b.keys():
            close(a[k], b[k], f"{path}.{k}", problems, tol)
    elif isinstance(a, list):
        if len(a) != len(b):
            problems.append(f"{path}: length {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            close(x, y, f"{path}[{i}]", problems, tol)
    elif isinstance(a, float) or isinstance(b, float):
        # frp is rounded to 1 decimal; Python rounds exact halves to even, Rust rounds them away from zero.
        t = 0.11 if path.endswith(".frp") else tol
        if a is None or b is None or not math.isclose(a, b, rel_tol=1e-6, abs_tol=t):
            problems.append(f"{path}: {a} vs {b}")
    elif a != b:
        problems.append(f"{path}: {a!r} vs {b!r}")


def main():
    ref = Reference(Config.load())
    failures = 0
    # Data with several continents (the global sample, pipeline/tests/fixture_global) has its own places.
    requests, exports = (GLOBAL_REQUESTS, GLOBAL_EXPORTS) if len(ref.areas) > 1 else (REQUESTS, EXPORTS)
    for req in requests:
        status, got = post(req)
        want = ref.query(req)
        problems = [] if status == 200 else [f"HTTP {status}: {got}"]
        if status == 200:
            close(want, got, "", problems)
        print("ok  " if not problems else "FAIL", json.dumps(req), {k: v for k, v in got.get("area", {}).items() if k != "ring"} if status == 200 else "")
        for p in problems[:8]:
            print("     ", p)
        failures += bool(problems)
    for req in BAD:
        status, got = post(req)
        ok = status == 400 and "error" in got
        print("ok  " if ok else "FAIL", "rejects", json.dumps(req), "->", status, got.get("error", "")[:80])
        failures += not ok
    for req in exports:
        status, body = post_raw("/api/export.csv", req)
        try:
            want, want_status = ref.export(req), 200
        except TooManyHotspots as e:
            want, want_status = e, 413
        except NoExport as e:
            want, want_status = e, 404
        if want_status == 404:
            got = json.loads(body) if status == 404 else {}
            ok = got.get("error") == str(want)
            print("ok  " if ok else "FAIL", "export unavailable", json.dumps(req), "->", status, body[:90])
        elif want_status == 413:
            got = json.loads(body) if status == 413 else {}
            ok = got.get("rows") == want.rows and got.get("limit") == want.limit and got.get("error") == str(want)
            print("ok  " if ok else "FAIL", "export refuses", json.dumps(req), "->", status, body[:90])
        else:
            ok = status == 200 and body == want
            print("ok  " if ok else "FAIL", "export", json.dumps(req), f"{body.count(chr(10)) - 1} rows")
            if not ok and status == 200:
                diff = next((i for i, (a, b) in enumerate(zip(body.splitlines(), want.splitlines())) if a != b), None)
                print("      first differing line:", diff, body.splitlines()[diff] if diff is not None else "(lengths differ)",
                      "|", want.splitlines()[diff] if diff is not None else "")
        failures += not ok
    meta = json.load(urllib.request.urlopen(BASE + "/api/meta"))
    problems = []
    close(ref.meta(), meta, "meta", problems)
    print("ok   meta" if not problems else f"FAIL meta {problems[:5]}")
    failures += bool(problems)
    print(f"{failures} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
