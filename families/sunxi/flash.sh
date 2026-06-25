#!/usr/bin/env bash
# families/sunxi/flash.sh — sunxi FAMILY hook: flash.
# Contract: in = resolved profile (PF_*) + a built .img(.xz); out = flashed device.
# sunxi flashes via `dd` to the SD behind the Dell two-LUN reader, selected by
# flash.slot. This delegates to the pocketforge-automation flash pipeline, which
# already owns SD discovery, safety gates, the webcam-gated serial arm, AND the
# A5 (tsp-48j.5) pf-lock device singleton lock — so different-device flashes run in
# parallel and same-device serialises. We do NOT re-implement device IO here.
set -euo pipefail
case "$PF_FLASH_METHOD" in
  dd-sd) ;;
  *) echo "[sunxi/flash] family sunxi only implements method=dd-sd (got '$PF_FLASH_METHOD')" >&2; exit 2 ;;
esac
PF_AUTOMATION="${PF_AUTOMATION:-$HOME/pocketforge-automation}"
flash="$PF_AUTOMATION/scripts/flash-owned-image.sh"
echo "[sunxi/flash] device=$PF_DEVICE_ID method=$PF_FLASH_METHOD slot=$PF_FLASH_SLOT image_name=$PF_IMAGE_NAME"
echo "[sunxi/flash] -> $flash --target dell --slot $PF_FLASH_SLOT (acquires pf-lock pf-device-$PF_DEVICE_ID; webcam-gated serial)"
if [ "${PF_DRY_RUN:-1}" = 1 ]; then
  echo "[sunxi/flash] PF_DRY_RUN=1 (default): not flashing (skeleton dispatch only)."
  exit 0
fi
[ -x "$flash" ] || { echo "[sunxi/flash] flash pipeline not found: $flash (set PF_AUTOMATION)" >&2; exit 1; }
exec "$flash" --target dell --slot "$PF_FLASH_SLOT" "$@"
