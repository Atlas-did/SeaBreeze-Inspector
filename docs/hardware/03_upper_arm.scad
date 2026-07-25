// ============================================================================
// P4_Upper_Arm_Link
// ============================================================================
// SeaBreeze-Inspector 3DOF 机械臂 — 3D打印零件
// 参数与代码完全吻合: L1=55, L2=45, L3=35, base_height=25
// 生成日期: 2026
// ============================================================================

$fn = 60;

L1 = 55;
L2 = 45;
L3 = 35;
BASE_H = 25;

// SG90 舵机参数 (mm)
SG90_BODY_W = 22.2;
SG90_BODY_H = 11.8;
SG90_BODY_L = 31.0;
SG90_AXIS_H = 26.5;
SG90_AXIS_D = 4.8;
SG90_EAR_HOLE_D = 2.0;
SG90_EAR_SPAN_X = 10.0;
SG90_EAR_SPAN_Y = 22.5;

// 紧固件
M2_D = 2.2;
M2p5_D = 2.7;
M3_D = 3.2;

// 打印参数
WALL = 2.0;
LINK_W = 15.0;
LINK_T = 3.0;


ARM_L = L1; ARM_W = LINK_W; ARM_T = LINK_T;
AXIS_HOLE_D = 5.5; SET_SCREW_D = M2_D;
FORK_W = 14; FORK_D = 32; FORK_WALL = WALL;

module upper_arm_link() {
    difference() {
        union() {
            translate([ARM_L/2, 0, ARM_T/2])
                cube([ARM_L, ARM_W, ARM_T], center=true);
            cylinder(h=ARM_T + 2, d=12);
            translate([ARM_L, 0, ARM_T/2])
                cube([FORK_D, ARM_W + 4, ARM_T], center=true);
        }
        translate([0, 0, -1])
            cylinder(h=ARM_T+4, d=AXIS_HOLE_D);
        translate([6, 0, ARM_T/2])
            rotate([0, 90, 0]) cylinder(h=8, d=SET_SCREW_D);
        translate([0, 6, ARM_T/2])
            rotate([90, 0, 0]) cylinder(h=8, d=SET_SCREW_D);
        translate([ARM_L/2, 0, -1])
            scale([2, 0.6, 1])
            cylinder(h=ARM_T+2, d=ARM_W * 0.5);
        translate([ARM_L + FORK_D/2 - FORK_WALL, 0, ARM_T/2])
            cube([FORK_D, FORK_W, ARM_T+2], center=true);
        for(side=[-1,1]) for(hole=[-1,1])
            translate([ARM_L + 8, side*FORK_W/2, SG90_AXIS_H - ARM_T/2])
            rotate([90, 0, 0])
            cylinder(h=FORK_WALL+2, d=M2_D);
    }
}
upper_arm_link();
