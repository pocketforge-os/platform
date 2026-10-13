#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="${ROOT}/core/pf-build.sh"
args="$(python3 "${ROOT}/core/profile.py" buildargs a133)"

grep -Fxq 'PF_CURSOR_THEME_SHA=c5783fbb7d9d89c82bc1b4757c303e267b6cd104' <<<"${args}"
grep -Fxq 'PF_CURSOR_TOOLS_IMAGE=10.0.32.86:5555/pocketforge/ci-tools@sha256:2ff536627228c90e5c32b7d6345b21600a38a17481c075b41683db47ead3e862' <<<"${args}"
grep -Fxq 'PF_CURSOR_TOOLS_RECIPE_SHA=22b8c9feb04565c9ee84858687ed30455da7ed58' <<<"${args}"

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
assert lock["cursor_theme"]["tools_recipe_sha"] == "22b8c9feb04565c9ee84858687ed30455da7ed58"
assert lock["cursor_theme"]["tools_image_digest"] == "2ff536627228c90e5c32b7d6345b21600a38a17481c075b41683db47ead3e862"
PY

echo 'cursor-theme staging contract: PASS'
