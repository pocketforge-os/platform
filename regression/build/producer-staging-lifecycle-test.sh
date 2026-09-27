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

write_build_manifest() {
    local tree="$1" bead="$2" start_delta="$3"
    mkdir -p "$tree"
    python3 - "$tree/.pf-build-tree.json" "$bead" "$start_delta" <<'PY'
import json
import os
from pathlib import Path
import sys

path = Path(sys.argv[1])
bead = sys.argv[2]
pid = os.getppid()
boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
stat_tail = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").rpartition(") ")[2]
start_ticks = int(stat_tail.split()[19]) + int(sys.argv[3])
manifest = {
    "schema": "pocketforge.build-tree/v1",
    "bead": bead,
    "device": "a133",
    "host": "hermetic-test",
    "created_utc": "2026-09-27T00:00:00Z",
    "producer": "build-owned-image.sh",
    "producer_version": 4,
    "state": "running",
    "owner": {
        "pid": pid,
        "boot_id": boot_id,
        "start_ticks": start_ticks,
    },
    "artifacts": [],
    "remote_log": "/tmp/hermetic-build.log",
}
path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
PY
}

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

# Ordinary staging is admitted only under an exact, live, manifest-owned #1045
# namespace. Legacy, malformed, dead-owner, and symlinked candidates are
# report-only and remain byte-for-byte untouched.
build_root="$TMP/build-tree"
mkdir -p "$build_root"
live_tree="$build_root/live-bead/a133"
write_build_manifest "$live_tree" live-bead 0
python3 "$HELPER" require-build-tree --root "$build_root" --tree "$live_tree" \
    --producer pf-build.sh --bead live-bead --device a133 > "$TMP/live-owner.out"
has "$TMP/live-owner.out" \
    "BUILD_TREE_OWNERSHIP producer=build-owned-image.sh device=a133 bead=live-bead state=running path=$live_tree" \
    'live manifest-owned build tree was not admitted'

legacy_build="$build_root/legacy-bead/a133"
mkdir -p "$legacy_build"
printf 'legacy source\n' > "$legacy_build/keep"
if python3 "$HELPER" require-build-tree --root "$build_root" --tree "$legacy_build" \
    --producer pf-build.sh --bead legacy-bead --device a133 \
    > "$TMP/legacy-build.out" 2>&1; then
    fail 'unmanifested ordinary build tree was adopted'
fi
has "$TMP/legacy-build.out" 'keep_reason=legacy_no_manifest' \
    'ordinary legacy refusal missing'
[ "$(cat "$legacy_build/keep")" = 'legacy source' ] \
    || fail 'ordinary legacy bytes changed'

malformed_build="$build_root/malformed-bead/a133"
mkdir -p "$malformed_build"
printf '{"schema":"pocketforge.build-tree/v1"}\n' \
    > "$malformed_build/.pf-build-tree.json"
malformed_build_before="$(sha256sum "$malformed_build/.pf-build-tree.json")"
if python3 "$HELPER" require-build-tree --root "$build_root" --tree "$malformed_build" \
    --producer pf-build.sh --bead malformed-bead --device a133 \
    > "$TMP/malformed-build.out" 2>&1; then
    fail 'malformed ordinary build manifest was accepted'
fi
has "$TMP/malformed-build.out" 'keep_reason=invalid_manifest' \
    'ordinary malformed-manifest refusal missing'
[ "$(sha256sum "$malformed_build/.pf-build-tree.json")" = "$malformed_build_before" ] \
    || fail 'ordinary malformed manifest changed'

dead_tree="$build_root/dead-bead/a133"
write_build_manifest "$dead_tree" dead-bead 1
dead_before="$(sha256sum "$dead_tree/.pf-build-tree.json")"
if python3 "$HELPER" require-build-tree --root "$build_root" --tree "$dead_tree" \
    --producer pf-build.sh --bead dead-bead --device a133 \
    > "$TMP/dead-owner.out" 2>&1; then
    fail 'dead-owner ordinary build tree was accepted'
fi
has "$TMP/dead-owner.out" 'keep_reason=owner_not_live' \
    'ordinary dead-owner refusal missing'
[ "$(sha256sum "$dead_tree/.pf-build-tree.json")" = "$dead_before" ] \
    || fail 'dead-owner manifest changed'

mkdir -p "$TMP/build-external" "$build_root/symlink-bead"
printf 'external ordinary source\n' > "$TMP/build-external/keep"
ln -s "$TMP/build-external" "$build_root/symlink-bead/a133"
if python3 "$HELPER" require-build-tree --root "$build_root" \
    --tree "$build_root/symlink-bead/a133" --producer pf-build.sh \
    --bead symlink-bead --device a133 > "$TMP/symlink-build.out" 2>&1; then
    fail 'symlinked ordinary build tree was accepted'
fi
has "$TMP/symlink-build.out" 'keep_reason=symlink_escape' \
    'ordinary symlink refusal missing'
[ "$(cat "$TMP/build-external/keep")" = 'external ordinary source' ] \
    || fail 'ordinary symlink target changed'

# An explicit one-shot caller contract is bounded to one pre-created empty
# directory and may never claim a managed-tree path or overwrite caller bytes.
# Admission creates an exclusive live-owner reservation, and only that owner can
# release it after its staging/build lifetime.
caller_tree="$TMP/caller-temporary"
mkdir -p "$caller_tree"
python3 "$HELPER" require-caller-temporary --root "$build_root" --tree "$caller_tree" \
    --producer pf-build.sh --bead caller-bead --device a133 > "$TMP/caller.out"
has "$TMP/caller.out" \
    "CALLER_TEMP_BOUND producer=pf-build.sh device=a133 max_active=1 active=1 bead=caller-bead path=$caller_tree" \
    'caller-temporary bound is missing'
python3 - "$caller_tree/.pf-caller-temporary.json" "$caller_tree" "$build_root" <<'PY'
import json
import os
from pathlib import Path
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    manifest = json.load(stream)
assert manifest["schema"] == "pocketforge.caller-temporary/v1"
assert manifest["producer"] == "pf-build.sh"
assert manifest["bead"] == "caller-bead"
assert manifest["device"] == "a133"
assert manifest["root"] == sys.argv[3]
assert manifest["tree"] == sys.argv[2]
assert manifest["state"] == "active"
assert manifest["owner_pid"] == os.getppid()
assert manifest["owner_boot_id"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip()
assert isinstance(manifest["owner_start_ticks"], int)
assert manifest["owner_start_ticks"] > 0
PY
printf 'caller-owned\n' > "$caller_tree/keep"
caller_before="$(sha256sum "$caller_tree/keep")"
if python3 "$HELPER" require-caller-temporary --root "$build_root" --tree "$caller_tree" \
    --producer pf-build.sh --bead caller-bead --device a133 \
    > "$TMP/caller-nonempty.out" 2>&1; then
    fail 'live caller-temporary reservation was accepted twice'
fi
has "$TMP/caller-nonempty.out" 'keep_reason=caller_temporary_active' \
    'live caller-temporary refusal missing'
[ "$(sha256sum "$caller_tree/keep")" = "$caller_before" ] \
    || fail 'caller-owned bytes changed'
python3 "$HELPER" release-caller-temporary --root "$build_root" --tree "$caller_tree" \
    --producer pf-build.sh --bead caller-bead --device a133 > "$TMP/caller-release.out"
has "$TMP/caller-release.out" \
    "CALLER_TEMP_RELEASE producer=pf-build.sh device=a133 max_active=1 active=0 bead=caller-bead path=$caller_tree" \
    'caller-temporary release bound is missing'
[ ! -e "$caller_tree/.pf-caller-temporary.json" ] \
    || fail 'caller-temporary reservation survived owner release'
[ "$(sha256sum "$caller_tree/keep")" = "$caller_before" ] \
    || fail 'caller-owned bytes changed during release'
if python3 "$HELPER" require-caller-temporary --root "$build_root" --tree "$caller_tree" \
    --producer pf-build.sh --bead caller-after-release --device a133 \
    > "$TMP/caller-nonempty.out" 2>&1; then
    fail 'nonempty released caller-temporary directory was accepted'
fi
has "$TMP/caller-nonempty.out" 'keep_reason=caller_temporary_not_empty' \
    'nonempty released caller-temporary refusal missing'
if python3 "$HELPER" require-caller-temporary --root "$build_root" --tree "$live_tree" \
    --producer pf-build.sh --bead live-bead --device a133 \
    > "$TMP/caller-managed.out" 2>&1; then
    fail 'managed build namespace was accepted as caller-temporary'
fi
has "$TMP/caller-managed.out" 'keep_reason=managed_namespace_requires_manifest' \
    'caller contract did not reject a managed namespace'

# Two callers cross one deterministic barrier and contend for the same empty
# directory. Exactly one atomic claim wins; the loser cannot add or replace a
# byte, and the winner's explicit release admits a later caller.
concurrent_tree="$TMP/caller-concurrent"
gate_fifo="$TMP/caller-gate.fifo"
result_fifo="$TMP/caller-result.fifo"
release_a_fifo="$TMP/caller-release-a.fifo"
release_b_fifo="$TMP/caller-release-b.fifo"
mkdir -p "$concurrent_tree"
mkfifo "$gate_fifo" "$result_fifo" "$release_a_fifo" "$release_b_fifo"
exec 8<> "$gate_fifo"
exec 9<> "$result_fifo"

caller_worker() {
    local bead="$1" output="$2" release_fifo="$3" rc
    IFS= read -r _ <&8
    set +e
    python3 "$HELPER" require-caller-temporary --root "$build_root" \
        --tree "$concurrent_tree" --producer pf-build.sh --bead "$bead" \
        --device a133 > "$output" 2>&1
    rc=$?
    set -e
    printf '%s %s\n' "$bead" "$rc" >&9
    if [ "$rc" -eq 0 ]; then
        IFS= read -r _ < "$release_fifo"
        python3 "$HELPER" release-caller-temporary --root "$build_root" \
            --tree "$concurrent_tree" --producer pf-build.sh --bead "$bead" \
            --device a133 >> "$output" 2>&1
    fi
}

caller_worker caller-a "$TMP/caller-a.out" "$release_a_fifo" &
caller_a_pid=$!
caller_worker caller-b "$TMP/caller-b.out" "$release_b_fifo" &
caller_b_pid=$!
printf 'go\ngo\n' >&8
read -r result_one_bead result_one_rc <&9
read -r result_two_bead result_two_rc <&9

if [ "$result_one_rc" -eq 0 ] && [ "$result_two_rc" -ne 0 ]; then
    winner="$result_one_bead"
    loser="$result_two_bead"
elif [ "$result_two_rc" -eq 0 ] && [ "$result_one_rc" -ne 0 ]; then
    winner="$result_two_bead"
    loser="$result_one_bead"
else
    fail "concurrent caller admission did not produce exactly one winner ($result_one_bead=$result_one_rc $result_two_bead=$result_two_rc)"
fi
has "$TMP/$loser.out" 'keep_reason=caller_temporary_active' \
    'concurrent caller loser did not refuse the live owner'
[ "$(find "$concurrent_tree" -mindepth 1 -maxdepth 1 | wc -l)" -eq 1 ] \
    || fail 'concurrent caller loser mutated the claimed tree'
python3 - "$concurrent_tree/.pf-caller-temporary.json" "$winner" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as stream:
    manifest = json.load(stream)
assert manifest["bead"] == sys.argv[2]
assert manifest["state"] == "active"
PY
if [ "$winner" = caller-a ]; then
    printf 'release\n' > "$release_a_fifo"
else
    printf 'release\n' > "$release_b_fifo"
fi
wait "$caller_a_pid"
wait "$caller_b_pid"
[ -z "$(find "$concurrent_tree" -mindepth 1 -maxdepth 1 -print -quit)" ] \
    || fail 'winner release left caller-temporary reservation bytes'
python3 "$HELPER" require-caller-temporary --root "$build_root" \
    --tree "$concurrent_tree" --producer pf-build.sh --bead caller-later \
    --device a133 > "$TMP/caller-later.out"
python3 "$HELPER" release-caller-temporary --root "$build_root" \
    --tree "$concurrent_tree" --producer pf-build.sh --bead caller-later \
    --device a133 > "$TMP/caller-later-release.out"
has "$TMP/caller-later.out" 'max_active=1 active=1 bead=caller-later' \
    'later caller was not admitted after winner release'
exec 8>&-
exec 9>&-

# Malformed and dead-owner reservations are proof failures, never cleanup
# invitations. Both stay byte-for-byte unchanged and block admission.
malformed_caller="$TMP/caller-malformed"
mkdir -p "$malformed_caller"
printf '{"schema":"pocketforge.caller-temporary/v1"}\n' \
    > "$malformed_caller/.pf-caller-temporary.json"
malformed_caller_before="$(sha256sum "$malformed_caller/.pf-caller-temporary.json")"
if python3 "$HELPER" require-caller-temporary --root "$build_root" \
    --tree "$malformed_caller" --producer pf-build.sh --bead malformed-caller \
    --device a133 > "$TMP/malformed-caller.out" 2>&1; then
    fail 'malformed caller-temporary reservation was accepted'
fi
has "$TMP/malformed-caller.out" 'keep_reason=invalid_manifest' \
    'malformed caller-temporary refusal missing'
[ "$(sha256sum "$malformed_caller/.pf-caller-temporary.json")" = "$malformed_caller_before" ] \
    || fail 'malformed caller-temporary reservation changed'

dead_caller="$TMP/caller-dead"
mkdir -p "$dead_caller"
python3 "$HELPER" require-caller-temporary --root "$build_root" --tree "$dead_caller" \
    --producer pf-build.sh --bead dead-caller --device a133 > "$TMP/dead-caller-start.out"
python3 - "$dead_caller/.pf-caller-temporary.json" <<'PY'
import json
from pathlib import Path
import sys
path = Path(sys.argv[1])
manifest = json.loads(path.read_text(encoding="utf-8"))
manifest["owner_start_ticks"] += 1
path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
dead_caller_before="$(sha256sum "$dead_caller/.pf-caller-temporary.json")"
if python3 "$HELPER" require-caller-temporary --root "$build_root" \
    --tree "$dead_caller" --producer pf-build.sh --bead another-caller \
    --device a133 > "$TMP/dead-caller.out" 2>&1; then
    fail 'dead-owner caller-temporary reservation was accepted'
fi
has "$TMP/dead-caller.out" 'keep_reason=owner_not_live' \
    'dead-owner caller-temporary refusal missing'
[ "$(sha256sum "$dead_caller/.pf-caller-temporary.json")" = "$dead_caller_before" ] \
    || fail 'dead-owner caller-temporary reservation changed'

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
