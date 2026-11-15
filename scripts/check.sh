#!/usr/bin/env bash
# Local checks, run before opening a pull request. Nothing here uses the network except package
# installs, and no data leaves this machine.
#
#   1. web      type-check and build the frontend
#   2. api      build the Rust API
#   3. sample   run the whole pipeline on a small local sample (pipeline/tests/fixture, git-ignored),
#               compare the Rust API with the Python reference on it, and run the browser tests
#               (web/e2e) against the API serving the built app
#   4. full     the same comparison and browser tests on the full published data (data/gold)
#
# Usage: scripts/check.sh [--fresh-sample]    (--fresh-sample rebuilds the sample from data/)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIXTURE="$ROOT/pipeline/tests/fixture"
API="$ROOT/api/target/release/firecal-api"
PORT=8090
FRESH=0
[[ "${1:-}" == "--fresh-sample" ]] && FRESH=1

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
api_pid=""
stop_api() {  # always succeeds: a killed process's exit status must not trip `set -e`
    if [[ -n "$api_pid" ]]; then kill "$api_pid" 2>/dev/null || true; wait "$api_pid" 2>/dev/null || true; fi
    api_pid=""
}
trap stop_api EXIT

# Start the API on $PORT for the data root in $1, serving the built app, and run the parity test and
# the browser tests against it.
against() {
    local root="$1" log
    log="$(mktemp)"
    FIRECAL_ROOT="$root" FIRECAL_WEB="$ROOT/web/build" FIRECAL_BIND="127.0.0.1:$PORT" "$API" > "$log" 2>&1 &
    api_pid=$!
    local ready=0
    for _ in $(seq 1 60); do
        kill -0 "$api_pid" 2>/dev/null || break  # exited, e.g. the port is taken
        curl -sf "http://127.0.0.1:$PORT/api/meta" > /dev/null && { ready=1; break; }
        sleep 1
    done
    # Fail unless the API answering is the one started here: another server already on $PORT would
    # otherwise be tested in its place.
    if [[ $ready == 0 ]] || ! kill -0 "$api_pid" 2>/dev/null; then
        echo "The API did not start on 127.0.0.1:$PORT (is the port in use?). Its log:"
        cat "$log"
        exit 1
    fi
    (cd "$ROOT/pipeline" && FIRECAL_ROOT="$root" uv run python tests/test_api_parity.py "http://127.0.0.1:$PORT" \
        | grep -v '^ok') || { cat "$log"; exit 1; }
    (cd "$ROOT/web" && FIRECAL_URL="http://127.0.0.1:$PORT" pnpm exec playwright test --reporter=dot) || { cat "$log"; exit 1; }
    stop_api
    rm -f "$log"
}

step "1/4 web: type-check and build"
(cd "$ROOT/web" && pnpm install --frozen-lockfile --silent && pnpm exec playwright install chromium > /dev/null \
    && pnpm check && pnpm build > /dev/null)

step "2/4 api: build"
cargo build --release --locked --quiet --manifest-path "$ROOT/api/Cargo.toml"

step "3/4 sample: pipeline, parity, browser tests"
if [[ $FRESH == 1 || ! -d "$FIXTURE/raw" ]]; then
    [[ -d "$ROOT/data/bronze" ]] || { echo "No data/bronze: build the full data first (README)."; exit 1; }
    (cd "$ROOT/pipeline" && uv run python -I tests/fixture/make_sample.py)
fi
rm -rf "$FIXTURE/out" && mkdir -p "$FIXTURE/out" && cp -r "$FIXTURE/raw/firms_api" "$FIXTURE/out/"
for s in ingest cells fit publish; do
    (cd "$ROOT/pipeline" && FIRECAL_ROOT="$FIXTURE" uv run python -m firecal_pipeline "$s" > /dev/null)
done
against "$FIXTURE"

step "4/4 full: parity and browser tests on the published data"
if [[ -f "$ROOT/data/gold/CURRENT" ]]; then
    against "$ROOT"
else
    echo "skipped: no data/gold yet"
fi

printf '\n\033[1mAll checks passed.\033[0m\n'
