#!/usr/bin/env bash
# regression/build/run.sh — the pf build orchestration regression suite. Exit 0 = pass.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" >/dev/null 2>&1 && pwd)"

echo "### stale-mirror SOURCE_DATE_EPOCH gate (tsp-hbpd) ###"
bash "$HERE/epoch-test.sh"
