#!/usr/bin/env bash
# Hermetic contract for producer-owned source/cache staging. No live build tree,
# mirror, container, or network endpoint is read or changed by this test.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/core/pf-build.sh"
HELPER="$ROOT/core/pf-stage-tree.py"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/pf-stage-tree.XXXXXX")"
trap 'find "$TMP" -depth -delete' EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
has() { grep -Fq -- "$2" "$1" || { sed -n '1,160p' "$1" >&2; fail "$3"; }; }

# Ordinary build staging is part of the already manifest-owned #1045 tree. Its
# success reduction and max-failed enforcement therefore own src and cache too;
# no per-bead sibling namespace may remain.
grep -F 'local cache_dir="$PF_OUT_DIR/cache" src_dir="$PF_OUT_DIR/src"' \
    "$BUILD" >/dev/null || fail 'ordinary src/cache are not inside PF_OUT_DIR'
if grep -F 'local cache_dir="/tmp/pf-build/$BEAD/cache" src_dir="/tmp/pf-build/$BEAD/src"' \
    "$BUILD" >/dev/null; then
    fail 'ordinary staging still creates an unmanaged per-bead sibling'
fi
grep -F 'STAGE_TREE_ROOT="${PF_STAGE_TREE_ROOT:-/tmp/pf-stage-only}"' \
    "$BUILD" >/dev/null || fail 'stage-only fixed producer namespace is not explicit'
grep -F 'pf-stage-tree.py' "$BUILD" >/dev/null || fail 'stage-only does not use its owner helper'

# One fixed device slot is the printed bound. Completion retains it for its
# consumer; a later bead is refused without replacing any byte.
slot="$TMP/stage-only/a133"
input_a=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
input_b=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
python3 "$HELPER" start --root "$TMP/stage-only" --tree "$slot" \
    --producer pf-build.sh --bead bead-a --device a133 --input-sha "$input_a" \
    > "$TMP/start-a.out"
has "$TMP/start-a.out" \
    'STAGE_TREE_BOUND producer=pf-build.sh device=a133 max_retained=1 retained=0' \
    'empty stage-only bound is missing'
printf 'retained source bytes\n' > "$slot/source.bin"
python3 "$HELPER" finish --root "$TMP/stage-only" --tree "$slot" \
    --producer pf-build.sh --bead bead-a --device a133 --input-sha "$input_a" \
    --state success > "$TMP/finish-a.out"
before="$(sha256sum "$slot/source.bin")"
if python3 "$HELPER" start --root "$TMP/stage-only" --tree "$slot" \
    --producer pf-build.sh --bead bead-b --device a133 --input-sha "$input_b" \
    > "$TMP/start-b.out" 2>&1; then
    fail 'a second stage-only bead replaced the retained slot'
fi
has "$TMP/start-b.out" \
    'STAGE_TREE_BOUND producer=pf-build.sh device=a133 max_retained=1 retained=1' \
    'occupied stage-only bound is missing'
has "$TMP/start-b.out" 'keep_reason=unconsumed_stage_tree' \
    'occupied stage-only refusal is not precise'
[ "$(sha256sum "$slot/source.bin")" = "$before" ] || fail 'retained slot bytes changed'

# Failed stage-only work remains the same single owned slot, so N failures cannot
# create failed-src growth. Its exact input digest and failure state are durable.
failed="$TMP/stage-only-failed/a133"
python3 "$HELPER" start --root "$TMP/stage-only-failed" --tree "$failed" \
    --producer pf-build.sh --bead failed-a --device a133 --input-sha "$input_a" \
    > "$TMP/failed-start.out"
python3 "$HELPER" finish --root "$TMP/stage-only-failed" --tree "$failed" \
    --producer pf-build.sh --bead failed-a --device a133 --input-sha "$input_a" \
    --state failed > "$TMP/failed-finish.out"
python3 - "$failed/.pf-stage-tree.json" "$input_a" <<'PY'
import json
import os
from pathlib import Path
import sys
with open(sys.argv[1], encoding="utf-8") as stream:
    manifest = json.load(stream)
assert manifest["schema"] == "pocketforge.stage-tree/v1"
assert manifest["state"] == "failed"
assert manifest["input_sha256"] == sys.argv[2]
assert manifest["owner_pid"] == os.getppid()
assert manifest["owner_boot_id"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip()
assert isinstance(manifest["owner_start_ticks"], int)
assert manifest["owner_start_ticks"] > 0
PY
if python3 "$HELPER" start --root "$TMP/stage-only-failed" --tree "$failed" \
    --producer pf-build.sh --bead failed-b --device a133 --input-sha "$input_b" \
    > "$TMP/failed-second.out" 2>&1; then
    fail 'a second failed stage-only bead escaped the fixed slot'
fi
[ "$(find "$TMP/stage-only-failed" -name .pf-stage-tree.json | wc -l)" -eq 1 ] \
    || fail 'failed stage-only manifests grew beyond one'

# Unmanifested and symlinked paths are report-only. Refusal must not follow the
# link, invent ownership, or alter legacy bytes.
legacy="$TMP/legacy/a133"
mkdir -p "$legacy"
printf 'legacy\n' > "$legacy/keep"
if python3 "$HELPER" start --root "$TMP/legacy" --tree "$legacy" \
    --producer pf-build.sh --bead legacy --device a133 --input-sha "$input_a" \
    > "$TMP/legacy.out" 2>&1; then
    fail 'unmanifested stage directory was adopted'
fi
has "$TMP/legacy.out" 'keep_reason=legacy_no_manifest' 'legacy refusal missing'
[ "$(cat "$legacy/keep")" = legacy ] || fail 'legacy bytes changed'

mkdir -p "$TMP/external"
printf 'external\n' > "$TMP/external/keep"
mkdir -p "$TMP/symlink"
ln -s "$TMP/external" "$TMP/symlink/a133"
if python3 "$HELPER" start --root "$TMP/symlink" --tree "$TMP/symlink/a133" \
    --producer pf-build.sh --bead symlink --device a133 --input-sha "$input_a" \
    > "$TMP/symlink.out" 2>&1; then
    fail 'symlinked stage directory was accepted'
fi
has "$TMP/symlink.out" 'keep_reason=symlink_escape' 'symlink refusal missing'
[ "$(cat "$TMP/external/keep")" = external ] || fail 'external symlink target changed'

# A manifest-shaped but incomplete legacy directory is not enough ownership
# proof. It remains byte-for-byte untouched and is reported as malformed.
malformed="$TMP/malformed/a133"
mkdir -p "$malformed"
printf '{"schema":"pocketforge.stage-tree/v1"}\n' > "$malformed/.pf-stage-tree.json"
malformed_before="$(sha256sum "$malformed/.pf-stage-tree.json")"
if python3 "$HELPER" start --root "$TMP/malformed" --tree "$malformed" \
    --producer pf-build.sh --bead malformed --device a133 --input-sha "$input_a" \
    > "$TMP/malformed.out" 2>&1; then
    fail 'malformed stage manifest was accepted'
fi
has "$TMP/malformed.out" 'keep_reason=manifest_identity_mismatch' \
    'malformed manifest refusal missing'
[ "$(sha256sum "$malformed/.pf-stage-tree.json")" = "$malformed_before" ] \
    || fail 'malformed manifest bytes changed'

printf 'PASS: producer-owned ordinary and stage-only staging bounds\n'
