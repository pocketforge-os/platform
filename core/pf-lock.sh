#!/usr/bin/env bash
# core/pf-lock.sh — `pf lock`: freeze every repo's CURRENT checkout SHA into
# platform.lock (the AOSP `repo manifest -r` / `west` / vcstool --exact / flake.lock
# freezer). The reproducibility anchor: builds use the .lock SHA, NEVER a branch tip.
#
# ⚠ GATED in B1 (tsp-1dl.1): SHA-seeding is bead tsp-1dl.1.1, gated on A1 (clean
#   trees) + B2 (kernel-sunxi collapse) — BOTH move the SHAs, so seeding now pins
#   phantom refs. This command therefore REFUSES to write without --force and prints
#   what it WOULD pin, so the mechanism is reviewable now and runnable at 1.1.
#
#   pf lock [--checkouts <dir>] [--force]
#     --checkouts DIR   where the repo working copies live (default: $HOME)
#     --force           actually write platform.lock (only at tsp-1dl.1.1)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
. "$SCRIPT_DIR/lib/common.sh"

CHECKOUTS="${PF_CHECKOUTS:-$HOME}"
FORCE=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --checkouts) CHECKOUTS="$2"; shift 2 ;;
        --force)     FORCE=1; shift ;;
        -h|--help)   grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) pf_die "unknown arg: $1" ;;
    esac
done

pf_log "would freeze checkouts under: $CHECKOUTS (target: $PF_PLATFORM_DIR/platform.lock)"
# List the repos from the lock + resolve each current SHA (read-only preview).
mapfile -t REPOS < <("$PF_PY" "$SCRIPT_DIR/profile.py" repos | sed -n 's/^  \([^[:space:]]*\).*/\1/p')
for r in "${REPOS[@]}"; do
    co="$CHECKOUTS/$r"
    if [ -d "$co/.git" ]; then
        sha="$(git -C "$co" rev-parse HEAD 2>/dev/null || echo '?')"
        printf '  %-22s %s  (%s)\n' "$r" "$sha" "$co" >&2
    else
        printf '  %-22s %s\n' "$r" "(no checkout at $co)" >&2
    fi
done
if [ "$FORCE" != 1 ]; then
    pf_die "refusing to seed platform.lock in B1 — SHA-seeding is tsp-1dl.1.1 (A1+B2 move SHAs). Re-run with --force only there."
fi
pf_die "real seeding writer is implemented at tsp-1dl.1.1 (this skeleton previews only)."
