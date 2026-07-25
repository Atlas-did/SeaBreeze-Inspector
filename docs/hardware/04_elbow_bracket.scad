// ============================================================================
// 04_Elbow_Bracket
// ============================================================================
// SeaBreeze-Inspector 3DOF 机械臂 — 肘部/小臂舵机支架
// 安装SG90舵机(S3)，U型槽内宽12.3mm适配机身宽11.8mm
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


// 肘部支架参数（基于 STL 包围盒 30.5 x 24.5 x 32）
FLANGE_W = 30;      // 法兰宽度 (x)
FLANGE_D = 24;      // 法兰深度 (y)
FLANGE_T = 3;       // 法兰厚度 (z)

U_W = 12.3;         // U型槽内宽 — 适配 SG90 机身宽 11.8mm，留 0.5mm 间隙
U_D = 22.5;         // U型槽内深 — 适配 SG90 机身长 22.2mm，留 0.3mm 间隙
U_H = 28;           // U型槽内高 — 适配 SG90 轴高 26.5mm，留 1.5mm 间隙
U_WALL = WALL;      // 槽壁厚度

module elbow_bracket() {
    difference() {
        union() {
            // 法兰底座
            translate([0, 0, FLANGE_T/2])
                cube([FLANGE_W, FLANGE_D, FLANGE_T], center=true);
            
            // U型槽左壁 (x方向)
            translate([-(U_W/2 + U_WALL/2), 0, U_H/2 + FLANGE_T])
                cube([U_WALL, U_D, U_H], center=true);
            
            // U型槽右壁 (x方向)
            translate([U_W/2 + U_WALL/2, 0, U_H/2 + FLANGE_T])
                cube([U_WALL, U_D, U_H], center=true);
            
            // U型槽底壁 (y方向背面)
            translate([0, -(U_D/2 + U_WALL/2), U_H/2 + FLANGE_T])
                cube([U_W + 2*U_WALL, U_WALL, U_H], center=true);
        }
        
        // 法兰安装孔 (4个，对称分布)
        for(i=[0:3])
            rotate([0, 0, i*90])
            translate([10, 0, -1])
            cylinder(h=FLANGE_T+2, d=M2_D);
        
        // SG90 安装耳孔 (侧壁上，x方向穿透)
        for(side=[-1,1]) for(hole=[-1,1])
            translate([side*(U_W/2 + U_WALL/2), hole*SG90_EAR_SPAN_X/2, SG90_AXIS_H - 5])
            rotate([0, 90, 0])
            cylinder(h=U_WALL+2, d=M2_D);
        
        // SG90 输出轴孔 (底壁上，y方向穿透)
        translate([0, -(U_D/2 + U_WALL + 1), SG90_AXIS_H])
            rotate([90, 0, 0])
            cylinder(h=U_WALL+2, d=8);
        
        // 减重槽（可选，如需要可取消注释）
        // translate([0, U_D/4, U_H/2 + FLANGE_T + 5])
        //     cube([U_W - 4, U_D/2, U_H/2], center=true);
    }
}

elbow_bracket();
