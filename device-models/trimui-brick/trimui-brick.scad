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
rear_thick_length = 60.0;
rear_transition_low_y = rear_thick_length;
rear_transition_high_y = 64.44;
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
menu_centre = [26.6, 8.0];
select_centre = [36.4, 8.0];
start_centre = [46.2, 8.0];

dpad_size = 18.43;
dpad_arm = 6.6;
face_button_diameter = 7.0;
system_button_diameter = 4.5;
system_button_gap = 5.3;
f_key_size = [6.25, 2.0];

shoulder_bevel = 3.7;
shoulder_outer_width = 17.51;
shoulder_inner_width = 10.32;
shoulder_outer_extension = 8.30;
shoulder_inner_extension = 9.86;
shoulder_inner_gap = 0.60;
// Symmetrical residual after the measured controls and 13.55 mm host boss.
shoulder_host_gap = 1.195;
host_housing_width = 13.55;
host_housing_extension = 4.44;
host_opening_width = 8.79;
host_centre_x = device_width / 2;

shoulder_l1_start = 0.00;
shoulder_l2_start =
    shoulder_l1_start + shoulder_outer_width + shoulder_inner_gap;
host_housing_start =
    shoulder_l2_start + shoulder_inner_width + shoulder_host_gap;
shoulder_r2_start =
    host_housing_start + host_housing_width + shoulder_host_gap;
shoulder_r1_start =
    shoulder_r2_start + shoulder_inner_width + shoulder_inner_gap;

fn_track_size = [10.65, 3.82];
fn_slider_length = 7.73;
fn_top_y = device_height - 18.0;
fn_centre_y = fn_top_y - fn_track_size.x / 2;
power_key_size = [7.0, 4.35];
power_top_y = fn_top_y - fn_track_size.x - 7.0;
power_centre_y = power_top_y - power_key_size.x / 2;

volume_key_size = [7.82, 3.52];
volume_gap = 2.85;
volume_up_top_y = device_height - 6.3;
volume_up_centre_y = volume_up_top_y - volume_key_size.x / 2;
volume_down_top_y =
    volume_up_top_y - volume_key_size.x - volume_gap;
volume_down_centre_y =
    volume_down_top_y - volume_key_size.x / 2;

front_brand_size = [15.9, 1.26];
rear_brand_size = [22.72, 2.88];
rear_design_size = [19.55, 0.92];
light_diffuser_size = [38.0, 3.56];
light_rear_drop = 2.0;
regulatory_copy_size = [36.19, 4.14];
regulatory_mark_height = 4.26;
fcc_mark_width = 5.40;
ce_mark_width = 4.63;
recycle_mark_width = 4.40;
weee_mark_width = 3.59;
copy_fcc_gap = 0.40;
fcc_ce_gap = 2.20;
ce_recycle_gap = 2.27;
recycle_weee_gap = 1.75;
regulatory_lockup_width =
    regulatory_copy_size.x + copy_fcc_gap + fcc_mark_width +
    fcc_ce_gap + ce_mark_width + ce_recycle_gap +
    recycle_mark_width + recycle_weee_gap + weee_mark_width;

speaker_left_x = 13.4;
speaker_right_x = device_width - speaker_left_x;
speaker_y = 13.15;
speaker_columns = 6;
speaker_block_size = [8.61, 1.75];
speaker_hole_diameter = 0.70;
speaker_hole_inner_diameter = 0.38;
speaker_stagger = 0.34;
speaker_pitch_x =
    (speaker_block_size.x - speaker_hole_diameter -
     speaker_stagger) / (speaker_columns - 1);
speaker_pitch_y = speaker_block_size.y - speaker_hole_diameter;

bottom_feature_z = 10.4;
bottom_sd_left = 10.0;
bottom_sd_width = 12.45;
bottom_sd_height = 1.45;          // visual estimate; card is 1.0 mm thick
bottom_sd_centre_x = bottom_sd_left + bottom_sd_width / 2;

bottom_sd_reset_gap = 2.36;
bottom_reset_diameter = 3.15;
bottom_reset_recess = 1.0;
bottom_reset_centre_x =
    bottom_sd_left + bottom_sd_width + bottom_sd_reset_gap +
    bottom_reset_diameter / 2;

bottom_reset_usb_gap = 3.20;
bottom_usb_width = host_opening_width;
bottom_usb_centre_x =
    bottom_reset_centre_x + bottom_reset_diameter / 2 +
    bottom_reset_usb_gap + bottom_usb_width / 2;

bottom_usb_mic_gap = 4.75;
bottom_mic_diameter = 0.70;       // visual estimate; owner reports pinhole
bottom_mic_centre_x =
    bottom_usb_centre_x + bottom_usb_width / 2 +
    bottom_usb_mic_gap + bottom_mic_diameter / 2;

bottom_mic_audio_gap = 5.0;
bottom_audio_diameter = 5.16;
bottom_audio_centre_x =
    bottom_mic_centre_x + bottom_mic_diameter / 2 +
    bottom_mic_audio_gap + bottom_audio_diameter / 2;

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
assert(abs(dpad_size - 18.43) < 0.001 &&
       abs(face_button_diameter - 7.0) < 0.001 &&
       abs(system_button_diameter - 4.5) < 0.001,
       "Owner-measured front-control dimensions changed");
assert(abs(select_centre.x - menu_centre.x -
           system_button_diameter - system_button_gap) < 0.001 &&
       abs(start_centre.x - select_centre.x -
           system_button_diameter - system_button_gap) < 0.001 &&
       abs(menu_centre.y - system_button_diameter / 2 - 5.75) <
           0.001,
       "System-button spacing or bottom margin changed");
assert(abs(shoulder_r1_start + shoulder_outer_width -
           device_width) < 0.001,
       "Measured shoulder/host chain no longer fills the top shelf");
assert(abs((fn_top_y - fn_track_size.x) - power_top_y - 7.0) <
           0.001 &&
       abs(volume_up_top_y - volume_key_size.x -
           volume_down_top_y - volume_gap) < 0.001,
       "Measured side-control clearances changed");
assert(abs(regulatory_lockup_width - 60.83) < 0.001,
       "Rear regulatory lockup width changed");
assert(abs(light_diffuser_size.x - 38.0) < 0.001 &&
       abs(light_diffuser_size.y - 3.56) < 0.001 &&
       abs(light_rear_drop - 2.0) < 0.001,
       "Owner-measured top diffuser dimensions changed");
assert(abs((speaker_columns - 1) * speaker_pitch_x +
           speaker_stagger + speaker_hole_diameter -
           speaker_block_size.x) < 0.001 &&
       abs(speaker_pitch_y + speaker_hole_diameter -
           speaker_block_size.y) < 0.001,
       "Speaker-array measured bounding box changed");
assert(abs(bottom_sd_left - 10.0) < 0.001 &&
       abs((bottom_reset_centre_x - bottom_reset_diameter / 2) -
           (bottom_sd_left + bottom_sd_width) -
           bottom_sd_reset_gap) < 0.001 &&
       abs((bottom_usb_centre_x - bottom_usb_width / 2) -
           (bottom_reset_centre_x + bottom_reset_diameter / 2) -
           bottom_reset_usb_gap) < 0.001 &&
       abs((bottom_mic_centre_x - bottom_mic_diameter / 2) -
           (bottom_usb_centre_x + bottom_usb_width / 2) -
           bottom_usb_mic_gap) < 0.001 &&
       abs((bottom_audio_centre_x - bottom_audio_diameter / 2) -
           (bottom_mic_centre_x + bottom_mic_diameter / 2) -
           bottom_mic_audio_gap) < 0.001,
       "Owner-measured bottom feature chain changed");
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

module xz_ring(point, outer_diameter, inner_diameter, thickness) {
    translate([point.x, point.y, point.z])
        rotate([90, 0, 0])
            linear_extrude(height = thickness, center = true)
                difference() {
                    circle(d = outer_diameter, $fn = 40);
                    circle(d = inner_diameter, $fn = 40);
                }
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
    // The three-circle triangle's raw bounds sit orbit/4 above its origin.
    // Re-centre the actual bounds so brand lockups align geometrically.
    translate([0, -orbit / 4])
        for (angle = [90, 210, 330])
            translate([orbit * cos(angle), orbit * sin(angle)])
                circle(d = dot_diameter, $fn = 18);
}

module line_segment_2d(first, second, width) {
    hull() {
        translate(first) circle(d = width, $fn = 18);
        translate(second) circle(d = width, $fn = 18);
    }
}

module exact_centred_art_2d(size) {
    resize(newsize = size, auto = false)
        children();
}

module front_vector_art(point, size, height = 0.06,
                        colour = silkscreen_color) {
    if (SHOW_GLYPHS)
        color(colour)
            translate(point)
                linear_extrude(height = height)
                    exact_centred_art_2d(size)
                        children();
}

module rear_vector_art(point, size, height = 0.055,
                       colour = silkscreen_color) {
    if (SHOW_GLYPHS)
        color(colour)
            translate(point)
                mirror([1, 0, 0])
                    linear_extrude(height = height)
                        exact_centred_art_2d(size)
                            children();
}

module front_brand_art(point, size, height = 0.06,
                       colour = silkscreen_color) {
    if (SHOW_GLYPHS)
        color(colour)
            translate(point)
                linear_extrude(height = height)
                    trimui_brick_lockup_2d(size);
}

module rear_brand_art(point, size, height = 0.055,
                      colour = silkscreen_color) {
    if (SHOW_GLYPHS)
        color(colour)
            translate(point)
                mirror([1, 0, 0])
                    linear_extrude(height = height)
                        trimui_brick_lockup_2d(size);
}

module trimui_brick_lockup_2d(size) {
    logo_dot = 1.05;
    logo_orbit = 1.15;
    logo_aspect =
        (sqrt(3) * logo_orbit + logo_dot) /
        (1.5 * logo_orbit + logo_dot);
    logo_height = 0.90 * size.y;
    logo_width = logo_aspect * logo_height;
    gap = 0.25 * size.y;
    copy_width = size.x - logo_width - 2 * gap;
    trimui_width = 0.545 * copy_width;
    brick_width = copy_width - trimui_width;
    left = -size.x / 2;
    trimui_x = left + trimui_width / 2;
    logo_x = left + trimui_width + gap + logo_width / 2;
    brick_x =
        left + trimui_width + gap + logo_width + gap +
        brick_width / 2;

    translate([trimui_x, 0])
        exact_centred_art_2d([trimui_width, size.y])
            label_text_2d(
                "TRIMUI", 3.0, "center", "center", brand_font);
    translate([logo_x, 0])
        exact_centred_art_2d([logo_width, logo_height])
            trimui_mark_2d(logo_dot, logo_orbit);
    translate([brick_x, 0])
        exact_centred_art_2d([brick_width, size.y])
            label_text_2d(
                "BRICK", 3.0, "center", "center", brand_font);
}

module regulatory_copy_2d() {
    line_spacing = 1.33;
    translate([0, line_spacing])
        label_text_2d(
            "MODEL: TG3040 . TRIMUI BRICK . DC 5V/3000mA . DESIGN BY",
            1.0, "center", "center", micro_font);
    label_text_2d(
        "TRIMUI . MADE IN CHINA. Built in rechareable li-po battery .",
        1.0, "center", "center", micro_font);
    translate([0, -line_spacing])
        label_text_2d(
            "Only can use certified charger. The battery may explode in the fire.",
            1.0, "center", "center", micro_font);
}

module fcc_mark_2d() {
    // Source-owned reconstruction of the FCC mark: the stepped F and
    // concentric open C arcs from the public-domain FCC vector.
    translate([-2.38, -1.90])
        polygon(points = [
            [1.22, 2.00], [0.40, 2.00], [0.40, 3.33],
            [1.38, 3.33], [1.68, 3.73], [0, 3.73],
            [0, -0.10], [0.40, 0.17], [0.40, 1.60],
            [1.22, 1.60]
        ]);
    for (arc = [
        [[0.48, 0], 0.93, 0.20, 31],
        [[0.33, 0], 1.78, 0.40, 35]
    ])
        translate(arc[0])
            difference() {
                difference() {
                    circle(r = arc[1], $fn = 72);
                    circle(r = arc[1] - arc[2], $fn = 72);
                }
                polygon(points = [
                    [0, 0],
                    [2.2 * arc[1] * cos(-arc[3]),
                     2.2 * arc[1] * sin(-arc[3])],
                    [2.2 * arc[1] * cos(arc[3]),
                     2.2 * arc[1] * sin(arc[3])]
                ]);
            }
}

module ce_mark_2d() {
    // Official 280:200 construction: two equal open rings, with the E's
    // centre stroke connected to its inner arc.
    for (centre_x = [-0.85, 0.85])
        translate([centre_x, 0])
            difference() {
                difference() {
                    circle(r = 1.0, $fn = 72);
                    circle(r = 0.70, $fn = 72);
                }
                translate([0.10, -1.05])
                    square([1.0, 2.10]);
            }
    translate([0.85 - 0.684, -0.15])
        square([0.584, 0.30]);
}

module recycle_arrow_2d() {
    polygon(points = [
        [-0.24, 0.30], [0.17, 1.13], [0.49, 0.97],
        [0.05, 1.87], [-0.85, 1.43], [-0.48, 1.28],
        [-0.91, 0.43]
    ]);
}

module recycle_mark_2d() {
    for (angle = [0, 120, 240])
        rotate(angle)
            translate([0, -0.10])
                recycle_arrow_2d();
}

module weee_mark_2d() {
    // Crossed-out wheeled bin plus the post-2005 underline.
    difference() {
        translate([-0.72, -0.82])
            polygon(points = [
                [0, 0], [1.44, 0], [1.22, 1.82], [0.22, 1.82]
            ]);
        translate([-0.50, -0.58])
            square([1.00, 1.15]);
    }
    translate([-0.92, 1.00]) square([1.84, 0.20]);
    translate([-0.35, 1.18]) square([0.70, 0.16]);
    translate([-0.51, -1.02]) circle(d = 0.30, $fn = 18);
    translate([0.51, -1.02]) circle(d = 0.30, $fn = 18);
    line_segment_2d([-1.04, 1.33], [1.04, -1.35], 0.20);
    line_segment_2d([-1.04, -1.35], [1.04, 1.33], 0.20);
    translate([-1.05, -1.56]) square([2.10, 0.20]);
}

module power_mark_2d() {
    difference() {
        difference() {
            circle(d = 2.55, $fn = 48);
            circle(d = 1.82, $fn = 48);
        }
        translate([-0.45, 0.35])
            square([0.90, 1.25]);
    }
    line_segment_2d([0, 0.10], [0, 1.26], 0.38);
}

module regulatory_lockup_2d() {
    fcc_x = regulatory_copy_size.x + copy_fcc_gap;
    ce_x = fcc_x + fcc_mark_width + fcc_ce_gap;
    recycle_x = ce_x + ce_mark_width + ce_recycle_gap;
    weee_x = recycle_x + recycle_mark_width + recycle_weee_gap;

    translate([regulatory_copy_size.x / 2, 0])
        exact_centred_art_2d(regulatory_copy_size)
            regulatory_copy_2d();
    translate([fcc_x + fcc_mark_width / 2, 0])
        exact_centred_art_2d([fcc_mark_width, regulatory_mark_height])
            fcc_mark_2d();
    translate([ce_x + ce_mark_width / 2, 0])
        exact_centred_art_2d([ce_mark_width, regulatory_mark_height])
            ce_mark_2d();
    translate([recycle_x + recycle_mark_width / 2, 0])
        exact_centred_art_2d(
            [recycle_mark_width, regulatory_mark_height])
                recycle_mark_2d();
    translate([weee_x + weee_mark_width / 2, 0])
        exact_centred_art_2d([weee_mark_width, regulatory_mark_height])
            weee_mark_2d();
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

module bottom_reset_cutout() {
    translate([bottom_reset_centre_x,
               bottom_reset_recess + 0.10,
               bottom_feature_z])
        rotate([90, 0, 0])
            cylinder(
                d = bottom_reset_diameter + 0.55,
                h = bottom_reset_recess + 0.35,
                $fn = 40);
}

module shell_volume() {
    color(shell_side_color)
        difference() {
            intersection() {
                rolled_outer_volume();
                stepped_profile_volume();
            }
            bottom_reset_cutout();
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
    for (row = [0 : 1], column = [0 : speaker_columns - 1])
        let(base_x = side == "left" ? speaker_left_x : speaker_right_x,
            direction = side == "left" ? 1 : -1,
            row_offset =
                row == 0 ? -speaker_stagger / 2 :
                           speaker_stagger / 2)
            [base_x +
                 direction *
                     ((column - (speaker_columns - 1) / 2) *
                      speaker_pitch_x + row_offset),
             speaker_y + row * speaker_pitch_y]
];

module speaker_array(side) {
    for (point = speaker_positions(side)) {
        color([0.006, 0.007, 0.009, 1.0])
            translate([point.x, point.y, front_z + 0.015])
                cylinder(d = speaker_hole_diameter,
                         h = 0.13, $fn = 12);
        color([0.18, 0.18, 0.18, 1.0])
            translate([point.x, point.y, front_z + 0.13])
                cylinder(d = speaker_hole_inner_diameter,
                         h = 0.025, $fn = 12);
    }
}

module front_printing() {
    // Owner-measured 15.9 mm lockup, kept tight and left justified.
    front_brand_art(
        [3.7 + front_brand_size.x / 2, 56.20, front_z + 0.055],
        front_brand_size, 0.05, silkscreen_color);
}

module host_port() {
    // The rear USB-C housing continues 4.44 mm beyond the 60 mm grip.
    color(shell_side_color)
        rounded_panel(
            [host_centre_x,
             rear_thick_length + host_housing_extension / 2],
            [host_housing_width, host_housing_extension],
            7.70, 0.72, 0.20);
    color([0.56, 0.57, 0.58, 1.0])
        xz_pill([host_centre_x,
                 rear_thick_length + host_housing_extension + 0.03,
                 4.15],
                [10.2, 3.55], 0.38);
    color(control_edge_color)
        xz_pill([host_centre_x,
                 rear_thick_length + host_housing_extension + 0.16,
                 4.15],
                [host_opening_width, 2.55], 0.42);
    color([0.45, 0.46, 0.47, 1.0])
        xz_pill([host_centre_x,
                 rear_thick_length + host_housing_extension + 0.28,
                 4.15],
                [6.15, 0.62], 0.46);
}

module rgb_light_bar() {
    // To the user this is one opaque diffuser, not a row of visible LEDs.
    diffuser_colour = [0.86, 0.87, 0.86, 1.0];
    color(diffuser_colour)
        xz_rounded_rect(
            [device_width / 2, device_height + 0.03,
             upper_rear_z + light_diffuser_size.y / 2],
            light_diffuser_size, 0.40, 0.34);
    // The same plastic turns down the rear face by 2 mm.
    color(diffuser_colour)
        rounded_panel(
            [device_width / 2,
             device_height - light_rear_drop / 2],
            [light_diffuser_size.x, light_rear_drop],
            0.20, 0.18, upper_rear_z - 0.19);
}

module bottom_ports() {
    edge_y = -0.12;

    // TF slot; its 1.45 mm opening height remains a visual estimate.
    color(control_edge_color)
        xz_pill([bottom_sd_centre_x, edge_y, bottom_feature_z],
                [bottom_sd_width, bottom_sd_height], 0.50);
    color([0.16, 0.17, 0.18, 1.0])
        xz_pill([bottom_sd_centre_x, edge_y - 0.27,
                 bottom_feature_z],
                [10.1, 0.42], 0.07);

    // Reset button face is one millimetre behind the bottom edge.
    color(control_edge_color)
        xz_ring([bottom_reset_centre_x, 0.45, bottom_feature_z],
                bottom_reset_diameter + 0.55,
                bottom_reset_diameter + 0.08, 1.25);
    color([0.15, 0.16, 0.17, 1.0])
        xz_pill([bottom_reset_centre_x,
                 bottom_reset_recess - 0.02,
                 bottom_feature_z],
                [bottom_reset_diameter, bottom_reset_diameter], 0.08);
    edge_label([bottom_reset_centre_x,
                bottom_reset_recess - 0.10,
                bottom_feature_z],
               "R", 1.05, "bottom", 0.05,
               silkscreen_color, micro_font);

    // DC USB-C.
    color([0.62, 0.63, 0.63, 1.0])
        xz_pill([bottom_usb_centre_x, edge_y, bottom_feature_z],
                [bottom_usb_width + 1.40, 4.05], 0.54);
    color(control_edge_color)
        xz_pill([bottom_usb_centre_x, edge_y - 0.19,
                 bottom_feature_z],
                [bottom_usb_width, 2.75], 0.58);
    color([0.40, 0.41, 0.42, 1.0])
        xz_pill([bottom_usb_centre_x, edge_y - 0.31,
                 bottom_feature_z],
                [6.10, 0.70], 0.06);

    // Microphone and audio.
    color(control_edge_color)
        xz_pill([bottom_mic_centre_x, edge_y, bottom_feature_z],
                [bottom_mic_diameter, bottom_mic_diameter], 0.55);
    color(control_edge_color)
        xz_pill([bottom_audio_centre_x, edge_y, bottom_feature_z],
                [bottom_audio_diameter, bottom_audio_diameter], 0.55);
    color([0.18, 0.19, 0.20, 1.0])
        xz_pill([bottom_audio_centre_x, edge_y - 0.25,
                 bottom_feature_z],
                [3.30, 3.30], 0.08);

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

    rear_brand_art([device_width / 2, 91.5, 7.52],
                   rear_brand_size, 0.055,
                   [0.68, 0.69, 0.70, 1.0]);
    rear_vector_art([device_width / 2, 88.5, 7.52],
                    rear_design_size, 0.05,
                    [0.48, 0.49, 0.50, 1.0])
        label_text_2d("DESIGN BY TRIMUI · MADE IN CHINA",
                      1.0, "center", "center", micro_font);

    screw_cross([5.2, 105.4], 7.57, true);
    screw_cross([device_width - 5.2, 105.4], 7.57, true);
}

module rear_lower_details() {
    // Shallow horizontal ribs on the thick lower grip.
    for (y = [7.0 : 2.25 : 55.0])
        color(rear_rib_color)
            translate([3.2, y, -0.23])
                cube([device_width - 6.4, 0.72, 0.20]);

    color([0.115, 0.118, 0.122, 1.0])
        translate([3.2, 18.4, -0.27])
            cube([device_width - 6.4, 8.0, 0.15]);

    if (SHOW_MICRO_DETAILS && SHOW_GLYPHS)
        color([0.50, 0.51, 0.52, 1.0])
            translate([device_width / 2, 22.4, -0.34])
                mirror([1, 0, 0])
                    linear_extrude(height = 0.05)
                        translate([-regulatory_lockup_width / 2, 0])
                            regulatory_lockup_2d();

    for (point = [
        [4.8, 56.0], [device_width - 4.8, 56.0],
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
            cylinder(d = face_button_diameter + 0.9,
                     h = 0.35, $fn = 40);
    color(active_color(id))
        translate([point.x, point.y, front_z + 0.30])
            bevel_cylinder(face_button_diameter, 1.45, 0.35);
    if (SHOW_GLYPHS)
        front_label([point.x, point.y, front_z + 1.74],
                    glyph, 2.7, 0.08,
                    is_active(id) ? highlight_dark_color
                                  : control_glyph_color,
                    "center", "center", ui_font);
}

module function_key(id, point) {
    color(control_edge_color)
        translate([point.x, point.y, front_z + 0.02])
            linear_extrude(height = 0.28)
                pill_2d(f_key_size.x + 0.55,
                        f_key_size.y + 0.50);
    color(active_color(id, silver_key_color))
        translate([point.x, point.y, front_z + 0.27])
            linear_extrude(height = 0.76, scale = 0.94)
                pill_2d(f_key_size.x, f_key_size.y);
}

module three_dot_icon(point, z, colour) {
    // Menu mark: one dot over a two-dot base.
    for (offset = [[0, 0.62], [-0.58, -0.42], [0.58, -0.42]])
        color(colour)
            translate([point.x + offset.x, point.y + offset.y, z])
                cylinder(d = 0.68, h = 0.07, $fn = 18);
}

module system_button(id, point, symbol) {
    color(control_edge_color)
        translate([point.x, point.y, front_z + 0.02])
            cylinder(d = system_button_diameter + 0.70,
                     h = 0.32, $fn = 36);
    color(active_color(id))
        translate([point.x, point.y, front_z + 0.30])
            bevel_cylinder(system_button_diameter, 1.05, 0.28);

    glyph_colour = is_active(id) ? highlight_dark_color
                                 : system_glyph_color;
    if (SHOW_GLYPHS) {
        if (symbol == "menu")
            three_dot_icon(point, front_z + 1.34, glyph_colour);
        else if (symbol == "select")
            color(glyph_colour)
                translate([point.x - 1.10, point.y - 0.25,
                           front_z + 1.34])
                    cube([2.20, 0.50, 0.07]);
        else
            color(glyph_colour)
                translate([point.x, point.y, front_z + 1.34])
                    linear_extrude(height = 0.07)
                        polygon(points = [
                            [1.12, 0], [-0.72, 1.00], [-0.72, -1.00]
                        ]);
    }
}

module shoulder_wedge_geometry(x_start, width, y_start, extension,
                               outer_side = "none") {
    back_z = 0.55;
    screen_z = 7.55;
    rear_top = y_start + extension - shoulder_bevel;
    screen_top = y_start + extension;
    rear_x0 =
        outer_side == "left" ? x_start + shoulder_bevel : x_start;
    rear_x1 =
        outer_side == "right" ?
            x_start + width - shoulder_bevel : x_start + width;

    polyhedron(
        points = [
            [rear_x0, y_start, back_z],
            [rear_x1, y_start, back_z],
            [rear_x1, rear_top, back_z],
            [rear_x0, rear_top, back_z],
            [x_start, y_start, screen_z],
            [x_start + width, y_start, screen_z],
            [x_start + width, screen_top, screen_z],
            [x_start, screen_top, screen_z]
        ],
        faces = [
            [0, 3, 2, 1],
            [4, 5, 6, 7],
            [0, 1, 5, 4],
            [1, 2, 6, 5],
            [2, 3, 7, 6],
            [3, 0, 4, 7]
        ],
        convexity = 4);
}

module shoulder_control(id, x_start, width, y_start, extension,
                        glyph, outer_side = "none") {
    color(active_color(id))
        shoulder_wedge_geometry(
            x_start, width, y_start, extension, outer_side);

    // Rear-readable artwork replaces the previous upside-down top labels.
    if (SHOW_GLYPHS)
        rear_label(
            [x_start + width / 2,
             y_start + (extension - shoulder_bevel) / 2,
             0.43],
            glyph, 2.15, 0.07,
            is_active(id) ? highlight_dark_color
                          : control_glyph_color,
            "center", "center", ui_font);
}

module volume_control(id, y, glyph) {
    color(control_edge_color)
        yz_rounded_rect([-0.08, y, 14.1],
                        volume_key_size + [0.55, 0.45],
                        0.70, 1.55);
    color(active_color(id))
        yz_rounded_rect([-0.42, y, 14.1],
                        volume_key_size, 0.78, 1.40);
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
        yz_rounded_rect([device_width + 0.08, fn_centre_y, 13.5],
                        fn_track_size, 0.70, 1.55);
    color(active_color(id))
        yz_rounded_rect([device_width + 0.43,
                         fn_centre_y - 0.65, 13.5],
                        [fn_slider_length, fn_track_size.y],
                        0.80, 1.45);
    if (SHOW_MICRO_DETAILS)
        for (offset = [-2.2 : 0.8 : 2.2])
            color(is_active(id) ? highlight_dark_color
                                : [0.10, 0.105, 0.11, 1.0])
                translate([device_width + 0.83,
                           fn_centre_y - 0.65 + offset - 0.12,
                           12.2])
                    cube([0.08, 0.24, 2.6]);
}

module power_control() {
    id = "btn_power";
    color(control_edge_color)
        yz_rounded_rect([device_width + 0.08, power_centre_y, 13.8],
                        power_key_size + [0.55, 0.45],
                        0.70, 1.70);
    color(active_color(id, power_key_color))
        yz_rounded_rect([device_width + 0.43,
                         power_centre_y, 13.8],
                        power_key_size, 0.80, 1.55);
    color(is_active(id) ? highlight_dark_color
                        : [0.00, 0.35, 0.38, 1.0])
        translate([device_width + 0.84, power_centre_y, 13.8])
            rotate([90, 0, 90])
                linear_extrude(height = 0.07)
                    rotate(-90)
                        power_mark_2d();
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
        function_key(id, f1_centre);
    else if (id == "btn_f2")
        function_key(id, f2_centre);
    else if (id == "btn_menu")
        system_button(id, menu_centre, "menu");
    else if (id == "btn_select")
        system_button(id, select_centre, "select");
    else if (id == "btn_start")
        system_button(id, start_centre, "start");
    else if (id == "btn_l1")
        shoulder_control(
            id, shoulder_l1_start, shoulder_outer_width,
            rear_thick_length, shoulder_outer_extension,
            "L1", "left");
    else if (id == "trig_l")
        shoulder_control(
            id, shoulder_l2_start, shoulder_inner_width,
            rear_thick_length + 2.0, shoulder_inner_extension,
            "L2");
    else if (id == "trig_r")
        shoulder_control(
            id, shoulder_r2_start, shoulder_inner_width,
            rear_thick_length + 2.0, shoulder_inner_extension,
            "R2");
    else if (id == "btn_r1")
        shoulder_control(
            id, shoulder_r1_start, shoulder_outer_width,
            rear_thick_length, shoulder_outer_extension,
            "R1", "right");
    else if (id == "vol_up")
        volume_control(id, volume_up_centre_y, "+");
    else if (id == "vol_down")
        volume_control(id, volume_down_centre_y, "-");
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
