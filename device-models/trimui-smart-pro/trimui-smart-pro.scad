/*
 * PocketForge semantic device model — TrimUI Smart Pro (TG5040, base/non-S)
 *
 * Coordinate system (millimetres):
 *   X = physical left -> right
 *   Y = physical bottom -> top
 *   Z = rear -> front / viewer
 *
 * PART:
 *   assembly  complete coloured model (default)
 *   shell     non-interactive shell, screen, ports, labels and speakers
 *   controls  all interactive controls
 *   control   only CONTROL_ID, for semantic mesh/export checks
 *   screen    only the active display surface, for projected-rect derivation
 *
 * HIGHLIGHT is "", "*", or one semantic id from CONTROL_IDS. These ids match
 * devices/a133/capabilities.toml [skin.parts] exactly, so the OpenSCAD source
 * can generate pf-hwprobe's neutral and all-controls-lit sprite pair without
 * device-specific application code.
 *
 * This is a visual/UI model, not a manufacturing-tolerance drawing. See the
 * adjacent README for source/confidence of every measurement family.
 */

PART = "assembly";
CONTROL_ID = "btn_east";
HIGHLIGHT = "";
SHOW_GLYPHS = true;
SHOW_MICRO_DETAILS = true;
SCREEN_MARKER = false;  // renderer-only projected display-rect probe
QUALITY = "render";

$fn = QUALITY == "draft" ? 24 : 56;
epsilon = 0.02;

// ---- Primary measured/reference envelope --------------------------------
device_width = 188.35;              // owner calipers (cradle bead)
device_height = 79.77;              // owner calipers (cradle bead)
nominal_overall_depth = 17.0;       // official product envelope
local_shell_depth = 10.7;           // owner-fit cradle proxy at clear edges
front_z = local_shell_depth;
device_centre = [device_width / 2, device_height / 2];

// The endcaps are horizontally tighter than a 40 mm-radius stadium. Rear and
// front photographs resolve them as approximately 30 x 40 mm half-ellipses.
endcap_radius_x = 30.0;
endcap_radius_y = device_height / 2;
outline_segments = QUALITY == "draft" ? 20 : 44;

// Official 4.96-inch 16:9 active area, separated from the slightly larger
// glass/recess so the physical panel fact is not conflated with bezel art.
screen_diagonal = 4.96 * 25.4;
screen_active = [
    screen_diagonal * 16 / sqrt(16 * 16 + 9 * 9),
    screen_diagonal * 9 / sqrt(16 * 16 + 9 * 9)
];
screen_glass = [111.6, 63.2];
screen_centre = [device_width / 2, 40.0];

// Photo-derived front landmarks. Bilateral pairs intentionally share Y and
// mirrored X unless repeat evidence proves a real enclosure asymmetry.
dpad_centre = [18.8, 55.7];
stick_left_centre = [19.5, 24.9];
stick_right_centre = [device_width - 19.5, 24.9];
face_centre = [device_width - 18.8, 55.8];
face_pitch = [7.55, 7.75];
menu_centre = [26.0, 8.8];
select_centre = [158.7, 8.8];
start_centre = [170.4, 8.8];

// Photo-derived speaker grille lattice.  Each side has two staggered rows of
// six shallow hexagonal recesses; the upper row steps toward its nearest
// endcap and the lower row steps toward the display.
speaker_left_centre_x = 44.775;
speaker_pitch_x = 1.90;
speaker_pitch_y = 1.50;
speaker_bottom_y = 1.65;
speaker_opening_diameter = 1.50;
speaker_throat_diameter = 0.90;

dpad_size = 19.2;
dpad_arm = 7.2;
stick_ring_diameter = 19.4;
stick_recess_diameter = 16.1;
stick_cap_diameter = 12.8;
face_button_diameter = 7.2;
system_button_diameter = 6.25;
system_button_recess_diameter = 7.15;

// Shoulder extents and top-edge feature centres are photo-derived.
shoulder_span = 32.0;
power_centre_x = 0.28 * device_width;
host_centre_x = 0.49 * device_width;
volume_minus_centre_x = 0.63 * device_width;
volume_plus_centre_x = 0.71 * device_width;

// Bottom-edge feature centres are photo-derived and remain non-interactive
// presentation details (the FN slider is not an evdev row in the descriptor).
fn_centre_x = 0.24 * device_width;
badge_centre_x = 0.37 * device_width;
dc_centre_x = 0.50 * device_width;
mic_centre_x = 0.56 * device_width;
card_centre_x = 0.625 * device_width;
audio_centre_x = 0.74 * device_width;

CONTROL_IDS = [
    "dpad",
    "stick_l",
    "stick_r",
    "btn_north",
    "btn_east",
    "btn_south",
    "btn_west",
    "btn_select",
    "btn_guide",
    "btn_start",
    "btn_l1",
    "btn_r1",
    "trig_l",
    "trig_r"
];

function contains(values, value) =
    len([for (candidate = values) if (candidate == value) 1]) > 0;
function is_active(id) = HIGHLIGHT == "*" || HIGHLIGHT == id;
function side_x(side, left_x) =
    side == "left" ? left_x : device_width - left_x;
function side_id(side, left_id, right_id) =
    side == "left" ? left_id : right_id;

assert(abs(device_width - 188.35) < 0.001 &&
       abs(device_height - 79.77) < 0.001,
       "TG5040 owner-caliper front envelope changed");
assert(nominal_overall_depth >= local_shell_depth,
       "Overall depth cannot be shallower than the clear shell edge");
assert(abs(sqrt(screen_active.x * screen_active.x +
                screen_active.y * screen_active.y) -
           screen_diagonal) < 0.001,
       "Screen active area lost its official 4.96-inch diagonal");
assert(screen_glass.x > screen_active.x &&
       screen_glass.y > screen_active.y,
       "Glass must remain larger than the active panel");
assert(PART != "control" || contains(CONTROL_IDS, CONTROL_ID),
       str("Unknown CONTROL_ID: ", CONTROL_ID));
assert(HIGHLIGHT == "" || HIGHLIGHT == "*" ||
       contains(CONTROL_IDS, HIGHLIGHT),
       str("Unknown HIGHLIGHT id: ", HIGHLIGHT));

// ---- Palette --------------------------------------------------------------
shell_rear_color = [0.125, 0.135, 0.145, 1.0];
shell_front_color = [0.190, 0.200, 0.210, 1.0];
shell_edge_color = [0.060, 0.066, 0.074, 1.0];
control_color = [0.055, 0.060, 0.068, 1.0];
control_edge_color = [0.020, 0.023, 0.028, 1.0];
ring_color = [0.74, 0.76, 0.76, 1.0];
glass_color = [0.012, 0.017, 0.027, 1.0];
glass_edge_color = [0.13, 0.15, 0.18, 1.0];
legend_color = [0.76, 0.78, 0.79, 1.0];
silkscreen_color = [0.93, 0.94, 0.92, 1.0];
highlight_color = [0.92, 0.08, 0.08, 1.0];
highlight_dark_color = [0.55, 0.025, 0.025, 1.0];

ui_font = "Liberation Sans:style=Bold";
silkscreen_font = "Ubuntu Sans:style=ExtraBold Italic";
brand_font = "Liberation Sans:style=Bold Italic";
brand_companion_font = "Liberation Sans:style=Regular";

function active_color(id, neutral = control_color) =
    is_active(id) ? highlight_color : neutral;
function active_dark_color(id, neutral = control_edge_color) =
    is_active(id) ? highlight_dark_color : neutral;
function speaker_positions(side) = [
    for (row = [0 : 1], column = [0 : 5])
        let(outward = side == "left" ? -1 : 1,
            row_stagger = (row == 1 ? 1 : -1) *
                          outward * speaker_pitch_x / 4)
            [side_x(side, speaker_left_centre_x) +
                 (column - 2.5) * speaker_pitch_x + row_stagger,
             speaker_bottom_y + row * speaker_pitch_y]
];

// ---- Reusable geometry ----------------------------------------------------
function left_endcap_points() = [
    for (index = [0 : outline_segments])
        let(angle = 90 + 180 * index / outline_segments)
            [endcap_radius_x + endcap_radius_x * cos(angle),
             device_height / 2 + endcap_radius_y * sin(angle)]
];

function right_endcap_points() = [
    for (index = [0 : outline_segments])
        let(angle = -90 + 180 * index / outline_segments)
            [device_width - endcap_radius_x +
                 endcap_radius_x * cos(angle),
             device_height / 2 + endcap_radius_y * sin(angle)]
];

function body_outline_points() = concat(
    [[endcap_radius_x, 0],
     [device_width - endcap_radius_x, 0]],
    right_endcap_points(),
    [[endcap_radius_x, device_height]],
    left_endcap_points()
);

module rounded_rect_2d(size, radius, centre = true) {
    translation = centre ? -size / 2 : [0, 0];
    translate(translation)
        offset(r = radius)
            offset(delta = -radius)
                square(size);
}

module pill_2d(length, width) {
    hull() {
        translate([-(length - width) / 2, 0]) circle(d = width);
        translate([ (length - width) / 2, 0]) circle(d = width);
    }
}

module body_outline_2d(inset = 0) {
    offset(delta = -inset)
        polygon(points = body_outline_points());
}

module outline_layer(z, inset, thickness = 0.05) {
    translate([0, 0, z])
        linear_extrude(height = thickness)
            body_outline_2d(inset);
}

module rounded_panel(point, size, height, radius, z) {
    translate([point.x, point.y, z])
        linear_extrude(height = height)
            rounded_rect_2d(size, radius);
}

module bevel_cylinder(diameter, height, bevel = 0.45) {
    safe_bevel = min(bevel, min(height / 2 - 0.02, diameter / 4));
    hull() {
        cylinder(d = diameter - 2 * safe_bevel, h = 0.05);
        translate([0, 0, safe_bevel])
            cylinder(d = diameter, h = 0.05);
        translate([0, 0, height - safe_bevel])
            cylinder(d = diameter, h = 0.05);
        translate([0, 0, height - 0.05])
            cylinder(d = diameter - 2 * safe_bevel, h = 0.05);
    }
}

module xz_pill(point, size, thickness) {
    translate([point.x, point.y, point.z])
        rotate([90, 0, 0])
            linear_extrude(height = thickness, center = true)
                pill_2d(size.x, size.y);
}

module xz_rounded_rect(point, size, thickness, radius) {
    translate([point.x, point.y, point.z])
        rotate([90, 0, 0])
            linear_extrude(height = thickness, center = true)
                rounded_rect_2d(size, radius);
}

module label_text_2d(message, size, halign, valign, font,
                     ink_spread = 0) {
    if (ink_spread > 0)
        offset(r = ink_spread)
            text(message, size = size, halign = halign,
                 valign = valign, font = font);
    else
        text(message, size = size, halign = halign,
             valign = valign, font = font);
}

module edge_label(point, message, size, side,
                  height = 0.10, colour = legend_color,
                  halign = "center", valign = "center",
                  font = ui_font, yaw = 0, ink_spread = 0) {
    if (SHOW_GLYPHS)
        color(colour)
            translate([point.x, point.y, point.z])
                rotate([0, 0, yaw])
                    rotate([side == "top" ? -90 : 90, 0, 0])
                        linear_extrude(height = height)
                            label_text_2d(message, size, halign, valign,
                                          font, ink_spread);
}

module embossed_label(point, message, size, height = 0.16,
                      halign = "center", valign = "center",
                      colour = legend_color, font = ui_font,
                      ink_spread = 0) {
    if (SHOW_GLYPHS)
        color(colour)
            translate([point.x, point.y, point.z])
                linear_extrude(height = height)
                    label_text_2d(message, size, halign, valign,
                                  font, ink_spread);
}

module triangle_2d(radius) {
    polygon(points = [
        [radius, 0],
        [-radius * 0.55, radius * 0.88],
        [-radius * 0.55, -radius * 0.88]
    ]);
}

module trimui_mark_2d(dot_diameter = 0.95, orbit = 1.05) {
    for (angle = [90, 210, 330])
        translate([orbit * cos(angle), orbit * sin(angle)])
            circle(d = dot_diameter, $fn = 18);
}

// The rear shell rolls away from Z=0, so rear fasteners must be recesses in
// that surface, not dark decals extruded behind it. Their coordinates are
// normalized from the owner's straight-on rear photograph.
function rear_fastener_positions() = [
    [8.0, device_height - 17.0],
    [device_width - 8.0, device_height - 17.0],
    [20.0, 6.3],
    [device_width - 20.0, 6.3]
];

module rear_fastener_recesses() {
    for (point = rear_fastener_positions())
        translate([point.x, point.y, -epsilon])
            cylinder(d = 3.2, h = 0.24, $fn = 28);
}

module speaker_recess_cutouts() {
    // The tapered cut exposes a shell-coloured chamfer around a dark, narrow
    // throat.  Cutting both shell solids below avoids the old raised-dot look.
    for (side = ["left", "right"], point = speaker_positions(side))
        translate([point.x, point.y, front_z - 0.43])
            cylinder(d1 = speaker_throat_diameter,
                     d2 = speaker_opening_diameter,
                     h = 0.50, $fn = 6);
}

// ---- Shell and static visual details ------------------------------------
module shell_volume() {
    // Five measured/observed depth bands: convex rear roll, broad body,
    // port/control band, front bevel, and the recessed face datum.
    difference() {
        union() {
            hull() {
                outline_layer(0.00, 2.2);
                outline_layer(1.20, 0.65);
            }
            hull() {
                outline_layer(1.20, 0.65);
                outline_layer(8.65, 0.00);
            }
            hull() {
                outline_layer(8.65, 0.00);
                outline_layer(10.15, 0.35);
            }
            hull() {
                outline_layer(10.15, 0.35);
                outline_layer(front_z - 0.05, 0.85);
            }
        }
        rear_fastener_recesses();
        speaker_recess_cutouts();
    }
}

module perimeter_seam() {
    color(shell_edge_color)
        translate([0, 0, 8.50])
            linear_extrude(height = 0.22)
                difference() {
                    body_outline_2d(0.04);
                    body_outline_2d(0.48);
                }
}

module front_face() {
    color(shell_front_color)
        difference() {
            translate([0, 0, front_z - 0.18])
                linear_extrude(height = 0.20)
                    body_outline_2d(0.82);
            speaker_recess_cutouts();
        }
}

module active_screen() {
    color(SCREEN_MARKER ? [1.0, 0.0, 1.0, 1.0]
                        : [0.018, 0.028, 0.048, 1.0])
        rounded_panel(screen_centre, screen_active,
                      0.08, 0.75, front_z + 0.47);
}

module screen() {
    // Thin recess/lip, glass, and active panel are distinct.
    color(glass_edge_color)
        rounded_panel(screen_centre, screen_glass + [1.1, 1.1],
                      0.18, 1.5, front_z + 0.01);
    color(glass_color)
        rounded_panel(screen_centre, screen_glass,
                      0.32, 1.15, front_z + 0.18);
    active_screen();
}

module speaker_array(side) {
    // Dark hexagonal floors sit below the tapered openings.  They are kept as
    // separate geometry so the grille remains legible in both preview and
    // the production raster renderer without protruding above the face.
    for (point = speaker_positions(side))
        color([0.018, 0.021, 0.025, 1.0])
            translate([point.x, point.y, front_z - 0.425])
                cylinder(d = speaker_throat_diameter - 0.08,
                         h = 0.035, $fn = 6);
}

module front_legends() {
    // The full lockup lives immediately left of the right speaker.  In the
    // photographs the three-dot mark is part of the wordmark, not a separate
    // centred ornament (which read as three errant speaker holes).
    embossed_label([107.5, 5.42, front_z + 0.03],
                   "TRIMUI", 2.15, 0.06, "left", "center",
                   legend_color, brand_font);
    embossed_label([119.0, 5.42, front_z + 0.03],
                   "SMART PRO", 2.15, 0.06, "left", "center",
                   legend_color, brand_companion_font);
    color(legend_color)
        translate([104.2, 5.42, front_z + 0.03])
            linear_extrude(height = 0.06)
                trimui_mark_2d();

    embossed_label([menu_centre.x, 4.35, front_z + 0.03],
                   "MENU", 1.25, 0.06, "center", "center",
                   silkscreen_color, silkscreen_font, 0.045);
    embossed_label([select_centre.x, 4.35, front_z + 0.03],
                   "SELECT", 1.25, 0.06, "center", "center",
                   silkscreen_color, silkscreen_font, 0.045);
    embossed_label([start_centre.x - 1.00, 4.35, front_z + 0.03],
                   "START", 1.25, 0.06, "center", "center",
                   silkscreen_color, silkscreen_font, 0.045);
}

module top_edge_details() {
    top_y = device_height - 0.15;

    // POWER is a raised, lighter key in a dark shallow bezel.
    color(control_edge_color)
        xz_pill([power_centre_x, top_y, 6.1], [11.0, 4.25], 0.58);
    color([0.255, 0.265, 0.272, 1.0])
        xz_pill([power_centre_x, top_y + 0.12, 6.1], [9.35, 3.25], 0.64);

    // HOST USB-C: visible metal rim, black cavity, and centre tongue.  Each
    // layer is deliberately stepped towards +Y so the top camera cannot hide
    // the tongue behind the recess (the previous solid-black capsule).
    color([0.62, 0.64, 0.65, 1.0])
        xz_pill([host_centre_x, top_y + 0.01, 5.8], [10.4, 4.15], 0.62);
    color(control_edge_color)
        xz_pill([host_centre_x, top_y + 0.10, 5.8], [9.15, 3.10], 0.66);
    color([0.70, 0.71, 0.70, 1.0])
        xz_pill([host_centre_x, top_y + 0.19, 5.8], [6.65, 0.78], 0.70);

    // One continuous two-half volume rocker: pill outside ends and a narrow,
    // straight centre seam, matching the photographed moulded part.
    rocker_centre_x = (volume_minus_centre_x + volume_plus_centre_x) / 2;
    rocker_width = volume_plus_centre_x - volume_minus_centre_x + 11.0;
    color(control_edge_color)
        xz_pill([rocker_centre_x, top_y, 6.1],
                [rocker_width + 1.0, 4.25], 0.58);
    color([0.235, 0.245, 0.252, 1.0])
        xz_pill([rocker_centre_x, top_y + 0.12, 6.1],
                [rocker_width, 3.25], 0.64);
    color(control_edge_color)
        xz_rounded_rect([rocker_centre_x, top_y + 0.22, 6.1],
                        [0.42, 3.10], 0.68, 0.08);

    if (SHOW_MICRO_DETAILS) {
        edge_label([power_centre_x - 11.3, device_height + 0.16, 6.2],
                   "POWER", 1.25, "top", 0.10, silkscreen_color,
                   "center", "center", silkscreen_font, 0, 0.045);
        edge_label([host_centre_x - 9.5, device_height + 0.16, 6.2],
                   "HOST", 1.25, "top", 0.10, silkscreen_color,
                   "center", "center", silkscreen_font, 0, 0.045);
        edge_label([volume_minus_centre_x, device_height + 0.43, 6.15],
                   "-", 1.8, "top", 0.10, control_edge_color);
        edge_label([volume_plus_centre_x, device_height + 0.43, 6.15],
                   "+", 1.8, "top", 0.10, control_edge_color);
    }
}

module bottom_edge_details() {
    bottom_y = 0.20;

    // FN slider track + ribbed thumb.
    color(control_edge_color)
        xz_pill([fn_centre_x, bottom_y, 5.8], [12.0, 4.0], 0.60);
    color([0.17, 0.18, 0.19, 1.0])
        xz_pill([fn_centre_x + 1.3, bottom_y - 0.08, 5.8],
                [6.0, 3.25], 0.68);
    if (SHOW_MICRO_DETAILS)
        for (offset = [-1.8 : 0.9 : 1.8])
            color([0.035, 0.038, 0.042, 1.0])
                xz_rounded_rect([fn_centre_x + 1.3 + offset,
                                 bottom_y - 0.43, 5.8],
                                [0.25, 2.55], 0.10, 0.08);

    // Recessed manufacturer plaque with the two legible identity lines.
    color(control_edge_color)
        xz_rounded_rect([badge_centre_x, bottom_y, 5.8],
                        [23.0, 5.8], 0.54, 1.15);
    color([0.27, 0.29, 0.30, 1.0])
        xz_rounded_rect([badge_centre_x, bottom_y, 5.8],
                        [21.8, 4.7], 0.62, 0.90);

    // DC USB-C, microphone, TF slot, and 3.5 mm audio jack.
    color(control_edge_color)
        xz_pill([dc_centre_x, bottom_y, 5.8], [9.5, 3.7], 0.62);
    color([0.62, 0.64, 0.65, 1.0])
        xz_pill([dc_centre_x, bottom_y - 0.05, 5.8], [6.2, 1.2], 0.68);
    color(control_edge_color)
        xz_pill([mic_centre_x, bottom_y, 5.8], [1.9, 1.9], 0.65);
    color(control_edge_color)
        xz_pill([card_centre_x, bottom_y, 5.8], [15.5, 1.5], 0.64);
    color(control_edge_color)
        xz_pill([audio_centre_x, bottom_y, 5.8], [5.5, 5.5], 0.64);
    color([0.33, 0.35, 0.36, 1.0])
        xz_pill([audio_centre_x, bottom_y - 0.06, 5.8],
                [3.3, 3.3], 0.70);

    if (SHOW_MICRO_DETAILS) {
        edge_label([fn_centre_x - 8.5, -0.16, 6.2],
                   "FN", 1.25, "bottom", 0.10, silkscreen_color,
                   "center", "center", silkscreen_font, 0, 0.045);
        edge_label([badge_centre_x, -0.18, 6.75],
                   "TRIMUI", 1.15, "bottom", 0.10, control_edge_color);
        edge_label([badge_centre_x, -0.18, 4.95],
                   "TG5040", 0.72, "bottom", 0.10, control_edge_color);
        edge_label([dc_centre_x, -0.16, 8.55],
                   "DC", 1.20, "bottom", 0.10, silkscreen_color,
                   "center", "center", silkscreen_font, 0, 0.045);
        edge_label([mic_centre_x, -0.16, 8.55],
                   "MIC", 1.10, "bottom", 0.10, silkscreen_color,
                   "center", "center", silkscreen_font, 0, 0.045);
    }
}

module rear_details() {
    // Four recessed fasteners are unambiguous in FCC rear evidence; the owner
    // black-device photo underexposes the right pair.  The upper pair sits
    // tighter to the shoulder cut-outs than the lower pair sits to the
    // endcap; they are not the corners of one rectangle.
    color([0.015, 0.018, 0.022, 1.0])
        for (point = rear_fastener_positions())
            translate([point.x, point.y, 0.15])
                cylinder(d = 2.85, h = 0.04, $fn = 28);

    if (SHOW_MICRO_DETAILS) {
        // Back-face text uses a Y half-turn.  It reverses the extrusion normal
        // without turning the line upside down in the fixed rear camera.  That
        // camera mirrors model X, so the source X placements below look
        // reversed while the rendered evidence matches the printed device.
        color(legend_color)
            translate([device_centre.x + 31, 19.0, -0.03])
                rotate([0, 180, 0])
                    linear_extrude(height = 0.10) {
                        translate([-17.0, 0])
                            text("TRIMUI", size = 3.0,
                                 halign = "left", valign = "center",
                                 font = brand_font);
                        translate([-1.2, 0])
                            text("SMART PRO", size = 3.0,
                                 halign = "left", valign = "center",
                                 font = brand_companion_font);
                        translate([-21.0, 0])
                            trimui_mark_2d(1.10, 1.20);
                    }
        color(legend_color)
            translate([device_centre.x - 2, 19.0, -0.03])
                rotate([0, 180, 0])
                    linear_extrude(height = 0.10)
                        text("CE  FCC", size = 2.1,
                             halign = "center", valign = "center",
                             font = "Liberation Sans:style=Bold");
        color(legend_color)
            translate([device_centre.x - 46, 19.7, -0.03])
                rotate([0, 180, 0])
                    linear_extrude(height = 0.10)
                        text("MODEL: TG5040", size = 1.35,
                             halign = "center", valign = "center",
                             font = "Liberation Sans:style=Bold");
        color(legend_color)
            translate([device_centre.x - 46, 16.8, -0.03])
                rotate([0, 180, 0])
                    linear_extrude(height = 0.10)
                        text("TRIMUI SMART PRO", size = 1.15,
                             halign = "center", valign = "center",
                             font = "Liberation Sans:style=Bold");
    }
}

module static_shell() {
    color(shell_rear_color) shell_volume();
    perimeter_seam();
    front_face();
    screen();
    speaker_array("left");
    speaker_array("right");
    front_legends();
    top_edge_details();
    bottom_edge_details();
    rear_details();
}

// ---- Semantic interactive controls --------------------------------------
module face_button(id, point, glyph) {
    color(active_color(id))
        translate([point.x, point.y, front_z + 0.20])
            bevel_cylinder(face_button_diameter, 1.55, 0.50);
    // Keep the glyph above the 1.75 mm button crown.  A prior 0.03 mm
    // intersection caused OpenCSG z-fighting and one-run raster drift.
    embossed_label([point.x, point.y, front_z + 1.78],
                   glyph, 3.25, 0.16, "center", "center",
                   active_dark_color(id));
}

module system_button(id, point, symbol) {
    // The physical keys have a narrow dark outer ring and a smaller convex
    // crown.  Keeping both pieces semantic lets the complete control light.
    color(active_dark_color(id))
        translate([point.x, point.y, front_z + 0.15])
            bevel_cylinder(system_button_recess_diameter, 0.72, 0.22);
    color(active_color(id))
        translate([point.x, point.y, front_z + 0.45])
            bevel_cylinder(system_button_diameter, 0.76, 0.24);

    color(active_dark_color(id))
        // The button crown ends at front_z + 1.21; leave a real air gap so
        // off-screen OpenCSG renders cannot race two coincident fragments.
        translate([point.x, point.y, front_z + 1.24])
            linear_extrude(height = 0.13) {
                if (symbol == "menu") {
                    for (angle = [90, 210, 330])
                        translate([1.25 * cos(angle), 1.25 * sin(angle)])
                            circle(d = 1.15, $fn = 18);
                } else if (symbol == "select") {
                    pill_2d(2.75, 0.82);
                } else {
                    triangle_2d(1.50);
                }
            }
}

module dpad_control() {
    id = "dpad";
    color(active_color(id))
        translate([dpad_centre.x, dpad_centre.y, front_z + 0.18])
            linear_extrude(height = 1.48)
                offset(r = 0.85)
                    offset(delta = -0.85)
                        union() {
                            square([dpad_size, dpad_arm], center = true);
                            square([dpad_arm, dpad_size], center = true);
                        }

    // Distinct centre medallion and three raised direction nubs.
    color(active_dark_color(id))
        translate([dpad_centre.x, dpad_centre.y, front_z + 1.62])
            cylinder(d = 6.6, h = 0.22, $fn = 32);
    color(is_active(id) ? highlight_color : [0.20, 0.21, 0.22, 1.0])
        for (angle = [90, 210, 330])
            translate([dpad_centre.x + 1.45 * cos(angle),
                       dpad_centre.y + 1.45 * sin(angle),
                       front_z + 1.80])
                cylinder(d = 1.15, h = 0.24, $fn = 16);
}

module stick_control(id, point) {
    color(is_active(id) ? highlight_color : ring_color)
        translate([point.x, point.y, front_z + 0.10])
            cylinder(d = stick_ring_diameter, h = 0.48);
    color(active_dark_color(id))
        translate([point.x, point.y, front_z + 0.53])
            cylinder(d = stick_recess_diameter, h = 0.67);
    color(active_color(id))
        translate([point.x, point.y, front_z + 1.15])
            hull() {
                cylinder(d = 9.7, h = 0.10);
                translate([0, 0, 2.20])
                    cylinder(d = stick_cap_diameter, h = 0.10);
                translate([0, 0, 3.25])
                    cylinder(d = stick_cap_diameter - 1.1, h = 0.12);
            }
    color(active_dark_color(id))
        translate([point.x, point.y, front_z + 4.47])
            cylinder(d = stick_cap_diameter - 2.0, h = 0.19);
}

module shoulder_tube(points, z, height) {
    union()
        for (index = [0 : len(points) - 2])
            hull() {
                translate([points[index].x, points[index].y, z])
                    cylinder(r = points[index].z, h = height);
                translate([points[index + 1].x, points[index + 1].y, z])
                    cylinder(r = points[index + 1].z, h = height);
            }
}

module shoulder_shape(side, kind) {
    is_left = side == "left";
    mirror_x = is_left ? 1 : -1;
    anchor_x = is_left ? 0 : device_width;
    if (kind == "bumper") {
        // L/R: front/edge bumper following and overlapping the real endcap.
        // Every control-section centre sits on the shell ellipse, so the
        // paddle is visibly joined along its full inner edge instead of being
        // suspended from a single peg like the first-pass "dog ear".
        shoulder_tube([
            [anchor_x + mirror_x * 6.0,  device_height - 13.8, 0.90],
            [anchor_x + mirror_x * 10.5, device_height - 7.7,  1.00],
            [anchor_x + mirror_x * 16.8, device_height - 3.25, 0.94],
            [anchor_x + mirror_x * 23.8, device_height - 0.95, 0.82],
            [anchor_x + mirror_x * 28.6, device_height - 0.18, 0.62]
        ], front_z - 1.65, 2.45);
    } else {
        // L2/R2: broader rear paddle on the same shell-connected arc, ending
        // inboard at the straight top tangent just like the photographed cap.
        shoulder_tube([
            [anchor_x + mirror_x * 5.1,  device_height - 14.5, 1.02],
            [anchor_x + mirror_x * 9.6,  device_height - 8.8,  1.18],
            [anchor_x + mirror_x * 15.8, device_height - 3.9,  1.12],
            [anchor_x + mirror_x * 23.0, device_height - 1.15, 0.94],
            [anchor_x + mirror_x * 28.4, device_height - 0.20, 0.66]
        ], 2.65, 5.95);
    }
}

module shoulder_control(side, kind) {
    id = kind == "bumper"
        ? side_id(side, "btn_l1", "btn_r1")
        : side_id(side, "trig_l", "trig_r");
    label = kind == "bumper"
        ? (side == "left" ? "L" : "R")
        : (side == "left" ? "L2" : "R2");

    color(active_color(id)) shoulder_shape(side, kind);

    // The moulded legends are on the top/outer faces seen from the edge, not
    // on the narrow screen-facing strips. Follow the local endcap tangent so
    // the text stays seated on the curved paddle instead of floating nearby.
    label_x = side == "left"
        ? (kind == "bumper" ? 10.0 : 9.0)
        : device_width - (kind == "bumper" ? 10.0 : 9.0);
    label_y = kind == "bumper" ? device_height - 6.85
                               : device_height - 7.80;
    label_z = kind == "bumper" ? front_z - 0.43 : 5.63;
    label_yaw = side == "left" ? 31 : -31;
    edge_label([label_x, label_y, label_z],
               label, kind == "bumper" ? 2.5 : 2.2, "top",
               0.13, active_dark_color(id), "center", "center",
               ui_font, label_yaw);
}

module named_control(id) {
    if (id == "dpad") {
        dpad_control();
    } else if (id == "stick_l") {
        stick_control(id, stick_left_centre);
    } else if (id == "stick_r") {
        stick_control(id, stick_right_centre);
    } else if (id == "btn_north") {
        face_button(id, face_centre + [0, face_pitch.y], "X");
    } else if (id == "btn_east") {
        face_button(id, face_centre + [face_pitch.x, 0], "A");
    } else if (id == "btn_south") {
        face_button(id, face_centre - [0, face_pitch.y], "B");
    } else if (id == "btn_west") {
        face_button(id, face_centre - [face_pitch.x, 0], "Y");
    } else if (id == "btn_select") {
        system_button(id, select_centre, "select");
    } else if (id == "btn_guide") {
        system_button(id, menu_centre, "menu");
    } else if (id == "btn_start") {
        system_button(id, start_centre, "start");
    } else if (id == "btn_l1") {
        shoulder_control("left", "bumper");
    } else if (id == "btn_r1") {
        shoulder_control("right", "bumper");
    } else if (id == "trig_l") {
        shoulder_control("left", "trigger");
    } else if (id == "trig_r") {
        shoulder_control("right", "trigger");
    }
}

module semantic_controls() {
    for (id = CONTROL_IDS)
        named_control(id);
}

// ---- Dispatch -------------------------------------------------------------
if (PART == "assembly") {
    static_shell();
    semantic_controls();
} else if (PART == "shell") {
    static_shell();
} else if (PART == "controls") {
    semantic_controls();
} else if (PART == "control") {
    named_control(CONTROL_ID);
} else if (PART == "screen") {
    active_screen();
} else {
    assert(false, str("Unknown PART: ", PART));
}
