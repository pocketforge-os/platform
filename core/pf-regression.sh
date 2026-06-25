#!/usr/bin/env bash
# core/pf-regression.sh — the REGRESSION GATE harness (R1; tsp-1dl.1 + tsp-1dl.4).
#
# WHY: while `pf build` still shells the legacy image/ scripts, it MUST reproduce the
# pre-replan `make build-image` artifact — component artifacts (kernel Image, GPU .ko,
# rootfs tar) bit-identical + a diffoscope of the whole .img empty-or-explained —
# BEFORE anything underneath changes. B6's cross-HOST SHA gate does NOT cover this
# same-host legacy-vs-new axis (two hosts can agree on a WRONG artifact). So the net is
# captured HERE (B1: harness + committed baseline) and ENFORCED at B4 (when pf build's
# internals diverge from the legacy path and the legacy path is retired).
#
#   pf regression baseline --device <id> <file...>   # record SHA-256 of each file
#   pf regression check    --device <id> <file...>   # diff fresh SHAs vs the baseline
#
# Files are the component artifacts + the whole .img (pass whatever the build emits).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
. "$SCRIPT_DIR/lib/common.sh"
BASEDIR="$PF_PLATFORM_DIR/regression"

sub="${1:-}"; [ "$#" -gt 0 ] && shift || true
DEVICE=""; FILES=()
while [ "$#" -gt 0 ]; do
    case "$1" in --device) DEVICE="$2"; shift 2 ;; *) FILES+=("$1"); shift ;; esac
done
[ -n "$DEVICE" ] || pf_die "--device <id> required"
[ "${#FILES[@]}" -gt 0 ] || pf_die "give one or more artifact files to hash"
mkdir -p "$BASEDIR"
BASELINE="$BASEDIR/$DEVICE.baseline.sha256"

hash_now() { for f in "${FILES[@]}"; do [ -f "$f" ] || pf_die "missing artifact: $f"; printf '%s  %s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "$(basename "$f")"; done; }

case "$sub" in
    baseline)
        hash_now | sort -k2 > "$BASELINE"
        pf_log "recorded baseline ($(wc -l < "$BASELINE") components) -> $BASELINE (commit it)"
        cat "$BASELINE" ;;
    check)
        [ -f "$BASELINE" ] || pf_die "no baseline at $BASELINE — run `pf regression baseline` first (B4)"
        now="$(hash_now | sort -k2)"
        if diff -u "$BASELINE" <(printf '%s\n' "$now") >/tmp/pf-regression.diff 2>&1; then
            pf_log "REGRESSION OK: all components bit-identical to baseline ($DEVICE)"
        else
            pf_log "REGRESSION FAIL ($DEVICE): components diverged from baseline:"; cat /tmp/pf-regression.diff >&2
            pf_log "for the whole .img, run: diffoscope <baseline.img> <new.img>"
            exit 1
        fi ;;
    *) pf_die "usage: pf regression {baseline|check} --device <id> <file...>" ;;
esac
