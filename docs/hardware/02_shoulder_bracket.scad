// ============================================================================
// P3_Shoulder_Bracket
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


U_W = 14; U_D = 34; U_H = 28; U_WALL = WALL;
FLANGE_W = 32; FLANGE_D = 22; FLANGE_T = 3;

module shoulder_bracket() {
    difference() {
        union() {
            translate([0, 0, FLANGE_T/2])
                cube([FLANGE_W, FLANGE_D, FLANGE_T], center=true);
            translate([-(U_W/2 + U_WALL/2), 0, U_H/2 + FLANGE_T])
                cube([U_WALL, U_D, U_H], center=true);
            translate([U_W/2 + U_WALL/2, 0, U_H/2 + FLANGE_T])
                cube([U_WALL, U_D, U_H], center=true);
            translate([0, -(U_D/2 + U_WALL/2), U_H/2 + FLANGE_T])
                cube([U_W + 2*U_WALL, U_WALL, U_H], center=true);
        }
        for(i=[0:3])
            rotate([0, 0, i*90])
            translate([10, 0, -1])
            cylinder(h=FLANGE_T+2, d=M2_D);
        for(side=[-1,1]) for(hole=[-1,1])
            translate([side*(U_W/2 + U_WALL/2), hole*SG90_EAR_SPAN_X/2, SG90_AXIS_H - 5])
            rotate([0, 90, 0])
            cylinder(h=U_WALL+2, d=M2_D);
        translate([-(U_W/2 + U_WALL + 1), 0, SG90_AXIS_H])
            rotate([0, 90, 0])
            cylinder(h=U_WALL+2, d=8);
    }
}
shoulder_bracket();
