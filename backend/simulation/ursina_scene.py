# -*- coding: utf-8 -*-
"""
SeaBreeze Inspector 鈥?Ursina 3D 鏈?灏忓彲杩愯?屽師鍨?
================================================
瀹夎??: pip install ursina
杩愯??: python backend/simulation/ursina_scene.py
鎺у埗: 绌烘牸=璧烽??  WASD=绉诲姩  QE=鍗囬檷  鏂瑰悜閿?璋冭噦  R=閲嶇疆
"""
from ursina import *
from panda3d.core import TextNode
import sys, os, math, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.simulation.models import Quadrotor3D, WindDisturbance, RobotArm3DOF, VirtualSensor
from backend.main import MissionController
from backend.utils.units import m_to_cm, mps_to_cmps, mps2_to_cmps2, cmps_to_mps
from backend.mission.states import MissionState

# =============================================================================
# 0. 閰嶇疆
# =============================================================================
HOVER_HEIGHT = 1.5       # 鎮?鍋滈珮搴? (m)
MOVE_SPEED = 0.06         # WASD 绉诲姩閫熷害 (m/frame)
LIFT_SPEED = 0.03
SCALE = 20                # 1m 鈫?20 units (璁?Tello 鍦ㄥ睆骞曚笂鍙?瑙?)
TURBINE_X = 8.0           # 椋庢満浣嶇疆 (m)

# =============================================================================
# 1. 鍒涘缓 Ursina App
# =============================================================================
app = Ursina(borderless=False, title='SeaBreeze Inspector 鈥?3D UAV Simulation')
window.size = (1280, 720)
window.position = (100, 50)
window.color = color.rgb(135, 206, 235)  # 澶╃┖钃?EditorCamera()  # 鍙抽敭鏃嬭浆瑙嗚??, 婊氳疆缂╂斁, 涓?閿?骞崇Щ

# =============================================================================
# 2. 鍦烘櫙鍏冪礌
# =============================================================================

# 鍦伴潰
ground = Entity(model='plane', scale=(200, 1, 200), texture='white_cube',
                texture_scale=(50, 50), color=color.rgb(34, 139, 34), collider='box')

# 椋庢満濉旂瓛 (蠁6m脳30m 鈫?缂╂斁鍚?
tower = Entity(model='cylinder', scale=(6*SCALE/2, 30*SCALE, 6*SCALE/2),
               position=(TURBINE_X*SCALE, 15*SCALE, 0), color=color.white,
               rotation=(0, 0, 0))

# 椋庢満鍙剁墖 (绠?鍖? 3 鏉￠暱绔嬫柟浣?
blades = []
for i in range(3):
    b = Entity(model='cube', scale=(0.5, 9*SCALE, 0.2),
               position=(TURBINE_X*SCALE, 30*SCALE, 0),
               color=color.rgb(200, 200, 210),
               rotation=(0, 0, i * 120))
    blades.append(b)
blade_center = Entity(model='sphere', scale=0.5, position=(TURBINE_X*SCALE, 30*SCALE, 0),
                      color=color.gray)

# 鏃犱汉鏈?(Tello 姣斾緥: 98脳92.5脳41mm 鈫?0.098脳0.093脳0.041m, 缂╂斁鍚?
drone_body = Entity(model='cube', scale=(0.098*SCALE, 0.041*SCALE, 0.093*SCALE),
                    color=color.gray, position=(0, HOVER_HEIGHT*SCALE, 0))
drone_indicator = Entity(model='sphere', scale=0.15, color=color.green,
                         position=(0, HOVER_HEIGHT*SCALE + 0.05*SCALE, 0))

# 鏈烘?拌??(浠?drone_body 涓嬫柟鎸傝浇)
arm_base = Entity(model='cylinder', scale=(0.02*SCALE, 0.025*SCALE, 0.02*SCALE),
                  color=color.orange, parent=drone_body,
                  position=(0, -0.02*SCALE, 0))
arm_link1 = Entity(model='cylinder', scale=(0.015*SCALE, 0.055*SCALE, 0.015*SCALE),
                   color=color.orange, parent=arm_base,
                   position=(0, -0.04*SCALE, 0), rotation=(0, 0, 0))
arm_link2 = Entity(model='cylinder', scale=(0.012*SCALE, 0.045*SCALE, 0.012*SCALE),
                   color=color.rgb(255, 140, 0), parent=arm_link1,
                   position=(0, -0.05*SCALE, 0))
arm_tip = Entity(model='sphere', scale=0.08, color=color.red, parent=arm_link2,
                 position=(0, -0.04*SCALE, 0))

# 杞ㄨ抗鎷栧熬
trail = []

# HUD 鏂囧瓧
hud_title = Text(text='SeaBreeze Inspector', position=(-0.85, 0.48), scale=1.5, color=color.white)
hud_state = Text(text='STATE: IDLE', position=(-0.85, 0.43), scale=1.0, color=color.white)
hud_pos = Text(text='POS: (0, 0, 0)', position=(-0.85, 0.40), scale=1.0, color=color.white)
hud_battery = Text(text='BATT: 100%', position=(-0.85, 0.37), scale=1.0, color=color.white)
hud_ekf = Text(text='EKF: OK', position=(-0.85, 0.34), scale=1.0, color=color.green)
hud_det = Text(text='DET: 0', position=(-0.85, 0.31), scale=1.0, color=color.white)
hud_arm = Text(text='ARM: [90, 90, 45]', position=(-0.85, 0.28), scale=1.0, color=color.white)
hud_help = Text(text='[Space]Fly [WASD]Move [QE]Up/Dn [Arrows]Arm [R]Reset',
                position=(-0.85, -0.47), scale=0.9, color=color.gray)

# =============================================================================
# 3. 鍚庣??閫昏緫 (澶嶇敤鍏ㄩ儴鐜版湁浠ｇ爜)
# =============================================================================
mc = MissionController(mode="simulation", mock=True)
mc.safety_guard.THRESHOLDS["timeout_land"] = 3600.0
mc.safety_guard.THRESHOLDS["timeout_kill"] = 3600.0
mc.state = "IDLE"

arm_model = RobotArm3DOF()
drone = Quadrotor3D()
wind = WindDisturbance(base_wind=np.array([0.05, 0.02, 0.0]), freq=0.5, gust_amp=0.03)
sensor = VirtualSensor(
    imu_noise=0.05, opt_noise=2.0, bar_noise=10.0, bias_drift_rate=0.001, rw_std=0.005)

_phys_acc = 0.0
_target = np.array([TURBINE_X, HOVER_HEIGHT, 1.0])
_frame = 0
_last_ctrl = np.zeros(3)

# =============================================================================
# 4. 涓诲惊鐜?# =============================================================================
def update():
    global _phys_acc, _target, _frame, _last_ctrl
    _frame += 1
    dt = min(time.dt, 0.05)  # 闄?max dt
    PHYS_DT = 0.02

    # ---- 閿?鐩樹簨浠? ----
    if mc.state != "EMERGENCY":
        if held_keys['space']:
            if mc.state == "IDLE" or mc.state == MissionState.IDLE:
                mc.takeoff(height=HOVER_HEIGHT * 100)
                drone.state[2] = HOVER_HEIGHT
                drone.set_velocity(np.zeros(3))
                _target = drone.get_position().copy()
        if mc.state == "HOVERING" or str(mc.state) == "HOVERING":
            step = MOVE_SPEED
            if held_keys['w']: _target[0] += step
            if held_keys['s']: _target[0] -= step
            if held_keys['a']: _target[2] += step
            if held_keys['d']: _target[2] -= step
            if held_keys['q']: _target[1] += LIFT_SPEED
            if held_keys['e']: _target[1] -= LIFT_SPEED
        if held_keys['r']:
            mc.request_state("IDLE", "reset")
            drone.state[:] = 0.0
            drone.set_velocity(np.zeros(3))
            drone.state[2] = 0.0
            _phys_acc = 0.0
            _target = np.array([TURBINE_X, HOVER_HEIGHT, 1.0])
            mc.ekf.reset()
            arm_model.set_angles([90, 90, 45])

        # 鏈烘?拌噦鎺у??        delta = 3 if held_keys['shift'] else 1
        if held_keys['left arrow']: arm_model.angles[0] = (arm_model.angles[0] - delta) % 180
        if held_keys['right arrow']: arm_model.angles[0] = (arm_model.angles[0] + delta) % 180
        if held_keys['up arrow']: arm_model.angles[1] = min(150, arm_model.angles[1] + delta)
        if held_keys['down arrow']: arm_model.angles[1] = max(30, arm_model.angles[1] - delta)
        arm_model.set_angles(arm_model.angles)
    # ---- 鐗╃悊瀛愭?ヨ??----
    _phys_acc += dt
    wind_vec = np.zeros(3)
    while _phys_acc >= PHYS_DT:
        wind_vec = wind.sample(PHYS_DT)
        if mc.state not in ("IDLE", "EMERGENCY"):
            v_des = _last_ctrl
            v_cur = drone.get_velocity()
            a_des = (v_des - v_cur) / 0.3
            thrust = drone.mass * (a_des[1] + drone.g)
            drone.step(np.array([thrust, 0.0, 0.0, 0.0]), disturbance=wind_vec)
        _phys_acc -= PHYS_DT

    # ---- 浼犳劅鍣?+ MC ----
    if mc.state not in ("IDLE", "EMERGENCY"):
        sensor_data = sensor.read_all(drone)
        z = np.array([sensor_data["imu"][0], sensor_data["imu"][1], sensor_data["imu"][2],
                      sensor_data["optical"][0], sensor_data["optical"][1], sensor_data["barometer"]])
        pos = drone.get_position()
        vel = drone.get_velocity()
        att = drone.get_attitude()
        mc._last_control_accel = mps2_to_cmps2(drone.get_acceleration())
        ctrl_cmps, state_dict = mc.update_with_external_data(
            z, m_to_cm(pos), mps_to_cmps(vel), att)
        _last_ctrl = cmps_to_mps(ctrl_cmps)
        drone.set_velocity(_last_ctrl)
    mc._battery -= dt * (1.5 if str(mc.state) == "HOVERING" else 0.1)
    mc._battery = max(0, mc._battery)

    # ---- 鏇存柊 3D 瀹炰綋 ----
    pos = drone.get_position()
    drone_body.position = (pos[0] * SCALE, pos[1] * SCALE, pos[2] * SCALE)
    # indicator 棰滆壊
    st = str(mc.state)
    drone_indicator.color = (color.green if st == "HOVERING"
                             else color.yellow if st in ("TAKEOFF", "NAVIGATE", "INSPECT", "RETURN")
                             else color.red if st == "EMERGENCY" else color.gray)
    drone_indicator.position = (drone_body.x, drone_body.y + 0.05 * SCALE, drone_body.z)

    # 鍙剁墖鏃嬭浆
    for i, b in enumerate(blades):
        b.rotation_z += 25 * dt
    blade_center.rotation_z += 25 * dt

    # 鏈烘?拌噦鍏宠妭鏇存??    a = arm_model.angles
    arm_link1.rotation_z = a[1] - 90       # shoulder 淇?浠?
    arm_link2.rotation_z = a[2] - 45        # elbow 淇?浠? (鐩稿??)
    arm_base.rotation_y = a[0] - 90         # base 鏃嬭浆

    # 杞ㄨ抗鎷栧熬
    if _frame % 5 == 0 and mc.state not in ("IDLE", "EMERGENCY"):
        t = Entity(model='sphere', scale=0.05, color=color.rgba(100, 200, 255, 180),
                   position=drone_body.position)
        trail.append(t)
        if len(trail) > 60:
            destroy(trail.pop(0))

    # ---- HUD ----
    hud_state.text = f'STATE: {st}'
    hud_pos.text = f'POS: ({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}) m'
    hud_battery.text = f'BATT: {int(mc._battery)}%'
    mahal = mc.ekf.mahalanobis_distance
    hud_ekf.text = f'EKF: D={mahal:.1f}'
    hud_ekf.color = color.green if mahal < 8 else color.yellow if mahal < 15 else color.red
    hud_det.text = f'DET: {mc._last_detection_count}'
    hud_arm.text = f'ARM: [{a[0]:.0f}, {a[1]:.0f}, {a[2]:.0f}]'
    if mc._battery < 20: hud_battery.color = color.red
    else: hud_battery.color = color.white

app.run()