#!/usr/bin/env bash
# Unit-test pf_ensure_insecure_builder's stale-config self-heal (tsp-mc9m.41.984.20).
# buildx copies the buildkitd config into the builder re-encoded: buildx v0.37.1
# (go-toml v2.4.3) writes [registry.'10.0.32.86:5555'] where older buildx wrote
# [registry."10.0.32.86:5555"]. Either form is in sync. Only a registry that is
# genuinely missing from the running config makes the builder stale; a false
# "stale" runs `docker buildx rm` and discards the build cache on every build.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/core/pf-build.sh"

# Extract the shipped function and drive it directly (same pattern as the other tests).
extract() { sed -n "/^$1()/,/^}/p" "$BUILD"; }
eval "$(extract pf_ensure_insecure_builder)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cat > "$WORK/buildkitd.toml" <<'EOF'
[registry]

  [registry."10.0.32.86:5555"]
    http = true
    insecure = true

  [registry."localhost:5000"]
    http = true
    insecure = true

[dns]
  nameservers = ["192.0.2.53"]
EOF
export PF_BUILDKITD_CONFIG="$WORK/buildkitd.toml"

LOG=""
pf_log() { LOG="$LOG$*"$'\n'; }
pf_die() { printf 'DIE: %s\n' "$*" >&2; exit 3; }

# Fake docker: `buildx inspect` succeeds (the builder exists), `exec ... cat` prints
# $RUNNING, and every other call is recorded in $CALLS.
CALLS="$WORK/calls"
docker() {
    case "$1 ${2:-}" in
        "buildx inspect") return 0 ;;
        "exec "*) printf '%s\n' "$RUNNING"; return 0 ;;
    esac
    printf '%s\n' "$*" >> "$CALLS"
}

# `! grep` does not trip errexit, so assert explicitly.
not_stale() {
    if grep -q 'config is stale' <<<"$LOG"; then
        printf 'FAIL: in-sync builder judged stale\n%s' "$LOG" >&2
        exit 1
    fi
}

run_case() {
    LOG=""; : > "$CALLS"
    pf_ensure_insecure_builder pf-test
}

# --- 1. buildx >= go-toml v2: literal-quoted registry keys are in sync -----------------
RUNNING="$(cat <<'EOF'
[dns]
  nameservers = ['192.0.2.53']

[registry]
  [registry.'10.0.32.86:5555']
    http = true
    insecure = true

  [registry.'localhost:5000']
    http = true
    insecure = true
EOF
)"
run_case
not_stale
test ! -s "$CALLS"
echo 'ok 1 - literal-quoted keys (buildx v0.37.1 re-encoding) are in sync; builder and cache kept'

# --- 2. older buildx: basic-quoted registry keys are in sync ---------------------------
RUNNING="$(cat <<'EOF'
[registry]
  [registry."10.0.32.86:5555"]
    http = true
    insecure = true
  [registry."localhost:5000"]
    http = true
    insecure = true
EOF
)"
run_case
not_stale
test ! -s "$CALLS"
echo 'ok 2 - basic-quoted keys (older buildx) are in sync; builder and cache kept'

# --- 3. a registry genuinely missing from the running config is still stale ------------
RUNNING="$(cat <<'EOF'
[registry]
  [registry.'localhost:5000']
    http = true
    insecure = true
EOF
)"
run_case
grep -q "buildx builder 'pf-test' buildkitd config is stale" <<<"$LOG"
grep -q '^buildx rm pf-test$' "$CALLS"
grep -q "^buildx create --name pf-test .*--buildkitd-config $PF_BUILDKITD_CONFIG --bootstrap$" "$CALLS"
echo 'ok 3 - a missing registry still recreates the builder with the config'

# --- 4. a host that only appears as a substring does not count as present --------------
RUNNING="$(cat <<'EOF'
[registry]
  [registry.'10.0.32.86:55550']
    http = true
  [registry.'localhost:5000']
    http = true
EOF
)"
run_case
grep -q 'config is stale' <<<"$LOG"
echo 'ok 4 - a longer host containing the registry as a prefix is not a match'

echo 'PASS: insecure builder config self-heal (4 checks)'
