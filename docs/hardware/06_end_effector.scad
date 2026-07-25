// ============================================================================
// P6_End_Effector_Mount
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


MOUNT_L = L3; MOUNT_W = LINK_W; MOUNT_T = LINK_T;
CAM_W = 20; CAM_D = 20; CAM_H = 8;

module end_effector_mount() {
    difference() {
        union() {
            translate([MOUNT_L/2, 0, MOUNT_T/2])
                cube([MOUNT_L, MOUNT_W, MOUNT_T], center=true);
            cylinder(h=MOUNT_T + 2, d=12);
            translate([MOUNT_L, 0, CAM_H/2 + MOUNT_T/2])
                cube([CAM_D, CAM_W, CAM_H], center=true);
            translate([MOUNT_L - 5, 0, MOUNT_T/2])
                cube([10, MOUNT_W, MOUNT_T + 4], center=true);
        }
        translate([0, 0, -1])
            cylinder(h=MOUNT_T+4, d=M2_D);
        for(side=[-1,1])
            translate([MOUNT_L, side*8, MOUNT_T/2 + CAM_H/2])
            rotate([90, 0, 0])
            cylinder(h=CAM_W+2, d=M2_D);
        translate([MOUNT_L/2, 0, -1])
            scale([2, 0.6, 1])
            cylinder(h=MOUNT_T+2, d=MOUNT_W * 0.5);
    }
}
end_effector_mount();
