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
from firecal_pipeline.reference import Reference

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
]
BAD = [
    {"area": {"bbox": [-60, -30, -65, -26]}},
    {"area": {"preset": "nowhere"}},
    {"area": {"preset": "chaco"}, "start": "1999-01"},
    {"area": {"preset": "chaco"}, "baseline": "mode"},
]


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
    for req in REQUESTS:
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
    meta = json.load(urllib.request.urlopen(BASE + "/api/meta"))
    problems = []
    close(ref.meta(), meta, "meta", problems)
    print("ok   meta" if not problems else f"FAIL meta {problems[:5]}")
    failures += bool(problems)
    print(f"{failures} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
