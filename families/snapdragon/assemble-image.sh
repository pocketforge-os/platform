#!/usr/bin/env bash
# families/snapdragon/assemble-image.sh — STUB (B8/M-5). Real behaviour: mkbootimg boot.img + GPT partition set (no genimage).
# Proves the seam only: the core dispatches the SAME hook name; the snapdragon
# plugin owns all fastboot/XBL/EDL vocabulary (the core never sees it).
set -euo pipefail
echo "[snapdragon/assemble_image] STUB device=$PF_DEVICE_ID — would: mkbootimg boot.img + GPT partition set (no genimage)"
echo "[snapdragon/assemble_image] not implemented in B1 (paper proof). Real onboarding: tsp-1dl.8 / M-5."
exit 0
