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
