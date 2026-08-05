// Powkiddy X55 nominal fixture-reference silhouette.
//
// This intentionally modest visual proxy exists beside fixture-contract.json
// so the manufacturing handoff never treats a contract as a device mesh.  The
// separate high-fidelity semantic-model bead tsp-98qq will replace this source
// after owner visual approval; fixture consumers use only the canonical JSON
// interface hash, never this geometry.

PART = "assembly";
QUALITY = "draft";

published_envelope = [212.5, 94.5, 19.0];
owner_contact_envelope = [210.0, 88.76];
screen_size = [121.78, 68.50];
screen_center = [105.0, 45.38];
corner_radius = 12.0;

module rounded_box(size, radius) {
    linear_extrude(height = size.z)
        offset(r = radius)
            square([size.x - 2 * radius, size.y - 2 * radius], center = true);
}

module shell() {
    translate([published_envelope.x / 2, published_envelope.y / 2, 0])
        rounded_box(published_envelope, corner_radius);
}

module screen_marker() {
    translate([screen_center.x, screen_center.y, published_envelope.z])
        linear_extrude(height = 0.3)
            square(screen_size, center = true);
}

if (PART == "assembly") {
    color([0.08, 0.18, 0.27]) shell();
    color([0.03, 0.03, 0.04]) screen_marker();
} else if (PART == "shell") {
    shell();
} else if (PART == "screen") {
    screen_marker();
} else {
    assert(false, str("Unsupported PART: ", PART));
}
