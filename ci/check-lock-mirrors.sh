#!/usr/bin/env bash
# Run the exact-consumer platform.lock mirror gate with a tomllib-capable Python.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." >/dev/null 2>&1 && pwd)"
PY="${PF_PY:-}"
if [ -n "$PY" ]; then
    command -v "$PY" >/dev/null 2>&1 || { echo "FATAL: PF_PY=$PY not found" >&2; exit 3; }
else
    for candidate in python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1 \
            && "$candidate" -c 'import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)'; then
            PY="$candidate"
            break
        fi
    done
fi
[ -n "$PY" ] || { echo "FATAL: no Python 3.11+ (tomllib) interpreter found" >&2; exit 3; }

exec "$PY" -B "$ROOT/ci/check_lock_mirrors.py" \
    --lock "$ROOT/platform.lock" \
    --manifest "$ROOT/ci/lock-mirrors.toml"
