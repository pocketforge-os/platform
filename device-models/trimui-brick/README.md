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
| Rear depth transition | Y=43–49 mm sloped band | TRIMUI six-view product art and FCC rear/side photographs registered to the owner envelope | Medium-low; no direct caliper transition coordinate |
| Manufacturer nominal envelope | 73.2 × 109.9 × approximately 19.9 mm | TRIMUI published specification | High as nominal marketing data; deliberately not averaged with the owner unit |
| Active display | 3.2 in, 4:3; 65.02 × 48.77 mm calculated | TRIMUI specification | High |
| Display glass | 67.35 × 51.35 mm; centre (36.4, 84.25) | Owner front image and TRIMUI/FCC near-front views registered to the known envelope | Medium-high |
| D-pad | centre (17.4, 37.2), 19.0 mm cross | Owner front image and black product front elevation | Medium-high |
| Face cluster | centre (54.9, 38.8), 8.25 mm cardinal pitch, 8.3 mm crowns | Owner front image; Nintendo X/A/B/Y product elevation | Medium-high |
| F1/F2 controls | centres (29.8/41.2, 51.3), silver pill topology | Owner front image, product elevation, and FCC front photographs | Medium-high |
| Menu/Select/Start controls | centres (28.0/36.4/44.8, 8.8) | Owner and manufacturer front elevations | Medium-high |
| Speaker perforations | mirrored 2 × 8 arrays near Y=13.15 | Owner front photograph and manufacturer front elevation | Medium for count/placement; hole dimensions are visual |
| Rear shoulder shelf | L1/L2/Host/R2/R1 at Y≈47.2, rear Z≈4.15 | Manufacturer top/rear/side elevations and FCC rear view | High for order/topology; medium-low for exact Z and shelf slope |
| RGB light bar | centred 25 mm bar on the overall top edge | Manufacturer six-view and perspective product art | Medium |
| Left-side controls | volume + above volume − | Manufacturer side elevation and user manual | High for order; medium for opening dimensions |
| Right-side controls | ridged Fn above cyan power key | Manufacturer side elevation and user manual | High for order/color; medium for dimensions |
| Bottom features | TF, reset, DC USB-C, microphone, 3.5 mm audio from left to right | FCC bottom photograph, manufacturer bottom elevation, and user manual | High for order; medium for dimensions |
| Rear surface | upper metal panel, six screws, lower horizontal ribs, identity/regulatory bands | Manufacturer rear elevation and FCC rear photographs | Medium-high for topology; printing is representational |

Public references:

- TRIMUI Brick product page:
  <https://trimui.com/pages/trimui-brick>
- TRIMUI launch/specification article:
  <https://trimui.com/blogs/news/introducing-the-trimui-brick-a-retro-inspired-handheld-game-console-coming-soon>
- FCC ID 2BD9O-TG3040 external photographs:
  <https://fccid.io/2BD9O-TG3040/External-Photos/External-photos-7726607>
- FCC ID 2BD9O-TG3040 user manual:
  <https://fccid.io/2BD9OTG3040/User-Manual/User-manual-7726616>

The locally reviewed owner evidence is
`/home/matt/Downloads/20260721_032132.jpg` and
`/home/matt/Downloads/20260721_032150.jpg`. Neither original is copied into
git. `compare.py` applies EXIF orientation, decodes RGB pixels, selects fixed
device/measurement crops, and writes fresh PNGs with no inherited metadata.

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
  coordinate and curvature of the rear depth transition remain photo-derived.
- The shoulder shelf order and shape are well constrained, but exact paddle
  travel, shelf angle, and protrusion need perpendicular macro photographs or
  calipers for manufacturing accuracy.
- Port order is verified; individual opening sizes, chamfers, and connector
  insertion depths are nominal visual estimates.
- Rear alloy finish, mould texture, rib height, tiny regulatory symbols, screw
  recess depth, and display-glass reflectance are representational OpenSCAD
  materials rather than scanned surface data.
- The owner evidence set has a strong front view and measurements but no
  perpendicular owner rear/top/bottom/left/right photographs. Public TRIMUI
  and FCC views cover those surfaces for this first pass.
- No fixture contract is added here. The existing Brick holder remains the
  physically qualified source for contact and retention decisions.
- No runtime descriptor, skin atlas, or simulator routing is added in this
  task. Those are a separate integration gate after explicit owner approval of
  this model's physical appearance.
