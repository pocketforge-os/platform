#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
bead="release-lock-state-test-$$"

set +e
override_output="$(PF_CONTAINER_OVERRIDE=registry.invalid/pocketforge/build:untrusted \
    "$ROOT/core/pf-build.sh" --device a133 --variant release --dry-run --bead "$bead" 2>&1)"
override_rc=$?
set -e

test "$override_rc" -ne 0
grep -Fq 'PF_CONTAINER_OVERRIDE is dev-only — release builds must use the committed container.pin' \
    <<< "$override_output"

set +e
output="$("$ROOT/core/pf-build.sh" --device a133 --variant release --stage-only --bead "$bead" 2>&1)"
rc=$?
set -e

test "$rc" -ne 0
grep -Fq 'platform.lock is INTERIM-seeded (dev-only) — a RELEASE build needs the authoritative seed' \
    <<< "$output"
test ! -e "/tmp/pf-build/$bead/src/image"

echo 'PASS: release builds reject dev-only container overrides and interim locks'
