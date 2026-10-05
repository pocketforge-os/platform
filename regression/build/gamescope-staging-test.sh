#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="${ROOT}/core/pf-build.sh"
SCRIPT_DIR="${ROOT}/core"
SELECTED=a133-open-7x-gpu

selected_args="$(python3 "${ROOT}/core/profile.py" buildargs "${SELECTED}")"
grep -Fxq 'PF_GAMESCOPE_MODE=g1' <<<"${selected_args}"
grep -Fxq 'PF_GAMESCOPE_REPO=gamescope' <<<"${selected_args}"
grep -Fxq 'PF_GAMESCOPE_SHA=4232739e75c95113871e260967e8b4ff995ea897' <<<"${selected_args}"
grep -Fxq 'PF_GAMESCOPE_UPSTREAM_BASE=bb2ddfc8b1091d6c4d0133b1ea9dcd2494b69ab9' <<<"${selected_args}"
grep -Fxq 'PF_GAMESCOPE_PATCH_SERIES_SHA256=cf0736049af178c1e94fd40bea54a28d309010c65d07fb3a981e130395a9508c' <<<"${selected_args}"
grep -Fxq 'PF_GAMESCOPE_DEPENDENCY_MANIFEST_SHA256=08222e97c66d1bc737d9ef0483e23476bd4b127ca19136e70dd0e843f3af51cf' <<<"${selected_args}"

for device in a133 a133-open a523 a133-open-7x-gpu-noradio a133-open-7x-gpu-spl-trace; do
    if python3 "${ROOT}/core/profile.py" buildargs "${device}" | grep -q '^PF_GAMESCOPE_'; then
        echo "FAIL: unrelated profile ${device} selected Gamescope" >&2
        exit 1
    fi
done

stage_body="$(sed -n '/^pf_stage_sources()/,/^}/p' "${BUILD}")"
docker_body="$(sed -n '/^pf_os_image_dockerbuild()/,/^}/p' "${BUILD}")"
grep -Fq 'gamescope|$(v PF_GAMESCOPE_REPO)|$(v PF_GAMESCOPE_SHA)|1' <<<"${stage_body}"
grep -Fq 'stage-gamescope-source.py' <<<"${stage_body}"
grep -Fq -- '--build-context "gamescope-src=$src_dir/gamescope"' <<<"${docker_body}"
if grep -Fq 'gamescope-deps' <<<"${docker_body}"; then
    echo 'FAIL: raw Gamescope dependency cache remains a Docker context' >&2
    exit 1
fi

extract() { sed -n "/^$1()/,/^}/p" "${BUILD}"; }
eval "$(extract pf_find_git_source)"
eval "$(extract pf_ensure_commit)"
eval "$(extract pf_stage_sources)"
pf_log() { :; }
pf_die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

tmp="$(mktemp -d "${RUNNER_TEMP:-/tmp}/gamescope-staging.XXXXXX")"
cleanup() {
    find "${tmp}" -mindepth 1 -delete
    rmdir "${tmp}"
}
trap cleanup EXIT
mkdir -p "${tmp}/home/gamescope/.github/scripts" "${tmp}/cache-seed/repos"

projects="${tmp}/projects.tsv"
for index in $(seq 0 31); do
    project="dep$(printf '%02d' "${index}")"
    work="${tmp}/dependency-${project}"
    mkdir "${work}"
    git -C "${work}" init -q
    git -C "${work}" config user.name test
    git -C "${work}" config user.email test@example.invalid
    printf 'licence for %s\n' "${project}" >"${work}/LICENSE"
    git -C "${work}" add LICENSE
    git -C "${work}" commit -qm licence
    revision="$(git -C "${work}" rev-parse HEAD)"
    license_sha="$(sha256sum "${work}/LICENSE" | cut -d' ' -f1)"
    git clone --bare -q "${work}" "${tmp}/cache-seed/repos/${project}.git"
    printf '%s\t%s\t%s\n' "${project}" "${revision}" "${license_sha}" >>"${projects}"
    find "${work}" -mindepth 1 -delete
    rmdir "${work}"
done

python3 - "${projects}" "${tmp}/home/gamescope/.github/pocketforge-source-closure.tsv" <<'PY'
import pathlib
import sys

fields = (
    "schema", "edge_id", "parent_id", "project_id", "path", "kind",
    "upstream_url", "upstream_revision", "declared_url", "locator_revision",
    "pf_url", "pf_revision", "tree_oid", "content_sha256", "license_path",
    "license_sha256", "selectors", "tests", "patch_status",
    "transform_receipt", "fork_history_proof", "fork_pin_ref",
)
projects = [line.split("\t") for line in pathlib.Path(sys.argv[1]).read_text().splitlines()]
rows = []
occurrences = list(range(29)) + [0, 1] + [29, 30, 31]
for edge, project_index in enumerate(occurrences):
    project, revision, license_sha = projects[project_index]
    kind = "gitlink" if edge < 31 else "vendored-snapshot"
    path = f"subprojects/{project}-{edge:02d}" if kind == "gitlink" else f"thirdparty/{project}.hpp"
    row = {
        "schema": "1", "edge_id": f"edge-{edge:02d}", "parent_id": "gamescope",
        "project_id": project, "path": path, "kind": kind,
        "upstream_url": f"https://example.invalid/{project}.git",
        "upstream_revision": revision, "declared_url": "-",
        "locator_revision": revision,
        "pf_url": f"https://github.com/pocketforge-os/{project}.git",
        "pf_revision": revision, "tree_oid": revision, "content_sha256": "-",
        "license_path": "LICENSE", "license_sha256": license_sha,
        "selectors": "native,aarch64", "tests": "fixture", "patch_status": "exact",
        "transform_receipt": "-", "fork_history_proof": "-",
        "fork_pin_ref": "refs/heads/pocketforge",
    }
    rows.append("\t".join(row[field] for field in fields))
path = pathlib.Path(sys.argv[2])
path.write_text("# gamescope-source-closure-v1\n" + "\t".join(fields) + "\n" + "\n".join(rows) + "\n")
PY
printf 'fixture vendored registry\n' >"${tmp}/home/gamescope/.github/vendored-sources.tsv"
cat >"${tmp}/home/gamescope/.github/scripts/prime-meson-sources.sh" <<'SH'
#!/bin/sh
set -eu
[ "${PF_MESON_CACHE_OFFLINE:-0}" = 1 ]
[ "${1:-}" = --offline ]
SH
chmod 0755 "${tmp}/home/gamescope/.github/scripts/prime-meson-sources.sh"
cat >"${tmp}/home/gamescope/.github/scripts/materialize-source-closure.py" <<'PY'
#!/usr/bin/env python3
import argparse, hashlib, json, os, pathlib, stat, subprocess
p = argparse.ArgumentParser()
for name in ("repo-root", "manifest", "vendored-registry", "cache-root", "output", "receipt"):
    p.add_argument(f"--{name}", required=True)
a = p.parse_args()
output = pathlib.Path(a.output)
output.mkdir()
archive = subprocess.Popen(["git", "-C", a.repo_root, "archive", "HEAD"], stdout=subprocess.PIPE)
subprocess.run(["tar", "-x", "-C", output], stdin=archive.stdout, check=True)
assert archive.wait() == 0
records = []
for path in sorted(output.rglob("*")):
    if not path.is_file() and not path.is_symlink():
        continue
    relative = path.relative_to(output).as_posix()
    mode = stat.S_IMODE(path.lstat().st_mode)
    if path.is_symlink():
        digest = hashlib.sha256(os.readlink(path).encode()).hexdigest(); kind = "symlink"
    else:
        digest = hashlib.sha256(path.read_bytes()).hexdigest(); kind = "file"
    records.append(f"{relative}\t{kind}\t{mode:o}\t{digest}\n")
receipt = {
    "schema": "gamescope-source-materialization-v1",
    "gamescope_head": subprocess.check_output(["git", "-C", a.repo_root, "rev-parse", "HEAD"], text=True).strip(),
    "generated_root_wrap_aliases": 2,
    "manifest_sha256": hashlib.sha256(pathlib.Path(a.manifest).read_bytes()).hexdigest(),
    "materialized_git_inputs": 31, "normalized_gitlink_urls": 19,
    "source_tree_sha256": hashlib.sha256("".join(records).encode()).hexdigest(),
    "verified_materialized_locator_targets": 33,
}
pathlib.Path(a.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
PY
chmod 0755 "${tmp}/home/gamescope/.github/scripts/materialize-source-closure.py"
printf 'fixture licence\n' >"${tmp}/home/gamescope/LICENSE"
printf 'base\n' >"${tmp}/home/gamescope/source"
git -C "${tmp}/home/gamescope" init -q
git -C "${tmp}/home/gamescope" config user.name test
git -C "${tmp}/home/gamescope" config user.email test@example.invalid
git -C "${tmp}/home/gamescope" add . LICENSE source
git -C "${tmp}/home/gamescope" commit -qm base
base="$(git -C "${tmp}/home/gamescope" rev-parse HEAD)"
printf 'one\n' >>"${tmp}/home/gamescope/source"
git -C "${tmp}/home/gamescope" commit -qam one
printf 'two\n' >>"${tmp}/home/gamescope/source"
git -C "${tmp}/home/gamescope" commit -qam two
head="$(git -C "${tmp}/home/gamescope" rev-parse HEAD)"
patch_ids="$(git -C "${tmp}/home/gamescope" rev-list --reverse "${base}..${head}" | while read -r commit; do git -C "${tmp}/home/gamescope" show --pretty=email --patch "${commit}" | git patch-id --stable | awk '{print $1}'; done | paste -sd' ' -)"
patch_digest="$(git -C "${tmp}/home/gamescope" format-patch --stdout --no-stat "${base}..${head}" | sha256sum | cut -d' ' -f1)"
license_digest="$(sha256sum "${tmp}/home/gamescope/LICENSE" | cut -d' ' -f1)"
manifest_digest="$(sha256sum "${tmp}/home/gamescope/.github/pocketforge-source-closure.tsv" | cut -d' ' -f1)"
mkdir -p "${tmp}/cache/${manifest_digest}"
mv "${tmp}/cache-seed/repos" "${tmp}/cache/${manifest_digest}/repos"
rmdir "${tmp}/cache-seed"
python3 - "${tmp}/cache/${manifest_digest}/admission-receipt.json" "${head}" "${manifest_digest}" <<'PY'
import json, pathlib, sys
pathlib.Path(sys.argv[1]).write_text(json.dumps({
    "schema": "gamescope-source-admission-v1", "gamescope_head": sys.argv[2],
    "manifest_sha256": sys.argv[3], "projects": [],
    "validated_edges": 34, "verified_project_pins": 32,
}, indent=2, sort_keys=True) + "\n")
PY

for repo in image libsdl3-sunxifb wpa-supplicant-tsp runtime sim pf-hwprobe poolsuite blobs vendor-manifest; do
    ln -s gamescope "${tmp}/home/${repo}"
done
common=$'PF_IMAGE_SHA='"${head}"$'\nPF_KERNEL_REPO=gamescope\nPF_KERNEL_SHA='"${head}"$'\nPF_GPU_REPO=none\nPF_GPU_SHA=\nPF_GPU_MODEL=ddk\nPF_LIBSDL3_SHA='"${head}"$'\nPF_WPA_SHA='"${head}"$'\nPF_RUNTIME_SHA='"${head}"$'\nPF_SIM_SHA='"${head}"$'\nPF_HWPROBE_SHA='"${head}"$'\nPF_POOLSUITE_SHA='"${head}"$'\nPF_BLOBS_SHA='"${head}"$'\nPF_VENDOR_MANIFEST_SHA='"${head}"$'\nPF_UBOOT_REPO=none\nPF_UBOOT_SHA=\nPF_TFA_REPO=none\nPF_TFA_SHA='
gamescope=$'\nPF_GAMESCOPE_MODE=g1\nPF_GAMESCOPE_REPO=gamescope\nPF_GAMESCOPE_REPO_URL=https://github.com/pocketforge-os/gamescope.git\nPF_GAMESCOPE_SHA='"${head}"$'\nPF_GAMESCOPE_UPSTREAM_BASE='"${base}"$'\nPF_GAMESCOPE_PRESENT_HEAD='"${head}"$'\nPF_GAMESCOPE_STAGING_HEAD='"${head}"$'\nPF_GAMESCOPE_ROTATION_HEAD='"${head}"$'\nPF_GAMESCOPE_REQUIRED_PATCH_IDS='"${patch_ids}"$'\nPF_GAMESCOPE_PATCH_SERIES_SHA256='"${patch_digest}"$'\nPF_GAMESCOPE_DEPENDENCY_MANIFEST_SHA256='"${manifest_digest}"$'\nPF_GAMESCOPE_LICENSE_SHA256='"${license_digest}"$'\nPF_GAMESCOPE_DIAGNOSTICS=0'

HOME="${tmp}/home" PF_MIRROR_DIR="${tmp}/mirrors" VARIANT=dev \
    PF_GAMESCOPE_DEPENDENCY_CACHE="${tmp}/cache" \
    pf_stage_sources "${tmp}/selected" "${common}${gamescope}"
python3 - "${tmp}/selected/gamescope" "${head}" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
receipt = json.loads((root / ".pf-gamescope-source.json").read_text())
assert receipt["schema"] == "pocketforge.gamescope-source/v1"
assert receipt["integrated_head"] == sys.argv[2]
assert receipt["source_url"] == "https://github.com/pocketforge-os/gamescope.git"
assert len(list((root / ".pf-source-licenses").iterdir())) == 32
assert (root / ".pf-gamescope-admission.json").is_file()
assert (root / ".pf-gamescope-materialization.json").is_file()
PY

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
    echo 'FAIL: missing tsp-op5a.440.7 dependency cache was accepted' >&2
    exit 1
fi
grep -Fq 'tsp-op5a.440.7' "${tmp}/no-cache.log"

echo 'PASS: exact Gamescope admission/materialization staging is profile-only and fail-closed'
