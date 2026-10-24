/*
 * PocketForge semantic visual model — PowKiddy X55
 *
 * Coordinates are physical millimetres:
 *   X left-to-right, Y bottom-to-top, Z rear-to-front.
 *
 * The owner-traced primary face shell is 210.0 x 88.76 mm.  PowKiddy's
 * published 212.5 x 94.5 x 19.0 mm envelope includes the raised shoulder
 * region and the maximum rear grip crown; it is not modelled as a uniform
 * 19 mm slab.
 *
 * This is a nominal visual/UI model, not a manufacturing-tolerance drawing.
 */

PART = "assembly";
CONTROL_ID = "btn_east";
HIGHLIGHT = "";
SHOW_GLYPHS = true;
SHOW_MICRO_DETAILS = true;
SCREEN_MARKER = false;
QUALITY = "render";
COLORWAY = "black";

$fn = QUALITY == "render" ? 64 : 28;
epsilon = 0.04;

// ---- Evidence-backed envelope -------------------------------------------
published_size = [212.5, 94.5, 19.0];
body_size = [210.0, 88.76];
body_origin = [(published_size.x - body_size.x) / 2, 0];
body_centre = [published_size.x / 2, body_size.y / 2];
front_z = published_size.z;
centre_rear_z = 4.70;       // 14.30 mm centre-back depth, photo-derived
core_rear_z = 6.00;         // 13.00 mm shallow core, photo-derived
grip_rear_z = 0.00;         // published 19 mm maximum at palm lobes

screen_diagonal = 139.7;    // 5.5 in
active_screen_size = [
    screen_diagonal * 16 / sqrt(16 * 16 + 9 * 9),
    screen_diagonal * 9 / sqrt(16 * 16 + 9 * 9)
];
screen_centre = [106.25, 47.80];
glass_size = [133.0, 78.5];
glass_centre = screen_centre;

// Front positions registered to PowKiddy's orthographic product elevation.
stick_l_centre = [23.0, 67.0];
dpad_centre = [23.0, 40.0];
face_centre = [188.0, 66.0];
stick_r_centre = [188.0, 39.0];
face_pitch = 8.90;
select_centre = [20.2, 15.8];
volume_up_centre = [32.6, 15.8];
volume_down_centre = [179.9, 15.8];
start_centre = [191.5, 15.8];

dpad_size = 24.0;
dpad_arm = 9.0;
stick_well_diameter = 22.4;
stick_ring_diameter = 20.0;
stick_cap_diameter = 13.2;
face_button_diameter = 7.7;
system_button_diameter = 7.0;

// Top edge positions reconcile the owner cradle annotations with public
// perpendicular top-edge photographs.
power_centre_x = 42.38;
audio_centre_x = 67.14;
charge_centre_x = 94.0;
hdmi_centre_x = 120.0;
host_centre_x = 147.4;
reset_centre_x = 168.77;
top_control_z = 12.2;

CONTROL_IDS = [
    "dpad",
    "stick_l",
    "stick_r",
    "btn_north",
    "btn_east",
    "btn_south",
    "btn_west",
    "btn_select",
    "vol_up",
    "vol_down",
    "btn_start",
    "btn_l1",
    "trig_l",
    "trig_r",
    "btn_r1",
    "btn_power",
    "btn_reset"
];

function contains(values, value) =
    len([for (candidate = values) if (candidate == value) candidate]) > 0;
function is_active(id) = HIGHLIGHT == "*" || HIGHLIGHT == id;
function mirror_x(x) = published_size.x - x;

// ---- Materials -----------------------------------------------------------
black_shell = [0.180, 0.185, 0.195, 1.0];
black_face = [0.200, 0.205, 0.215, 1.0];
blue_shell = [0.015, 0.285, 0.485, 1.0];
blue_face = [0.020, 0.325, 0.535, 1.0];
shell_color = COLORWAY == "blue" ? blue_shell : black_shell;
face_color = COLORWAY == "blue" ? blue_face : black_face;
shell_edge_color = COLORWAY == "blue"
    ? [0.008, 0.120, 0.220, 1.0]
    : [0.020, 0.022, 0.025, 1.0];
seam_color = COLORWAY == "blue"
    ? [0.010, 0.085, 0.145, 1.0]
    : [0.012, 0.013, 0.015, 1.0];
glass_color = [0.006, 0.008, 0.011, 1.0];
glass_edge_color = [0.15, 0.16, 0.17, 1.0];
screen_color = [0.010, 0.014, 0.019, 1.0];
screen_marker_color = [1.0, 0.0, 0.86, 1.0];
control_color = [0.045, 0.047, 0.050, 1.0];
control_top_color = [0.080, 0.082, 0.086, 1.0];
top_key_face_color = COLORWAY == "blue"
    ? [0.018, 0.245, 0.400, 1.0]
    : control_top_color;
control_edge_color = [0.014, 0.015, 0.017, 1.0];
metal_color = [0.50, 0.52, 0.54, 1.0];
silver_ring_color = [0.25, 0.27, 0.29, 1.0];
legend_color = COLORWAY == "blue"
    ? [0.030, 0.085, 0.120, 1.0]
    : [0.40, 0.42, 0.44, 1.0];
shoulder_legend_color = [0.17, 0.18, 0.19, 1.0];
rear_print_color = COLORWAY == "blue"
    ? [0.90, 0.94, 0.97, 1.0]
    : [0.78, 0.80, 0.82, 1.0];
highlight_color = [1.0, 0.10, 0.46, 1.0];
highlight_dark_color = [0.43, 0.00, 0.12, 1.0];

function active_color(id, neutral = control_top_color) =
    is_active(id) ? highlight_color : neutral;
function active_dark_color(id, neutral = control_edge_color) =
    is_active(id) ? highlight_dark_color : neutral;

assert(abs(body_size.x - 210.0) < 0.001 &&
       abs(body_size.y - 88.76) < 0.001,
       "Owner-traced X55 primary face envelope changed");
assert(abs(published_size.x - 212.5) < 0.001 &&
       abs(published_size.y - 94.5) < 0.001 &&
       abs(published_size.z - 19.0) < 0.001,
       "PowKiddy published maximum envelope changed");
assert(abs(sqrt(active_screen_size.x * active_screen_size.x +
                active_screen_size.y * active_screen_size.y) -
           screen_diagonal) < 0.001,
       "Active display lost its published 5.5-inch diagonal");
assert(PART != "control" || contains(CONTROL_IDS, CONTROL_ID),
       str("Unknown CONTROL_ID: ", CONTROL_ID));
assert(HIGHLIGHT == "" || HIGHLIGHT == "*" ||
       contains(CONTROL_IDS, HIGHLIGHT),
       str("Unknown HIGHLIGHT id: ", HIGHLIGHT));

// ---- General geometry helpers -------------------------------------------
module rounded_rect_2d(size, radius, centre = true) {
    translated = centre ? -size / 2 : [0, 0];
    translate(translated)
        offset(r = radius)
            square([
                max(epsilon, size.x - 2 * radius),
                max(epsilon, size.y - 2 * radius)
            ]);
}

module trapezoid_2d(size, taper) {
    polygon([
        [-size.x / 2, -size.y / 2],
        [size.x / 2, -size.y / 2],
        [size.x / 2 - taper, size.y / 2],
        [-size.x / 2 + taper, size.y / 2]
    ]);
}

module line_segment_2d(first, second, width) {
    hull() {
        translate(first)
            circle(d = width);
        translate(second)
            circle(d = width);
    }
}

module triangle_2d(radius) {
    polygon([
        [0, radius],
        [-0.866 * radius, -0.5 * radius],
        [0.866 * radius, -0.5 * radius]
    ]);
}

module rounded_panel(point, size, height, radius, z) {
    translate([point.x, point.y, z])
        linear_extrude(height = height)
            rounded_rect_2d(size, radius);
}

module bevel_cylinder(diameter, height, bevel = 0.35) {
    union() {
        cylinder(h = bevel, d1 = diameter - 2 * bevel, d2 = diameter);
        translate([0, 0, bevel])
            cylinder(h = max(epsilon, height - 2 * bevel), d = diameter);
        translate([0, 0, max(bevel, height - bevel)])
            cylinder(h = bevel, d1 = diameter, d2 = diameter - 2 * bevel);
    }
}

module rounded_point_hull(points, radius) {
    hull()
        for (point = points)
            translate(point)
                sphere(
                    r = radius,
                    $fn = QUALITY == "render" ? 20 : 12
                );
}

module rounded_path_3d(points, radius) {
    for (index = [0 : len(points) - 2])
        hull() {
            translate(points[index])
                sphere(r = radius);
            translate(points[index + 1])
                sphere(r = radius);
        }
}

module xz_rounded_rect(point, size, thickness, radius) {
    translate([point.x - size.x / 2, point.y, point.z - size.y / 2])
        rotate([90, 0, 0])
            linear_extrude(height = thickness)
                rounded_rect_2d(size, radius, false);
}

module xz_circle(point, diameter, thickness) {
    translate(point)
        rotate([90, 0, 0])
            cylinder(h = thickness, d = diameter);
}

module xz_trapezoid(point, size, thickness, taper) {
    translate(point)
        rotate([90, 0, 0])
            linear_extrude(height = thickness)
                trapezoid_2d(size, taper);
}

module xz_trapezoid_ring(point, size, thickness, taper, stroke) {
    translate(point)
        rotate([90, 0, 0])
            linear_extrude(height = thickness)
                difference() {
                    trapezoid_2d(size, taper);
                    offset(delta = -stroke)
                        trapezoid_2d(size, taper);
                }
}

module front_text(point, message, size, height = 0.06,
                  font = "Liberation Sans:style=Regular",
                  halign = "center") {
    translate([point.x, point.y, point.z])
        linear_extrude(height = height)
            text(message, size = size, font = font,
                 halign = halign, valign = "center");
}

module rear_text(point, message, size, height = 0.06,
                 font = "Liberation Sans:style=Regular",
                 halign = "center") {
    translate(point)
        rotate([0, 180, 0])
            linear_extrude(height = height)
                text(message, size = size, font = font,
                     halign = halign, valign = "center");
}

module top_text(point, message, size, height = 0.06,
                font = "Liberation Sans:style=Regular") {
    translate(point)
        rotate([-90, 0, 0])
            linear_extrude(height = height)
                text(message, size = size, font = font,
                     halign = "center", valign = "center");
}

module sloped_top_text(point, message, size, slope,
                       height = 0.06,
                       font = "Liberation Sans:style=Regular") {
    translate(point)
        rotate([0, 0, slope])
            rotate([-90, 0, 0])
                linear_extrude(height = height)
                    text(message, size = size, font = font,
                         halign = "center", valign = "center");
}

module bottom_text(point, message, size, height = 0.06,
                   font = "Liberation Sans:style=Regular") {
    translate(point)
        rotate([90, 0, 0])
            linear_extrude(height = height)
                text(message, size = size, font = font,
                     halign = "center", valign = "center");
}

module recycle_mark_2d(size = 4.0) {
    stroke = size * 0.12;
    union() {
        line_segment_2d(
            [-0.29 * size, -0.27 * size],
            [0.27 * size, -0.27 * size],
            stroke
        );
        translate([0.31 * size, -0.27 * size])
            rotate([0, 0, -90])
                triangle_2d(size * 0.16);

        line_segment_2d(
            [0.30 * size, -0.16 * size],
            [0.01 * size, 0.36 * size],
            stroke
        );
        translate([-0.01 * size, 0.40 * size])
            rotate([0, 0, 30])
                triangle_2d(size * 0.16);

        line_segment_2d(
            [-0.09 * size, 0.36 * size],
            [-0.38 * size, -0.16 * size],
            stroke
        );
        translate([-0.40 * size, -0.20 * size])
            rotate([0, 0, 150])
                triangle_2d(size * 0.16);
    }
}

module circular_arrow_mark_2d(size = 4.0) {
    stroke = size * 0.12;
    difference() {
        difference() {
            circle(d = size);
            circle(d = size - 2 * stroke);
        }
        translate([size * 0.34, size * 0.31])
            square([size * 0.42, size * 0.42], center = true);
    }
    translate([size * 0.32, size * 0.30])
        rotate([0, 0, -42])
            triangle_2d(size * 0.17);
}

module under_three_mark_2d(size = 4.0) {
    stroke = size * 0.10;
    difference() {
        circle(d = size);
        circle(d = size - 2 * stroke);
    }
    text("0-3", size = size * 0.30,
         font = "Liberation Sans:style=Bold",
         halign = "center", valign = "center");
    rotate([0, 0, 48])
        square([stroke, size * 1.12], center = true);
}

module crossed_bin_mark_2d(size = 4.0) {
    stroke = size * 0.10;
    difference() {
        union() {
            translate([0, -size * 0.03])
                square([size * 0.46, size * 0.58], center = true);
            translate([0, size * 0.34])
                square([size * 0.62, stroke], center = true);
            translate([0, size * 0.42])
                square([size * 0.28, stroke], center = true);
        }
        translate([0, -size * 0.03])
            square([
                size * 0.46 - 2 * stroke,
                size * 0.58 - 2 * stroke
            ], center = true);
    }
    translate([-size * 0.16, -size * 0.39])
        circle(d = stroke * 1.4);
    translate([size * 0.16, -size * 0.39])
        circle(d = stroke * 1.4);
    rotate([0, 0, 48])
        square([stroke, size * 1.18], center = true);
}

// ---- Rounded/waisted primary shell --------------------------------------
function left_outline_points() = [
    [published_size.x / 2, 88.76],
    [76.0, 88.76],
    [50.0, 88.72],
    [37.0, 88.48],
    [29.0, 87.60],
    [22.0, 85.10],
    [16.0, 81.25],
    [11.0, 76.10],
    [7.2, 69.80],
    [4.5, 62.00],
    [2.8, 53.30],
    [1.55, 44.00],
    [1.25, 36.00],
    [1.70, 29.00],
    [3.60, 22.00],
    [6.80, 15.70],
    [11.30, 10.00],
    [16.80, 5.70],
    [23.30, 2.75],
    [31.0, 1.10],
    [42.0, 0.62],
    [62.0, 0.88],
    [83.0, 1.18],
    [published_size.x / 2, 1.40]
];

function right_outline_points() = [
    for (index = [len(left_outline_points()) - 2 : -1 : 1])
        [mirror_x(left_outline_points()[index].x),
         left_outline_points()[index].y]
];

function body_outline_points() =
    concat(left_outline_points(), right_outline_points());

function mix_point(first, second, amount) = [
    first.x + (second.x - first.x) * amount,
    first.y + (second.y - first.y) * amount
];

function chaikin_once(points) = [
    for (index = [0 : len(points) - 1], amount = [0.25, 0.75])
        mix_point(
            points[index],
            points[(index + 1) % len(points)],
            amount
        )
];

function smooth_closed_path(points, passes) =
    passes <= 0
        ? points
        : smooth_closed_path(chaikin_once(points), passes - 1);

module body_outline_2d(inset = 0) {
    smoothed = smooth_closed_path(body_outline_points(), 2);
    if (inset == 0)
        polygon(smoothed);
    else
        offset(delta = -inset)
            polygon(smoothed);
}

module scaled_outline_segment(z0, z1, scale0, scale1) {
    translate([body_centre.x, body_centre.y, z0])
        linear_extrude(
            height = z1 - z0,
            scale = scale1 / scale0
        )
            scale([scale0, scale0])
                translate([-body_centre.x, -body_centre.y])
                    body_outline_2d();
}

module core_shell_volume() {
    union() {
        scaled_outline_segment(centre_rear_z, 7.15, 0.962, 0.985);
        scaled_outline_segment(7.05, 17.80, 0.985, 1.000);
        scaled_outline_segment(17.70, front_z, 1.000, 0.994);
    }
}

function smoothstep(value) =
    value * value * (3 - 2 * value);

module rear_grip_lobe(point, radii) {
    radial_steps = QUALITY == "render" ? 36 : 22;
    profile = concat(
        [[0, grip_rear_z]],
        [
            for (step = [1 : radial_steps])
                let(radius = step / radial_steps)
                    [
                        radius,
                        grip_rear_z
                            + (centre_rear_z - grip_rear_z)
                                * smoothstep(radius)
                    ]
        ],
        [[1, core_rear_z], [0, core_rear_z]]
    );

    translate([point.x, point.y, 0])
        scale([radii.x, radii.y, 1])
            rotate_extrude(convexity = 8)
                polygon(profile);
}

module grip_bulge(side) {
    grip_x = side == "left" ? 25.0 : mirror_x(25.0);
    intersection() {
        // The production back has no separate grip pad or join line.  This
        // smoothstep surface is flat at both the palm crown and its outer
        // blend radius, so it joins the shallow centre back without the
        // hard oval boundary created by intersecting ellipsoids.
        rear_grip_lobe([grip_x, 38.0], [40.0, 55.0]);
        translate([0, 0, -epsilon])
            linear_extrude(height = core_rear_z + 2 * epsilon)
                body_outline_2d(0.45);
    }
}

module shell_volume() {
    union() {
        core_shell_volume();
        grip_bulge("left");
        grip_bulge("right");
    }
}

module front_face() {
    color(face_color)
        translate([0, 0, front_z - 0.30])
            linear_extrude(height = 0.31)
                body_outline_2d(0.48);
}

module front_perimeter_seam() {
    color(seam_color)
        translate([0, 0, front_z + 0.012])
            linear_extrude(height = 0.055)
                difference() {
                    body_outline_2d(0.55);
                    body_outline_2d(0.90);
                }
}

// ---- Display and non-interactive front detail ----------------------------
module active_screen() {
    color(SCREEN_MARKER ? screen_marker_color : screen_color)
        rounded_panel(
            screen_centre,
            active_screen_size,
            0.10,
            1.25,
            front_z + 0.43
        );
}

module screen() {
    color(glass_edge_color)
        rounded_panel(
            glass_centre,
            glass_size + [1.0, 1.0],
            0.24,
            3.05,
            front_z + 0.08
        );
    color(glass_color)
        rounded_panel(
            glass_centre,
            glass_size,
            0.22,
            2.75,
            front_z + 0.27
        );
    active_screen();
}

module front_static_details() {
    // Small status/charge pinhole above the right control field.
    color([0.005, 0.006, 0.007, 1.0])
        translate([176.3, 77.5, front_z + 0.055])
            cylinder(h = 0.22, d = 0.85);

    color(legend_color) {
        front_text([select_centre.x, 8.7, front_z + 0.08],
                   "SELECT", 1.85);
        front_text([volume_up_centre.x, 8.7, front_z + 0.08],
                   "VOL+", 1.85);
        front_text([volume_down_centre.x, 8.7, front_z + 0.08],
                   "VOL-", 1.85);
        front_text([start_centre.x, 8.7, front_z + 0.08],
                   "START", 1.85);
    }
}

// ---- Top/bottom interfaces ----------------------------------------------
module port_opening(point, size, radius = 0.8, metal = false) {
    color(control_edge_color)
        xz_rounded_rect(point, size + [0.8, 0.65], 0.28, radius + 0.25);
    if (metal)
        color(metal_color)
            xz_rounded_rect(
                [point.x, point.y - 0.025, point.z],
                size,
                0.30,
                radius
            );
    color([0.004, 0.005, 0.006, 1.0])
        xz_rounded_rect(
            [point.x, point.y - 0.055, point.z],
            size - [0.55, 0.55],
            0.31,
            max(0.20, radius - 0.20)
        );
}

module top_edge_static() {
    top_y = 88.92;

    // The connector field is only a fine moulded trapezoidal seam.  The
    // shell colour remains visible inside it, matching the production case.
    color(shell_edge_color)
        xz_trapezoid_ring([107.0, top_y + 0.01, 11.7],
                          [94.0, 8.7], 0.12, 5.0, 0.34);

    port_opening([host_centre_x, top_y + 0.03, 11.6],
                 [9.0, 3.45], 1.35, true);
    port_opening([hdmi_centre_x, top_y + 0.03, 11.5],
                 [10.2, 3.15], 0.65, true);
    port_opening([charge_centre_x, top_y + 0.03, 11.6],
                 [9.0, 3.45], 1.35, true);

    color(control_edge_color)
        xz_circle([audio_centre_x, top_y + 0.04, 11.7], 5.45, 0.30);
    color([0.003, 0.004, 0.005, 1.0])
        xz_circle([audio_centre_x, top_y - 0.01, 11.7], 4.25, 0.31);

    color(legend_color) {
        top_text([host_centre_x, top_y + 0.08, 16.25],
                 "HOST", 1.65);
        top_text([hdmi_centre_x, top_y + 0.08, 16.25],
                 "HD", 1.65);
        top_text([charge_centre_x, top_y + 0.08, 16.25],
                 "DC/OTG", 1.45);
        top_text([audio_centre_x, top_y + 0.08, 16.25],
                 "AUDIO", 1.40);
    }
}

function speaker_hole_positions(side) = [
    for (row = [0 : 4], column = [0 : 12])
        [
            (side == "left" ? 24.0 : mirror_x(24.0))
                + (column - 6) * 1.30
                + (row % 2 == 0 ? -0.31 : 0.31),
            8.05 + row * 1.08
    ]
];

function bottom_surface_y(x) =
    max(1.25, 10.20 - 0.29 * min(x, mirror_x(x)));

module bottom_speaker(side) {
    color([0.006, 0.007, 0.008, 1.0])
        for (point = speaker_hole_positions(side))
            xz_circle(
                [point.x, bottom_surface_y(point.x) + 0.12, point.y],
                0.62,
                0.22
            );
}

function left_speaker_panel_points() = [
    [10.0, 11.35, 15.35],
    [38.0, 1.20, 15.35],
    [43.2, 1.05, 13.35],
    [38.3, 1.15, 8.00],
    [19.0, 4.85, 6.95],
    [10.0, 11.35, 8.65],
    [10.0, 11.35, 15.35]
];

function speaker_panel_points(side) =
    side == "left"
        ? left_speaker_panel_points()
        : [
            for (point = left_speaker_panel_points())
                [mirror_x(point.x), point.y, point.z]
        ];

module bottom_speaker_panel(side) {
    color(seam_color)
        rounded_path_3d(speaker_panel_points(side), 0.15);
}

module bottom_edge_static() {
    bottom_speaker_panel("left");
    bottom_speaker_panel("right");
    bottom_speaker("left");
    bottom_speaker("right");

    color(shell_edge_color)
        xz_trapezoid_ring([106.25, 1.48, 10.55],
                          [102.0, 8.0], 0.26, 5.0, 0.34);

    port_opening([89.0, 1.55, 10.4], [13.5, 2.20], 0.35, false);
    port_opening([126.5, 1.55, 10.4], [13.5, 2.20], 0.35, false);

    color(legend_color) {
        bottom_text([78.5, 1.20, 10.4], "TF1", 1.90);
        bottom_text([137.0, 1.20, 10.4], "TF2", 1.90);
    }
}

// ---- Rear shell detail ---------------------------------------------------
rear_screws = [
    [18.0, 69.0],
    [61.0, 82.0],
    [151.5, 82.0],
    [194.5, 69.0],
    [12.0, 25.5],
    [59.0, 7.8],
    [153.5, 7.8],
    [200.5, 25.5]
];

function grip_radius_at(x, y, centre_x) =
    sqrt(
        pow((x - centre_x) / 40.0, 2)
        + pow((y - 38.0) / 55.0, 2)
    );

function grip_surface_z_at(x, y, centre_x) =
    let(radius = grip_radius_at(x, y, centre_x))
        radius < 1
            ? grip_rear_z
                + (centre_rear_z - grip_rear_z)
                    * smoothstep(radius)
            : centre_rear_z;

function rear_surface_z_at(x, y) =
    min(
        centre_rear_z,
        grip_surface_z_at(x, y, 25.0),
        grip_surface_z_at(x, y, mirror_x(25.0))
    );

module rear_screw(point) {
    z = rear_surface_z_at(point.x, point.y) + 0.10;
    color(control_edge_color)
        translate([point.x, point.y, z - 0.10])
            rotate([180, 0, 0])
                cylinder(h = 0.17, d1 = 2.05, d2 = 1.60);
    if (SHOW_MICRO_DETAILS)
        color([0.16, 0.17, 0.18, 1.0])
            translate([point.x, point.y, z - 0.205])
                rotate([0, 0, 28])
                    linear_extrude(height = 0.035)
                        square([1.05, 0.22], center = true);
}

module rear_regulatory_marks() {
    z = centre_rear_z - 0.145;
    color(rear_print_color) {
        rear_text([106.25, 49.5, z], "PowKiddy", 4.8, 0.055,
                  "Liberation Sans:style=Bold");
        rear_text([106.25, 44.7, z], "MODE:X55", 2.05);
        rear_text([110.0, 38.7, z],
                  "BATTERY:Li-Po 4000 mAh", 1.25, 0.055,
                  "Liberation Sans:style=Regular", "right");
        rear_text([110.0, 36.5, z],
                  "ADAPTER INPUT: 5V=1.5A", 1.25, 0.055,
                  "Liberation Sans:style=Regular", "right");
        rear_text([110.0, 34.3, z],
                  "MADE IN CHINA", 1.25, 0.055,
                  "Liberation Sans:style=Regular", "right");
        rear_text([98.0, 36.5, z], "CE", 3.65, 0.055,
                  "Liberation Sans:style=Bold");
        translate([88.0, 36.5, z])
            rotate([0, 180, 0])
                linear_extrude(height = 0.055)
                    circular_arrow_mark_2d(3.75);
        translate([79.0, 36.5, z])
            rotate([0, 180, 0])
                linear_extrude(height = 0.055)
                    recycle_mark_2d(3.15);
        translate([70.0, 36.5, z])
            rotate([0, 180, 0])
                linear_extrude(height = 0.055)
                    under_three_mark_2d(3.55);
        translate([61.8, 36.5, z])
            rotate([0, 180, 0])
                linear_extrude(height = 0.055)
                    crossed_bin_mark_2d(3.65);
    }
}

module rear_details() {
    for (point = rear_screws)
        rear_screw(point);
    rear_regulatory_marks();
}

// ---- Semantic front controls --------------------------------------------
module dpad_cross_2d(inset = 0) {
    offset(r = 0.80)
        offset(delta = -0.80)
            union() {
                square([dpad_arm - 2 * inset,
                        dpad_size - 2 * inset], center = true);
                square([dpad_size - 2 * inset,
                        dpad_arm - 2 * inset], center = true);
            }
}

module dpad_control() {
    id = "dpad";
    color(active_dark_color(id))
        translate([dpad_centre.x, dpad_centre.y, front_z + 0.18])
            linear_extrude(height = 1.55)
                dpad_cross_2d();
    color(active_color(id, control_top_color))
        translate([dpad_centre.x, dpad_centre.y, front_z + 1.05])
            linear_extrude(height = 1.18, scale = 0.965)
                dpad_cross_2d(0.42);

    if (SHOW_GLYPHS)
        color(is_active(id) ? highlight_dark_color : [0.16, 0.17, 0.18, 1.0])
            for (angle = [0 : 90 : 270])
                translate([
                    dpad_centre.x + 7.1 * cos(angle),
                    dpad_centre.y + 7.1 * sin(angle),
                    front_z + 2.26
                ])
                    rotate([0, 0, angle - 90])
                        linear_extrude(height = 0.055)
                            triangle_2d(1.45);

    color(is_active(id) ? highlight_dark_color : control_edge_color)
        translate([dpad_centre.x, dpad_centre.y, front_z + 2.23])
            cylinder(h = 0.07, d = 2.4);
}

module stick_control(id, point) {
    color(active_dark_color(id))
        translate([point.x, point.y, front_z + 0.10])
            cylinder(h = 0.65, d = stick_well_diameter);
    color(is_active(id) ? highlight_dark_color : silver_ring_color)
        translate([point.x, point.y, front_z + 0.62])
            difference() {
                cylinder(h = 0.28, d = stick_ring_diameter);
                translate([0, 0, -epsilon])
                    cylinder(h = 0.28 + 2 * epsilon,
                             d = stick_ring_diameter - 0.75);
            }
    color(active_color(id, control_color))
        translate([point.x, point.y, front_z + 0.72])
            bevel_cylinder(stick_cap_diameter, 2.70, 0.55);

    color(is_active(id) ? highlight_dark_color : [0.14, 0.15, 0.16, 1.0])
        translate([point.x, point.y, front_z + 3.36]) {
            difference() {
                cylinder(h = 0.055, d = stick_cap_diameter - 2.15);
                translate([0, 0, -epsilon])
                    cylinder(h = 0.055 + 2 * epsilon,
                             d = stick_cap_diameter - 2.72);
            }
            for (angle = [0 : 90 : 270])
                rotate([0, 0, angle])
                    translate([stick_cap_diameter / 2 - 1.55, 0, 0])
                        cube([1.45, 0.36, 0.055], center = true);
        }
}

function face_glyph_color(glyph) =
    glyph == "X" ? [0.15, 0.50, 1.00, 1.0] :
    glyph == "Y" ? [0.15, 0.82, 0.42, 1.0] :
    glyph == "A" ? [1.00, 0.27, 0.25, 1.0] :
                   [1.00, 0.82, 0.12, 1.0];

module face_button(id, point, glyph) {
    color(active_dark_color(id))
        translate([point.x, point.y, front_z + 0.16])
            cylinder(h = 0.60, d = face_button_diameter + 0.75);
    color(active_color(id, control_top_color))
        translate([point.x, point.y, front_z + 0.55])
            bevel_cylinder(face_button_diameter, 2.00, 0.38);

    if (SHOW_GLYPHS)
        color(is_active(id) ? highlight_dark_color : face_glyph_color(glyph))
            front_text(
                [point.x, point.y, front_z + 2.52],
                glyph,
                3.35,
                0.07,
                "Liberation Sans:style=Bold"
            );
}

module system_button(id, point) {
    color(active_dark_color(id))
        translate([point.x, point.y, front_z + 0.06])
            cylinder(h = 0.33, d = system_button_diameter + 0.55);
    color(active_color(id, control_color))
        translate([point.x, point.y, front_z + 0.24])
            bevel_cylinder(system_button_diameter, 0.78, 0.22);
}

// ---- Sculpted shoulder and top keys -------------------------------------
function shoulder_bounds(side, kind) =
    side == "left"
        ? (kind == "bumper"
            ? [15.0, 34.0, 88.0, 89.9, 10.7, 18.4]
            : [15.0, 36.5, 84.8, 90.8, 1.0, 10.0])
        : (kind == "bumper"
            ? [mirror_x(34.0), mirror_x(15.0),
               88.0, 89.9, 10.7, 18.4]
            : [mirror_x(36.5), mirror_x(15.0),
               84.8, 90.8, 1.0, 10.0]);

function shell_top_y_at(x) =
    let(edge_x = min(x, mirror_x(x)))
        edge_x <= 7.2
            ? 69.8
            : edge_x <= 11.0
                ? 69.8 + (edge_x - 7.2) / 3.8 * (76.1 - 69.8)
                : edge_x <= 16.0
                    ? 76.1 + (edge_x - 11.0) / 5.0
                        * (81.25 - 76.1)
                    : edge_x <= 22.0
                        ? 81.25 + (edge_x - 16.0) / 6.0
                            * (85.1 - 81.25)
                        : edge_x <= 29.0
                            ? 85.1 + (edge_x - 22.0) / 7.0
                                * (87.6 - 85.1)
                            : edge_x <= 37.0
                                ? 87.6 + (edge_x - 29.0) / 8.0
                                    * (88.48 - 87.6)
                                : 88.48;

function shoulder_inner_fraction(x, side, bounds) =
    side == "left"
        ? (x - bounds[0]) / (bounds[1] - bounds[0])
        : (bounds[1] - x) / (bounds[1] - bounds[0]);

function shoulder_upper_y(x, side, kind, bounds) =
    let(
        inner = max(
            0,
            min(1, shoulder_inner_fraction(x, side, bounds))
        ),
        lift = kind == "trigger"
            ? 1.00 + 1.00 * pow(inner, 1.55)
            : 0.80 + 0.80 * pow(inner, 1.45)
    )
        shell_top_y_at(x) + lift;

function mix_value(first, second, amount) =
    first + (second - first) * amount;

function shoulder_segment_points(
    side,
    kind,
    first_amount,
    second_amount,
    radius = 1.05
) =
    let(
        bounds = shoulder_bounds(side, kind),
        x0 = bounds[0],
        x1 = bounds[1],
        z0 = bounds[4],
        z1 = bounds[5],
        rear_taper = kind == "bumper" ? 1.8 : 2.7,
        outer_taper = kind == "bumper" ? 1.0 : 2.1,
        low_x0 = x0 + radius
            + (side == "left" ? rear_taper : outer_taper),
        low_x1 = x1 - radius
            - (side == "left" ? outer_taper : rear_taper),
        high_x0 = x0 + radius,
        high_x1 = x1 - radius,
        depth = kind == "trigger" ? 5.8 : 1.9,
        low_first_x = mix_value(
            low_x0, low_x1, first_amount
        ),
        low_second_x = mix_value(
            low_x0, low_x1, second_amount
        ),
        high_first_x = mix_value(
            high_x0, high_x1, first_amount
        ),
        high_second_x = mix_value(
            high_x0, high_x1, second_amount
        ),
        low_first_y = shoulder_upper_y(
            low_first_x, side, kind, bounds
        ),
        low_second_y = shoulder_upper_y(
            low_second_x, side, kind, bounds
        ),
        high_first_y = shoulder_upper_y(
            high_first_x, side, kind, bounds
        ),
        high_second_y = shoulder_upper_y(
            high_second_x, side, kind, bounds
        )
    )
    [
        [
            low_first_x,
            low_first_y - depth + radius,
            z0 + radius
        ],
        [
            low_second_x,
            low_second_y - depth + radius,
            z0 + radius
        ],
        [low_first_x, low_first_y - radius, z0 + radius],
        [low_second_x, low_second_y - radius, z0 + radius],
        [
            high_first_x,
            high_first_y - depth + radius,
            z1 - radius
        ],
        [
            high_second_x,
            high_second_y - depth + radius,
            z1 - radius
        ],
        [high_first_x, high_first_y - radius, z1 - radius],
        [high_second_x, high_second_y - radius, z1 - radius]
    ];

module shoulder_control(id, side, kind, glyph) {
    radius = 0.90;
    segments = 4;
    bounds = shoulder_bounds(side, kind);
    label_x = (bounds[0] + bounds[1]) / 2;
    label_y = shoulder_upper_y(label_x, side, kind, bounds) + 0.015;
    label_slope = atan(
        (
            shoulder_upper_y(
                label_x + 0.30, side, kind, bounds
            )
            - shoulder_upper_y(
                label_x - 0.30, side, kind, bounds
            )
        ) / 0.60
    );
    colour = kind == "trigger"
        ? [0.035, 0.037, 0.040, 1.0]
        : [0.050, 0.052, 0.055, 1.0];
    color(active_color(id, colour))
        union()
            for (segment = [0 : segments - 1])
                rounded_point_hull(
                    shoulder_segment_points(
                        side,
                        kind,
                        segment / segments,
                        (segment + 1) / segments,
                        radius
                    ),
                    radius
                );

    color(is_active(id) ? highlight_dark_color : shoulder_legend_color)
        sloped_top_text([
            label_x,
            label_y,
            (bounds[4] + bounds[5]) / 2
        ], glyph, 2.25, label_slope, 0.055,
        "Liberation Sans:style=Bold");
}

module power_mark_2d() {
    difference() {
        circle(d = 2.55);
        circle(d = 1.75);
        translate([0, 1.05])
            square([1.1, 1.6], center = true);
    }
    translate([0, 0.70])
        square([0.42, 2.1], center = true);
}

module top_key_control(id, point_x, symbol) {
    key_size = symbol == "power" ? [7.8, 4.8] : [7.0, 4.55];
    outer_size = key_size + [2.0, 1.35];
    top_y = 89.18;
    color(active_dark_color(id))
        xz_trapezoid([point_x, top_y, top_control_z],
                     outer_size, 0.70, 1.75);
    color(active_color(id, top_key_face_color))
        xz_trapezoid([point_x, top_y + 0.12, top_control_z],
                     key_size, 0.82, 1.25);

    color(is_active(id) ? highlight_dark_color : legend_color)
        translate([point_x, top_y + 0.97, top_control_z])
            rotate([-90, 0, 0])
                linear_extrude(height = 0.055)
                    if (symbol == "power")
                        power_mark_2d();
                    else
                        text("R", size = 2.25,
                             font = "Liberation Sans:style=Bold",
                             halign = "center", valign = "center");
}

module named_control(id) {
    assert(contains(CONTROL_IDS, id), str("Unknown CONTROL_ID: ", id));

    if (id == "dpad")
        dpad_control();
    else if (id == "stick_l")
        stick_control(id, stick_l_centre);
    else if (id == "stick_r")
        stick_control(id, stick_r_centre);
    else if (id == "btn_north")
        face_button(id, face_centre + [0, face_pitch], "X");
    else if (id == "btn_east")
        face_button(id, face_centre + [face_pitch, 0], "A");
    else if (id == "btn_south")
        face_button(id, face_centre + [0, -face_pitch], "B");
    else if (id == "btn_west")
        face_button(id, face_centre + [-face_pitch, 0], "Y");
    else if (id == "btn_select")
        system_button(id, select_centre);
    else if (id == "vol_up")
        system_button(id, volume_up_centre);
    else if (id == "vol_down")
        system_button(id, volume_down_centre);
    else if (id == "btn_start")
        system_button(id, start_centre);
    else if (id == "btn_l1")
        shoulder_control(id, "left", "bumper", "L1");
    else if (id == "trig_l")
        shoulder_control(id, "left", "trigger", "L2");
    else if (id == "trig_r")
        shoulder_control(id, "right", "trigger", "R2");
    else if (id == "btn_r1")
        shoulder_control(id, "right", "bumper", "R1");
    else if (id == "btn_power")
        top_key_control(id, power_centre_x, "power");
    else if (id == "btn_reset")
        top_key_control(id, reset_centre_x, "reset");
}

module semantic_controls() {
    for (id = CONTROL_IDS)
        named_control(id);
}

module static_shell() {
    color(shell_color)
        shell_volume();
    front_face();
    front_perimeter_seam();
    screen();
    front_static_details();
    top_edge_static();
    bottom_edge_static();
    rear_details();
}

// ---- Contract dispatch ---------------------------------------------------
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
