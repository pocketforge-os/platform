#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="${ROOT}/core/pf-build.sh"
SELECTED=a133-open-7x-gpu

selected_args="$(python3 "${ROOT}/core/profile.py" buildargs "${SELECTED}")"
grep -Fxq 'PF_GAMESCOPE_MODE=g1' <<<"${selected_args}"
grep -Fxq 'PF_GAMESCOPE_REPO=gamescope' <<<"${selected_args}"
grep -Fxq 'PF_GAMESCOPE_SHA=1b55348e5ec40caf46528103ff2b9291422f13c1' <<<"${selected_args}"
grep -Fxq 'PF_GAMESCOPE_UPSTREAM_BASE=79399f4b34b5571ba5b03f61c4717eaf93ff75b3' <<<"${selected_args}"
grep -Fxq 'PF_GAMESCOPE_PATCH_SERIES_SHA256=bcf1ee23703ad096371a41f6d4fe83c696d4c3803716ba98839213bf7e65d8ea' <<<"${selected_args}"
grep -Fxq 'PF_GAMESCOPE_DEPENDENCY_MANIFEST_SHA256=cb7169f3d8c2848aadd25c5d4e40b8d954a03cda106e194968ef16d6f71e3fbd' <<<"${selected_args}"

for device in a133 a133-open a523 a133-open-7x-gpu-noradio a133-open-7x-gpu-spl-trace; do
    if python3 "${ROOT}/core/profile.py" buildargs "${device}" | grep -q '^PF_GAMESCOPE_'; then
        echo "FAIL: unrelated profile ${device} selected Gamescope" >&2
        exit 1
    fi
done

stage_body="$(sed -n '/^pf_stage_sources()/,/^}/p' "${BUILD}")"
docker_body="$(sed -n '/^pf_os_image_dockerbuild()/,/^}/p' "${BUILD}")"
grep -Fq 'gamescope|$(v PF_GAMESCOPE_REPO)|$(v PF_GAMESCOPE_SHA)|1' <<<"${stage_body}"
grep -Fq -- '--build-context "gamescope-src=$src_dir/gamescope"' <<<"${docker_body}"
grep -Fq -- '--build-context "gamescope-deps=$src_dir/gamescope-deps"' <<<"${docker_body}"

extract() { sed -n "/^$1()/,/^}/p" "${BUILD}"; }
eval "$(extract pf_find_git_source)"
eval "$(extract pf_ensure_commit)"
eval "$(extract pf_verify_gamescope_source)"
eval "$(extract pf_stage_sources)"
pf_log() { :; }
pf_die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

tmp="$(mktemp -d "${RUNNER_TEMP:-/tmp}/gamescope-staging.XXXXXX")"
cleanup() {
    find "${tmp}" -mindepth 1 -delete
    rmdir "${tmp}"
}
trap cleanup EXIT
mkdir -p "${tmp}/home/gamescope" "${tmp}/cache/manifest-key"
git -C "${tmp}/home/gamescope" init -q
git -C "${tmp}/home/gamescope" config user.name test
git -C "${tmp}/home/gamescope" config user.email test@example.invalid
printf 'fixture licence\n' >"${tmp}/home/gamescope/LICENSE"
printf 'base\n' >"${tmp}/home/gamescope/source"
git -C "${tmp}/home/gamescope" add LICENSE source
git -C "${tmp}/home/gamescope" commit -qm base
base="$(git -C "${tmp}/home/gamescope" rev-parse HEAD)"
printf 'one\n' >>"${tmp}/home/gamescope/source"
git -C "${tmp}/home/gamescope" commit -qam one
printf 'two\n' >>"${tmp}/home/gamescope/source"
git -C "${tmp}/home/gamescope" commit -qam two
head="$(git -C "${tmp}/home/gamescope" rev-parse HEAD)"
patch_ids="$(
    git -C "${tmp}/home/gamescope" rev-list --reverse "${base}..${head}" |
        while read -r commit; do
            git -C "${tmp}/home/gamescope" show --pretty=email --patch "${commit}" |
                git patch-id --stable | awk '{print $1}'
        done | paste -sd' ' -
)"
patch_digest="$(
    git -C "${tmp}/home/gamescope" format-patch --stdout --no-stat "${base}..${head}" |
        sha256sum | cut -d' ' -f1
)"
license_digest="$(sha256sum "${tmp}/home/gamescope/LICENSE" | cut -d' ' -f1)"
printf 'cache fixture\n' >"${tmp}/cache/manifest-key/archive.tar.gz"
for repo in image libsdl3-sunxifb wpa-supplicant-tsp runtime sim pf-hwprobe poolsuite blobs vendor-manifest; do
    ln -s gamescope "${tmp}/home/${repo}"
done

common=$'PF_IMAGE_SHA='"${head}"$'\nPF_KERNEL_REPO=gamescope\nPF_KERNEL_SHA='"${head}"$'\nPF_GPU_REPO=none\nPF_GPU_SHA=\nPF_GPU_MODEL=ddk\nPF_LIBSDL3_SHA='"${head}"$'\nPF_WPA_SHA='"${head}"$'\nPF_RUNTIME_SHA='"${head}"$'\nPF_SIM_SHA='"${head}"$'\nPF_HWPROBE_SHA='"${head}"$'\nPF_POOLSUITE_SHA='"${head}"$'\nPF_BLOBS_SHA='"${head}"$'\nPF_VENDOR_MANIFEST_SHA='"${head}"$'\nPF_UBOOT_REPO=none\nPF_UBOOT_SHA=\nPF_TFA_REPO=none\nPF_TFA_SHA='
gamescope=$'\nPF_GAMESCOPE_MODE=g1\nPF_GAMESCOPE_REPO=gamescope\nPF_GAMESCOPE_REPO_URL=https://github.com/pocketforge-os/gamescope.git\nPF_GAMESCOPE_SHA='"${head}"$'\nPF_GAMESCOPE_UPSTREAM_BASE='"${base}"$'\nPF_GAMESCOPE_PRESENT_HEAD='"${head}"$'\nPF_GAMESCOPE_STAGING_HEAD='"${head}"$'\nPF_GAMESCOPE_ROTATION_HEAD='"${head}"$'\nPF_GAMESCOPE_REQUIRED_PATCH_IDS='"${patch_ids}"$'\nPF_GAMESCOPE_PATCH_SERIES_SHA256='"${patch_digest}"$'\nPF_GAMESCOPE_DEPENDENCY_MANIFEST_SHA256='"$(printf 'd%.0s' {1..64})"$'\nPF_GAMESCOPE_LICENSE_SHA256='"${license_digest}"$'\nPF_GAMESCOPE_DIAGNOSTICS=0'

HOME="${tmp}/home" PF_MIRROR_DIR="${tmp}/mirrors" VARIANT=dev \
    PF_GAMESCOPE_DEPENDENCY_CACHE="${tmp}/cache" \
    pf_stage_sources "${tmp}/selected" "${common}${gamescope}"
python3 - "${tmp}/selected/gamescope/.pf-gamescope-source.json" "${head}" <<'PY'
import json
import pathlib
import sys
receipt = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert receipt["schema"] == "pocketforge.gamescope-source/v1"
assert receipt["integrated_head"] == sys.argv[2]
assert receipt["source_url"] == "https://github.com/pocketforge-os/gamescope.git"
PY
cmp "${tmp}/cache/manifest-key/archive.tar.gz" \
    "${tmp}/selected/gamescope-deps/manifest-key/archive.tar.gz"

if ( HOME="${tmp}/home" PF_MIRROR_DIR="${tmp}/mirrors" VARIANT=dev \
    PF_GAMESCOPE_DEPENDENCY_CACHE="${tmp}/cache" \
    pf_stage_sources "${tmp}/stale" \
    "${common}${gamescope/PF_GAMESCOPE_REQUIRED_PATCH_IDS=${patch_ids}/PF_GAMESCOPE_REQUIRED_PATCH_IDS=$(printf '0%.0s' {1..40})}" \
    2>/dev/null ); then
    echo 'FAIL: stale Gamescope patch identity was accepted' >&2
    exit 1
fi

if ( HOME="${tmp}/home" PF_MIRROR_DIR="${tmp}/mirrors" VARIANT=dev \
    pf_stage_sources "${tmp}/no-cache" "${common}${gamescope}" 2>"${tmp}/no-cache.log" ); then
    echo 'FAIL: missing .440.7 dependency cache was accepted' >&2
    exit 1
fi
grep -Fq 'tsp-op5a.440.7' "${tmp}/no-cache.log"

echo 'PASS: exact Gamescope source/receipt/cache staging is profile-only and fail-closed'
