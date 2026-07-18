"""SimRuntime - Single simulation control loop wrapping MissionController.

Phase 3: Replaces the private FSM in http_bridge.py with a clean wrapper
around mc.update_with_external_data(). All simulations use the same
control loop; only the data source (virtual vs real sensors) differs.
"""

import time, threading
import numpy as np

from backend.utils.units import m_to_cm, mps_to_cmps


HOVER_HEIGHT = 1.2       # meters (z-up)
CRUISE_SPEED = 1.5       # m/s horizontal
VERTICAL_SPEED = 0.8     # m/s vertical
BATTERY_DRAIN = 0.05     # percent per second when flying
TURBINE_POS = np.array([9.0, 0.0, 0.0])   # turbine base center, z-up (z=0 地面)

# 级联控制参数 (位置环 → 速度环 → 加速度/姿态指令)
POS_TAU = 0.5            # 位置环时间常数 (s): 误差→期望速度
VEL_TAU = 0.25           # 速度环时间常数 (s): 速度误差→期望加速度
MAX_SPEED = 2.0          # 水平最大速度 (m/s)
MAX_VSPEED = 1.0         # 垂直最大速度 (m/s)
MAX_ACCEL = 3.0          # 最大加速度 (m/s²)


class SimRuntime:
    """Single simulation control loop.

    Wraps MissionController.update_with_external_data() with
    key handling, physics stepping, and state management.

    Usage:
        runtime = SimRuntime(mc, quad, wind, arm, sensor)
        state = runtime.step(dt, keys)  # keys = {"Space", "KeyW", ...}
        print(state["pos"], state["state"])
    """

    def __init__(self, mc, quad, wind_model, arm, sensor):
        self.mc = mc
        self.quad = quad
        self.wind = wind_model
        self.arm = arm
        self.sensor = sensor

        # Internal state (z-up meters)
        self._sim_state = "IDLE"
        self._target_pos = np.array([0.0, 0.0, 0.0])
        self._mission_timer = 0.0
        self._flight_log = []

        self._add_log("SIM_INIT", "Runtime started")

    def _add_log(self, event, detail=""):
        self._flight_log.append({
            "t": time.time(), "event": event, "detail": detail
        })
        if len(self._flight_log) > 200:
            self._flight_log.pop(0)

    def step(self, dt, keys):
        """Run one simulation frame.

        Args:
            dt: time delta (seconds)
            keys: set of key codes e.g. {"Space", "KeyW"}

        Returns:
            dict with pos, vel, state, battery, arm_angles, etc.
        """
        sim_dt = min(0.02, dt) if dt > 0 else 0.02

        # ---- Key handling -> state transitions ----
        self._process_keys(keys)

        # ---- State-specific target updates ----
        pos = self.quad.get_position()
        self._update_state(sim_dt, pos, keys)

        # ---- Physics: 级联控制 (位置→速度→加速度→推力+期望姿态) ----
        # 风在本帧只采样一次, 既作用于机体也用于前端显示
        wind_f = self.wind.sample(sim_dt)
        if self._sim_state != "IDLE":
            vel = self.quad.get_velocity()
            err = self._target_pos - pos
            # 位置环: 误差 → 期望速度 (限幅)
            v_des = np.clip(err / POS_TAU, -MAX_SPEED, MAX_SPEED)
            v_des[2] = np.clip(v_des[2], -MAX_VSPEED, MAX_VSPEED)
            # 速度环: 速度误差 → 期望加速度 (限幅)
            a_des = np.clip((v_des - vel) / VEL_TAU, -MAX_ACCEL, MAX_ACCEL)
            # 加速度指令 → 推力 + 期望倾角 (水平分力靠机身倾斜产生)
            az_cmd = a_des[2] + self.quad.g
            thrust = self.quad.mass * max(0.0, az_cmd)
            pitch_des = float(np.arctan2(a_des[0], az_cmd))   # 前加速→低头
            roll_des = float(np.arctan2(-a_des[1], az_cmd))   # 侧加速→侧倾
            self.quad.step(np.array([thrust, roll_des, pitch_des, 0.0]),
                           disturbance=wind_f, dt=sim_dt)

        # ---- Sensors + MissionController pipeline ----
        sensor_data = self.sensor.read_all(self.quad)
        imu = sensor_data["imu"]
        opt = sensor_data["optical"]
        bar = sensor_data["barometer"]
        z = np.array([imu[0], imu[1], imu[2], opt[0], opt[1], bar])

        vel = self.quad.get_velocity()
        att = self.quad.get_attitude()

        ctrl_cmps, state_dict = self.mc.update_with_external_data(
            z, m_to_cm(pos), mps_to_cmps(vel), att
        )

        # ---- Battery drain ----
        battery = float(self.mc._battery)
        if self._sim_state not in ("IDLE", "EMERGENCY"):
            battery = max(0, battery - BATTERY_DRAIN * sim_dt)
            self.mc._battery = battery

        # ---- Wind (本帧已采样, 直接复用) ----
        wind_vec = wind_f

        # ---- Detections (mock near turbine) ----
        # z-up: 水平面是 x-y, 距离不应混入高度 z
        dist_t = float(np.linalg.norm(pos[:2] - TURBINE_POS[:2]))
        detections = []
        if self._sim_state in ("INSPECT", "NAVIGATE") and dist_t < 15:
            detections = [
                {"cls": "crack", "conf": 0.82, "bbox": [100, 30, 50, 25]},
                {"cls": "corrosion", "conf": 0.71, "bbox": [140, 70, 55, 30]},
            ]
            if dist_t < 6:
                detections.append({"cls": "rust", "conf": 0.65, "bbox": [120, 120, 40, 22]})

        # ---- Build result ----
        ep_m = self.arm.get_endpoint()

        return {
            "pos": pos.tolist(),
            "vel": vel.tolist(),
            "state": self._sim_state,
            "battery": round(battery, 1),
            "wind": wind_vec.tolist(),
            "arm_angles": self.arm.angles.tolist(),
            "arm_endpoint": [round(float(v) * 1000, 1) for v in ep_m],
            "ekf_mahal": round(float(self.mc.ekf.mahalanobis_distance), 1),
            "safety_tier": (
                "EMERGENCY" if self._sim_state == "EMERGENCY"
                else "WARN" if battery < 30 else "NOMINAL"
            ),
            "detections": detections,
            "flight_log": list(self._flight_log[-100:]),
        }

    def _process_keys(self, keys):
        """Translate key presses to state transitions."""
        if not keys:
            return

        if "Space" in keys:
            if self._sim_state == "IDLE":
                self._sim_state = "TAKING_OFF"
                self._target_pos = self.quad.get_position().copy()
                self._target_pos[2] = HOVER_HEIGHT  # z-up
                self.mc.takeoff(height=HOVER_HEIGHT * 100)
                self._add_log("TAKEOFF", f"Target: {HOVER_HEIGHT}m")
            elif self._sim_state in ("HOVERING", "NAVIGATE", "INSPECT"):
                self._sim_state = "LANDING"
                self._target_pos = self.quad.get_position().copy()
                self._target_pos[2] = 0.0
                self.mc.request_state("LAND", "manual")
                self._add_log("LAND", "Manual")

        if "KeyR" in keys:
            self._sim_state = "IDLE"
            self.quad.state[:] = 0.0
            self.quad.set_velocity(np.zeros(3))
            self._target_pos = np.array([0.0, 0.0, 0.0])
            self.arm.set_angles([90.0, 90.0, 45.0])
            self.mc.ekf.reset()
            self.mc.request_state("IDLE", "reset")
            self._flight_log.clear()
            self._add_log("RESET", "Full reset")

        if "KeyE" in keys:
            self._sim_state = "EMERGENCY"
            self.mc.request_state("EMERGENCY", "manual")
            self._add_log("EMERGENCY", "Manual")

        if "KeyM" in keys and self._sim_state == "HOVERING":
            self._sim_state = "NAVIGATE"
            self._target_pos = TURBINE_POS.copy()
            self._target_pos[2] = HOVER_HEIGHT + 3.0  # z-up
            self._mission_timer = 0.0
            self._add_log("MISSION", "Navigating to turbine")

        # Arrow keys -> arm control
        delta = 3.0
        angles = self.arm.angles.copy()
        if "ArrowLeft" in keys: angles[0] = (angles[0] - delta) % 180
        if "ArrowRight" in keys: angles[0] = (angles[0] + delta) % 180
        if "ArrowUp" in keys: angles[1] = min(150, angles[1] + delta)
        if "ArrowDown" in keys: angles[1] = max(30, angles[1] - delta)
        if not np.array_equal(angles, self.arm.angles):
            self.arm.set_angles(angles)

    def _update_state(self, dt, pos, keys):
        """State-specific target position updates."""
        step = CRUISE_SPEED * dt

        if self._sim_state == "TAKING_OFF":
            if pos[2] >= HOVER_HEIGHT - 0.05:  # z-up
                self._sim_state = "HOVERING"
                self.quad.set_velocity(np.zeros(3))
                self._add_log("HOVERING", "Reached hover")
            else:
                self._target_pos[2] = HOVER_HEIGHT

        elif self._sim_state == "HOVERING":
            if "KeyW" in keys: self._target_pos[0] += step
            if "KeyS" in keys: self._target_pos[0] -= step
            if "KeyA" in keys: self._target_pos[1] -= step  # z-up: Y = lateral
            if "KeyD" in keys: self._target_pos[1] += step
            # 垂直升降 (helpbar 已标注 PgUp/PgDn, 之前漏了实现)
            if "PageUp" in keys:   self._target_pos[2] += VERTICAL_SPEED * dt
            if "PageDown" in keys: self._target_pos[2] -= VERTICAL_SPEED * dt
            self._target_pos[2] = max(0.3, min(5.0, self._target_pos[2]))

        elif self._sim_state == "NAVIGATE":
            self._mission_timer += dt
            to_target = self._target_pos - pos
            dist = float(np.linalg.norm(to_target))
            if dist < 0.5:
                self._sim_state = "INSPECT"
                self._add_log("INSPECT", "Arrived")
                self._mission_timer = 0.0
            elif dist > 0:
                self._target_pos = pos + (to_target / dist) * step * 0.8

        elif self._sim_state == "INSPECT":
            self._mission_timer += dt
            if self._mission_timer > 8.0:
                self._sim_state = "RETURNING"
                self._target_pos = np.array([0.0, 0.0, HOVER_HEIGHT])  # home, z-up
                self._add_log("RETURN", "Inspection done")

        elif self._sim_state == "RETURNING":
            home = np.array([0.0, 0.0, HOVER_HEIGHT])
            to_home = home - pos
            dist = float(np.linalg.norm(to_home))
            if dist < 0.5:
                self._sim_state = "LANDING"
                self._target_pos = np.array([0.0, 0.0, 0.0])
                self._add_log("LAND", "Arrived home")
            elif dist > 0:
                self._target_pos = pos + (to_home / dist) * step * 0.8

        elif self._sim_state == "LANDING":
            if pos[2] <= 0.05:  # z-up
                self._sim_state = "IDLE"
                self.quad.state[:] = 0.0
                self.quad.set_velocity(np.zeros(3))
                self._target_pos = np.array([0.0, 0.0, 0.0])
                self._add_log("IDLE", "Landed")
            else:
                # 目标自身递减 (不能从 pos 重算, 否则参考系追着自己尾巴跑, 下降率趋零)
                self._target_pos[2] = max(0.0, self._target_pos[2] - VERTICAL_SPEED * dt)

        elif self._sim_state == "EMERGENCY":
            self._target_pos[2] = max(0.0, self._target_pos[2] - 3.0 * dt)
            if pos[2] <= 0.02:
                self._sim_state = "IDLE"
                self.quad.state[:] = 0.0
                self.quad.set_velocity(np.zeros(3))
                self._add_log("IDLE", "Emergency landed")