#!/usr/bin/env bash
# FreshDocs refresh entrypoint (used by CI and locally).
#
#   bash scripts/run_refresh.sh            # refresh all sources, embed changes
#   bash scripts/run_refresh.sh --dry-run  # scrape + diff only, write nothing
#   bash scripts/run_refresh.sh --full     # full scrape (same as default)
#   bash scripts/run_refresh.sh --source docker
#
# Exit code is non-zero when any source fails its health check, so CI can
# react (and the heal step can run).

set -euo pipefail
cd "$(dirname "$0")/.."

MODE="refresh"
SOURCE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) MODE="dry-run" ;;
    --full) MODE="refresh" ;;
    --source) SOURCE="$2"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

if [[ ! -f .env ]]; then
  echo "missing .env — copy .env.example and fill in BRIGHT_DATA_API_TOKEN, BRIGHT_DATA_COLLECTOR_IDS, OPENAI_API_KEY" >&2
  exit 2
fi
set -a; source .env; set +a

export PYTHONPATH="$PWD/src:${PYTHONPATH:-}"

DRY_FLAG=""
[[ "$MODE" == "dry-run" ]] && DRY_FLAG="--dry-run"

if [[ -n "$SOURCE" ]]; then
  .venv/bin/python -m freshdocs.cli refresh --source "$SOURCE" $DRY_FLAG
else
  .venv/bin/python -m freshdocs.cli refresh $DRY_FLAG
fi
