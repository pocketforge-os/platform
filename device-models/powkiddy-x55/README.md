# Powkiddy X55 fixture reference

This package currently owns the provisional manufacturing handoff for the
Powkiddy X55 test-node holder. `fixture-contract.json` records the owner-traced
contact envelope, safe contact intervals, keep-outs, service opening, and the
three explicitly provisional local depths consumed downstream by
`test-node-hw`.

`powkiddy-x55.scad` is deliberately only a nominal visual reference. It is not
a manufacturing input and is not the pending high-fidelity semantic model
owned by `tsp-98qq`. Fixture consumers use the canonical interface payload and
SHA-256 from the JSON contract; they never derive fit from this mesh.

The contract remains unqualified until `tsp-bcx.21.28` records owner calipers
for the bottom, top, and short-side contact bands plus the maximum rear grip
depth, followed by coupon, carrier, and installed-camera acceptance.

The 210 × 88.76 mm `xy_bounds_mm` remains the owner-traced contact shell. The
separate `physical_xy_bounds_mm` records Powkiddy's published 212.5 × 94.5 mm
maximum collision envelope, provisionally centered in X on the contact shell
and sharing its bottom datum. This permits the shoulder/trigger keep-out to
reach the published envelope without turning that larger box into a hook-fit
surface.

The corrected left-top chain is control keep-out through X=46.28 mm, safe
contact X=46.28–62.64 mm (selected midpoint X=54.46 mm), then I/O keep-out
X=62.64–71.64 mm, exactly matching the cited cradle source.
