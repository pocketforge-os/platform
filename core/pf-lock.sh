#!/usr/bin/env bash
# core/pf-lock.sh — `pf lock`: freeze every repo's ref tip into platform.lock
# (the AOSP `repo manifest -r` / west / vcstool --exact / flake.lock freezer).
# Thin wrapper over core/pf_lock.py (real writer landed in tsp-1dl.1.1); the
# reproducibility anchor: builds use the .lock SHA, NEVER a branch tip.
#
#   pf lock                         preview (resolve + print, write nothing)
#   pf lock --interim               write a DEV-ONLY, non-authoritative seed
#   pf lock --authoritative --i-know-b2-is-done   write the release seed (post-B2)
#   pf lock --source checkouts [--checkouts DIR]   pin local HEADs instead of ref tips
#
# See `pf lock --help` (core/pf_lock.py) for the full contract.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
exec "${PF_PY:-python3}" "$SCRIPT_DIR/pf_lock.py" "$@"
