# TrimUI Smart Pro S semantic model (TG5050)

`trimui-smart-pro-s.scad` is PocketForge's source-owned visual model for the
TrimUI Smart Pro S. Its coordinate space is millimetres: X is physical left to
right, Y is bottom to top, and Z is rear to front. The measured source envelope
is 188.35 × 79.77 mm.

The Pro S deliberately derives from the owner-approved TG5040 model in
[`../trimui-smart-pro/`](../trimui-smart-pro/README.md). The two products share
their outer chassis, display and primary front-control layout, so retaining the
accepted baseline is both more accurate and more reviewable than drawing a
second approximation. The TG5050 source adds the visible Pro S identity and
hardware deltas: the semantic Home key, revised top-edge labels, recessed `R`
reset key, microphone pinhole, `SMART PRO S` / `TG5050` markings, front status
motif, and active-cooling vents.

This remains a 1:1 nominal visual/UI model. It is suitable for device identity,
input highlighting, layout studies and early clearance concepts. It is not a
manufacturing-tolerance enclosure drawing.

## Measurement and provenance

| Feature | Value used | Evidence | Confidence |
|---|---:|---|---|
| Maximum X/Y envelope | 188.35 × 79.77 mm | Owner TG5050 cradle measurement drawing and near-orthographic front photo; identical to the accepted TG5040 caliper envelope | High |
| Published overall envelope | 188 × 80 × 17 mm | TrimUI product specification | High as a nominal envelope; Z datum remains unspecified |
| Shell, display and primary front controls | Inherited from TG5040 source | Shared chassis, owner TG5050 front photo, FCC/product multi-view photos | High for topology; TG5040 confidence table continues to govern individual photo-derived dimensions |
| Home key centre | X = 0.39W (73.46 mm), round 3.60 mm crown in 5.00 mm bezel | Owner top-edge macro plus owner visual review against the physical TG5050 | Medium-high |
| TG5050 top-edge order | POWER → HOME → HOST → split volume rocker | Owner top-edge macro and public TG5050 multi-view photography | High |
| Top-edge depth placement | Controls centred at Z = 5.35 mm; smaller legends on the screen-facing side | Owner visual review against the top-edge macro | Medium-high |
| Reset / microphone | Recessed `R` key at X = 0.55W; MIC pinhole at X = 0.82W on the bottom edge | Owner reset-key macro and visual correction | High for topology and identity; medium for photo-derived size |
| Front identity | `TRIMUI SMART PRO S`, central TrimUI mark and four-bar status motif | Owner front photo and public TG5050 front elevations | Medium-high |
| Front control insets | Stick centres X = 23.5 / 164.85 mm; ABXY centre X = 165.55 mm | Owner visual review against the physical TG5050 | Medium-high |
| Lower face row | Y = 7.15 mm optical centre; Menu X = 25.0 mm, Select X = 162.5 mm, Start X = 170.5 mm | Owner visual review against the physical TG5050 | Medium-high |
| Speaker centres | X = 33.25 / 155.10 mm, Y = 7.15 mm; aligned rows terminate at the adjacent screen edges | Owner visual review against the physical TG5050 | Medium-high |
| Rear active cooling | Two-row upper exhaust plus three striped circular fan-intake fields | FCC/public rear elevations | High for topology; medium for photo-derived size and placement |
| Clear-edge shell depth | 10.7 mm | Shared-chassis TG5040 owner-fit cradle proxy | Medium |

Private owner references used by `compare.py` are
`20260719_142542.jpg` (front) and `20260719_144623.jpg` (top). They stay outside
git. The comparison tool applies EXIF orientation, decodes RGB pixels and writes
fresh PNGs without carrying source metadata.

Public corroboration:

- TrimUI Smart Pro S product page:
  <https://trimui.net/products/trimui-smart-pro-s-handheld>
- FCC ID 2BD9O-TG5050:
  <https://fcc.report/FCC-ID/2BD9O-TG5050>
- TG5050 multi-view product photography:
  <https://mechdiy.com/products/trimui-smart-pro-s-retro-handheld-game-console>

## Semantic contract

The model exposes the fifteen drawable controls in
`devices/a523/capabilities.toml`:

`dpad`, `stick_l`, `stick_r`, `btn_north`, `btn_east`, `btn_south`,
`btn_west`, `btn_select`, `btn_guide`, `btn_start`, `btn_home`, `btn_l1`,
`btn_r1`, `trig_l`, and `trig_r`.

The Pro S adds clickable L3/R3 switches, but those inputs intentionally reuse
the existing `stick_l` and `stick_r` visual parts. Home is separate from the
front gamepad Guide/Menu key and is independently selectable and highlightable.

Useful OpenSCAD overrides:

```text
PART="assembly"                 complete coloured device
PART="shell"                    shell and non-interactive detail
PART="controls"                 all semantic controls
PART="control" CONTROL_ID="…"  one semantic control
HIGHLIGHT="" | "*" | "…"       neutral, all, or one red control
QUALITY="draft" | "render"      tessellation level
```

## Reproduce and compare

From the platform repository root:

```bash
python3 -m py_compile \
  device-models/trimui-smart-pro-s/render.py \
  device-models/trimui-smart-pro-s/compare.py
python3 device-models/trimui-smart-pro-s/render.py \
  --views out/tg5050-views
python3 device-models/trimui-smart-pro-s/compare.py \
  --photos /path/to/owner/photos \
  --views out/tg5050-views \
  --output out/tg5050-comparison
```

Rendering expects the `Liberation Sans` and `Ubuntu Sans` font families.

The renderer already targets `devices/a523/capabilities.toml` and
`skins/a523/`. Its `--write` and `--check` modes retain the TG5040 renderer's
deterministic camera, one-control highlight passes, pairwise-disjoint
rectangles and lit-atlas composition. The separate `tsp-4y55` integration
change owns invoking `--write`, reconciling the derived a523 rectangles, wiring
`skins/generate-bezel.py`, and committing the runtime PNG/metadata outputs.
Until that integration lands, use `--views` for this source model; the current
descriptor still contains schematic-fallback rectangles by design.

## Known limits

- The shared front/envelope geometry inherits the accepted TG5040 evidence,
  while Home, reset and cooling details are photo-ratio estimates rather than
  caliper dimensions.
- The rear vent topology is honest, but slot pitch and recess depth are visual
  parameters; do not use them to design an airflow seal or fan duct.
- A manufacturing-grade revision still needs perpendicular TG5050 edge/rear
  ruler photos and caliper measurements for shell depth, Home/reset openings,
  stick height, port openings, cooling apertures and shoulder projections.
- Comparison IoU is a regression aid after normalizing silhouettes. Phone lens
  distortion, reflections and perspective make it unsuitable as a tolerance
  certification.
