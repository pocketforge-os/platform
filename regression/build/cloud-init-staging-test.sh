#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/core/pf-build.sh"

args="$(python3 "$ROOT/core/profile.py" buildargs a133-open-7x-gpu dev)"
cloud_sha="$(sed -n 's/^PF_CLOUD_INIT_SHA=//p' <<< "$args")"
[ "$cloud_sha" = "a298e3711500549a467aedc5a72689b8c42e21ab" ] || {
    printf 'FAIL: PF_CLOUD_INIT_SHA did not resolve the cloud-init-tsp lock pin (got %s)\n' \
        "${cloud_sha:-missing}" >&2
    exit 1
}

stage_body="$(sed -n '/^pf_stage_sources()/,/^}/p' "$BUILD")"
docker_body="$(sed -n '/^pf_os_image_dockerbuild()/,/^}/p' "$BUILD")"
# shellcheck disable=SC2016 -- these assertions match the literal shipped shell interface.
grep -Fq 'cloud-init-tsp|cloud-init-tsp|$(v PF_CLOUD_INIT_SHA)' <<< "$stage_body"
# shellcheck disable=SC2016
grep -Fq -- '--build-context "cloud-init-src=$src_dir/cloud-init-tsp"' <<< "$docker_body"

extract() { sed -n "/^$1()/,/^}/p" "$BUILD"; }
eval "$(extract pf_find_git_source)"
eval "$(extract pf_ensure_commit)"
eval "$(extract pf_stage_sources)"
pf_log() { :; }
pf_die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

tmp="$(mktemp -d "${RUNNER_TEMP:-/tmp}/pf-cloud-init-staging.XXXXXX")"
cleanup() {
    find "$tmp" -mindepth 1 -delete
    rmdir "$tmp"
}
trap cleanup EXIT
mkdir -p "$tmp/home/fixture"
git -C "$tmp/home/fixture" init -q
git -C "$tmp/home/fixture" config user.name test
git -C "$tmp/home/fixture" config user.email test@example.invalid
printf 'cloud-init fixture\n' > "$tmp/home/fixture/README"
git -C "$tmp/home/fixture" add README
git -C "$tmp/home/fixture" commit -qm fixture
sha="$(git -C "$tmp/home/fixture" rev-parse HEAD)"
for repo in image source-kernel libsdl3-sunxifb wpa-supplicant-tsp cloud-init-tsp runtime \
        sim pf-hwprobe poolsuite blobs vendor-manifest; do
    ln -s fixture "$tmp/home/$repo"
done

common=$'PF_IMAGE_SHA='"$sha"$'\nPF_KERNEL_REPO=source-kernel\nPF_KERNEL_SHA='"$sha"$'\nPF_GPU_MODEL=ddk\nPF_GPU_REPO=none\nPF_GPU_SHA=\nPF_LIBSDL3_SHA='"$sha"$'\nPF_WPA_SHA='"$sha"$'\nPF_CLOUD_INIT_SHA='"$sha"$'\nPF_RUNTIME_SHA='"$sha"$'\nPF_SIM_SHA='"$sha"$'\nPF_HWPROBE_SHA='"$sha"$'\nPF_POOLSUITE_SHA='"$sha"$'\nPF_BLOBS_SHA='"$sha"$'\nPF_VENDOR_MANIFEST_SHA='"$sha"$'\nPF_UBOOT_REPO=none\nPF_UBOOT_SHA=\nPF_TFA_REPO=none\nPF_TFA_SHA='

HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" VARIANT=dev \
    pf_stage_sources "$tmp/staged" "$common"
test "$(cat "$tmp/staged/cloud-init-tsp/README")" = 'cloud-init fixture'
test "$(cat "$tmp/staged/cloud-init-tsp/.pf-source-revision")" = "$sha"

mv "$tmp/home/cloud-init-tsp" "$tmp/home/cloud-init-tsp-unavailable"
if ( HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" VARIANT=dev \
        pf_stage_sources "$tmp/missing" "$common" >/dev/null 2>&1 ); then
    echo 'FAIL: missing cloud-init-tsp source was silently accepted' >&2
    exit 1
fi

echo 'PASS: cloud-init-tsp is lock-resolved, receipt-bound, staged, and passed as cloud-init-src'
