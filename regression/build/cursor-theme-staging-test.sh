#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="${ROOT}/core/pf-build.sh"
args="$(python3 "${ROOT}/core/profile.py" buildargs a133)"

grep -Fxq 'PF_CURSOR_THEME_SHA=c5783fbb7d9d89c82bc1b4757c303e267b6cd104' <<<"${args}"
grep -Fxq 'PF_CURSOR_TOOLS_IMAGE=10.0.32.86:5555/pocketforge/ci-tools@sha256:2ff536627228c90e5c32b7d6345b21600a38a17481c075b41683db47ead3e862' <<<"${args}"
grep -Fxq 'PF_CURSOR_TOOLS_RECIPE_SHA=ec5b2621f636261978d3bb4fd9843ae22a59c320' <<<"${args}"

stage_body="$(sed -n '/^pf_stage_sources()/,/^}/p' "${BUILD}")"
grep -Fq 'cursor-theme|pf-cursor-theme|$(v PF_CURSOR_THEME_SHA)|1' <<<"${stage_body}"
grep -Fq 'kernel|wpa-supplicant-tsp|cloud-init-tsp|cursor-theme' <<<"${stage_body}"
grep -Fq 'chmod 0444 "$dest/.pf-source-revision"' <<<"${stage_body}"
grep -Fq 'if [ "$logical" = cursor-theme ]' <<<"${stage_body}"
grep -Fq -- '--build-context "cursor-theme-src=$src_dir/cursor-theme"' "${BUILD}"
grep -Fq 'component-test-cursor-theme' "${BUILD}"

python3 - "${ROOT}/platform.lock" <<'PY'
import sys, tomllib
with open(sys.argv[1], "rb") as stream:
    lock = tomllib.load(stream)
repos = {repo["name"]: repo for repo in lock["repos"]}
cursor = repos["pf-cursor-theme"]
assert cursor["ref"] == "pocketforge-linear"
assert cursor["sha"] == "c5783fbb7d9d89c82bc1b4757c303e267b6cd104"
assert lock["cursor_theme"]["tools_recipe_sha"] == "ec5b2621f636261978d3bb4fd9843ae22a59c320"
assert lock["cursor_theme"]["tools_image_digest"] == "2ff536627228c90e5c32b7d6345b21600a38a17481c075b41683db47ead3e862"
PY

python3 - "${ROOT}" <<'PY'
import importlib.util
import pathlib
import sys
import tempfile

root = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("profile", root / "core/profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
profile.load_lock()

with tempfile.TemporaryDirectory(prefix="cursor-tools-binding.") as directory:
    candidate = pathlib.Path(directory) / "platform.lock"
    candidate.write_bytes((root / "platform.lock").read_bytes().replace(
        b"ec5b2621f636261978d3bb4fd9843ae22a59c320", b"0000000000000000000000000000000000000000"))
    profile.LOCK = str(candidate)
    try:
        profile.load_lock()
    except profile.ProfileSchemaError as error:
        assert "cursor_tools_recipe_binding=refused reason=tools_recipe_binding_mismatch" in str(error)
    else:
        raise AssertionError("mismatched cursor tools recipe was accepted")
PY

extract() { sed -n "/^$1()/,/^}/p" "${BUILD}"; }
eval "$(extract pf_find_git_source)"
eval "$(extract pf_ensure_commit)"
eval "$(extract pf_stage_sources)"
pf_log() { :; }
pf_die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

tmp="$(mktemp -d "${RUNNER_TEMP:-/tmp}/cursor-theme-staging.XXXXXX")"
cleanup() {
    find "${tmp}" -type d -exec chmod u+rwx {} +
    find "${tmp}" -type f -exec chmod u+rw {} +
    find "${tmp}" -mindepth 1 -delete
    rmdir "${tmp}"
}
trap cleanup EXIT
mkdir -p "${tmp}/home/fixture"
git -C "${tmp}/home/fixture" init -q
git -C "${tmp}/home/fixture" config user.name test
git -C "${tmp}/home/fixture" config user.email test@example.invalid
printf 'cursor fixture\n' >"${tmp}/home/fixture/README"
git -C "${tmp}/home/fixture" add README
git -C "${tmp}/home/fixture" commit -qm fixture
sha="$(git -C "${tmp}/home/fixture" rev-parse HEAD)"
for repo in image source-kernel libsdl3-sunxifb wpa-supplicant-tsp cloud-init-tsp \
        pf-cursor-theme runtime blobs vendor-manifest; do
    ln -s fixture "${tmp}/home/${repo}"
done
unrelated_args=$'PF_IMAGE_SHA='"${sha}"$'\nPF_KERNEL_REPO=source-kernel\nPF_KERNEL_SHA='"${sha}"$'\nPF_GPU_MODEL=ddk\nPF_GPU_REPO=none\nPF_GPU_SHA=\nPF_LIBSDL3_SHA='"${sha}"$'\nPF_WPA_SHA='"${sha}"$'\nPF_CLOUD_INIT_SHA='"${sha}"$'\nPF_RUNTIME_SHA='"${sha}"$'\nPF_BLOBS_SHA='"${sha}"$'\nPF_VENDOR_MANIFEST_SHA='"${sha}"$'\nPF_UBOOT_REPO=none\nPF_UBOOT_SHA=\nPF_TFA_REPO=none\nPF_TFA_SHA='

# The build-arg key is the shipping property: profile.py always emits it for an
# OS image. Focused source-staging fixtures omit it and must remain independent.
HOME="${tmp}/home" PF_MIRROR_DIR="${tmp}/mirrors" VARIANT=release \
    pf_stage_sources "${tmp}/unrelated" "${unrelated_args}"
test ! -e "${tmp}/unrelated/cursor-theme"

HOME="${tmp}/home" PF_MIRROR_DIR="${tmp}/mirrors" VARIANT=release \
    pf_stage_sources "${tmp}/shipping" \
    "${unrelated_args}"$'\nPF_CURSOR_THEME_SHA='"${sha}"
test "$(cat "${tmp}/shipping/cursor-theme/.pf-source-revision")" = "${sha}"

missing_log="${tmp}/missing-pin.log"
if ( HOME="${tmp}/home" PF_MIRROR_DIR="${tmp}/mirrors" VARIANT=release \
    pf_stage_sources "${tmp}/missing-pin" \
    "${unrelated_args}"$'\nPF_CURSOR_THEME_SHA=' 2>"${missing_log}" ); then
    echo 'FAIL: cursor-shipping staging accepted an empty cursor pin' >&2
    exit 1
fi
grep -Fq 'no platform.lock SHA for pf-cursor-theme (cursor-theme)' "${missing_log}"

echo 'cursor-theme staging contract: PASS'
