# PocketForge semantic device-model contract

Read the repository’s current `device-models/README.md` first. This reference
summarizes the stable pattern; repository documentation wins if it evolves.

## Package shape

Use:

```text
device-models/<slug>/
├── <slug>.scad
├── README.md
├── render.py
└── compare.py
```

Do not add private photographs, generated evidence directories, or auxiliary
process documentation to the package.

## OpenSCAD contract

Author in millimetres with X left-to-right, Y bottom-to-top, and Z rear-to-front
unless a documented accepted baseline uses another fixed convention.

Support:

```text
PART="assembly"                 complete device
PART="shell"                    non-interactive geometry
PART="controls"                 all semantic controls
PART="control" CONTROL_ID="…"  one semantic control
HIGHLIGHT="" | "*" | "…"       neutral, all, or one control
QUALITY="draft" | "render"      preview/render tessellation
```

Keep decorative features out of semantic control geometry. Include the full
visible control—crown plus bezel/recess—when highlighting that complete
physical input is intentional.

## Semantic IDs

Read `devices/<id>/capabilities.toml` before modeling. `render.py`’s
`CONTROL_IDS`, derived metadata controls, and `[skin.parts]` keys must describe
the same drawable parts.

Logical inputs may share a drawable part only when documented. For example,
L3/R3 can reuse `stick_l`/`stick_r`; do not invent invisible duplicate parts.

## Renderer contract

Derive from the nearest accepted `render.py` and preserve:

- fixed `APP_CAMERA`, canvas, crop, padding, and rotation;
- fixed six-view `VIEW_CAMERAS`;
- neutral assembly render;
- active-screen marker used to derive `display_rect`;
- one-control-at-a-time renders;
- exact or thresholded diff rectangles;
- pairwise-disjoint control rectangles;
- lit atlas composition from individual control frames;
- source, renderer, camera, and output hashes in model metadata.

Additional clickable views use their own neutral/lit atlas and parts table.
They do not carry the front screen’s `display_rect`.

Before runtime integration, call `render_skin_set()` directly or use the
skill validator; `render.py --check` may correctly fail while committed skin
assets still belong to a schematic fallback.

## Comparison contract

Keep comparison code separate from the renderer. The renderer must never read
owner photographs.

Have `compare.py`:

- accept an external private photo directory;
- apply EXIF orientation while decoding;
- convert to RGB;
- write only fresh PNG outputs;
- compare fixed model views with named source views;
- report silhouette overlap as a regression aid;
- carry no source metadata.

## Documentation contract

Include:

- coordinate system and intended use;
- baseline lineage;
- measurement/provenance/confidence table;
- public source links;
- semantic control list and reuse decisions;
- reproduction commands;
- renderer/font requirements;
- known limitations and missing measurements.

State explicitly that a nominal visual/UI model is not a
manufacturing-tolerance enclosure drawing.

## Validation ladder

Use absolute OpenSCAD output paths; some OpenSCAD builds fail to export to a
relative `out/` path.

Run, in order:

1. Python source compile checks.
2. OpenSCAD assembly CSG with hard warnings.
3. Six evidence views.
4. A second clean render and byte comparison.
5. Standalone `PART="control"` sweep.
6. Full semantic atlas derivation and rectangle-overlap check.
7. Descriptor drawable-ID parity.
8. Privacy-safe comparison.
9. Repository capability and skin-drift checks when integrated.
10. `render.py --check` on the canonical render host when committed assets are
    in scope.

The live OpenSCAD GUI can contend with off-screen rendering on some hosts.
Close it for the deterministic pass and reopen the exact final commit for
visual review.

## Model versus integration task

The source-model task owns the SCAD package, evidence renderer, comparison
tool, and owner approval of physical appearance.

The runtime-integration task owns:

- adding the device to `skins/generate-bezel.py` routing where required;
- generating `skins/<id>/body*.png`, lit atlases, and metadata;
- reconciling `[skin.parts]` and any `[skin.views.*.parts]`;
- capability validation and drift-gate enrollment;
- owner approval of the application-facing skin.

Keep these as separate tasks when one can land without the other. Close and
merge the source model first, then explicitly unblock the integration task.

## Repository lifecycle

Follow `AGENTS.md`. In the PocketForge workflow:

1. sync Beads and inspect/claim the work order;
2. create a `pf-wt` worktree on the bead branch;
3. implement and append validation evidence to the bead;
4. push a PR with Summary, checked Test plan, and Related PRs;
5. wait for ABI and automated-review gates;
6. merge only after explicit owner visual approval;
7. verify approved-head ancestry on `origin/main`;
8. remove the clean worktree, close the bead, and push Beads state.
