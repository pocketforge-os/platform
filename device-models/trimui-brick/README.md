# TrimUI Brick semantic model (TG3040)

`trimui-brick.scad` is PocketForge's source-owned visual model of the black
TrimUI Brick. Its coordinate space is millimetres: X is physical left to right,
Y is bottom to top, and Z is rear to front. The primary envelope is the owner's
72.8 × 110.75 mm measurement, with a planar front at Z=20 mm and stepped rear
datums at Z=0/8 mm for the measured 20/12 mm lower/upper depths.

This is a nominal visual/UI model for device identity, input highlighting,
fixture visualization, simulator-skin generation, and layout studies. It is
not a manufacturing-tolerance enclosure drawing. Holder geometry continues to
come from the measured contract and fit work in `test-node-hw`, not by taking a
pressure fit from this visual surface.

## Baseline lineage

The package contract, semantic selection, deterministic rendering, and
privacy-safe comparison flow are derived from the accepted
`device-models/trimui-smart-pro/` package. The Brick shares no enclosure
geometry with that device, so its shell, screen, controls, rear step, ports,
and labels are authored independently from Brick evidence rather than scaled
from the Smart Pro.

This source-model bead intentionally stops before runtime integration. There
is no committed TrimUI Brick `devices/<id>/capabilities.toml` descriptor yet.
The semantic IDs below are stable model-stage names derived from the physical
controls and existing PocketForge conventions; the later descriptor/runtime
task must reconcile them and generate the app-facing skins only after owner
visual approval.

## Measurement and provenance

| Feature | Value used | Evidence | Confidence |
|---|---:|---|---|
| Maximum face envelope | 72.8 × 110.75 mm | Owner graph-paper measurement `20260721_032150.jpg`; reused by Brick cradle bead `tsp-bcx.21.23` | High |
| Lower / upper shell depth | 20.0 / 12.0 mm | Owner annotations in `20260721_032132.jpg` and `20260721_032150.jpg`; cradle fit profile | High at the measured contact regions |
| Rear thick section / transition | 60.0 mm lower section, transitioning through the 4.44 mm USB/shoulder band | Owner caliper measurements supplied 2026-07-29 | High in Y; transition surface remains a visual interpolation |
| Manufacturer nominal envelope | 73.2 × 109.9 × approximately 19.9 mm | TRIMUI published specification | High as nominal marketing data; deliberately not averaged with the owner unit |
| Active display | 3.2 in, 4:3; 65.02 × 48.77 mm calculated | TRIMUI specification | High |
| Display glass | 67.35 × 51.35 mm; centre (36.4, 84.25) | Owner front image and TRIMUI/FCC near-front views registered to the known envelope | Medium-high |
| D-pad | centre (17.4, 37.2), 18.43 mm overall X/Y | Owner caliper measurement supplied 2026-07-29 | High for size; centre remains registered from imagery |
| Face cluster | centre (54.9, 38.8), 8.25 mm cardinal pitch, 7.0 mm crowns | Owner caliper measurement supplied 2026-07-29; Nintendo X/A/B/Y product elevation | High for diameter; medium-high for pitch |
| F1/F2 controls | centres (29.8/41.2, 51.3), each 6.25 × 2.0 mm and intentionally unlabelled | Owner caliper/visual correction supplied 2026-07-29 | High |
| Menu/Select/Start controls | 4.5 mm crowns; centres (26.6/36.4/46.2, 8.0); 5.3 mm clear gaps; 5.75 mm bottom margin | Owner caliper measurements supplied 2026-07-29 | High |
| Front identity lockup | left-justified `TRIMUI` + three-dot mark + `BRICK`, 15.9 mm overall width | Owner caliper/visual correction supplied 2026-07-29 | High |
| Speaker perforations | mirrored 2 × 8 arrays near Y=13.15 | Owner front photograph and manufacturer front elevation | Medium for count/placement; hole dimensions are visual |
| Rear shoulder shelf | L1/R1 17.51 × 8.30 mm; L2/R2 10.32 × 9.86 mm after a 2.0 mm travel gap; 3.7 mm rear bevel on all four and outer bevel on L1/R1 | Owner caliper/visual correction supplied 2026-07-29 | High in X/Y |
| Rear USB-C housing | 13.55 × 4.44 mm beyond the thick section; 8.79 mm opening | Owner caliper measurement supplied 2026-07-29 | High |
| Top light diffuser | one opaque 38.0 × 3.56 mm strip with a 2.0 mm rear return | Owner caliper/visual correction supplied 2026-07-29 | High |
| Left-side controls | volume +/− each 7.82 × 3.52 mm; 2.85 mm clear gap; + top is 6.3 mm below case top | Owner caliper measurements supplied 2026-07-29 | High |
| Right-side controls | Fn track 10.65 × 3.82 mm with 7.73 mm slider, top 18.0 mm below case top; cyan power 7.0 × 4.35 mm with 7.0 mm gap below Fn | Owner caliper/visual corrections supplied 2026-07-29 | High |
| Bottom features | TF, reset, DC USB-C, microphone, 3.5 mm audio from left to right | FCC bottom photograph, manufacturer bottom elevation, and user manual | High for order; medium for dimensions |
| Rear identity | `TRIMUI` + three-dot mark + `BRICK` at 22.72 × 2.88 mm; design line at 19.55 × 0.92 mm | Owner caliper measurements supplied 2026-07-29 | High |
| Rear regulatory lockup | three-line verbatim copy at 36.19 × 4.14 mm; FCC/CE/recycle/WEEE marks 4.26 mm high with measured widths and gaps | Owner transcription and caliper measurements supplied 2026-07-29 | High for bounds/gaps; vector linework is a visual reconstruction |

Public references:

- TRIMUI Brick product page:
  <https://trimui.com/pages/trimui-brick>
- TRIMUI launch/specification article:
  <https://trimui.com/blogs/news/introducing-the-trimui-brick-a-retro-inspired-handheld-game-console-coming-soon>
- FCC ID 2BD9O-TG3040 external photographs:
  <https://fccid.io/2BD9O-TG3040/External-Photos/External-photos-7726607>
- FCC ID 2BD9O-TG3040 user manual:
  <https://fccid.io/2BD9OTG3040/User-Manual/User-manual-7726616>
- European Commission CE marking artwork and proportion guidance:
  <https://single-market-economy.ec.europa.eu/single-market/goods/ce-marking_en>
- European Union crossed-out wheeled-bin label guidance:
  <https://europa.eu/youreurope/business/product-rules-compliance/recycling-waste-management/weee-label/indexamp_en.htm>
- Public-domain FCC vector, sourced from the FCC website:
  <https://commons.wikimedia.org/wiki/File:FCC_New_Logo.svg>
- Public-domain three-arrow Möbius-loop reference:
  <https://commons.wikimedia.org/wiki/File:Recycle001.svg>

The locally reviewed owner evidence is
`/home/matt/Downloads/20260721_032132.jpg` and
`/home/matt/Downloads/20260721_032150.jpg`. Neither original is copied into
git. `compare.py` applies EXIF orientation, decodes RGB pixels, selects fixed
device/measurement crops, and writes fresh PNGs with no inherited metadata.

The four rear compliance marks are reproduced as source-owned OpenSCAD vector
geometry at the owner's measured bounds and gaps. No downloaded SVG is needed
at render time. The CE construction preserves the official equal-ring
proportions before scaling to the device's measured mark bounds; the WEEE mark
includes both the crossed-out wheeled bin and its underline.

## Semantic controls

The OpenSCAD source exposes:

`dpad`, `btn_north`, `btn_east`, `btn_south`, `btn_west`, `btn_f1`,
`btn_f2`, `btn_menu`, `btn_select`, `btn_start`, `btn_l1`, `trig_l`,
`trig_r`, `btn_r1`, `vol_up`, `vol_down`, `btn_fn`, and `btn_power`.

The directional face IDs name physical position. Printed glyphs use the
Nintendo layout: X north, A east, B south, and Y west. `trig_l`/`trig_r` name
the physical L2/R2 keys and do not imply analog travel.

Useful OpenSCAD overrides:

```text
PART="assembly"                 complete coloured device
PART="shell"                    non-interactive geometry and detail
PART="controls"                 all semantic controls
PART="control" CONTROL_ID="…"  one semantic control
PART="screen"                   active display surface
HIGHLIGHT="" | "*" | "…"       neutral, all, or one red control
QUALITY="draft" | "render"      tessellation level
```

`render.py` exposes the same 18 IDs. Because the physical controls occupy four
different visible surfaces, `render_skin_set()` produces a model-review atlas:
front controls in the main tile, shoulder controls in the top tile, volume in
the left tile, and Fn/power in the right tile. Each rectangle is derived from a
one-control render and proven pairwise disjoint. This is evidence for the
source model, not a committed runtime skin contract.

## Reproduce and compare

From the platform repository root:

```bash
python3 device-models/trimui-brick/render.py \
  --views /tmp/trimui-brick-views
python3 device-models/trimui-brick/render.py \
  --semantic-output /tmp/trimui-brick-semantic
python3 device-models/trimui-brick/render.py --check
python3 device-models/trimui-brick/compare.py \
  --photos /home/matt/Downloads \
  --views /tmp/trimui-brick-views \
  --output /tmp/trimui-brick-comparison
python3 /home/matt/.codex/skills/model-handheld-device/scripts/validate_model_package.py \
  device-models/trimui-brick \
  --photos /home/matt/Downloads \
  --output /tmp/trimui-brick-validation
```

Rendering requires OpenSCAD 2021.01 or newer, Pillow, Liberation Sans, and
DejaVu Sans. The fixed orthographic cameras and output transforms live in
`render.py`; comparison output and generated evidence stay outside the
repository.

The front silhouette IoU emitted by `compare.py` is a regression aid. Phone
lens distortion, graph-paper perspective, shadows, and thresholding make it
unsuitable as a tolerance or fit claim.

## Known limits and next evidence gate

- The measured X/Y envelope and two depth datums are strong. The exact Y
  curvature of the 60–64.44 mm rear transition remains interpolated.
- Shoulder X/Y bounds and the 3.7 mm bevel are measured. Exact Z profile,
  paddle travel, shelf angle, and protrusion still need perpendicular macro
  photographs or a depth measurement for manufacturing accuracy.
- Port order is verified and the rear USB-C housing/opening is measured;
  bottom-edge opening sizes, chamfers, and insertion depths remain nominal.
- Rear alloy finish, mould texture, rib height, compliance-mark linework,
  screw recess depth, and display-glass reflectance are representational
  OpenSCAD materials rather than scanned surface data.
- The owner evidence set has a strong front view and measurements but no
  perpendicular owner rear/top/bottom/left/right photographs. Public TRIMUI
  and FCC views cover those surfaces for this first pass.
- No fixture contract is added here. The existing Brick holder remains the
  physically qualified source for contact and retention decisions.
- No runtime descriptor, skin atlas, or simulator routing is added in this
  task. Those are a separate integration gate after explicit owner approval of
  this model's physical appearance.
