#!/usr/bin/env bash
# Platform-owned device descriptor staging (tsp-f3fm.202.1 R1 / B3).
# A133-open profiles stage devices/<id>/capabilities.toml verbatim into the
# `platform-inputs-src` named context; every other profile stages nothing and
# its docker command gains no context. Exercises the SHIPPED staging functions.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/core/pf-build.sh"
PY="${PF_PY:-python3}"

open_args="$("$PY" "$ROOT/core/profile.py" buildargs a133-open)"
a523_args="$("$PY" "$ROOT/core/profile.py" buildargs a523)"
closed_args="$("$PY" "$ROOT/core/profile.py" buildargs a133)"
docker_body="$(sed -n '/^pf_os_image_dockerbuild()/,/^}/p' "$BUILD")"

grep -q '^PF_DEVICE_DESCRIPTOR_ID=a133$' <<< "$open_args"
want_sha="$(sha256sum "$ROOT/devices/a133/capabilities.toml" | cut -d' ' -f1)"
grep -q "^PF_DEVICE_DESCRIPTOR_SHA256=$want_sha\$" <<< "$open_args"
# (`! grep` is exempt from errexit, so negative checks are explicit.)
for args in "$a523_args" "$closed_args"; do
    if grep -q '^PF_DEVICE_DESCRIPTOR_' <<< "$args"; then
        echo 'FAIL: a non-open profile emitted a device descriptor build arg' >&2
        exit 1
    fi
done
# The context is passed only when the descriptor build arg is present.
grep -q -- '--build-context "platform-inputs-src=$src_dir/platform-inputs"' <<< "$docker_body"
grep -B4 -- '--build-context "platform-inputs-src=' <<< "$docker_body" \
    | grep -q 's/^PF_DEVICE_DESCRIPTOR_ID=//p'

extract() { sed -n "/^$1()/,/^}/p" "$BUILD"; }
eval "$(extract pf_find_git_source)"
eval "$(extract pf_ensure_commit)"
eval "$(extract pf_stage_device_descriptor)"
eval "$(extract pf_stage_sources)"
pf_log() { :; }
pf_die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
# shellcheck disable=SC2034  # read by the eval-extracted pf_stage_device_descriptor
PF_PLATFORM_DIR="$ROOT"

tmp="$(mktemp -d)"
cleanup() {
    find "$tmp" -type d -exec chmod u+rwx {} +
    find "$tmp" -type f -exec chmod u+rw {} +
    find "$tmp" -mindepth 1 -delete
    rmdir "$tmp"
}
trap cleanup EXIT
mkdir -p "$tmp/home/src-fixture"
git -C "$tmp/home/src-fixture" init -q
git -C "$tmp/home/src-fixture" config user.name test
git -C "$tmp/home/src-fixture" config user.email test@example.invalid
printf 'fixture\n' > "$tmp/home/src-fixture/README"
git -C "$tmp/home/src-fixture" add README
git -C "$tmp/home/src-fixture" commit -qm fixture
sha="$(git -C "$tmp/home/src-fixture" rev-parse HEAD)"
for repo in image libsdl3-sunxifb wpa-supplicant-tsp cloud-init-tsp runtime sim pf-hwprobe poolsuite blobs vendor-manifest launcher recovery gpu-um; do
    ln -s src-fixture "$tmp/home/$repo"
done
common=$'PF_IMAGE_SHA='"$sha"$'\nPF_KERNEL_REPO=src-fixture\nPF_KERNEL_SHA='"$sha"$'\nPF_GPU_REPO=none\nPF_GPU_SHA=\nPF_LIBSDL3_SHA='"$sha"$'\nPF_WPA_SHA='"$sha"$'\nPF_CLOUD_INIT_SHA='"$sha"$'\nPF_RUNTIME_SHA='"$sha"$'\nPF_SIM_SHA='"$sha"$'\nPF_HWPROBE_SHA='"$sha"$'\nPF_POOLSUITE_SHA='"$sha"$'\nPF_BLOBS_SHA='"$sha"$'\nPF_VENDOR_MANIFEST_SHA='"$sha"$'\nPF_UBOOT_REPO=none\nPF_UBOOT_SHA=\nPF_TFA_REPO=none\nPF_TFA_SHA='
open_stack=$'\nPF_GPU_MODEL=open\nPF_GPU_UM_REPO=gpu-um\nPF_GPU_UM_SHA='"$sha"$'\nPF_LAUNCHER_REPO=launcher\nPF_LAUNCHER_SHA='"$sha"$'\nPF_RECOVERY_REPO=recovery\nPF_RECOVERY_SHA='"$sha"
descriptor_lines="$(grep '^PF_DEVICE_DESCRIPTOR_' <<< "$open_args")"

stage() { HOME="$tmp/home" PF_MIRROR_DIR="$tmp/mirrors" VARIANT="$1" pf_stage_sources "$2" "$3"; }

# A133-open (dev and release): exactly one file, byte-identical, mode 0644.
for variant in dev release; do
    stage "$variant" "$tmp/open-$variant" "$common$open_stack"$'\n'"$descriptor_lines"
    staged="$tmp/open-$variant/platform-inputs/devices/a133/capabilities.toml"
    cmp "$ROOT/devices/a133/capabilities.toml" "$staged"
    test "$(stat -c %a "$staged")" = 644
    staged_neutral="$tmp/open-$variant/platform-inputs/device/capabilities.toml"
    cmp "$ROOT/devices/a133/capabilities.toml" "$staged_neutral"
    test "$(stat -c %a "$staged_neutral")" = 644
    test "$(cd "$tmp/open-$variant/platform-inputs" && find . -mindepth 1 | LC_ALL=C sort | tr '\n' ' ')" \
        = './device ./device/capabilities.toml ./devices ./devices/a133 ./devices/a133/capabilities.toml '
done

# Every other profile shape stages no platform-inputs directory at all.
stage dev "$tmp/closed" "$common"$'\nPF_GPU_MODEL=ddk\nPF_GPU_UM_REPO=\nPF_GPU_UM_SHA='
test ! -e "$tmp/closed/platform-inputs"
contexts() { find "$1" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort; }
test "$(contexts "$tmp/open-dev")" \
    = "$({ contexts "$tmp/closed"; printf '%s\n' gpu-um launcher platform-inputs recovery; } | LC_ALL=C sort)"

# Fail closed: wrong digest, malformed digest, path-escaping id, missing descriptor.
refuses() {
    if ( stage dev "$tmp/$1" "$common$open_stack"$'\n'"$2" 2>/dev/null ); then
        printf 'FAIL: descriptor staging accepted %s\n' "$1" >&2
        exit 1
    fi
}
refuses wrong-sha $'PF_DEVICE_DESCRIPTOR_ID=a133\nPF_DEVICE_DESCRIPTOR_SHA256='"$(printf '0%.0s' {1..64})"
refuses no-sha $'PF_DEVICE_DESCRIPTOR_ID=a133\nPF_DEVICE_DESCRIPTOR_SHA256='
refuses escape-id $'PF_DEVICE_DESCRIPTOR_ID=../a133\nPF_DEVICE_DESCRIPTOR_SHA256='"$want_sha"
refuses absent-id $'PF_DEVICE_DESCRIPTOR_ID=a133-open\nPF_DEVICE_DESCRIPTOR_SHA256='"$want_sha"

# Device-neutral path: when any device descriptor is staged, an identical copy lands at
# ./device/capabilities.toml alongside the per-SoC ./devices/<id>/capabilities.toml.
# The a133-open path exercises this through pf_stage_sources above; this block exercises it
# for the a523 descriptor directly (pf_stage_device_descriptor is the shared function).
a523_stage="$tmp/a523-stage"
a523_src="$ROOT/devices/a523/capabilities.toml"
a523_want="$(sha256sum "$a523_src" | cut -d' ' -f1)"
create_context_dir() { mkdir -p -- "$1"; }
pf_stage_device_descriptor "$a523_stage" a523 "$a523_want"
cmp "$a523_src" "$a523_stage/platform-inputs/devices/a523/capabilities.toml"
cmp "$a523_src" "$a523_stage/platform-inputs/device/capabilities.toml"
test "$(stat -c %a "$a523_stage/platform-inputs/device/capabilities.toml")" = 644

echo 'PASS: device descriptor staged verbatim for A133-open only, digest-verified, fail-closed'
