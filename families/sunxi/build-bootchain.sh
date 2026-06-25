#!/usr/bin/env bash
# families/sunxi/build-bootchain.sh — sunxi FAMILY hook: build_bootchain.
# Contract: out = SPL/U-Boot/BL31 set OR a pass-through vendor blob group.
# The sunxi family handles BOTH cases declaratively from the profile:
#   - a523: model=sunxi-spl-uboot  -> build U-Boot (bootchain-sunxi) + TF-A BL31.
#   - a133: model=sunxi-boot0-fex  -> NO owned U-Boot for sun50iw10; pass through the
#           blob group ($PF_BOOTCHAIN_BLOB_GROUP) fetched by the core fetch stage.
#
# M-1 SKELETON: documents the per-device path; real build moves in at B2/B4.
set -euo pipefail
echo "[sunxi/build_bootchain] device=$PF_DEVICE_ID model=$PF_BOOTCHAIN_MODEL boot_proto=$PF_BOOT_PROTO"
case "$PF_BOOTCHAIN_MODEL" in
  sunxi-spl-uboot)
    echo "[sunxi/build_bootchain]   source-built: U-Boot(${PF_UBOOT_REPO:-?}) + TF-A BL31 -> SPL@${PF_SPL_OFFSET_KIB:-8}KiB"
    echo "[sunxi/build_bootchain]   M-1: built by legacy flow; B2 collapses to bootchain-sunxi, B4 builds in-container." ;;
  sunxi-boot0-fex)
    echo "[sunxi/build_bootchain]   pass-through vendor blob group: ${PF_BOOTCHAIN_BLOB_GROUP:?} (no owned U-Boot for this SoC)" ;;
  *)
    echo "[sunxi/build_bootchain] unknown bootchain model: $PF_BOOTCHAIN_MODEL" >&2; exit 2 ;;
esac
