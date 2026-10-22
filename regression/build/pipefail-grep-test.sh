#!/usr/bin/env bash
# Prevent early-exit grep assertions from turning a successful producer match
# into a pipefail failure when the producer receives SIGPIPE.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." >/dev/null 2>&1 && pwd)"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

# Positive control: this runner must actually expose the failure mode. `head`
# exits after one line while `yes` is still producing, so pipefail reports the
# producer's SIGPIPE instead of the consumer's successful match.
set +e
yes forced-sigpipe | head -n 1 >/dev/null
control_rc=$?
set -e
[ "$control_rc" -ne 0 ] \
    || fail "forced-SIGPIPE control did not fail under pipefail"

# Regression: pipefail-enabled scripts must materialize producer output before
# a quiet grep assertion. Normalize shell line continuations so wrapped
# pipelines cannot escape the check.
python3 - "$ROOT/regression" "${BASH_SOURCE[0]}" <<'PY'
import pathlib
import re
import sys

regression = pathlib.Path(sys.argv[1])
this_test = pathlib.Path(sys.argv[2]).resolve()
unsafe = re.compile(r"\|\s*grep\s+(?:-[^\s]*q\b|--quiet\b)")
findings = []

for path in sorted(regression.rglob("*.sh")):
    if path.resolve() == this_test:
        continue
    source = path.read_text(encoding="utf-8")
    if not re.search(r"^set\s+[^\n]*pipefail", source, re.MULTILINE):
        continue
    normalized = re.sub(r"\\\n[ \t]*", " ", source)
    for line_no, line in enumerate(normalized.splitlines(), 1):
        if unsafe.search(line):
            findings.append(f"{path.relative_to(regression.parent)}:{line_no}:{line.strip()}")

if findings:
    print("FAIL: pipefail-unsafe producer | grep -q assertions remain:", file=sys.stderr)
    print("\n".join(findings), file=sys.stderr)
    raise SystemExit(1)
PY

printf 'PASS: forced SIGPIPE reproduced and all quiet-grep assertions are materialized\n'
