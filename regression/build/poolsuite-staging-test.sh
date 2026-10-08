#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/core/pf-build.sh"

dev_args="$(python3 "$ROOT/core/profile.py" buildargs a133 dev)"
release_args="$(python3 "$ROOT/core/profile.py" buildargs a133 release)"
stage_body="$(sed -n '/^pf_stage_sources()/,/^}/p' "$BUILD")"
docker_body="$(sed -n '/^pf_os_image_dockerbuild()/,/^}/p' "$BUILD")"
# shellcheck disable=SC2016  # Match the literal variant gate in the source.
unconditional_contexts="$(sed -n '/# Source repos as named build contexts/,/if \[ "$VARIANT" = dev \]; then/p' \
    <<< "$docker_body")"

# shellcheck disable=SC2016  # Structural assertions intentionally match literal shell source.
grep -Fq 'poolsuite|poolsuite|$(v PF_POOLSUITE_SHA)' <<< "$stage_body"
# shellcheck disable=SC2016
grep -Fq -- '--build-context "poolsuite-src=$src_dir/poolsuite"' <<< "$unconditional_contexts"
grep -Eq '^PF_POOLSUITE_SHA=[0-9a-f]{40}$' <<< "$dev_args"
grep -q '^PF_POOLSUITE_SHA=$' <<< "$release_args"

# Exercise the shipped staging function with one throwaway repository standing in
# for every source. Dev archives the pinned Poolsuite tree; release creates the same
# named context as an empty directory. A missing dev pin is fatal unless the caller
# explicitly opts into partial staging, which still produces a valid empty context.
extract() { sed -n "/^$1()/,/^}/p" "$BUILD"; }
eval "$(extract pf_find_git_source)"
eval "$(extract pf_ensure_commit)"
eval "$(extract pf_stage_sources)"
pf_log() { :; }
pf_die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/home/poolsuite"
git -C "$tmp/home/poolsuite" init -q
git -C "$tmp/home/poolsuite" config user.name test
git -C "$tmp/home/poolsuite" config user.email test@example.invalid
printf 'poolsuite fixture\n' > "$tmp/home/poolsuite/README"
git -C "$tmp/home/poolsuite" add README
git -C "$tmp/home/poolsuite" commit -qm fixture
sha="$(git -C "$tmp/home/poolsuite" rev-parse HEAD)"
for repo in image source-kernel libsdl3-sunxifb wpa-supplicant-tsp cloud-init-tsp runtime sim pf-hwprobe blobs vendor-manifest; do
    ln -s poolsuite "$tmp/home/$repo"
done

common_args=$'PF_IMAGE_SHA='"$sha"$'\nPF_KERNEL_REPO=source-kernel\nPF_KERNEL_SHA='"$sha"$'\nPF_GPU_MODEL=ddk\nPF_GPU_REPO=none\nPF_GPU_SHA=\nPF_LIBSDL3_SHA='"$sha"$'\nPF_WPA_SHA='"$sha"$'\nPF_CLOUD_INIT_SHA='"$sha"$'\nPF_RUNTIME_SHA='"$sha"$'\nPF_SIM_SHA='"$sha"$'\nPF_HWPROBE_SHA='"$sha"$'\nPF_BLOBS_SHA='"$sha"$'\nPF_VENDOR_MANIFEST_SHA='"$sha"$'\nPF_UBOOT_REPO=none\nPF_UBOOT_SHA=\nPF_TFA_REPO=none\nPF_TFA_SHA='

HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" VARIANT=dev \
    pf_stage_sources "$tmp/dev" "$common_args"$'\nPF_POOLSUITE_SHA='"$sha"
test "$(cat "$tmp/dev/poolsuite/README")" = 'poolsuite fixture'

HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" VARIANT=release \
    pf_stage_sources "$tmp/release" "$common_args"$'\nPF_POOLSUITE_SHA='
test -d "$tmp/release/poolsuite"
test -z "$(find "$tmp/release/poolsuite" -mindepth 1 -print -quit)"

if ( HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" VARIANT=dev \
    pf_stage_sources "$tmp/missing-pin" "$common_args"$'\nPF_POOLSUITE_SHA=' \
    >/dev/null 2>&1 ); then
    echo 'FAIL: missing dev Poolsuite pin was silently accepted' >&2
    exit 1
fi

HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" PF_STAGE_ALLOW_MISSING=1 VARIANT=dev \
    pf_stage_sources "$tmp/allowed-missing-pin" "$common_args"$'\nPF_POOLSUITE_SHA='
test -d "$tmp/allowed-missing-pin/poolsuite"
test -z "$(find "$tmp/allowed-missing-pin/poolsuite" -mindepth 1 -print -quit)"

mv "$tmp/home/poolsuite" "$tmp/home/poolsuite-unavailable"
HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" PF_STAGE_ALLOW_MISSING=1 VARIANT=dev \
    pf_stage_sources "$tmp/allowed-missing-source" "$common_args"$'\nPF_POOLSUITE_SHA='"$sha"
test -d "$tmp/allowed-missing-source/poolsuite"
test -z "$(find "$tmp/allowed-missing-source/poolsuite" -mindepth 1 -print -quit)"

echo 'PASS: Poolsuite staging is pinned/dev-only, always-context, and fail-closed by default'
