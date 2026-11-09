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
# Anything else is refused by name before buildx runs. Proven against the real
# pf-build.sh dry-run argv and the sed-extracted shipped validator.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." >/dev/null 2>&1 && pwd)"
# shellcheck source=core/lib/common.sh
. "$ROOT/core/lib/common.sh"
extract() { sed -n "/^$1()/,/^}/p" "$ROOT/core/pf-build.sh"; }
eval "$(extract pf_validate_build_stage_target; extract pf_registry_cache_args)"
for f in pf_validate_build_stage_target pf_registry_cache_args; do
    declare -F "$f" >/dev/null || { echo "FAIL: could not extract $f from core/pf-build.sh"; exit 1; }
done

TMP="$(mktemp -d "${RUNNER_TEMP:-/tmp}/pf-registry-cache-test.XXXXXX")"
trap 'find "$TMP" -mindepth 1 -delete; rmdir "$TMP"' EXIT
REF=10.0.32.86:5555/pocketforge/cache-owned-image
FROM3="type=registry,ref=$REF:slot-1
type=registry,ref=$REF:slot-2
type=registry,ref=$REF:slot-3"
TO2="type=registry,ref=$REF:slot-2,mode=max,image-manifest=true,oci-mediatypes=true,compression=zstd,ignore-error=true"

dry() {  # [VAR=value...] — the real pf-build.sh dry-run argv, inputs scrubbed first
    env -u PF_BUILDX_CACHE_FROM -u PF_BUILDX_CACHE_TO -u PF_BUILD_STAGE_TARGET "$@" \
        "$ROOT/core/pf-build.sh" --device a133 --variant dev --dry-run \
        --bead registry-cache-test 2>&1
}

echo "== 1. default argv carries no registry cache =="
out="$(dry)"
if grep -Eq 'type=registry|cacheonly' <<< "$out"; then
    echo "FAIL: default build gained registry cache flags"; exit 1
fi
grep -Fq -- '--target export' <<< "$out" || { echo "FAIL: default target is not export"; exit 1; }
echo "ok   - unset inputs leave the argv unchanged"

echo "== 2. warm import: three slot refs, in order, no export =="
out="$(dry PF_BUILDX_CACHE_FROM="$FROM3")"
got="$(grep -o -- '--cache-from [^ ]*' <<< "$out" | sed 's/\\//g')"
want="$(printf -- '--cache-from %s\n' "type=registry,ref=$REF:slot-1" "type=registry,ref=$REF:slot-2" "type=registry,ref=$REF:slot-3")"
[ "$got" = "$want" ] || { echo "FAIL: cache-from argv:"; printf '%s\n' "$got"; exit 1; }
! grep -Fq -- '--cache-to' <<< "$out" || { echo "FAIL: import-only build exports"; exit 1; }
grep -Fq -- '--output type=local' <<< "$out" || { echo "FAIL: image build lost its local output"; exit 1; }
echo "ok   - --cache-from x3 on the export target"

echo "== 3. cache-export solve: own slot ref, cacheonly output =="
out="$(dry PF_BUILD_STAGE_TARGET=cache-export PF_BUILDX_CACHE_FROM="$FROM3" PF_BUILDX_CACHE_TO="$TO2")"
grep -Fq -- '--target cache-export' <<< "$out" || { echo "FAIL: cache-export target not selected"; exit 1; }
[ "$(grep -o -- '--cache-to [^ ]*' <<< "$out" | sed 's/\\//g')" = "--cache-to $TO2" ] \
    || { echo "FAIL: cache-to argv wrong"; grep -o -- '--cache-to [^ ]*' <<< "$out"; exit 1; }
grep -Fq -- '--output type=cacheonly' <<< "$out" || { echo "FAIL: cache-export must output cacheonly"; exit 1; }
! grep -Fq -- '--output type=local' <<< "$out" || { echo "FAIL: cache-export extracts files"; exit 1; }
echo "ok   - one --cache-to, --output type=cacheonly"

echo "== 4. refusals are named and happen before buildx =="
refuse() {  # <expected-message> <stage> <host> <from> <to>
    local want="$1" rc
    set +e
    # shellcheck disable=SC2034  # cmd is the array pf_registry_cache_args appends to
    ( cmd=(); PF_BUILDX_CACHE_FROM="$4" PF_BUILDX_CACHE_TO="$5" pf_registry_cache_args "$2" "$3" ) \
        >"$TMP/r.out" 2>"$TMP/r.err"
    rc=$?
    set -e
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
