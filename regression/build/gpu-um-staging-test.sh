#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/core/pf-build.sh"

closed_args="$(python3 "$ROOT/core/profile.py" buildargs a133)"
open_args="$(python3 "$ROOT/core/profile.py" buildargs a133-open)"
stage_body="$(sed -n '/^pf_stage_sources()/,/^}/p' "$BUILD")"
docker_body="$(sed -n '/^pf_os_image_dockerbuild()/,/^}/p' "$BUILD")"

grep -q 'specs+=( "gpu-um|$(v PF_GPU_UM_REPO)|$(v PF_GPU_UM_SHA)|1" )' <<< "$stage_body"
grep -q -- '--build-context "gpu-um-src=$src_dir/gpu-um"' <<< "$docker_body"
grep -q '^PF_GPU_MODEL=ddk$' <<< "$closed_args"
grep -q '^PF_GPU_UM_SHA=$' <<< "$closed_args"
grep -q '^PF_GPU_MODEL=open$' <<< "$open_args"
grep -Eq '^PF_GPU_UM_SHA=[0-9a-f]{40}$' <<< "$open_args"

# Exercise the shipped staging function with local throwaway repositories. Open
# stages gpu-um as a git archive; closed does not create that directory.
extract() { sed -n "/^$1()/,/^}/p" "$BUILD"; }
eval "$(extract pf_find_git_source)"
eval "$(extract pf_ensure_commit)"
eval "$(extract pf_stage_sources)"
pf_log() { :; }
pf_die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/home/gpu-um-tsp"
git -C "$tmp/home/gpu-um-tsp" init -q
git -C "$tmp/home/gpu-um-tsp" config user.name test
git -C "$tmp/home/gpu-um-tsp" config user.email test@example.invalid
printf 'open mesa\n' > "$tmp/home/gpu-um-tsp/README"
git -C "$tmp/home/gpu-um-tsp" add README
git -C "$tmp/home/gpu-um-tsp" commit -qm fixture
sha="$(git -C "$tmp/home/gpu-um-tsp" rev-parse HEAD)"
for repo in image libsdl3-sunxifb wpa-supplicant-tsp runtime blobs vendor-manifest; do
    ln -s gpu-um-tsp "$tmp/home/$repo"
done
common_args=$'PF_IMAGE_SHA='"$sha"$'\nPF_KERNEL_REPO=none\nPF_KERNEL_SHA=\nPF_GPU_REPO=none\nPF_GPU_SHA=\nPF_LIBSDL3_SHA='"$sha"$'\nPF_WPA_SHA='"$sha"$'\nPF_RUNTIME_SHA='"$sha"$'\nPF_BLOBS_SHA='"$sha"$'\nPF_VENDOR_MANIFEST_SHA='"$sha"$'\nPF_UBOOT_REPO=none\nPF_UBOOT_SHA=\nPF_TFA_REPO=none\nPF_TFA_SHA='

HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" pf_stage_sources "$tmp/open" \
    "$common_args"$'\nPF_GPU_MODEL=open\nPF_GPU_UM_REPO=gpu-um-tsp\nPF_GPU_UM_SHA='"$sha"
test "$(cat "$tmp/open/gpu-um/README")" = 'open mesa'

HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" pf_stage_sources "$tmp/closed" \
    "$common_args"$'\nPF_GPU_MODEL=ddk\nPF_GPU_UM_REPO=\nPF_GPU_UM_SHA='
test ! -e "$tmp/closed/gpu-um"

# Required open UM must fail even when partial staging is explicitly allowed.
if ( HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" PF_STAGE_ALLOW_MISSING=1 \
    pf_stage_sources "$tmp/missing" \
    "$common_args"$'\nPF_GPU_MODEL=open\nPF_GPU_UM_REPO=missing-repo\nPF_GPU_UM_SHA=0123456789012345678901234567890123456789' 2>/dev/null ); then
    echo 'FAIL: unstageable open GPU UM was silently skipped' >&2
    exit 1
fi

echo 'PASS: open GPU UM staging is conditional and fail-closed'
