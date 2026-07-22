# TrimUI Smart Pro semantic model (TG5040, base/non-S)

`trimui-smart-pro.scad` is the canonical PocketForge visual model for the base
TrimUI Smart Pro.  Its coordinate space is millimetres: X is physical left to
right, Y is bottom to top, and Z is rear to front.  The source envelope is
188.35 × 79.77 mm; generated app art is a perspective projection of that model,
not a flat sketch.

This is a 1:1 nominal visual/UI model.  It is suitable for on-screen device
identity, input highlighting, layout studies, and early holder concepts.  It is
not yet a tolerance drawing for a snap fit: the owner-photo set does not include
coplanar ruler views of both short sides, and the 17 mm published depth does not
say which protrusions are included.

## Measurement and provenance table

| Feature | Value used | Evidence | Confidence |
|---|---:|---|---|
| Maximum X/Y envelope | 188.35 × 79.77 mm | Owner calipers, preserved by the existing TG5040 cradle work | High |
| Published overall envelope | 188 × 80 × 17 mm | TrimUI product specification | High as a nominal envelope; Z datum is unspecified |
| Clear-edge shell depth | 10.7 mm | Owner-fit cradle proxy | Medium; deliberately distinct from 17 mm overall depth |
| Active display | 4.96 in, 16:9 (109.80 × 61.76 mm calculated) | TrimUI specification | High |
| Display glass/recess | 111.6 × 63.2 mm | FCC and owner-photo registration against the known envelope | Medium |
| Endcap curve | 30.0 × 39.885 mm half-ellipse | Rear silhouette fit; a 40 mm stadium endcap visibly overfilled the photos | Medium |
| D-pad centre / size | (18.8, 55.7), 19.2 mm | FCC near-front view plus owner left-front close-up | Medium-high |
| Stick centres | (19.5, 24.9), mirrored; 19.4 mm outer ring | FCC ruler view plus both owner front close-ups | Medium-high |
| Face cluster | centre (169.55, 55.8), pitch 7.55 × 7.75 mm, buttons 7.2 mm | Owner right-front close-up | Medium-high |
| Menu / Select / Start centres | (26.0, 8.8) / (156.4, 8.8) / (165.8, 8.8) | Owner front close-ups and FCC front view | Medium-high |
| Speaker grilles / front printing | Two mirrored 2 × 6 arrays of tapered hexagonal recesses, 1.90 mm horizontal pitch with a half-pitch row stagger; bold-italic system silkscreen; three-dot mark immediately precedes `TRIMUI SMART PRO` left of the right grille | Owner left/right front close-ups and owner correction collages | High for count/order/style; medium-high for photo-derived dimensions and placement |
| Top-edge centres | power 0.28W, host 0.49W, volume − 0.63W, + 0.71W | Two overlapping owner top-edge photographs | Medium |
| Top-edge control topology | Raised POWER key; rim/cavity/tongue HOST USB-C; one continuous volume rocker with centre seam | Owner top-edge macros and owner correction collages | Medium-high |
| Bottom-edge centres | FN 0.24W, badge 0.37W, DC 0.50W, mic 0.56W, TF 0.625W, audio 0.74W | Owner bottom-edge photograph | Medium |
| L/L2 and R/R2 surfaces | Five-section shell-following paddles joining the top tangent at approximately 29 mm | Owner top, rear, shoulder-macro photographs, and owner correction collages | Medium-low in Z; attachment topology and control identity/order are high |
| Rear fasteners and printing | asymmetric upper/lower inset pattern; lower printed band | Owner rear photograph and FCC rear view | Medium |

Public references:

- TrimUI product page: <https://trimui.net/es/products/trimui-smart-pro>
- FCC external photographs, FCC ID 2BD9O-TG5040:
  <https://fcc.report/FCC-ID/2BD9O-TG5040/7016363.pdf>

The locally reviewed owner photographs are named `20260721_192724.jpg` through
`20260721_192845.jpg`.  Six follow-up correction collages are named
`20260721_213243-COLLAGE.jpg` through `20260721_214420-COLLAGE~2.jpg`.  Neither
set is copied into this repository: the originals contain EXIF and the primary
set includes precise GPS coordinates.  The comparison script strips metadata
by decoding pixels and writing new PNG files.

## Semantic contract

The model exposes the fourteen physical controls already described by
`devices/a133/capabilities.toml`:

`dpad`, `stick_l`, `stick_r`, `btn_north`, `btn_east`, `btn_south`,
`btn_west`, `btn_select`, `btn_guide`, `btn_start`, `btn_l1`, `btn_r1`,
`trig_l`, and `trig_r`.

The base unit's L2/R2 parts are physical binary switches reported on ABS_Z and
ABS_RZ.  Keeping them as separately highlightable trigger geometry makes that
important “analog-shaped wire, binary actuator” result visible in the mapping
test instead of silently treating them as analogue travel.

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
python3 device-models/trimui-smart-pro/render.py --write
python3 device-models/trimui-smart-pro/render.py --check
python3 device-models/trimui-smart-pro/render.py --views out/tg5040-views
python3 device-models/trimui-smart-pro/compare.py \
  --photos /path/to/owner/photos \
  --views out/tg5040-views \
  --output out/tg5040-comparison
```

Rendering expects the `Liberation Sans` and `Ubuntu Sans` font families; the
latter supplies the photographed extra-bold italic enclosure silkscreen.

`--write` updates the checked-in neutral PNG and composes the shared all-lit
atlas from one-control renders after proving every crop rectangle pairwise
disjoint.  This matters for the diagonal shoulder arcs: their exposed bands are
split/trimmed so L/L2 and R/R2 remain independent without a shoulder press
painting the D-pad or a face button.  The command records the camera, source and
renderer hashes, output hashes, atlas policy, and derived rectangles in
`skins/a133/model-render.json`.  `--check` rerenders from source and fails if a
PNG, capability rectangle, atlas pixel, or non-overlap invariant has drifted.
The comparison output is review evidence only and remains under ignored `out/`.

## Known limits and next measurement gate

- The front/rear X/Y envelope and control layout are substantially constrained;
  the shoulder paddle depth and the compound rear roll remain the weakest
  surfaces.
- Phone wide-angle distortion makes raw pixel residuals misleading.  The rear
  silhouette IoU emitted by `compare.py` is a regression aid, not a tolerance
  certification.
- A manufacturing-grade revision needs perpendicular left/right/top/bottom
  photos with a ruler in the same plane, plus caliper measurements for bare
  shell depth, stick height, shoulder projections, port openings, and corner
  radii.  Until then, holder geometry should preserve clearance rather than
  assume a pressure fit from this visual model.
