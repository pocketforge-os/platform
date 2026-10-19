#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/core/pf-build.sh"

stage_body="$(sed -n '/^pf_stage_sources()/,/^}/p' "$BUILD")"
docker_body="$(sed -n '/^pf_os_image_dockerbuild()/,/^}/p' "$BUILD")"
# shellcheck disable=SC2016 -- these assertions match the literal shipped interface.
grep -Fq 'kernel-uapi|$(v PF_KERNEL_REPO)|$(v PF_FFMPEG_UAPI_SHA)|1' <<< "$stage_body"
# shellcheck disable=SC2016
grep -Fq 'kernel|kernel-uapi|wpa-supplicant-tsp|cloud-init-tsp|cursor-theme' <<< "$stage_body"
# shellcheck disable=SC2016
grep -Fq -- '--build-context "kernel-uapi-src=$src_dir/kernel-uapi"' <<< "$docker_body"

extract() { sed -n "/^$1()/,/^}/p" "$BUILD"; }
eval "$(extract pf_find_git_source)"
eval "$(extract pf_ensure_commit)"
eval "$(extract pf_stage_sources)"
pf_log() { :; }
pf_die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

tmp="$(mktemp -d "${RUNNER_TEMP:-/tmp}/pf-kernel-uapi-staging.XXXXXX")"
cleanup() {
    find "$tmp" -mindepth 1 -delete
    rmdir "$tmp"
}
trap cleanup EXIT

mkdir -p "$tmp/home/source-kernel"
git -C "$tmp/home/source-kernel" init -q
git -C "$tmp/home/source-kernel" config user.name test
git -C "$tmp/home/source-kernel" config user.email test@example.invalid
printf 'authenticated uapi\n' > "$tmp/home/source-kernel/UAPI"
git -C "$tmp/home/source-kernel" add UAPI
git -C "$tmp/home/source-kernel" commit -qm uapi
uapi_sha="$(git -C "$tmp/home/source-kernel" rev-parse HEAD)"
printf 'boot policy\n' > "$tmp/home/source-kernel/BOOT"
git -C "$tmp/home/source-kernel" add BOOT
git -C "$tmp/home/source-kernel" commit -qm boot
boot_sha="$(git -C "$tmp/home/source-kernel" rev-parse HEAD)"
test "$uapi_sha" != "$boot_sha"

for repo in image libsdl3-sunxifb wpa-supplicant-tsp cloud-init-tsp runtime \
        blobs vendor-manifest; do
    ln -s source-kernel "$tmp/home/$repo"
done

common=$'PF_IMAGE_SHA='"$boot_sha"$'\nPF_KERNEL_REPO=source-kernel\nPF_KERNEL_SHA='"$boot_sha"$'\nPF_GPU_MODEL=ddk\nPF_GPU_REPO=none\nPF_GPU_SHA=\nPF_LIBSDL3_SHA='"$boot_sha"$'\nPF_WPA_SHA='"$boot_sha"$'\nPF_CLOUD_INIT_SHA='"$boot_sha"$'\nPF_RUNTIME_SHA='"$boot_sha"$'\nPF_BLOBS_SHA='"$boot_sha"$'\nPF_VENDOR_MANIFEST_SHA='"$boot_sha"$'\nPF_UBOOT_REPO=none\nPF_UBOOT_SHA=\nPF_TFA_REPO=none\nPF_TFA_SHA='

HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" VARIANT=release \
    pf_stage_sources "$tmp/selected" \
    "$common"$'\nPF_FFMPEG_UAPI_SHA='"$uapi_sha"
test "$(cat "$tmp/selected/kernel/.pf-source-revision")" = "$boot_sha"
test "$(cat "$tmp/selected/kernel-uapi/.pf-source-revision")" = "$uapi_sha"
test -f "$tmp/selected/kernel/BOOT"
test ! -e "$tmp/selected/kernel-uapi/BOOT"
test "$(cat "$tmp/selected/kernel-uapi/UAPI")" = 'authenticated uapi'

# Unselected profiles still need the unconditional named context, but it must be empty.
HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" VARIANT=release \
    pf_stage_sources "$tmp/unselected" "$common"
test -d "$tmp/unselected/kernel-uapi"
test -z "$(find "$tmp/unselected/kernel-uapi" -mindepth 1 -print -quit)"

# The selected runtime source is required even in explicitly partial staging.
missing_sha=0000000000000000000000000000000000000000
if ( HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" PF_STAGE_ALLOW_MISSING=1 \
        VARIANT=release pf_stage_sources "$tmp/missing" \
        "$common"$'\nPF_FFMPEG_UAPI_SHA='"$missing_sha" >/dev/null 2>&1 ); then
    echo 'FAIL: missing authenticated kernel UAPI commit was silently accepted' >&2
    exit 1
fi

echo 'PASS: boot kernel and authenticated UAPI sources are staged separately and fail closed'
