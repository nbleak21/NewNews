#!/bin/bash
# Run one feed build and log to logs/YYYY-MM-DD.log.
# Called by launchd (see TASKS.md task 10) or by hand:  scripts/run.sh [--dry-run]
#
# HINT: launchd starts jobs with a minimal PATH and no shell profile, so this
# script uses absolute paths derived from its own location and activates the
# venv directly instead of relying on `uv` being on PATH.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

mkdir -p logs state build
LOG_FILE="logs/$(date +%Y-%m-%d).log"

if [ ! -f .venv/bin/activate ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') ERROR .venv missing; run 'uv sync' first" >> "$LOG_FILE"
  exit 1
fi

# Load secrets (feed token, ntfy topic) if present.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# shellcheck disable=SC1091
source .venv/bin/activate

CONFIG="${NEWNEWS_CONFIG:-config/sources.yaml}"

{
  echo "$(date '+%Y-%m-%d %H:%M:%S') ---- run start ----"
  status=0
  commute-news build --config "$CONFIG" "$@" || status=$?
  echo "$(date '+%Y-%m-%d %H:%M:%S') ---- run end (exit $status) ----"
  exit "$status"
} >> "$LOG_FILE" 2>&1
# HINT: old logs are not rotated yet; `find logs -name '*.log' -mtime +30 -delete`
# is enough if they ever grow.
