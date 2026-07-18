# =============================================================================
# SeaBreeze Inspector — Blender 参数化建模脚本 (bpy)
# -----------------------------------------------------------------------------
# 用法:
#   1. 把本文件重命名为 seabreeze_models_bpy.py  (去掉 .txt 后缀)
#   2. 命令行无头运行:  blender -b -P seabreeze_models_bpy.py
#      或在 Blender 的 Scripting 工作区打开 → Run Script
#   3. 产物:
#      - 场景内生成 3 个集合: Tello / Arm3DOF / Turbine (带材质与关节层级)
#      - 底部开关 EXPORT_OBJ / EXPORT_GLB 控制导出 (默认导出 GLB 到脚本同目录)
#
# 尺寸权威来源 (与代码库一致, 改这里=全局生效):
#   - Tello:     98 x 92.5 x 41 mm, 桨径 76mm, 电机对角轴距 ~120mm  (Ryze 官方)
#   - 机械臂:    L1=55, L2=45, L3=35 mm, 基座高 25mm  (arm_config.yaml / arm_kinematics.py)
#   - SG90 舵机: 23 x 12.2 x 29 mm, 法兰 32 x 12.2 x 2.5 mm
#   - 风机:      塔筒 phi3m x 30m (演示用 1:10 缩放, DEMO_SCALE=0.1)
#
# 坐标系: Blender Z-up, 单位 mm (场景 Unit Scale = 0.001, 即 1 BU = 1mm)
# 机械臂关节用 Empty 做 FK 层级, 与 backend/arm/arm_kinematics.py 的 FK 对应:
#   J1_Base (绕Z偏航) -> J2_Shoulder (绕X俯仰) -> J3_Elbow (绕X俯仰) -> EE
# =============================================================================

import bpy
import math
from mathutils import Vector

# ---------------- 总开关 ----------------
EXPORT_OBJ = False          # 导出 tello.obj / arm.obj / turbine.obj
EXPORT_GLB = True           # 导出 seabreeze_models.glb (推荐, 给 Three.js/Ursina 用)
EXPORT_DIR = "//"           # "//" = 当前 .blend / 脚本所在目录

DEMO_SCALE_TURBINE = 0.1    # 风机演示缩放 (真实 30m 塔太高)

# =============================================================================
# 参数 (毫米)
# =============================================================================
# --- Tello ---
TELLO_BODY   = (98.0, 92.5, 41.0)    # 长x宽x高
TELLO_PROP_D = 76.0
MOTOR_DIST   = 60.0                  # 电机中心距原点的 x/y 偏移
GUARD_R      = 45.0

# --- 机械臂 ---
ARM_L1, ARM_L2, ARM_L3 = 55.0, 45.0, 35.0
BASE_PLATE_D, BASE_PLATE_T = 50.0, 2.5
DISC_D, DISC_T = 36.0, 4.0
BASE_H = 25.0                        # 基座高
SG90_BODY   = (23.0, 12.2, 29.0)
SG90_FLANGE = (32.0, 12.2, 2.5)
CARBON_TUBE_D = 6.0                  # 碳管外径

# --- 风机 (真实尺寸, 渲染时再缩放) ---
TURBINE_H      = 30000.0             # 塔高 30m
TURBINE_R      = 1500.0              # 塔半径 1.5m (底部)
TURBINE_BLADE  = 12000.0             # 叶片长 12m (示意)

# =============================================================================
# 工具函数
# =============================================================================
def clean_scene():
    """清空场景"""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for col in list(bpy.data.collections):
        if col.name != "Collection":
            bpy.data.collections.remove(col)

def make_mat(name, rgb, rough=0.55, metallic=0.0, emission=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    # Find Principled BSDF by type (works across all Blender versions)
    bsdf = None
    for node in m.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            bsdf = node
            break
    if bsdf is None:
        raise KeyError("Cannot find BSDF_PRINCIPLED node in material '{}'.".format(name))
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 2.0
    return m

def _apply_mat(obj, mat):
    if mat and obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.append(mat)

def add_box(name, size, loc=(0, 0, 0), mat=None, parent=None, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    if bevel > 0:
        mod = o.modifiers.new("Bevel", 'BEVEL')
        mod.width = bevel
        mod.segments = 2
    _apply_mat(o, mat)
    if parent: o.parent = parent
    return o

def add_cyl(name, radius, depth, loc=(0, 0, 0), mat=None, parent=None, vertices=24, rot=None):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, vertices=vertices, location=loc)
    o = bpy.context.active_object
    o.name = name
    if rot: o.rotation_euler = rot
    _apply_mat(o, mat)
    if parent: o.parent = parent
    return o

def add_sphere(name, radius, loc=(0, 0, 0), mat=None, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=20, ring_count=12, location=loc)
    o = bpy.context.active_object
    o.name = name
    _apply_mat(o, mat)
    if parent: o.parent = parent
    return o

def add_torus(name, major_r, minor_r, loc=(0, 0, 0), mat=None, parent=None, rot=None):
    bpy.ops.mesh.primitive_torus_add(major_radius=major_r, minor_radius=minor_r,
                                    major_segments=28, minor_segments=8, location=loc)
    o = bpy.context.active_object
    o.name = name
    if rot: o.rotation_euler = rot
    _apply_mat(o, mat)
    if parent: o.parent = parent
    return o

def add_empty(name, loc=(0, 0, 0), parent=None):
    o = bpy.data.objects.new(name, None)
    o.empty_display_size = 8
    o.location = loc
    bpy.context.collection.objects.link(o)
    if parent: o.parent = parent
    return o

def new_collection(name):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col

def move_to_collection(obj, col):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)

# =============================================================================
# 1. Tello 无人机
# =============================================================================
def build_tello(mats):
    col = new_collection("Tello")
    root = add_empty("Tello_ROOT")

    bx, by, bz = TELLO_BODY
    body = add_box("Tello_Body", (bx, by, bz), mat=mats['white'], bevel=4.0, parent=root)
    move_to_collection(body, col)

    top = add_box("Tello_TopPlate", (70, 70, 8), loc=(0, 0, bz / 2 + 4), mat=mats['dark'], parent=root)
    move_to_collection(top, col)

    # 底部 IR 视觉定位传感器窗口 (黑色椭圆)
    sensor = add_cyl("Tello_IRSensor", 9, 3, loc=(0, 0, -bz / 2 - 1.5), mat=mats['black'], parent=root)
    sensor.scale.y = 0.65
    move_to_collection(sensor, col)

    # 前置摄像头小窗
    cam = add_box("Tello_Camera", (12, 4, 10), loc=(0, -by / 2 - 2, 2), mat=mats['black'], parent=root)
    move_to_collection(cam, col)

    # 4 电机 + 桨 + 护罩
    for i, (sx, sy) in enumerate([(1, 1), (1, -1), (-1, 1), (-1, -1)]):
        mx, my = sx * MOTOR_DIST, sy * MOTOR_DIST
        # 电机臂 (从机身指向电机)
        mid = (mx * 0.55, my * 0.55, 8)
        arm = add_box(f"Tello_MotorArm_{i}", (14, math.hypot(mx, my) * 0.9, 10),
                      loc=mid, mat=mats['white'], parent=root)
        arm.rotation_euler.z = math.atan2(my, mx) - math.pi / 2
        move_to_collection(arm, col)

        motor = add_cyl(f"Tello_Motor_{i}", 10, 16, loc=(mx, my, 14), mat=mats['dark'], parent=root)
        move_to_collection(motor, col)

        # 桨叶组 (独立 Empty 便于加旋转动画)
        prop_root = add_empty(f"Tello_PropSpin_{i}", loc=(mx, my, 24), parent=root)
        for s in (-1, 1):
            bl = add_box(f"Tello_Prop_{i}_{s}", (TELLO_PROP_D / 2, 8, 2),
                         loc=(s * TELLO_PROP_D / 4, 0, 0), mat=mats['prop'], parent=prop_root)
            move_to_collection(bl, col)
        move_to_collection(prop_root, col)

        # 护罩 (半环, 朝外)
        guard = add_torus(f"Tello_Guard_{i}", GUARD_R, 4, loc=(mx, my, 20),
                          mat=mats['dark'], parent=root)
        move_to_collection(guard, col)

    move_to_collection(root, col)
    return root

# =============================================================================
# 2. 3DOF 机械臂 (FK 关节层级, 与 arm_kinematics.py 对应)
# =============================================================================
def build_arm(mats):
    col = new_collection("Arm3DOF")

    # --- 底板 ---
    plate = add_cyl("Arm_BasePlate", BASE_PLATE_D / 2, BASE_PLATE_T, mat=mats['blue'])
    move_to_collection(plate, col)

    # --- J1 底座旋转关节 (绕 Z) ---
    j1 = add_empty("J1_Base", loc=(0, 0, BASE_PLATE_T))
    disc = add_cyl("Arm_RotationDisc", DISC_D / 2, DISC_T,
                   loc=(0, 0, DISC_T / 2), mat=mats['dark'], parent=j1)
    move_to_collection(disc, col)

    # 底座舵机 SG90 (简化: 壳体 + 法兰)
    sg1 = add_box("Arm_Servo_Base", SG90_BODY, loc=(0, 0, DISC_T + SG90_BODY[2] / 2),
                  mat=mats['servo'], parent=j1, bevel=1.0)
    move_to_collection(sg1, col)

    base_col = add_cyl("Arm_BaseColumn", 8, BASE_H,
                       loc=(0, 0, DISC_T + BASE_H / 2), mat=mats['dark'], parent=j1)
    move_to_collection(base_col, col)

    # --- J2 大臂俯仰关节 (绕 X) ---
    j2 = add_empty("J2_Shoulder", loc=(0, 0, DISC_T + BASE_H), parent=j1)
    add_sphere("Arm_Joint_S", 7, mat=mats['dark'], parent=j2)
    move_to_collection(bpy.data.objects["Arm_Joint_S"], col)

    # L1 碳管 (沿关节局部 -Z 向下? 不 — 装配姿态: 臂朝上, 沿 +Z)
    # 与 FK 对应: θ2=90° 时臂竖直向上
    l1 = add_cyl("Arm_Link1", CARBON_TUBE_D / 2, ARM_L1,
                 loc=(0, 0, ARM_L1 / 2), mat=mats['green'], parent=j2)
    move_to_collection(l1, col)

    # --- J3 小臂俯仰关节 (绕 X) ---
    j3 = add_empty("J3_Elbow", loc=(0, 0, ARM_L1), parent=j2)
    add_sphere("Arm_Joint_E", 6, mat=mats['dark'], parent=j3)
    move_to_collection(bpy.data.objects["Arm_Joint_E"], col)

    l2 = add_cyl("Arm_Link2", CARBON_TUBE_D / 2 * 0.85, ARM_L2,
                 loc=(0, 0, ARM_L2 / 2), mat=mats['yellow'], parent=j3)
    move_to_collection(l2, col)

    # L3 末端延伸 + 执行器平台
    l3 = add_cyl("Arm_Link3", CARBON_TUBE_D / 2 * 0.7, ARM_L3,
                 loc=(0, 0, ARM_L2 + ARM_L3 / 2), mat=mats['red'], parent=j3)
    move_to_collection(l3, col)

    ee = add_empty("EE", loc=(0, 0, ARM_L2 + ARM_L3), parent=j3)
    tool = add_box("Arm_EndEffector", (16, 12, 3), mat=mats['ee'], parent=ee, bevel=0.8)
    move_to_collection(tool, col)

    move_to_collection(j1, col)

    return {'j1': j1, 'j2': j2, 'j3': j3, 'ee': ee}

def pose_arm(joints, theta1=90, theta2=90, theta3=45):
    """设置关节角 (度), 与 arm_config.yaml 的限位一致:
       θ1∈[0,180] 底座偏航, θ2∈[15,165] 大臂俯仰, θ3∈[0,180] 小臂俯仰
       90/90/45 = 归位姿态"""
    joints['j1'].rotation_euler.z = math.radians(theta1 - 90)
    joints['j2'].rotation_euler.x = math.radians(90 - theta2)
    joints['j3'].rotation_euler.x = math.radians(-theta3 + 45)

# =============================================================================
# 3. 海上风机 (红白条纹塔筒 + 机舱 + 三叶片)
# =============================================================================
def build_turbine(mats):
    col = new_collection("Turbine")
    s = DEMO_SCALE_TURBINE
    root = add_empty("Turbine_ROOT")
    root.scale = (s, s, s)

    H, R = TURBINE_H, TURBINE_R
    segs = 6
    seg_h = H / segs
    for i in range(segs):
        r0 = R * (1 - i * 0.04)
        t = add_cyl(f"Turbine_Tower_{i}", r0, seg_h,
                    loc=(0, 0, seg_h * (i + 0.5)),
                    mat=mats['twhite'] if i % 2 == 0 else mats['tred'])
        move_to_collection(t, col)

    nacelle = add_box("Turbine_Nacelle", (5000, 3000, 3000),
                      loc=(2000, 0, H + 1500), mat=mats['twhite'], parent=root, bevel=300)
    move_to_collection(nacelle, col)

    rotor = add_empty("Turbine_RotorSpin", loc=(4500, 0, H + 1500), parent=root)
    hub = add_sphere("Turbine_Hub", 900, mat=mats['twhite'], parent=rotor)
    move_to_collection(hub, col)
    for i in range(3):
        blade_root = add_empty(f"Turbine_BladeRoot_{i}", parent=rotor)
        blade_root.rotation_euler.x = math.radians(i * 120)
        bl = add_box(f"Turbine_Blade_{i}", (300, TURBINE_BLADE, 1200),
                     loc=(0, TURBINE_BLADE / 2 + 600, 0), mat=mats['twhite'],
                     parent=blade_root, bevel=120)
        move_to_collection(bl, col)
        move_to_collection(blade_root, col)

    move_to_collection(rotor, col)
    move_to_collection(root, col)
    return root

# =============================================================================
# 4. 动画 (桨叶 & 风机叶片旋转)
# =============================================================================
def add_spin_anim(obj, axis='Z', frames=(1, 60), cycles=2.0):
    """给对象加线性旋转动画 (loop)"""
    obj.rotation_mode = 'XYZ'
    f0, f1 = frames
    idx = {'X': 0, 'Y': 1, 'Z': 2}[axis]
    obj.rotation_euler[idx] = 0
    obj.keyframe_insert("rotation_euler", index=idx, frame=f0)
    obj.rotation_euler[idx] = math.pi * 2 * cycles
    obj.keyframe_insert("rotation_euler", index=idx, frame=f1)
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'
            cyc = fc.modifiers.new('CYCLES')

# =============================================================================
# 主流程
# =============================================================================
def main():
    clean_scene()

    # 场景单位: 毫米
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 0.001

    # 材质
    mats = {
        'white':  make_mat("M_White",  (0.91, 0.91, 0.91)),
        'dark':   make_mat("M_Dark",   (0.40, 0.40, 0.40)),
        'black':  make_mat("M_Black",  (0.05, 0.05, 0.05), rough=0.3, metallic=0.6),
        'prop':   make_mat("M_Prop",   (0.60, 0.60, 0.60), metallic=0.3),
        'blue':   make_mat("M_Blue",   (0.27, 0.51, 0.71)),
        'servo':  make_mat("M_Servo",  (0.82, 0.82, 0.82)),
        'green':  make_mat("M_Green",  (0.31, 0.78, 0.31)),
        'yellow': make_mat("M_Yellow", (0.86, 0.78, 0.24)),
        'red':    make_mat("M_Red",    (0.90, 0.35, 0.24)),
        'ee':     make_mat("M_EE",     (1.00, 0.24, 0.24), emission=(0.4, 0.05, 0.05)),
        'twhite': make_mat("M_TWhite", (0.91, 0.91, 0.91)),
        'tred':   make_mat("M_TRed",   (0.78, 0.16, 0.16)),
    }

    # --- 建模 ---
    tello = build_tello(mats)
    joints = build_arm(mats)
    pose_arm(joints, 90, 90, 45)               # 归位姿态
    turbine = build_turbine(mats)

    # 布局: 机械臂挂 Tello 机腹 (演示装配), 风机放旁边
    joints['j1'].location = (0, 0, -TELLO_BODY[2] / 2 - BASE_PLATE_T)
    joints['j1'].parent = tello
    tello.location = (0, 0, 1200)              # 无人机悬停在 1.2m
    turbine.location = (9000, -2000, 0)

    # --- 动画 ---
    for i in range(4):
        add_spin_anim(bpy.data.objects[f"Tello_PropSpin_{i}"], axis='Z', frames=(1, 24), cycles=4.0)
    add_spin_anim(bpy.data.objects["Turbine_RotorSpin"], axis='X', frames=(1, 120), cycles=1.0)
    scene.frame_start, scene.frame_end = 1, 120

    # --- 相机 + 灯光 (离线渲染用) ---
    bpy.ops.object.camera_add(location=(2500, -3500, 2200))
    cam = bpy.context.active_object
    cam.rotation_euler = (math.radians(62), 0, math.radians(36))
    scene.camera = cam

    bpy.ops.object.light_add(type='SUN', location=(2000, -1000, 5000))
    sun = bpy.context.active_object
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(35), math.radians(15), math.radians(30))

    bpy.ops.object.light_add(type='AREA', location=(-1500, 1500, 3000))
    fill = bpy.context.active_object
    fill.data.energy = 500
    fill.data.shape = 'DISK'
    fill.data.size = 2000

    # 渲染设置 (EEVEE 快速出图)
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720

    # --- 导出 ---
    if EXPORT_GLB:
        bpy.ops.export_scene.gltf(
            filepath=EXPORT_DIR + "seabreeze_models.glb",
            export_format='GLB',
            export_animation_mode='ACTIONS',
            export_yup=True,                    # 给 Three.js/Ursina 用 Y-up
        )
        print("[EXPORT] seabreeze_models.glb 已导出")

    if EXPORT_OBJ:
        for name, fname in [("Tello", "tello.obj"), ("Arm3DOF", "arm.obj"), ("Turbine", "turbine.obj")]:
            bpy.ops.object.select_all(action='DESELECT')
            col = bpy.data.collections.get(name)
            if not col:
                continue
            for o in col.all_objects:
                o.select_set(True)
            bpy.ops.wm.obj_export(
                filepath=EXPORT_DIR + fname,
                export_selected_objects=True,
                export_triangulated_mesh=True,
                forward_axis='NEGATIVE_Z', up_axis='Y',
            )
            print(f"[EXPORT] {fname} 已导出")

    # 保存 .blend 便于二次编辑
    bpy.ops.wm.save_as_mainfile(filepath=EXPORT_DIR + "seabreeze_models.blend")
    print("[DONE] 建模完成: Tello / Arm3DOF / Turbine 三个集合已生成")

main()
