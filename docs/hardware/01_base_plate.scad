// ============================================================================
// P1_Base_Mount
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


BP_W = 50; BP_D = 50; BP_T = 4;
TELLO_HOLE_D = M3_D; TELLO_HOLE_OFF = 5;
PCA_MX = -18; PCA_MY = 16; PCA_MH = 6;
NANO_MX = 18; NANO_MY = 16; NANO_MH = 4;

module base_mount() {
    difference() {
        union() {
            translate([0, 0, BP_T/2])
                cube([BP_W, BP_D, BP_T], center=true);
            translate([PCA_MX, PCA_MY, BP_T])
                cylinder(h=PCA_MH, d=5);
            translate([PCA_MX + 55, PCA_MY, BP_T])
                cylinder(h=PCA_MH, d=5);
            translate([NANO_MX, NANO_MY, BP_T])
                cylinder(h=NANO_MH, d=4);
            translate([NANO_MX, NANO_MY - 30, BP_T])
                cylinder(h=NANO_MH, d=4);
        }
        for(mx=[-1,1]) for(my=[-1,1])
            translate([mx*(BP_W/2 - TELLO_HOLE_OFF), my*(BP_D/2 - TELLO_HOLE_OFF), -1])
            cylinder(h=BP_T+2, d=TELLO_HOLE_D);
        translate([0, 0, BP_T - 1.5])
            cube([SG90_BODY_L + 1, SG90_BODY_W + 1, 2], center=true);
        for(mx=[-1,1]) for(my=[-1,1])
            translate([mx*SG90_EAR_SPAN_X/2, my*SG90_EAR_SPAN_Y/2, -1])
            cylinder(h=BP_T+2, d=M2_D);
        translate([PCA_MX, PCA_MY, BP_T + 2])
            cylinder(h=PCA_MH, d=M2p5_D);
        translate([PCA_MX + 55, PCA_MY, BP_T + 2])
            cylinder(h=PCA_MH, d=M2p5_D);
        translate([NANO_MX, NANO_MY, BP_T])
            cylinder(h=NANO_MH, d=M2_D);
        translate([NANO_MX, NANO_MY - 30, BP_T])
            cylinder(h=NANO_MH, d=M2_D);
    }
}
base_mount();
