#!/usr/bin/env bash
# Regenerate every derivative of one device model after a .scad edit, then run
# the CI gates over the result.
#
#     device-models/regen.sh <model-slug>      # e.g. trimui-smart-pro
#
# The .scad is the single source of truth. In order this runs:
#   1. <slug>/render.py --write (+ --write-views when the skin has extra views):
#      skins/<id>/{body,body_lit}.png, body_<view>.png, model-render.json rects
#      (skipped for a model-only package with no rendered skin, e.g. the Brick);
#   2. export_gltf.py --model <slug> --write: skins/<id>/model.glb + model-glb.json;
#   3. render_glb_views.py skins/<id>/model.glb: skins/<id>/views/*.png and the
#      model-glb.json "views" block;
#   4. check-skin-drift.py and export_gltf.py --check (what CI runs).
# It then prints every file it changed; commit all of them. Local only: needs
# OpenSCAD (OPENSCAD=<path> overrides), Python 3.11+, numpy and Pillow.
set -euo pipefail

usage() { echo "usage: device-models/regen.sh <model-slug>" >&2; exit 2; }
[ "$#" -eq 1 ] || usage
slug="$1"

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

openscad="${OPENSCAD:-openscad}"
if ! command -v "$openscad" >/dev/null 2>&1; then
  echo "regen.sh: refusing: openscad not found ($openscad); install OpenSCAD 2021.01 or set OPENSCAD" >&2
  exit 2
fi
openscad="$(command -v "$openscad")"

PY=""
for c in python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)'; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || { echo "regen.sh: refusing: no Python 3.11+ found" >&2; exit 2; }

skin="$("$PY" -c '
import sys
sys.path.insert(0, "device-models")
import export_gltf
model = export_gltf.MODELS.get(sys.argv[1])
print(model.skin if model else "")
' "$slug")"
if [ -z "$skin" ]; then
  known="$("$PY" -c 'import sys; sys.path.insert(0, "device-models"); import export_gltf; print(" ".join(sorted(export_gltf.MODELS)))')"
  echo "regen.sh: refusing: unknown model slug '$slug' (known: $known)" >&2
  exit 2
fi
if ! "$PY" -c 'import numpy, PIL' >/dev/null 2>&1; then
  echo "regen.sh: refusing: render_glb_views.py needs numpy and Pillow for $PY" >&2
  exit 2
fi

skin_dir="skins/$skin"
snapshot() {
  if [ -d "$skin_dir" ]; then
    find "$skin_dir" -type f -print0 | sort -z | xargs -0 -r sha256sum
  fi
}
before="$(snapshot)"

render_meta="$skin_dir/model-render.json"
if [ -f "$render_meta" ]; then
  has_views="$("$PY" -c 'import json,sys; print(1 if json.load(open(sys.argv[1])).get("views") else 0)' "$render_meta")"
  echo "== 1/4 device-models/$slug/render.py --write"
  OPENSCAD="$openscad" "$PY" "device-models/$slug/render.py" --write
  if [ "$has_views" = 1 ]; then
    # --write rewrites model-render.json without its "views" block; restore it.
    echo "== 1/4 device-models/$slug/render.py --write-views"
    OPENSCAD="$openscad" "$PY" "device-models/$slug/render.py" --write-views
  fi
else
  echo "== 1/4 skipped: $slug has no rendered skin ($render_meta absent; model-only)"
fi

echo "== 2/4 export_gltf.py --model $slug --write"
"$PY" device-models/export_gltf.py --model "$slug" --write --openscad "$openscad"

echo "== 3/4 render_glb_views.py $skin_dir/model.glb"
"$PY" device-models/render_glb_views.py "$skin_dir/model.glb"

echo "== 4/4 gates: check-skin-drift.py, export_gltf.py --check"
"$PY" device-models/check-skin-drift.py
"$PY" device-models/export_gltf.py --check

after="$(snapshot)"
changed="$(diff <(printf '%s\n' "$before") <(printf '%s\n' "$after") \
  | sed -n 's/^[<>] [0-9a-f]\{64\}  //p' | sort -u || true)"
if [ -z "$changed" ]; then
  echo "regen=pass slug=$slug skin=$skin changed=0 (outputs already current)"
else
  echo "regen=pass slug=$slug skin=$skin changed=$(printf '%s\n' "$changed" | wc -l); commit:"
  printf '%s\n' "$changed" | sed 's/^/  /'
fi
