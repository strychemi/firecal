#!/usr/bin/env bash
# Bring the data up to date: download recent FIRMS days, rebuild, publish, prune old versions.
# Run by hand (`mise run refresh`); once deployed, the server's scheduler runs it daily (ARCHITECTURE.md
# section 7). A running API picks up the new version within 10 seconds.
#
# Steps: download -> ingest -> cells -> publish -> prune. `fit` is skipped (recent days are after the
# calibration and held-out years, so the model does not change).
# Logs go to data/logs/refresh-<UTC time>.log; the last 30 are kept.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$ROOT/data/logs"
LOCK="$ROOT/data/.refresh.lock"
mkdir -p "$LOGS"
LOG="$LOGS/refresh-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$LOG") 2>&1

# One run at a time; a lock left by a crashed run is cleared after 6 hours.
if ! mkdir "$LOCK" 2>/dev/null; then
    if [[ -n "$(find "$LOCK" -maxdepth 0 -mmin +360 2>/dev/null)" ]]; then
        echo "clearing a stale lock"; rm -rf "$LOCK"; mkdir "$LOCK"
    else
        echo "another refresh is running; exiting"; exit 0
    fi
fi
trap 'rm -rf "$LOCK"' EXIT

echo "refresh started $(date -u +%FT%TZ)"
cd "$ROOT/pipeline"
for step in download ingest cells publish prune; do
    echo "== $step"
    uv run python -m firecal_pipeline "$step"
done
echo "current version: $(cat "$ROOT/data/gold/CURRENT")"
echo "refresh finished $(date -u +%FT%TZ)"

ls -1t "$LOGS"/refresh-*.log 2>/dev/null | tail -n +31 | while read -r f; do rm -f "$f"; done
