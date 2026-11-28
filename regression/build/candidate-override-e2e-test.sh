#!/usr/bin/env bash
# End-to-end test of the candidate overrides (tsp-hqm1p.182.949.6): run core/pf-build.sh as
# a PROCESS with env PF_GPU_UM_SHA / PF_IMAGE_SHA set, exactly as a caller would.
#
# Why a process test: the unit tests (gpu-um- and image-candidate-override-test.sh) drive
# the extracted functions directly, so they cannot see what pf-build.sh does to the env
# before the override runs. pf_load_env evals `profile.py env`, which exports
# PF_GPU_UM_SHA=<lock pin>; that clobbered the caller's candidate, and a real candidate
# build silently built the lock pin while logging "matches the platform.lock gpu-um pin"
# (gpu-16 verification (b), 2026-11-28).
#
# Hermetic and offline: HOME, PF_MIRROR_DIR and the image repo are empty temp dirs. The
# overrides run in pf_os_image_dockerbuild right after the lock-state gate; the build then
# dies at the missing image Dockerfile, before any epoch, fetch, staging or container call.
# The candidate record (written only by a real build) is covered by the unit test.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEVICE=a133-open-7x-gpu-cts
GPU_UM_CAND=0123456789abcdef0123456789abcdef01234567
IMG_CAND=89abcdef0123456789abcdef0123456789abcdef

T="$(mktemp -d)"
trap 'rm -rf -- "$T"' EXIT
mkdir -p "$T/home" "$T/mirrors" "$T/image"

fail() { echo "FAIL: $*" >&2; exit 1; }

# The lock pins this device builds without an override.
ba="$(python3 "$ROOT/core/profile.py" buildargs "$DEVICE" dev)"
GPU_UM_PIN="$(printf '%s\n' "$ba" | sed -n 's/^PF_GPU_UM_SHA=//p')"
IMG_PIN="$(printf '%s\n' "$ba" | sed -n 's/^PF_IMAGE_SHA=//p')"
[ "${#GPU_UM_PIN}" -eq 40 ] || fail "no 40-hex gpu-um pin for $DEVICE"
[ "${#IMG_PIN}" -eq 40 ] || fail "no 40-hex image pin for $DEVICE"
[ "$GPU_UM_CAND" != "$GPU_UM_PIN" ] && [ "$IMG_CAND" != "$IMG_PIN" ]

# run_build <name> [VAR=value ...] — run pf-build.sh in dry-run under a scrubbed env;
# leaves the combined log in $T/<name>.log.
run_build() {
    local name="$1"; shift
    set +e
    env -i HOME="$T/home" PATH="$PATH" LANG=C.UTF-8 \
        PF_MIRROR_DIR="$T/mirrors" PF_BUILD_TREE_ROOT="$T" \
        PF_BUILD_STAGE_TARGET=component-test-gpu-um \
        "$@" \
        bash "$ROOT/core/pf-build.sh" --device "$DEVICE" --artifact os-image \
            --target dev-modelmaker --variant dev --bead "candidate-e2e-$name" \
            --image-repo "$T/image" --dry-run \
        >"$T/$name.log" 2>&1
    set -e
}
show() { sed 's/^/    | /' "$T/$1.log" >&2; }
log_has() { grep -Fq -- "$2" "$T/$1.log" || { show "$1"; fail "$1: log lacks: $2"; }; }
log_lacks() { ! grep -Fq -- "$2" "$T/$1.log" || { show "$1"; fail "$1: log has: $2"; }; }
# Every case must get past the overrides to the deterministic Dockerfile stop (or die in
# the override itself), so a passing case cannot be an early unrelated failure.
DOCKERFILE_STOP="missing $T/image/build/Dockerfile.pf"

# 1. gpu-um candidate: the caller's value survives pf_load_env and the override fires.
run_build gpu_um PF_GPU_UM_SHA="$GPU_UM_CAND"
log_has gpu_um "!!! NON-HERMETIC CANDIDATE: gpu-um-src overridden to $GPU_UM_CAND (lock pin was $GPU_UM_PIN)"
log_lacks gpu_um "matches the platform.lock gpu-um pin"
log_has gpu_um "$DOCKERFILE_STOP"
echo "ok - gpu-um candidate survives pf_load_env and fires"

# 2. Image candidate, end to end (profile env does not export PF_IMAGE_SHA today; this
#    keeps a future export from clobbering it silently).
run_build image PF_IMAGE_SHA="$IMG_CAND"
log_has image "!!! NON-HERMETIC CANDIDATE: image-src overridden to $IMG_CAND (lock pin was $IMG_PIN)"
log_has image "$DOCKERFILE_STOP"
echo "ok - image candidate fires end to end"

# 3. Both at once.
run_build both PF_GPU_UM_SHA="$GPU_UM_CAND" PF_IMAGE_SHA="$IMG_CAND"
log_has both "gpu-um-src overridden to $GPU_UM_CAND"
log_has both "image-src overridden to $IMG_CAND"
echo "ok - both candidates fire together"

# 4. Equal to the pin: hermetic.
run_build pin PF_GPU_UM_SHA="$GPU_UM_PIN"
log_has pin "PF_GPU_UM_SHA=$GPU_UM_PIN matches the platform.lock gpu-um pin"
log_lacks pin "NON-HERMETIC CANDIDATE"
log_has pin "$DOCKERFILE_STOP"
echo "ok - a pin-equal PF_GPU_UM_SHA is hermetic"

# 5. No override at all: the profile's own PF_GPU_UM_SHA export is NOT a request.
run_build none
log_lacks none "NON-HERMETIC CANDIDATE"
log_lacks none "matches the platform.lock gpu-um pin"
log_has none "$DOCKERFILE_STOP"
echo "ok - no override: the profile export alone is not a candidate request"

# 6. A refusal sees the caller's value end to end.
run_build malformed PF_GPU_UM_SHA=NOT-A-SHA
log_has malformed "PF_GPU_UM_SHA must be exactly 40 lowercase hex chars (got 'NOT-A-SHA')"
echo "ok - a malformed caller PF_GPU_UM_SHA is refused end to end"

echo "PASS: candidate overrides end to end (6 cases)"
