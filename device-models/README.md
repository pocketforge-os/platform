# Semantic device models

This directory is the source-owned 3D device library used by PocketForge UI
surfaces.  A model is authored in millimetres, names its physical controls with
the same semantic ids as `devices/<id>/capabilities.toml`, and can produce both
human-review views and the neutral/lit skin pair consumed by `pf-hwprobe`.

Each model directory should contain:

- one documented OpenSCAD source with a fixed physical coordinate system;
- a measurement/provenance table that separates measured, published, and
  photo-derived dimensions;
- deterministic rendering and stale-artifact checks;
- semantic control selection (`PART="control"`, `CONTROL_ID="…"`) and
  highlighting (`HIGHLIGHT="…"` or `"*"`);
- a clear limitations section.  Millimetre coordinates do not turn uncertain
  photo-derived surfaces into manufacturing-tolerance geometry.

Generated PNGs remain checked in because the target app must not need OpenSCAD.
The model source and render metadata make those PNGs reproducible.  Original
owner photographs stay outside git: comparison tooling may read them, but must
write fresh PNGs without copying EXIF metadata.

The first implementation is
[`trimui-smart-pro/`](trimui-smart-pro/README.md), whose fourteen semantic
controls map directly to the A133 capability descriptor.
