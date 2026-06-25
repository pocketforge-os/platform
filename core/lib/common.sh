#!/usr/bin/env bash
# core/lib/common.sh — shared CORE helpers (SoC-agnostic; no family vocabulary).
set -euo pipefail

PF_PLATFORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." >/dev/null 2>&1 && pwd)"
export PF_PLATFORM_DIR
PF_PY="${PF_PY:-python3}"

pf_log()  { printf '[pf] %s\n' "$*" >&2; }
pf_die()  { printf '[pf] ERROR: %s\n' "$*" >&2; exit 1; }

# Resolve a device profile to flattened PF_* env and source it into the caller.
pf_load_env() {
    local dev="$1"
    local env_out
    env_out="$("$PF_PY" "$PF_PLATFORM_DIR/core/profile.py" env "$dev")" \
        || pf_die "profile env failed for '$dev'"
    eval "$env_out"
}

# Validate a profile; abort on ERROR (warnings are printed, non-fatal).
pf_validate() {
    local dev="$1"
    "$PF_PY" "$PF_PLATFORM_DIR/core/profile.py" validate "$dev" \
        || pf_die "profile '$dev' failed validation (see ERROR lines above)"
}

pf_family_dir() { printf '%s/families/%s' "$PF_PLATFORM_DIR" "$1"; }
