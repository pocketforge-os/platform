#!/usr/bin/env bash
# regression/abi/run.sh — the E8 per-family ABI view + app-descriptor validator test suite
# (tsp-ziac.1). Runs the anti-drift gate proof + the validator/view unit tests. Exit 0 = pass.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" >/dev/null 2>&1 && pwd)"

echo "### abi view drift gate ###"
bash "$HERE/drift-test.sh"
echo
echo "### app-descriptor validator + view unit tests ###"
python3 "$HERE/appmanifest-test.py"
