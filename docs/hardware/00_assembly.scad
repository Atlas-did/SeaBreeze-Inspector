// ============================================================================
// AS_Assembly — 3DOF Robotic Arm for SeaBreeze Inspector
// ============================================================================
// Usage: Place all 01-07 .scad files in same directory, open this file.
// Render with OpenSCAD: F6 (CGAL) for STL export.
//
// Joint limits match arm_config.yaml:
//   θ1 (base yaw):    [0, 180] deg
//   θ2 (shoulder):    [30, 150] deg
//   θ3 (elbow):       [0, 135] deg
//
// Default pose: θ1=90, θ2=90, θ3=45 (home position)
// ============================================================================

$fn = 60;

// ---- Pose (degrees) — change these to preview different arm poses ----
theta1 = 90;   // base yaw
theta2 = 90;   // shoulder pitch
theta3 = 45;   // elbow pitch

// Helpers
function rad(d) = d * 3.14159 / 180;

// ---- Part files (uncomment when exporting to STL) ----
// For assembly preview, include parts. For individual STL export, comment out others.
include <01_base_plate.scad>
include <02_shoulder_bracket.scad>
include <03_upper_arm.scad>
include <04_elbow_bracket.scad>
include <05_forearm.scad>
include <06_end_effector.scad>
include <07_coupler.scad>

// ---- Assembly ----
module assembly(theta1=90, theta2=90, theta3=45) {
    // Base plate (fixed to drone)
    base_plate();

    // J1: base rotation (yaw)
    translate([0, 0, 3])
    rotate([0, 0, rad(theta1 - 90)])
    shoulder_bracket();

    // J2: shoulder pitch
    translate([0, 0, 30])
    rotate([0, rad(90 - theta2), 0])
    upper_arm();

    // J3: elbow pitch
    translate([0, 0, 30 + 55])
    rotate([0, rad(-theta3 + 45), 0])
    translate([0, 0, -55])
    elbow_bracket();

    // Forearm (L2 = 45mm)
    translate([0, 0, 30 + 55 + 45])
    rotate([0, rad(-theta3 + 45), 0])
    translate([0, 0, -55])
    translate([0, 0, 0])
    forearm();

    // End effector (L3 = 35mm)
    translate([0, 0, 30 + 55 + 45 + 35])
    rotate([0, rad(-theta3 + 45), 0])
    translate([0, 0, -55])
    translate([0, 0, 0])
    end_effector();

    // Coupler
    coupler();
}

// Render
assembly(theta1, theta2, theta3);
