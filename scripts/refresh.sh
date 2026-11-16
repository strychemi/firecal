#!/usr/bin/env bash
# Bring the data up to date: download recent FIRMS days, rebuild, publish, prune old versions.
# Run by hand (`mise run refresh`); once deployed, the server's scheduler runs it daily (ARCHITECTURE.md
# section 7). A running API picks up the new version within 10 seconds.
#
# Steps: download -> ingest -> cells -> publish -> prune. `fit` is skipped (recent days are after the
# calibration and held-out years, so the model does not change).
# Logs go to logs/refresh-<UTC time>.log in the run's data folder; the last 30 are kept.
#
# The global run: FIRECAL_ROOT=global scripts/refresh.sh (a relative FIRECAL_ROOT is taken from the
# folder you run it in). One refresh runs at a time across both runs (they share data/.refresh.lock).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${FIRECAL_ROOT:-}" ]]; then
    FIRECAL_ROOT="$(cd "$FIRECAL_ROOT" && pwd)"   # the steps run from pipeline/, so make it absolute
    export FIRECAL_ROOT
fi
# The run's data folder ([data] out_dir of its firecal.toml): data/ for Argentina, data/global/ globally.
OUT="$(cd "$ROOT/pipeline" && uv run --quiet python -c 'from firecal_pipeline.config import Config; print(Config.load().out.resolve())')"
LOGS="$OUT/logs"
LOCK="$ROOT/data/.refresh.lock"
mkdir -p "$LOGS"
LOG="$LOGS/refresh-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$LOG") 2>&1

# One run at a time: an flock on $LOCK, held through file descriptor 9 by this script and the steps it
# starts. The kernel releases it once they have all exited, even after a crash, so there is no stale
# lock to clear, and a step left running by a killed script still blocks a new run.
# (flock(1) is not on macOS, so Python takes the lock on the inherited descriptor.) The file is never
# deleted: deleting it would let a second run lock a new file while the first still holds the old one.
exec 9>> "$LOCK"
if ! (cd "$ROOT/pipeline" && uv run --quiet python -c 'import fcntl; fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)') 2>/dev/null; then
    echo "another refresh is running; exiting"; exit 0
fi

echo "refresh started $(date -u +%FT%TZ)"
cd "$ROOT/pipeline"
for step in download ingest cells publish prune; do
    echo "== $step"
    uv run python -m firecal_pipeline "$step"
done
echo "current version: $(cat "$OUT/gold/CURRENT")"
echo "refresh finished $(date -u +%FT%TZ)"

ls -1t "$LOGS"/refresh-*.log 2>/dev/null | tail -n +31 | while read -r f; do rm -f "$f"; done
