// ============================================================================
// 07_Coupler
// ============================================================================
// SeaBreeze-Inspector 3DOF 机械臂 — 舵盘联轴器/转接器
// 连接 SG90 舵盘与连杆，适配舵机轴 φ4.8mm
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


// 联轴器参数（基于 STL 包围盒 30 x 20 x 6）
DISC_D = 20;        // 主圆盘直径
DISC_T = 6;         // 主圆盘厚度
AXIS_HOLE_D = 5.5;  // 中心轴孔 — 适配 SG90 舵机轴 φ4.8mm，留 0.7mm 间隙
SET_SCREW_D = M2_D; // 顶丝孔

// 偏心法兰（连接连杆）
FLANGE_OFF_X = 12;  // 法兰偏移距离
FLANGE_W = 12;      // 法兰宽度
FLANGE_D = 10;      // 法兰深度
FLANGE_HOLE_D = M2_D;

module coupler() {
    difference() {
        union() {
            // 主圆盘（连接舵盘）
            cylinder(h=DISC_T, d=DISC_D);
            
            // 中心轴套加强
            cylinder(h=DISC_T + 1, d=8);
            
            // 偏心法兰（连接连杆）
            translate([FLANGE_OFF_X, 0, DISC_T/2])
                cube([FLANGE_W, FLANGE_D, DISC_T], center=true);
        }
        
        // 中心轴孔（通孔）
        translate([0, 0, -1])
            cylinder(h=DISC_T + 3, d=AXIS_HOLE_D);
        
        // 顶丝孔（M2，垂直于轴，2个互成90°）
        translate([DISC_D/2 - 2, 0, DISC_T/2])
            rotate([0, 90, 0])
            cylinder(h=5, d=SET_SCREW_D);
        translate([0, DISC_D/2 - 2, DISC_T/2])
            rotate([90, 0, 0])
            cylinder(h=5, d=SET_SCREW_D);
        
        // 法兰安装孔
        translate([FLANGE_OFF_X, 0, -1])
            cylinder(h=DISC_T+2, d=FLANGE_HOLE_D);
    }
}

coupler();
