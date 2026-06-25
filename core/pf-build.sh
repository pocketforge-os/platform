#!/usr/bin/env bash
# core/pf-build.sh — the SoC-AGNOSTIC `pf build` dispatcher.
#
# Reads a device profile, validates it, resolves the family, and calls the family's
# four hooks in order. The core owns everything BETWEEN the hooks (validate, fetch,
# rootfs, reproducibility-finalize, SHA emit); the family owns everything INSIDE them.
# The core contains ZERO family vocabulary (ci/core-purity-check.sh enforces this).
#
#   pf build --device <id> --artifact {os-image|containers} --target {ci-dell|dev-modelmaker}
#            [--dry-run] [--bead <id>] [--image-repo <path>]
#
# M-1 SKELETON (tsp-1dl.1): the family hooks are dispatch placeholders (DRY by default),
# so this proves the seam end to end. The real per-stage container build lands in B4.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=core/lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

DEVICE="" ARTIFACT="os-image" TARGET="dev-modelmaker" BEAD="${PF_BEAD:-adhoc}"
PF_DRY_RUN="${PF_DRY_RUN:-1}"
PF_IMAGE_REPO="${PF_IMAGE_REPO:-$HOME/image}"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --device)     DEVICE="$2"; shift 2 ;;
        --artifact)   ARTIFACT="$2"; shift 2 ;;
        --target)     TARGET="$2"; shift 2 ;;
        --bead)       BEAD="$2"; shift 2 ;;
        --image-repo) PF_IMAGE_REPO="$2"; shift 2 ;;
        --dry-run)    PF_DRY_RUN=1; shift ;;
        --no-dry-run) PF_DRY_RUN=0; shift ;;
        -h|--help)    grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) pf_die "unknown arg: $1" ;;
    esac
done
[ -n "$DEVICE" ] || pf_die "--device <id> is required (see: pf list)"
case "$ARTIFACT" in os-image|containers) ;; *) pf_die "--artifact must be os-image|containers" ;; esac
case "$TARGET"   in ci-dell|dev-modelmaker) ;; *) pf_die "--target must be ci-dell|dev-modelmaker" ;; esac

pf_log "build device=$DEVICE artifact=$ARTIFACT target=$TARGET bead=$BEAD dry_run=$PF_DRY_RUN"
pf_validate "$DEVICE"
pf_load_env "$DEVICE"

# Bead-id-keyed dirs (infra-013 concurrency: two builds never collide).
PF_OUT_DIR="${PF_OUT_DIR:-/tmp/pf-build/$BEAD/$DEVICE}"
mkdir -p "$PF_OUT_DIR"
export PF_OUT_DIR PF_DRY_RUN PF_IMAGE_REPO PF_PLATFORM_DIR PF_BEAD="$BEAD"

FAM_DIR="$(pf_family_dir "$PF_FAMILY")"
[ -d "$FAM_DIR" ] || pf_die "family plugin missing: $FAM_DIR"

run_hook() {
    local hook="$1"; shift
    local path="$FAM_DIR/$hook"
    [ -f "$path" ] || pf_die "family '$PF_FAMILY' missing hook $hook"
    pf_log "hook ${PF_FAMILY}/$hook"
    bash "$path" "$@"
}

if [ "$ARTIFACT" = "os-image" ]; then
    # CORE: (fetch blob groups by CID, build_rootfs) are stubbed in M-1 -> B3/B4.
    pf_log "core: fetch blob groups [$PF_BLOB_GROUPS] (B3 multistage fetch-by-CID — stub in M-1)"
    pf_log "core: build_rootfs (mmdebstrap, SoC-agnostic — legacy image/ build in M-1)"
    run_hook build-kernel.sh
    run_hook build-bootchain.sh
    run_hook assemble-image.sh
    pf_log "core: reproducibility_finalize (faketime/disorderfs/SOURCE_DATE_EPOCH — B4/B6)"
    pf_log "core: emit artifact '$PF_IMAGE_NAME' + SHA + provenance under $PF_OUT_DIR (B4)"
else
    pf_log "core: container-image path (apko-DROP -> mmdebstrap->tar->OCI) is B5 — not in B1"
fi
pf_log "build dispatch complete (device=$DEVICE artifact=$ARTIFACT)."
