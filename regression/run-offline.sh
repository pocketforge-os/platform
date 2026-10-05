#!/usr/bin/env bash
# regression/run-offline.sh — run EVERY regression/ suite that is offline,
# docker-free and seconds-fast from a clean checkout. Exit 0 = all pass.
#
# WHY THIS EXISTS (tsp-mc9m.41.984.63): platform#261 pinned Cedrus image#169 and
# shipped STALE profile goldens — `python3 -m unittest regression.profile.test_profile`
# failed 2 tests at its head 3311f52b, yet all 3 PR checks were green because NO
# required check ran regression/. This script is what .github/workflows/
# regression-suites.yml executes on every PR, so a pin change without refreshed
# goldens goes RED in CI, not only in review.
#
# Suites (all stdlib-only; the build gates grep shipped sources / fake docker):
#   regression/lock_mirrors/ exact-pin gate's hermetic RED/GREEN and fail-closed cases
#   regression/abi/run.sh        ABI view drift gate + version policy + appmanifest
#   regression/build/run.sh      pf build orchestration gates
#   regression/profile/test_*.py profile goldens incl. test_profile.py (the #261 miss)
#   regression/caps/test_caps.py capabilities descriptor self-tests
#
# Suites needing a device, labgrid or a real docker build are deliberately NOT
# here; they belong to the pf-test / hil lanes.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd "$HERE/.." >/dev/null 2>&1 && pwd)"

# Pick a Python 3.11+ (tomllib) interpreter; honour PF_PY. Some sub-suites call
# bare `python3`, so pin the pick by shadowing PATH with a shim dir.
PY="${PF_PY:-}"
if [ -n "$PY" ]; then
    command -v "$PY" >/dev/null 2>&1 || { echo "FATAL: PF_PY=$PY not found" >&2; exit 3; }
else
    for c in python3.12 python3.11 python3; do
        if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)'; then
            PY="$c"; break
        fi
    done
fi
if [ -z "$PY" ]; then
    echo "FATAL: no Python 3.11+ (tomllib) interpreter found" >&2
    exit 3
fi
"$PY" -c 'import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)' \
    || { echo "FATAL: $PY ($("$PY" -V 2>&1)) is older than 3.11 (tomllib)" >&2; exit 3; }

shim="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/pf-regression-py.XXXXXX")"
trap 'find "$shim" -mindepth 1 -delete; rmdir "$shim"' EXIT
ln -s "$(command -v "$PY")" "$shim/python3"
export PATH="$shim:$PATH"
export PF_PY="$PY"
echo "using $PY ($("$PY" -V 2>&1))"

cd "$ROOT"

echo
echo "### regression/lock_mirrors ###"
"$PY" -B -m unittest discover -s "$HERE/lock_mirrors" -p 'test_*.py' -v

echo
echo "### regression/abi ###"
bash "$HERE/abi/run.sh"

echo
echo "### regression/build ###"
bash "$HERE/build/run.sh"

echo
echo "### regression/profile ###"
for t in "$HERE"/profile/test_*.py; do
    echo "-- regression/profile/$(basename "$t")"
    "$PY" -B "$t" -v
done

echo
echo "### regression/caps ###"
"$PY" -B "$HERE/caps/test_caps.py"

echo
echo "ALL OFFLINE REGRESSION SUITES PASSED"
