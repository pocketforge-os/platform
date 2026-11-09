#!/usr/bin/env bash
# regression/build/registry-cache-flags-test.sh — pins the cross-slot registry cache
# aperture (tsp-hqm1p.182.13).
#
# Owned-image CI imports the BuildKit cache of every slot from the NAS registry L2
# and, in a separate `--target cache-export` solve after a gated image build, exports
# only its own slot's ref. pf-build.sh admits that through two env inputs:
#   PF_BUILDX_CACHE_FROM  0-3 newline-separated exact slot refs
#   PF_BUILDX_CACHE_TO    0-1 slot ref with allowlisted export options, and only for
#                         the cache-export target, which then outputs cacheonly.
# Anything else is refused by name before buildx runs. Proven against the
# sed-extracted shipped functions (the cmd array they build) plus a structural pin
# of their call site in pf_os_image_dockerbuild. It is hermetic: no image checkout,
# no source mirrors, no network. (A full `pf-build.sh --dry-run` resolves every
# pinned SHA's epoch through ~/wt/.mirrors, which the offline CI runner lacks.)
set -Eeuo pipefail
trap 'rc=$?; echo "FAIL: line ${LINENO}: ${BASH_COMMAND} (rc=${rc})" >&2; exit "${rc}"' ERR
ROOT="$(cd "$(dirname "$0")/../.." >/dev/null 2>&1 && pwd)"
# shellcheck source=core/lib/common.sh
. "$ROOT/core/lib/common.sh"
extract() { sed -n "/^$1()/,/^}/p" "$ROOT/core/pf-build.sh"; }
eval "$(extract pf_validate_build_stage_target; extract pf_registry_cache_args; extract pf_build_output_args)"
for f in pf_validate_build_stage_target pf_registry_cache_args pf_build_output_args; do
    declare -F "$f" >/dev/null || { echo "FAIL: could not extract $f from core/pf-build.sh"; exit 1; }
done

TMP="$(mktemp -d "${RUNNER_TEMP:-/tmp}/pf-registry-cache-test.XXXXXX")"
trap 'find "$TMP" -mindepth 1 -delete; rmdir "$TMP"' EXIT
REF=10.0.32.86:5555/pocketforge/cache-owned-image
FROM3="type=registry,ref=$REF:slot-1
type=registry,ref=$REF:slot-2
type=registry,ref=$REF:slot-3"
TO2="type=registry,ref=$REF:slot-2,mode=max,image-manifest=true,oci-mediatypes=true,compression=zstd,ignore-error=true"

argv() {  # <stage> <host> <from> <to> -> the aperture's cmd words, one per line
    local cmd=()
    PF_BUILDX_CACHE_FROM="$3" PF_BUILDX_CACHE_TO="$4" pf_registry_cache_args "$1" "$2"
    pf_build_output_args "$1" /out
    printf '%s\n' "${cmd[@]}"
}
expect() {  # <label> <want> <got>
    [ "$2" = "$3" ] || { printf 'FAIL: %s\n--- want\n%s\n--- got\n%s\n' "$1" "$2" "$3" >&2; exit 1; }
}

echo "== 1. default: no registry cache, local output =="
expect "default argv" "--output
type=local,dest=/out" "$(argv export ephemeral "" "")"
echo "ok   - unset inputs add nothing but the unchanged local output"

echo "== 2. warm import: three slot refs, in order, no export =="
expect "import argv" "--cache-from
type=registry,ref=$REF:slot-1
--cache-from
type=registry,ref=$REF:slot-2
--cache-from
type=registry,ref=$REF:slot-3
--output
type=local,dest=/out" "$(argv export ephemeral "$FROM3" "")"
echo "ok   - --cache-from x3 on the export target"

echo "== 3. cache-export solve: own slot ref, cacheonly output =="
expect "cache-export argv" "--cache-from
type=registry,ref=$REF:slot-1
--cache-from
type=registry,ref=$REF:slot-2
--cache-from
type=registry,ref=$REF:slot-3
--cache-to
$TO2
--output
type=cacheonly" "$(argv cache-export ephemeral "$FROM3" "$TO2")"
echo "ok   - one --cache-to, --output type=cacheonly"

echo "== 3b. the shipped build wires both functions into its buildx argv =="
body="$(extract pf_os_image_dockerbuild)"
# The patterns below match pf-build.sh's literal variable text.
# shellcheck disable=SC2016
grep -Fxq '    pf_registry_cache_args "$build_stage_target" "$TARGET"' <<< "$body" \
    || { echo "FAIL: pf_os_image_dockerbuild does not call pf_registry_cache_args" >&2; exit 1; }
# shellcheck disable=SC2016
grep -Fxq '    pf_build_output_args "$build_stage_target" "$PF_OUT_DIR"' <<< "$body" \
    || { echo "FAIL: pf_os_image_dockerbuild does not call pf_build_output_args" >&2; exit 1; }
# shellcheck disable=SC2016
order="$(grep -nE '^    (pf_registry_cache_args|pf_build_output_args) |--metadata-file|--target "\$build_stage_target"|"\$SCRIPT_DIR/lib/pf-build-env" "\$\{cmd\[@\]\}"' <<< "$body" | cut -d: -f1 | paste -sd' ')"
read -r t_line c_line o_line m_line x_line <<< "$order"
if ! { [ -n "${x_line:-}" ] && [ "$t_line" -lt "$c_line" ] && [ "$c_line" -lt "$o_line" ] \
    && [ "$o_line" -lt "$m_line" ] && [ "$m_line" -lt "$x_line" ]; }; then
    echo "FAIL: call order --target < cache args < output < metadata < exec, got lines: $order" >&2
    exit 1
fi
if grep -Eq -- '--output +"type=local' <<< "$body"; then
    echo "FAIL: pf_os_image_dockerbuild still spells its own --output" >&2; exit 1
fi
echo "ok   - target, cache args, output, metadata, then the one exec of cmd"

echo "== 4. refusals are named and happen before buildx =="
refuse() {  # <expected-message> <stage> <host> <from> <to>
    local want="$1" rc=0
    # `|| rc=$?` keeps the expected refusal out of the ERR trap.
    # shellcheck disable=SC2034  # cmd is the array pf_registry_cache_args appends to
    ( cmd=(); PF_BUILDX_CACHE_FROM="$4" PF_BUILDX_CACHE_TO="$5" pf_registry_cache_args "$2" "$3" ) \
        >"$TMP/r.out" 2>"$TMP/r.err" || rc=$?
    [ "$rc" -ne 0 ] || { echo "FAIL: admitted ($want): from='$4' to='$5' stage=$2 host=$3"; exit 1; }
    grep -Fq "$want" "$TMP/r.err" || { echo "FAIL: refusal not named '$want':"; cat "$TMP/r.err"; exit 1; }
}
bad_from='PF_BUILDX_CACHE_FROM line is not an admitted registry cache ref'
bad_to='PF_BUILDX_CACHE_TO is not an admitted registry cache ref'
refuse "$bad_from" export ephemeral "type=registry,ref=registry.invalid/pocketforge/cache-owned-image:slot-1" ""
refuse "$bad_from" export ephemeral "type=registry,ref=$REF-x:slot-1" ""
refuse "$bad_from" export ephemeral "type=registry,ref=$REF:slot-0" ""
refuse "$bad_from" export ephemeral "type=registry,ref=$REF:slot-1,mode=max" ""
refuse "$bad_from" export ephemeral "type=local,src=/tmp/x" ""
refuse "$bad_from" export ephemeral "type=registry,ref=$REF:slot-1;touch /tmp/x" ""
refuse "$bad_from" export ephemeral " type=registry,ref=$REF:slot-1" ""
refuse 'PF_BUILDX_CACHE_FROM repeats a ref' export ephemeral "type=registry,ref=$REF:slot-1
type=registry,ref=$REF:slot-1" ""
refuse 'PF_BUILDX_CACHE_FROM admits at most 3 refs' export ephemeral "$FROM3
type=registry,ref=$REF:slot-4" ""
refuse "$bad_to" cache-export ephemeral "" "type=registry,ref=$REF:slot-2,push=true"
refuse "$bad_to" cache-export ephemeral "" "type=registry,ref=$REF:slot-2,mode=min,mode=max;x"
refuse "$bad_to" cache-export ephemeral "" "$TO2
$TO2"
refuse 'PF_BUILDX_CACHE_TO is only admitted for the cache-export target' export ephemeral "" "$TO2"
refuse 'the cache-export target needs PF_BUILDX_CACHE_TO' cache-export ephemeral "$FROM3" ""
refuse 'registry cache flags do not combine with the ci-dell local cache' export ci-dell "$FROM3" ""
echo "ok   - foreign/other-repo/slot-0/option-bearing/non-registry/metachar refs, duplicates,"
echo "       >3 imports, unknown export options, two exports, export off cache-export,"
echo "       cache-export without export and ci-dell mixing all refuse by name"

echo "== 5. cache-export is an admitted target; arbitrary stages still are not =="
[ "$(pf_validate_build_stage_target cache-export)" = cache-export ] \
    || { echo "FAIL: cache-export target rejected"; exit 1; }
for target in rootfs assemble debuginfo kernel; do
    if ( pf_validate_build_stage_target "$target" ) >/dev/null 2>&1; then
        echo "FAIL: $target admitted"; exit 1
    fi
done
echo "ok   - allowlist widened by exactly cache-export"

echo "REGISTRY CACHE FLAGS GATE OK"
