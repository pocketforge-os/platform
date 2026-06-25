#!/usr/bin/env bash
# core/pf-flash.sh — `pf flash`: load a device's env and dispatch the family flash hook.
# The core never knows HOW a family flashes — the method is the family's business; it
# only loads the profile and calls families/<family>/flash.sh. Args pass to the hook.
#   pf flash --device <id> [--no-dry-run] [hook args...]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
. "$SCRIPT_DIR/lib/common.sh"

DEVICE=""; PASS=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --device)     DEVICE="$2"; shift 2 ;;
        --no-dry-run) export PF_DRY_RUN=0; shift ;;
        --dry-run)    export PF_DRY_RUN=1; shift ;;
        *) PASS+=("$1"); shift ;;
    esac
done
[ -n "$DEVICE" ] || pf_die "--device <id> is required"
pf_validate "$DEVICE"
pf_load_env "$DEVICE"
export PF_DRY_RUN="${PF_DRY_RUN:-1}" PF_PLATFORM_DIR
FAM_DIR="$(pf_family_dir "$PF_FAMILY")"
[ -f "$FAM_DIR/flash.sh" ] || pf_die "family '$PF_FAMILY' has no flash.sh"
pf_log "flash device=$DEVICE family=$PF_FAMILY method=$PF_FLASH_METHOD slot=${PF_FLASH_SLOT:-} dry_run=$PF_DRY_RUN"
exec bash "$FAM_DIR/flash.sh" "${PASS[@]}"
