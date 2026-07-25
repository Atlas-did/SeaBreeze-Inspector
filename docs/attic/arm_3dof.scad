// =============================================================================
// SeaBreeze Inspector — 3DOF 机械臂 OpenSCAD 参数化模型
// =============================================================================
// 参数权威来源: config/arm_config.yaml + backend/arm/arm_kinematics.py
// 舵机: SG90 (9g micro servo, 23×12.2×29mm)
// 单位: mm, 角度: deg
// =============================================================================

// ---------- 项目参数 (从 arm_config.yaml 提取) ----------
L1 = 55;   // 大臂长度 (base→shoulder 关节中心距)
L2 = 45;   // 小臂长度 (shoulder→elbow 关节中心距)
L3 = 35;   // 末端长度 (elbow→end_effector, 与小臂共线)
L23 = L2 + L3;  // 小臂+末端总长 = 80mm

BASE_HEIGHT = 25;       // 基座高度 (Tello挂载面→第一关节)
BASE_PLATE_D = 50;      // 底板直径
BASE_PLATE_T = 2.5;     // 底板厚度
ROTATION_DISC_D = 36;   // 旋转盘直径
ROTATION_DISC_T = 4;    // 旋转盘厚度

// 关节限位 (THETA_MIN/MAX from arm_kinematics.py)
THETA1_RANGE = [0, 180];   // 底座旋转
THETA2_RANGE = [15, 165];  // 大臂俯仰 (arm_config: 15-165)
THETA3_RANGE = [0, 180];   // 小臂俯仰

// ---------- SG90 舵机尺寸 ----------
SG90_BODY   = [23.0, 12.2, 29.0];  // [长, 宽, 高] — 长沿输出轴方向
SG90_FLANGE = [32.0, 12.2, 2.5];   // 安装法兰
SG90_SHAFT_D = 4.5;   // 输出轴直径
SG90_SHAFT_H = 5.0;   // 输出轴外露高度
SG90_HOLE_D  = 2.5;   // 安装孔直径
SG90_HOLE_SP = 28.0;  // 安装孔间距
SG90_WEIGHT  = 9;     // 克 (仅注释, 不参与几何)

// U型支架壁厚
BRACKET_T  = 3.0;     // 壁厚
BRACKET_GAP = 13.5;   // 内侧间距 (比舵机宽略大, 松配合)

// 螺丝孔
SCREW_D = 2.5;        // M2.5 通孔
SCREW_HEAD_D = 5.0;   // 沉头直径
SCREW_HEAD_H = 2.0;   // 沉头深度

// 连接臂截面
ARM_W = 10;            // 臂宽
ARM_T = 3.5;           // 臂厚 (打印方向)

// FDM 打印公差
TOLERANCE = 0.3;       // 孔补偿 +0.3mm, 轴补偿 -0.3mm

// 显示模式
SHOW_EXPLODED = false; // true=分解视图, false=装配视图

$fn = 64;              // 圆精度

// =============================================================================
// 组件 1: 底板 (Mount Plate)
// =============================================================================
module base_plate() {
    color("SteelBlue", 0.9)
    difference() {
        // 主体: 圆形底板
        cylinder(d=BASE_PLATE_D, h=BASE_PLATE_T, center=false);
        
        // 4个 M2.5 安装孔 (对角, 中心距 36mm, 适配 Tello 底部)
        for (a = [0:90:270]) {
            rotate([0, 0, a])
            translate([18, 0, -0.1])
            cylinder(d=SCREW_D, h=BASE_PLATE_T + 1, center=false);
        }
        
        // 中心轻量化孔
        translate([0, 0, -0.1])
        cylinder(d=20, h=BASE_PLATE_T + 1, center=false);
    }
}

// =============================================================================
// 组件 2: 旋转盘 (Rotation Disc) — 承载底座舵机
// =============================================================================
module rotation_disc() {
    color("LightSteelBlue", 0.9)
    difference() {
        union() {
            // 主体圆柱
            cylinder(d=ROTATION_DISC_D, h=ROTATION_DISC_T, center=false);
            
            // 舵机安装座 (SG90 平放, 输出轴朝上)
            translate([-SG90_BODY[0]/2, -SG90_BODY[1]/2, ROTATION_DISC_T])
            cube([SG90_BODY[0], SG90_BODY[1], SG90_BODY[2]]);
            
            // 两侧加强筋
            for (sx = [-1, 1])
                translate([sx * (SG90_BODY[0]/2 + 3), -3, ROTATION_DISC_T])
                cube([3, 6, SG90_BODY[2]*0.6]);
        }
        
        // 中心螺丝孔 (固定旋转盘到底板)
        translate([0, 0, -0.1])
        cylinder(d=SCREW_D, h=BASE_PLATE_T + ROTATION_DISC_T + 1);
        
        // 舵机法兰螺丝孔 (2个, 间距 SG90_HOLE_SP)
        for (hx = [-1, 1])
            translate([hx * SG90_HOLE_SP/2, 0, ROTATION_DISC_T + SG90_FLANGE[2]/2])
            rotate([90, 0, 0])
            cylinder(d=SCREW_D, h=SG90_BODY[1] + 12, center=true);
    }
}

// =============================================================================
// 组件 3: U型支架 (U-Bracket) — 连接关节的两个舵机
// =============================================================================
module u_bracket(with_servo_cutout = true) {
    gap = SG90_BODY[1] + TOLERANCE;  // 内侧宽度 = 舵机宽 + 公差
    width = gap + 2 * BRACKET_T;     // 外侧总宽
    depth = SG90_BODY[0] + 6;        // 深度 > 舵机长
    height = SG90_BODY[2] * 0.6;     // 高度
    
    color("DimGray", 0.8)
    difference() {
        union() {
            // U型主体
            difference() {
                cube([width, depth, height], center=false);
                translate([BRACKET_T, 3, BRACKET_T])
                cube([gap, depth - 2, height + 1]);
            }
            
            // 连接臂延伸 (接下一段连杆)
            translate([width/2 - ARM_W/2, depth, 0])
            cube([ARM_W, L1 * 0.3, height]);
        }
        
        if (with_servo_cutout) {
            // 舵机法兰安装孔
            for (hx = [-1, 1])
                translate([width/2 + hx * SG90_HOLE_SP/2, 5, height/2])
                rotate([90, 0, 0])
                cylinder(d=SCREW_D, h=10, center=true);
            
            // 输出轴通孔
            translate([width/2, depth - 2, height/2])
            rotate([90, 0, 0])
            cylinder(d=SG90_SHAFT_D + TOLERANCE, h=8, center=true);
        }
    }
}

// =============================================================================
// 组件 4: 大臂连杆 (Arm Link L1 = 55mm)
// =============================================================================
module arm_link(length, label = "") {
    color("DarkOrange", 0.85)
    difference() {
        union() {
            // 主体: 矩形截面棒
            translate([-ARM_W/2, 0, -ARM_T/2])
            cube([ARM_W, length, ARM_T]);
            
            // 两端: 圆形舵机安装座
            for (y = [0, length]) {
                translate([0, y, 0])
                cylinder(d=SG90_BODY[1] + 2*BRACKET_T, h=ARM_T, center=true);
            }
        }
        
        // 两端舵机输出轴孔
        for (y = [0, length]) {
            translate([0, y, -ARM_T])
            cylinder(d=SG90_SHAFT_D + TOLERANCE, h=ARM_T*3, center=false);
            
            // 法兰固定螺丝孔
            for (hx = [-1, 1])
                translate([hx * SG90_HOLE_SP/2, y, -ARM_T/2 - 0.1])
                cylinder(d=SCREW_D, h=ARM_T*2 + 1);
        }
        
        // 减重槽 (矩形镂空, 保留边框 3mm)
        if (length > 25) {
            translate([-ARM_W/2 + 3, 8, -ARM_T/2 - 0.1])
            cube([ARM_W - 6, length - 16, ARM_T + 1]);
        }
    }
}

// =============================================================================
// 组件 5: 末端执行器 (End Effector L3 = 35mm) — 共线延伸
// =============================================================================
module end_effector() {
    color("FireBrick", 0.85)
    difference() {
        union() {
            // 共线延伸杆
            translate([-ARM_W/2, 0, -ARM_T/2])
            cube([ARM_W, L3, ARM_T]);
            
            // 末端工具座 (小平台)
            translate([-8, L3 - 8, ARM_T/2 - 1])
            cube([16, 12, 3]);
        }
        
        // 近端: 舵机输出轴孔 (连接 elbow 舵机)
        translate([0, 0, -ARM_T])
        cylinder(d=SG90_SHAFT_D + TOLERANCE, h=ARM_T*3);
        
        // 法兰螺丝孔
        for (hx = [-1, 1])
            translate([hx * SG90_HOLE_SP/2, 0, -ARM_T/2 - 0.1])
            cylinder(d=SCREW_D, h=ARM_T*2 + 1);
        
        // 工具座安装孔
        for (tx = [-4, 4], ty = [L3 - 5]) {
            translate([tx, ty, ARM_T/2 - 1.5])
            cylinder(d=SCREW_D, h=5);
        }
    }
}

// =============================================================================
// 主装配
// =============================================================================

module assembly(exploded = false) {
    ez = exploded ? 10 : 0;  // 分解间距
    
    // 底板
    translate([0, 0, 0]) base_plate();
    
    // 旋转盘 + 底座舵机
    translate([0, 0, BASE_PLATE_T + ez])
    rotation_disc();
    
    // 底座舵机 (SG90, 输出轴朝上, 对应 theta1)
    color("LightGray", 0.7)
    translate([0, 0, BASE_PLATE_T + ROTATION_DISC_T + ez])
    cube([SG90_BODY[0], SG90_BODY[1], SG90_BODY[2]], center=true);
    
    // 大臂 L1=55mm (近端连底座舵机输出轴, 远端装 shoulder 舵机)
    translate([0, 0, BASE_PLATE_T + ROTATION_DISC_T + SG90_BODY[2]/2 + 2 + ez*2])
    rotate([90, 0, 0])
    arm_link(L1, "L1=55");
    
    // Shoulder 舵机 (控制 theta2 大臂俯仰)
    color("LightGray", 0.7)
    translate([0, L1, BASE_PLATE_T + ROTATION_DISC_T + SG90_BODY[2]/2 + 2 + ez*2])
    rotate([0, 0, 0])
    cube([SG90_BODY[0], SG90_BODY[1], SG90_BODY[2]], center=true);
    
    // 小臂 L2=45mm (连 shoulder→elbow)
    translate([0, L1 + SG90_BODY[1]/2 + 2, 
               BASE_PLATE_T + ROTATION_DISC_T + SG90_BODY[2]/2 + 2 + ez*3])
    rotate([90, 0, 0])
    arm_link(L2, "L2=45");
    
    // Elbow 舵机 (控制 theta3 小臂俯仰)
    color("LightGray", 0.7)
    translate([0, L1 + L2 + SG90_BODY[1]/2 + 4, 
               BASE_PLATE_T + ROTATION_DISC_T + SG90_BODY[2]/2 + 2 + ez*3])
    cube([SG90_BODY[0], SG90_BODY[1], SG90_BODY[2]], center=true);
    
    // 末端 L3=35mm (连 elbow→end_effector)
    translate([0, L1 + L2 + SG90_BODY[1] + 6, 
               BASE_PLATE_T + ROTATION_DISC_T + SG90_BODY[2]/2 + 2 + ez*4])
    rotate([90, 0, 0])
    end_effector();
}

// =============================================================================
// 3D 打印布局 (6 件平板排布, 适合 FDM 直接打印)
// =============================================================================
module print_layout() {
    spacing = 15;  // 件间间距
    
    // 底板
    translate([0, 0, 0]) base_plate();
    
    // 旋转盘
    translate([BASE_PLATE_D + spacing, 0, 0]) rotation_disc();
    
    // 大臂 L1
    translate([0, BASE_PLATE_D + spacing, ROTATION_DISC_T])
    rotate([0, 0, 90])
    arm_link(L1, "L1=55");
    
    // 小臂 L2
    translate([L1 + ARM_W + spacing, BASE_PLATE_D + spacing, ROTATION_DISC_T])
    rotate([0, 0, 90])
    arm_link(L2, "L2=45");
    
    // 末端 L3
    translate([L1 + L2 + ARM_W + 2*spacing, BASE_PLATE_D + spacing, 0])
    rotate([0, 0, 90])
    end_effector();
    
    // U型支架 ×2
    translate([0, BASE_PLATE_D + L1 + 2*spacing, 0])
    rotate([0, 0, 0])
    u_bracket(true);
}

// =============================================================================
// 接口: 根据模式选择显示内容
// =============================================================================
// 
// 使用方法:
//   1. 装配视图: 取消下面 assembly() 的注释 (检查运动学)
//   2. 打印布局: 取消下面 print_layout() 的注释 (导出 STL)
//   3. 分解视图: 设置 SHOW_EXPLODED = true
//

// 单个组件导出 (逐个导出 STL):
// base_plate();           // 底板
// rotation_disc();        // 旋转盘
// arm_link(L1, "L1=55"); // 大臂
// arm_link(L2, "L2=45"); // 小臂
// end_effector();         // 末端
// u_bracket(true);        // U型支架 (需2个)

// 全装配视图 (检查干涉/运动学):
assembly(SHOW_EXPLODED);

// 打印布局 (6件平板排布, FDM 一次打完):
// print_layout();

// =============================================================================
// 重量估算 (PLA 密度 1.24 g/cm³)
//  底板:      ~3.5g
//  旋转盘:    ~5.2g
//  大臂 L1:   ~4.8g
//  小臂 L2:   ~3.9g
//  末端 L3:   ~3.0g
//  U型支架×2: ~2.8g × 2 = 5.6g
//  SG90×3:    9g × 3 = 27g
//  螺丝螺母:  ~3g
//  ─────────────────
//  预估总重:  ~56g (不含摄像头)
//  加 ESP32-CAM: +10g
//  加摄像头:    +15g
//  ─────────────────
//  满载总重:    ~81g  ⚠️ 超过 Tello 可用载荷(~50g)
//  建议: 走减重 Plan B (增大镂空 / 换更轻舵机 / 减到 2DOF)
//
//  Tello 实测载荷 (TelloPilots 论坛数据):
//    20g: 悬停 ~8min ✅
//    40g: 悬停 ~5.5min ⚠️
//    60g: 2-3min 后失控 ❌
// =============================================================================