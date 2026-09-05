#!/usr/bin/env bash
# regression/abi/drift-test.sh — proves the anti-drift gate (tsp-ziac.1).
#
# The bead requires "a script/test proving the view never drifts from the lock". The view is
# DERIVED, so it cannot silently diverge; this test proves the GATE that enforces re-freezing:
#   1. `pf abi check` is GREEN against the committed snapshot.
#   2. Move a substrate SHA in a throwaway copy of platform.lock -> `pf abi check` goes RED.
#   3. Interim re-freeze without a bump -> GREEN against the historical baseline.
#   4. Entering authoritative state without bumps -> RED.
#   5. Increment every existing family -> GREEN.
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
BASELINE="$TMP/baseline.json"
cp "$TMP/abi/platform-abi.json" "$BASELINE"
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

echo "== 3. interim re-freeze without a version bump is legitimate =="
python3 "$TMP/core/abi_view.py" generate
python3 "$TMP/core/abi_view.py" check --baseline-file "$BASELINE"
echo "ok   - interim SHA movement regenerated in place"

echo "== 4. freezing without version bumps goes RED =="
python3 - "$TMP/platform.lock" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read().replace("seeded           = false", "seeded           = true")
s = s.replace("interim_seed     = true", "interim_seed     = false")
open(p, "w").write(s)
PY
python3 "$TMP/core/abi_view.py" generate
if python3 "$TMP/core/abi_view.py" check --baseline-file "$BASELINE" >"$TMP/freeze-red.log" 2>&1; then
    echo "FAIL: authoritative freeze reused interim platform versions"; exit 1
fi
grep -q 'reason=frozen_set_moved_without_version_bump' "$TMP/freeze-red.log"
echo "ok   - authoritative freeze without bumps was rejected"

echo "== 5. incrementing all existing families restores GREEN =="
python3 - "$TMP/abi/families.toml" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
s, count = re.subn(r'(platform_version\s*=\s*")(\d+)(")',
                   lambda m: m.group(1) + str(int(m.group(2)) + 1) + m.group(3), s)
assert count > 0
open(p, "w").write(s)
PY
python3 "$TMP/core/abi_view.py" generate
python3 "$TMP/core/abi_view.py" check --baseline-file "$BASELINE"
echo "ok   - authoritative freeze with per-family increments passed"

echo "ABI DRIFT GATE OK"
