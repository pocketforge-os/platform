#!/usr/bin/env bash
# families/snapdragon/flash.sh — STUB (B8/M-5). Real behaviour: fastboot flash named partitions; EDL/Firehose recovery.
# Proves the seam only: the core dispatches the SAME hook name; the snapdragon
# plugin owns all fastboot/XBL/EDL vocabulary (the core never sees it).
set -euo pipefail
echo "[snapdragon/flash] STUB device=$PF_DEVICE_ID — would: fastboot flash named partitions; EDL/Firehose recovery"
echo "[snapdragon/flash] not implemented in B1 (paper proof). Real onboarding: tsp-1dl.8 / M-5."
exit 0
