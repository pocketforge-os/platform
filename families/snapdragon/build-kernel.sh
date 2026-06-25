#!/usr/bin/env bash
# families/snapdragon/build-kernel.sh — STUB (B8/M-5). Real behaviour: build msm-DRM kernel + DTB (source-built; better ownership than sunxi-a133).
# Proves the seam only: the core dispatches the SAME hook name; the snapdragon
# plugin owns all fastboot/XBL/EDL vocabulary (the core never sees it).
set -euo pipefail
echo "[snapdragon/build_kernel] STUB device=$PF_DEVICE_ID — would: build msm-DRM kernel + DTB (source-built; better ownership than sunxi-a133)"
echo "[snapdragon/build_kernel] not implemented in B1 (paper proof). Real onboarding: tsp-1dl.8 / M-5."
exit 0
