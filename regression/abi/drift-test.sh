#!/usr/bin/env bash
# regression/abi/drift-test.sh — proves the anti-drift gate (tsp-ziac.1).
#
# The bead requires "a script/test proving the view never drifts from the lock". The view is
# DERIVED, so it cannot silently diverge; this test proves the GATE that enforces re-freezing:
#   1. `pf abi check` is GREEN against the committed snapshot.
#   2. Move a substrate SHA in a throwaway copy of platform.lock -> `pf abi check` goes RED.
#   3. Re-freeze (`pf abi generate`) against the moved lock -> GREEN again.
# No committed file is left modified (everything happens in a temp ROOT copy).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." >/dev/null 2>&1 && pwd)"

echo "== 1. committed snapshot is in sync with the live lock =="
python3 "$ROOT/core/abi_view.py" check

echo "== 2. a moved kernel SHA makes the gate go RED =="
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# Minimal copy: the abi_view needs core/, abi/, devices/, families/, platform.lock.
cp -r "$ROOT/core" "$ROOT/abi" "$ROOT/devices" "$ROOT/families" "$ROOT/platform.lock" "$TMP/"
# Flip the kernel-sunxi-4.9 SHA (which IS in the a133-powervr view) to a bogus value, COPY only.
python3 - "$TMP/platform.lock" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
# Replace the sha in the [[repos]] block whose name is kernel-sunxi-4.9 (an in-view repo).
s2 = re.sub(r'(name\s*=\s*"kernel-sunxi-4\.9".*?\n(?:.*\n)*?\s*sha\s*=\s*")[0-9a-f]{40}(")',
            r'\g<1>' + '0'*40 + r'\g<2>', s, count=1)
assert s2 != s, "test bug: kernel-sunxi-4.9 sha not found/replaced in the lock copy"
open(p, "w").write(s2)
PY
if python3 "$TMP/core/abi_view.py" check >/dev/null 2>&1; then
    echo "FAIL: gate stayed GREEN after a substrate SHA moved — drift is not detected"; exit 1
fi
echo "ok   - gate went RED on the moved SHA (drift detected)"

echo "== 3. re-freezing against the moved lock restores GREEN =="
python3 "$TMP/core/abi_view.py" generate
python3 "$TMP/core/abi_view.py" check
echo "ok   - re-freeze (pf abi generate) restores the gate to GREEN"

echo "ABI DRIFT GATE OK"
