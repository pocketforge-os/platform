/*
 * PocketForge semantic device model — TrimUI Brick (TG3040)
 *
 * Coordinate system (millimetres):
 *   X = physical left -> right
 *   Y = physical bottom -> top
 *   Z = rear -> front / viewer
 *
 * PART:
 *   assembly  complete coloured model (default)
 *   shell     non-interactive shell, screen, ports, labels and speakers
 *   controls  all semantic controls
 *   control   only CONTROL_ID
 *   screen    only the active display surface
 *
 * HIGHLIGHT is "", "*", or one id from CONTROL_IDS.
 *
 * This is a nominal visual/UI model, not a manufacturing-tolerance drawing.
 * Measurement provenance and remaining uncertainty are recorded in README.md.
 */

PART = "assembly";
CONTROL_ID = "btn_east";
HIGHLIGHT = "";
SHOW_GLYPHS = true;
SHOW_MICRO_DETAILS = true;
SCREEN_MARKER = false;
QUALITY = "render";

$fn = QUALITY == "draft" ? 24 : 56;
epsilon = 0.02;

// ---- Owner-measured envelope and photo-derived landmarks ----------------
device_width = 72.8;
device_height = 110.75;
front_z = 20.0;
lower_rear_z = 0.0;
upper_rear_z = 8.0;               // 20 mm lower / 12 mm upper depth
rear_transition_low_y = 43.0;
rear_transition_high_y = 49.0;
bottom_corner_radius = 4.8;
top_corner_radius = 2.7;
outline_steps = QUALITY == "draft" ? 8 : 18;

screen_diagonal = 3.2 * 25.4;
screen_active = [
    screen_diagonal * 4 / 5,
    screen_diagonal * 3 / 5
];
screen_glass = [67.35, 51.35];
screen_centre = [device_width / 2, 84.25];

dpad_centre = [17.4, 37.2];
face_centre = [54.9, 38.8];
face_pitch = 8.25;
f1_centre = [29.8, 51.3];
f2_centre = [41.2, 51.3];
menu_centre = [28.0, 8.8];
select_centre = [36.4, 8.8];
start_centre = [44.8, 8.8];

dpad_size = 19.0;
dpad_arm = 6.8;
face_button_diameter = 8.3;
system_button_diameter = 7.1;

shoulder_y = 47.2;
shoulder_z = 4.15;
shoulder_centres = [7.3, 21.0, 51.8, 65.5];
host_centre_x = device_width / 2;

speaker_left_x = 13.4;
speaker_right_x = device_width - speaker_left_x;
speaker_y = 13.15;
speaker_pitch_x = 1.35;
speaker_pitch_y = 1.22;

CONTROL_IDS = [
    "dpad",
    "btn_north",
    "btn_east",
    "btn_south",
    "btn_west",
    "btn_f1",
    "btn_f2",
    "btn_menu",
    "btn_select",
    "btn_start",
    "btn_l1",
    "trig_l",
    "trig_r",
    "btn_r1",
    "vol_up",
    "vol_down",
    "btn_fn",
    "btn_power"
];

function contains(values, value) =
    len([for (candidate = values) if (candidate == value) 1]) > 0;
function is_active(id) = HIGHLIGHT == "*" || HIGHLIGHT == id;

assert(abs(device_width - 72.8) < 0.001 &&
       abs(device_height - 110.75) < 0.001,
       "TG3040 owner-measured face envelope changed");
assert(abs(front_z - lower_rear_z - 20.0) < 0.001 &&
       abs(front_z - upper_rear_z - 12.0) < 0.001,
       "TG3040 stepped 20/12 mm shell depth changed");
assert(abs(sqrt(screen_active.x * screen_active.x +
                screen_active.y * screen_active.y) -
           screen_diagonal) < 0.001,
       "Screen active area lost its official 3.2-inch diagonal");
assert(PART != "control" || contains(CONTROL_IDS, CONTROL_ID),
       str("Unknown CONTROL_ID: ", CONTROL_ID));
assert(HIGHLIGHT == "" || HIGHLIGHT == "*" ||
       contains(CONTROL_IDS, HIGHLIGHT),
       str("Unknown HIGHLIGHT id: ", HIGHLIGHT));

// ---- Palette -------------------------------------------------------------
shell_rear_color = [0.040, 0.043, 0.047, 1.0];
shell_side_color = [0.070, 0.073, 0.078, 1.0];
shell_front_color = [0.095, 0.098, 0.103, 1.0];
shell_edge_color = [0.018, 0.020, 0.023, 1.0];
rear_panel_color = [0.205, 0.210, 0.218, 1.0];
rear_rib_color = [0.105, 0.109, 0.115, 1.0];
control_color = [0.025, 0.028, 0.032, 1.0];
control_edge_color = [0.008, 0.010, 0.013, 1.0];
control_glyph_color = [0.49, 0.50, 0.51, 1.0];
system_glyph_color = [0.62, 0.63, 0.64, 1.0];
glass_color = [0.004, 0.006, 0.009, 1.0];
glass_edge_color = [0.16, 0.17, 0.18, 1.0];
silkscreen_color = [0.54, 0.55, 0.56, 1.0];
silver_key_color = [0.72, 0.73, 0.72, 1.0];
power_key_color = [0.00, 0.82, 0.82, 1.0];
highlight_color = [0.92, 0.07, 0.06, 1.0];
highlight_dark_color = [0.53, 0.018, 0.015, 1.0];

ui_font = "Liberation Sans:style=Bold";
micro_font = "Liberation Sans:style=Regular";
brand_font = "Liberation Sans:style=Bold";

function active_color(id, neutral = control_color) =
    is_active(id) ? highlight_color : neutral;
function active_dark_color(id, neutral = control_edge_color) =
    is_active(id) ? highlight_dark_color : neutral;

// ---- Reusable geometry ---------------------------------------------------
function lower_left_points() = [
    for (index = [0 : outline_steps])
        let(angle = 180 + 90 * index / outline_steps)
            [bottom_corner_radius +
                 bottom_corner_radius * cos(angle),
             bottom_corner_radius +
                 bottom_corner_radius * sin(angle)]
];

function lower_right_points() = [
    for (index = [0 : outline_steps])
        let(angle = 270 + 90 * index / outline_steps)
            [device_width - bottom_corner_radius +
                 bottom_corner_radius * cos(angle),
             bottom_corner_radius +
                 bottom_corner_radius * sin(angle)]
];

function upper_right_points() = [
    for (index = [0 : outline_steps])
        let(angle = 90 * index / outline_steps)
            [device_width - top_corner_radius +
                 top_corner_radius * cos(angle),
             device_height - top_corner_radius +
                 top_corner_radius * sin(angle)]
];

function upper_left_points() = [
    for (index = [0 : outline_steps])
        let(angle = 90 + 90 * index / outline_steps)
            [top_corner_radius + top_corner_radius * cos(angle),
             device_height - top_corner_radius +
                 top_corner_radius * sin(angle)]
];

function body_outline_points() = concat(
    lower_left_points(),
    lower_right_points(),
    upper_right_points(),
    upper_left_points()
);

module body_outline_2d(inset = 0) {
    offset(delta = -inset)
        polygon(points = body_outline_points());
}

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

module bevel_cylinder(diameter, height, bevel = 0.35) {
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

module xz_rounded_rect(point, size, thickness, radius) {
    translate([point.x, point.y, point.z])
        rotate([90, 0, 0])
            linear_extrude(height = thickness, center = true)
                rounded_rect_2d(size, radius);
}

module xz_pill(point, size, thickness) {
    translate([point.x, point.y, point.z])
        rotate([90, 0, 0])
            linear_extrude(height = thickness, center = true)
                pill_2d(size.x, size.y);
}

module yz_rounded_rect(point, size, thickness, radius) {
    translate([point.x, point.y, point.z])
        rotate([90, 0, 90])
            linear_extrude(height = thickness, center = true)
                rounded_rect_2d(size, radius);
}

module label_text_2d(message, size, halign = "center",
                     valign = "center", font = ui_font,
                     ink_spread = 0) {
    if (ink_spread > 0)
        offset(r = ink_spread)
            text(message, size = size, halign = halign,
                 valign = valign, font = font);
    else
        text(message, size = size, halign = halign,
             valign = valign, font = font);
}

module front_label(point, message, size, height = 0.07,
                   colour = silkscreen_color, halign = "center",
                   valign = "center", font = ui_font,
                   ink_spread = 0) {
    if (SHOW_GLYPHS)
        color(colour)
            translate([point.x, point.y, point.z])
                linear_extrude(height = height)
                    label_text_2d(message, size, halign, valign,
                                  font, ink_spread);
}

module rear_label(point, message, size, height = 0.06,
                  colour = silkscreen_color, halign = "center",
                  valign = "center", font = micro_font,
                  ink_spread = 0) {
    if (SHOW_GLYPHS)
        color(colour)
            translate([point.x, point.y, point.z])
                mirror([1, 0, 0])
                    linear_extrude(height = height)
                        label_text_2d(message, size, halign, valign,
                                      font, ink_spread);
}

module edge_label(point, message, size, side,
                  height = 0.08, colour = silkscreen_color,
                  font = ui_font) {
    if (SHOW_GLYPHS)
        color(colour)
            translate([point.x, point.y, point.z])
                rotate([side == "top" ? -90 : 90, 0, 0])
                    linear_extrude(height = height)
                        label_text_2d(message, size, "center",
                                      "center", font);
}

module trimui_mark_2d(dot_diameter = 0.65, orbit = 0.72) {
    for (angle = [90, 210, 330])
        translate([orbit * cos(angle), orbit * sin(angle)])
            circle(d = dot_diameter, $fn = 18);
}

// ---- Shell and static details -------------------------------------------
module rolled_outer_volume() {
    union() {
        hull() {
            outline_layer(0.00, 1.05);
            outline_layer(1.15, 0.20);
        }
        hull() {
            outline_layer(1.15, 0.20);
            outline_layer(18.65, 0.05);
        }
        hull() {
            outline_layer(18.65, 0.05);
            outline_layer(front_z - 0.05, 0.68);
        }
    }
}

module stepped_profile_volume() {
    // Local polygon X maps to global Y, local Y to global Z, and the
    // extrusion axis maps to global X.
    rotate([90, 0, 90])
        linear_extrude(height = device_width)
            polygon(points = [
                [0, lower_rear_z],
                [rear_transition_low_y, lower_rear_z],
                [rear_transition_high_y, upper_rear_z],
                [device_height, upper_rear_z],
                [device_height, front_z],
                [0, front_z]
            ]);
}

module shell_volume() {
    color(shell_side_color)
        intersection() {
            rolled_outer_volume();
            stepped_profile_volume();
        }
}

module perimeter_seam() {
    color(shell_edge_color)
        translate([0, 0, 18.25])
            linear_extrude(height = 0.16)
                difference() {
                    body_outline_2d(0.12);
                    body_outline_2d(0.44);
                }
}

module front_face() {
    color(shell_front_color)
        translate([0, 0, front_z - 0.12])
            linear_extrude(height = 0.16)
                body_outline_2d(0.68);
}

module active_screen() {
    color(SCREEN_MARKER ? [1.0, 0.0, 1.0, 1.0]
                        : [0.008, 0.011, 0.016, 1.0])
        rounded_panel(screen_centre, screen_active,
                      0.07, 0.42, front_z + 0.44);
}

module screen() {
    color(glass_edge_color)
        rounded_panel(screen_centre, screen_glass + [0.85, 0.85],
                      0.16, 1.18, front_z + 0.02);
    color(glass_color)
        rounded_panel(screen_centre, screen_glass,
                      0.27, 0.92, front_z + 0.18);
    active_screen();

    // A very narrow satin highlight keeps the black glass legible without
    // pretending that the panel is illuminated.
    color([0.12, 0.13, 0.14, 1.0])
        translate([screen_centre.x - screen_glass.x / 2 + 0.33,
                   screen_centre.y - screen_glass.y / 2 + 0.65,
                   front_z + 0.47])
            cube([0.11, screen_glass.y - 1.3, 0.025]);
}

function speaker_positions(side) = [
    for (row = [0 : 1], column = [0 : 7])
        let(base_x = side == "left" ? speaker_left_x : speaker_right_x,
            direction = side == "left" ? 1 : -1,
            stagger = row == 0 ? 0 : 0.34)
            [base_x +
                 direction * ((column - 3.5) * speaker_pitch_x + stagger),
             speaker_y + row * speaker_pitch_y]
];

module speaker_array(side) {
    for (point = speaker_positions(side)) {
        color([0.006, 0.007, 0.009, 1.0])
            translate([point.x, point.y, front_z + 0.015])
                cylinder(d = 0.82, h = 0.13, $fn = 12);
        color([0.18, 0.18, 0.18, 1.0])
            translate([point.x, point.y, front_z + 0.13])
                cylinder(d = 0.44, h = 0.025, $fn = 12);
    }
}

module front_printing() {
    front_label([3.7, 56.20, front_z + 0.055],
                "TRIMUI", 1.40, 0.05, silkscreen_color,
                "left", "center", brand_font);
    color(silkscreen_color)
        translate([15.2, 56.20, front_z + 0.055])
            linear_extrude(height = 0.05)
                trimui_mark_2d(0.43, 0.49);
    front_label([17.2, 56.20, front_z + 0.055],
                "BRICK", 1.40, 0.05, silkscreen_color,
                "left", "center", brand_font);
}

module host_port() {
    color([0.56, 0.57, 0.58, 1.0])
        xz_pill([host_centre_x, shoulder_y + 0.55, shoulder_z],
                [10.3, 4.15], 0.52);
    color(control_edge_color)
        xz_pill([host_centre_x, shoulder_y + 0.78, shoulder_z],
                [8.9, 2.95], 0.57);
    color([0.45, 0.46, 0.47, 1.0])
        xz_pill([host_centre_x, shoulder_y + 0.87, shoulder_z],
                [6.3, 0.70], 0.61);
}

module rgb_light_bar() {
    color([0.52, 0.55, 0.57, 1.0])
        xz_rounded_rect([device_width / 2, device_height + 0.05, 13.25],
                        [25.0, 2.35], 0.46, 0.40);
    if (SHOW_MICRO_DETAILS) {
        color([0.10, 0.74, 0.74, 1.0])
            xz_rounded_rect([device_width / 2 - 8.0,
                             device_height + 0.30, 13.25],
                            [7.5, 1.55], 0.08, 0.28);
        color([0.52, 0.30, 0.75, 1.0])
            xz_rounded_rect([device_width / 2,
                             device_height + 0.30, 13.25],
                            [7.5, 1.55], 0.08, 0.28);
        color([0.12, 0.55, 0.92, 1.0])
            xz_rounded_rect([device_width / 2 + 8.0,
                             device_height + 0.30, 13.25],
                            [7.5, 1.55], 0.08, 0.28);
    }
}

module bottom_ports() {
    edge_y = -0.12;
    port_z = 10.4;

    // TF slot.
    color(control_edge_color)
        xz_pill([10.3, edge_y, port_z], [12.6, 2.05], 0.50);
    color([0.16, 0.17, 0.18, 1.0])
        xz_pill([10.3, edge_y - 0.27, port_z], [9.8, 0.55], 0.07);

    // Reset recess.
    color(control_edge_color)
        xz_pill([23.1, edge_y, port_z], [2.70, 2.70], 0.54);

    // DC USB-C.
    color([0.62, 0.63, 0.63, 1.0])
        xz_pill([36.4, edge_y, port_z], [10.2, 4.05], 0.54);
    color(control_edge_color)
        xz_pill([36.4, edge_y - 0.19, port_z], [8.6, 2.75], 0.58);
    color([0.40, 0.41, 0.42, 1.0])
        xz_pill([36.4, edge_y - 0.31, port_z], [6.1, 0.70], 0.06);

    // Microphone and audio.
    color(control_edge_color)
        xz_pill([47.7, edge_y, port_z], [1.55, 1.55], 0.55);
    color(control_edge_color)
        xz_pill([59.4, edge_y, port_z], [5.65, 5.65], 0.55);
    color([0.18, 0.19, 0.20, 1.0])
        xz_pill([59.4, edge_y - 0.25, port_z], [3.35, 3.35], 0.08);

    if (SHOW_MICRO_DETAILS) {
        edge_label([10.3, -0.44, 15.7], "TF", 1.12, "bottom",
                   0.05, silkscreen_color, micro_font);
        edge_label([23.1, -0.44, 15.7], "R", 1.12, "bottom",
                   0.05, silkscreen_color, micro_font);
        edge_label([36.4, -0.44, 15.7], "DC", 1.12, "bottom",
                   0.05, silkscreen_color, micro_font);
    }
}

module screw_cross(point, z, rear_surface) {
    screw_z = rear_surface ? z - 0.28 : z;
    color([0.60, 0.61, 0.61, 1.0])
        translate([point.x, point.y, screw_z])
            cylinder(d = 3.0, h = 0.24, $fn = 28);
    color([0.13, 0.14, 0.15, 1.0]) {
        translate([point.x - 0.76, point.y - 0.13, screw_z - 0.025])
            cube([1.52, 0.26, 0.04]);
        translate([point.x - 0.13, point.y - 0.76, screw_z - 0.025])
            cube([0.26, 1.52, 0.04]);
    }
}

module rear_upper_panel() {
    panel_size = [70.0, device_height - rear_transition_high_y - 1.6];
    panel_centre = [device_width / 2,
                    rear_transition_high_y + panel_size.y / 2 + 0.4];
    color(rear_panel_color)
        rounded_panel(panel_centre, panel_size, 0.22, 1.2, 7.62);

    rear_label([device_width / 2, 91.5, 7.52],
               "TRIMUI   BRICK", 2.05, 0.055,
               [0.68, 0.69, 0.70, 1.0], "center", "center",
               brand_font);
    rear_label([device_width / 2, 88.9, 7.52],
               "DESIGN BY TRIMUI · MADE IN CHINA", 0.72, 0.05,
               [0.48, 0.49, 0.50, 1.0]);

    screw_cross([5.2, 105.4], 7.57, true);
    screw_cross([device_width - 5.2, 105.4], 7.57, true);
}

module rear_lower_details() {
    // Shallow horizontal ribs on the thick lower grip.
    for (y = [7.0 : 2.25 : 39.5])
        color(rear_rib_color)
            translate([3.2, y, -0.23])
                cube([device_width - 6.4, 0.72, 0.20]);

    color([0.115, 0.118, 0.122, 1.0])
        translate([3.2, 18.4, -0.27])
            cube([device_width - 6.4, 8.0, 0.15]);

    if (SHOW_MICRO_DETAILS) {
        rear_label([5.6, 23.5, -0.34],
                   "MODEL: TG3040  TRIMUI BRICK  DC 5V/3000mA",
                   0.66, 0.05, [0.43, 0.44, 0.45, 1.0],
                   "right", "center", micro_font);
        rear_label([5.6, 21.9, -0.34],
                   "DESIGN BY TRIMUI · MADE IN CHINA",
                   0.66, 0.05, [0.43, 0.44, 0.45, 1.0],
                   "right", "center", micro_font);
        rear_label([54.6, 20.4, -0.34],
                   "FC  CE", 2.05, 0.05,
                   [0.50, 0.51, 0.52, 1.0],
                   "center", "center", brand_font);
    }

    for (point = [
        [4.8, 44.9], [device_width - 4.8, 44.9],
        [4.8, 4.8], [device_width - 4.8, 4.8]
    ])
        screw_cross(point, -0.02, true);
}

module static_shell() {
    shell_volume();
    perimeter_seam();
    front_face();
    screen();
    speaker_array("left");
    speaker_array("right");
    front_printing();
    host_port();
    rgb_light_bar();
    bottom_ports();
    rear_upper_panel();
    rear_lower_details();
}

// ---- Semantic controls ---------------------------------------------------
module dpad_cross_2d(inset = 0) {
    offset(delta = -inset)
        union() {
            rounded_rect_2d([dpad_size, dpad_arm], 1.55);
            rounded_rect_2d([dpad_arm, dpad_size], 1.55);
        }
}

module dpad_control() {
    color(active_dark_color("dpad"))
        translate([dpad_centre.x, dpad_centre.y, front_z + 0.03])
            linear_extrude(height = 0.38)
                dpad_cross_2d();
    color(active_color("dpad"))
        translate([dpad_centre.x, dpad_centre.y, front_z + 0.34])
            linear_extrude(height = 1.05, scale = 0.94)
                dpad_cross_2d(0.14);
    color(is_active("dpad") ? highlight_dark_color
                            : [0.33, 0.34, 0.35, 1.0])
        translate([dpad_centre.x, dpad_centre.y, front_z + 1.40])
            cylinder(d = 5.3, h = 0.18, $fn = 32);
    if (SHOW_GLYPHS)
        for (angle = [90, 210, 330])
            color(is_active("dpad") ? highlight_dark_color
                                    : [0.08, 0.085, 0.09, 1.0])
                translate([dpad_centre.x + 1.45 * cos(angle),
                           dpad_centre.y + 1.45 * sin(angle),
                           front_z + 1.57])
                    cylinder(d = 1.25, h = 0.08, $fn = 6);
}

module face_button(id, point, glyph) {
    color(control_edge_color)
        translate([point.x, point.y, front_z + 0.02])
            cylinder(d = face_button_diameter + 1.7,
                     h = 0.35, $fn = 40);
    color(active_color(id))
        translate([point.x, point.y, front_z + 0.30])
            bevel_cylinder(face_button_diameter, 1.45, 0.35);
    if (SHOW_GLYPHS)
        front_label([point.x, point.y, front_z + 1.74],
                    glyph, 3.2, 0.08,
                    is_active(id) ? highlight_dark_color
                                  : control_glyph_color,
                    "center", "center", ui_font);
}

module function_key(id, point, glyph) {
    color(control_edge_color)
        translate([point.x, point.y, front_z + 0.02])
            linear_extrude(height = 0.28)
                pill_2d(10.0, 4.45);
    color(active_color(id, silver_key_color))
        translate([point.x, point.y, front_z + 0.27])
            linear_extrude(height = 0.76, scale = 0.94)
                pill_2d(8.9, 3.35);
    if (SHOW_MICRO_DETAILS)
        front_label([point.x, point.y, front_z + 1.04],
                    glyph, 1.45, 0.06,
                    is_active(id) ? highlight_dark_color
                                  : [0.43, 0.44, 0.45, 1.0],
                    "center", "center", micro_font);
}

module four_dot_icon(point, z, colour) {
    for (offset = [[-0.9, 0], [0.9, 0], [0, -0.9], [0, 0.9]])
        color(colour)
            translate([point.x + offset.x, point.y + offset.y, z])
                cylinder(d = 0.88, h = 0.07, $fn = 18);
}

module system_button(id, point, symbol) {
    color(control_edge_color)
        translate([point.x, point.y, front_z + 0.02])
            cylinder(d = system_button_diameter + 1.55,
                     h = 0.32, $fn = 36);
    color(active_color(id))
        translate([point.x, point.y, front_z + 0.30])
            bevel_cylinder(system_button_diameter, 1.05, 0.28);

    glyph_colour = is_active(id) ? highlight_dark_color
                                 : system_glyph_color;
    if (SHOW_GLYPHS) {
        if (symbol == "menu")
            four_dot_icon(point, front_z + 1.34, glyph_colour);
        else if (symbol == "select")
            color(glyph_colour)
                translate([point.x - 1.55, point.y - 0.34,
                           front_z + 1.34])
                    cube([3.1, 0.68, 0.07]);
        else
            color(glyph_colour)
                translate([point.x, point.y, front_z + 1.34])
                    linear_extrude(height = 0.07)
                        polygon(points = [
                            [1.65, 0], [-1.05, 1.45], [-1.05, -1.45]
                        ]);
    }
}

module shoulder_control(id, x, glyph, outer = false) {
    size = outer ? [12.6, 6.2] : [12.1, 6.5];
    color(control_edge_color)
        xz_rounded_rect([x, shoulder_y, shoulder_z],
                        size + [0.7, 0.55], 3.05, 1.0);
    color(active_color(id))
        xz_rounded_rect([x, shoulder_y + 0.22, shoulder_z],
                        size, 3.15, outer ? 1.25 : 0.85);
    if (SHOW_GLYPHS)
        edge_label([x, shoulder_y + 1.83, shoulder_z],
                   glyph, 2.15, "top", 0.07,
                   is_active(id) ? highlight_dark_color
                                 : control_glyph_color,
                   ui_font);
}

module volume_control(id, y, glyph) {
    color(control_edge_color)
        yz_rounded_rect([-0.08, y, 14.1], [8.6, 4.4], 0.70, 1.75);
    color(active_color(id))
        yz_rounded_rect([-0.42, y, 14.1], [7.6, 3.45], 0.78, 1.45);
    if (SHOW_GLYPHS)
        // The relief is represented as a shallow bar/cross rather than text
        // so it remains visible on a vertical side elevation.
        color(is_active(id) ? highlight_dark_color : control_glyph_color) {
            translate([-0.83, y - 1.25, 14.0])
                cube([0.10, 2.50, 0.30]);
            if (glyph == "+")
                translate([-0.83, y - 0.15, 12.90])
                    cube([0.10, 0.30, 2.50]);
        }
}

module fn_control() {
    id = "btn_fn";
    color(control_edge_color)
        yz_rounded_rect([device_width + 0.08, 72.0, 13.5],
                        [10.3, 4.7], 0.70, 1.8);
    color(active_color(id))
        yz_rounded_rect([device_width + 0.43, 72.0, 13.5],
                        [8.9, 3.65], 0.80, 1.45);
    if (SHOW_MICRO_DETAILS)
        for (offset = [-2.7 : 0.9 : 2.7])
            color(is_active(id) ? highlight_dark_color
                                : [0.10, 0.105, 0.11, 1.0])
                translate([device_width + 0.83,
                           72.0 + offset - 0.12, 12.2])
                    cube([0.08, 0.24, 2.6]);
}

module power_control() {
    id = "btn_power";
    color(control_edge_color)
        yz_rounded_rect([device_width + 0.08, 57.0, 13.8],
                        [8.5, 8.0], 0.70, 3.2);
    color(active_color(id, power_key_color))
        yz_rounded_rect([device_width + 0.43, 57.0, 13.8],
                        [7.25, 6.7], 0.80, 2.85);
    color(is_active(id) ? highlight_dark_color
                        : [0.00, 0.42, 0.45, 1.0]) {
        translate([device_width + 0.84, 56.1, 13.65])
            rotate([0, 90, 0])
                cylinder(d = 3.0, h = 0.07, $fn = 32);
        translate([device_width + 0.82, 56.8, 13.70])
            cube([0.10, 2.0, 0.28]);
    }
}

module named_control(id) {
    if (id == "dpad")
        dpad_control();
    else if (id == "btn_north")
        face_button(id, face_centre + [0, face_pitch], "X");
    else if (id == "btn_east")
        face_button(id, face_centre + [face_pitch, 0], "A");
    else if (id == "btn_south")
        face_button(id, face_centre + [0, -face_pitch], "B");
    else if (id == "btn_west")
        face_button(id, face_centre + [-face_pitch, 0], "Y");
    else if (id == "btn_f1")
        function_key(id, f1_centre, "F1");
    else if (id == "btn_f2")
        function_key(id, f2_centre, "F2");
    else if (id == "btn_menu")
        system_button(id, menu_centre, "menu");
    else if (id == "btn_select")
        system_button(id, select_centre, "select");
    else if (id == "btn_start")
        system_button(id, start_centre, "start");
    else if (id == "btn_l1")
        shoulder_control(id, shoulder_centres[0], "L1", true);
    else if (id == "trig_l")
        shoulder_control(id, shoulder_centres[1], "L2");
    else if (id == "trig_r")
        shoulder_control(id, shoulder_centres[2], "R2");
    else if (id == "btn_r1")
        shoulder_control(id, shoulder_centres[3], "R1", true);
    else if (id == "vol_up")
        volume_control(id, 77.4, "+");
    else if (id == "vol_down")
        volume_control(id, 66.8, "-");
    else if (id == "btn_fn")
        fn_control();
    else if (id == "btn_power")
        power_control();
}

module semantic_controls() {
    for (id = CONTROL_IDS)
        named_control(id);
}

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
