#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENTRY="$ROOT/scripts/pf-ci-buildx"
T="$(mktemp -d "${RUNNER_TEMP:-/tmp}/platform-pf-ci-buildx-test.XXXXXX")"
cleanup_test() {
    find "$T" -mindepth 1 -delete
    rmdir "$T"
}
trap cleanup_test EXIT
mkdir -p "$T/bin" "$T/state"

cat > "$T/bin/docker" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$PF_TEST_STATE/docker.calls"
case "$1 $2" in
    "buildx inspect") [ -e "$PF_TEST_STATE/builder" ] ;;
    "buildx create")
        : > "$PF_TEST_STATE/builder"
        while [ "$#" -gt 0 ]; do
            if [ "$1" = --config ]; then
                cp -- "$2" "$PF_TEST_STATE/effective-config.toml"
                break
            fi
            shift
        done
        ;;
    "buildx build") [ "${PF_TEST_BUILD_FAIL:-0}" != 1 ] || exit 7 ;;
    "buildx prune"|"buildx rm") exit 0 ;;
    *) exit 97 ;;
esac
SH
chmod +x "$T/bin/docker"

env -i PATH="$T/bin:/usr/bin:/bin" PF_TEST_STATE="$T/state" \
    PF_CI_BUILDX_LOCK="$T/builder.lock" PF_CI_BUILDX_NAMESERVERS=10.0.0.53 \
    RUNNER_TEMP="$T" "$ENTRY" build --load --tag pocketforge-sim:test fixture

grep -qxF 'buildx build --builder pf-ci --label org.pocketforge.cache-owner=pf-build-ci --load --tag pocketforge-sim:test fixture' \
    "$T/state/docker.calls"
grep -qxF 'buildx prune --builder pf-ci --all --force --keep-storage 8gb' \
    "$T/state/docker.calls"
grep -qxF '  nameservers = ["10.0.0.53",]' "$T/state/effective-config.toml"
# shellcheck disable=SC2016 # Assert the literal workflow variable reference.
grep -qF '"$platform_wd/scripts/pf-ci-buildx" build --load' \
    "$ROOT/.github/workflows/sim-descriptor-gate.yml"
if grep -Ev '^[[:space:]]*#' "$ROOT/.github/workflows/sim-descriptor-gate.yml" \
        | grep -Eq '^[[:space:]]*docker build([[:space:]\\]|$)'; then
    echo 'sim descriptor gate still writes the integrated builder' >&2
    exit 1
fi

: > "$T/state/docker.calls"
set +e
env -i PATH="$T/bin:/usr/bin:/bin" PF_TEST_STATE="$T/state" PF_TEST_BUILD_FAIL=1 \
    PF_CI_BUILDX_LOCK="$T/builder.lock" PF_CI_BUILDX_NAMESERVERS=10.0.0.53 \
    RUNNER_TEMP="$T" "$ENTRY" build --load --tag pocketforge-sim:test fixture
rc=$?
set -e
[ "$rc" -eq 7 ]
grep -qxF 'buildx prune --builder pf-ci --all --force --keep-storage 8gb' \
    "$T/state/docker.calls"

: > "$T/state/docker.calls"
exec 8> "$T/busy.lock"
flock -n 8
if env -i PATH="$T/bin:/usr/bin:/bin" PF_TEST_STATE="$T/state" \
    PF_CI_BUILDX_LOCK="$T/busy.lock" PF_CI_BUILDX_NAMESERVERS=10.0.0.53 \
    RUNNER_TEMP="$T" "$ENTRY" build --load fixture > "$T/busy.out" 2>&1; then
    echo 'platform builder accepted an active producer lock' >&2
    exit 1
fi
flock -u 8
grep -q 'reason=builder_busy' "$T/busy.out"
test ! -s "$T/state/docker.calls"

python3 - "$ROOT/buildkit/pf-ci-buildkitd.toml" <<'PY'
import sys, tomllib
policy = tomllib.load(open(sys.argv[1], "rb"))["worker"]["oci"]
assert policy == {"gc": True, "reservedSpace": "2GB", "maxUsedSpace": "8GB", "minFreeSpace": "64GB"}
PY

printf 'platform_pf_ci_buildx_test=PASS builder=pf-ci keep_storage=8gb\n'
