"""SimRuntime - Single simulation control loop wrapping MissionController.

Phase 3 (revised): State management fully delegated to mc.state.
SimRuntime does NOT maintain a separate _sim_state field.

铁律 #4 / Rule 4: All simulations share this single control loop.
  - mc.state is the single source of truth for task state
  - SimRuntime only reads mc.state, never writes it directly
  - State transitions go through mc.takeoff() / mc.request_state() / mc.trigger_emergency()
  - Automatic transitions (TAKEOFF→HOVERING, NAVIGATE→INSPECT, etc.) are handled
    by mc's own _handle_state_machine() inside update_with_external_data()

Physics: SimRuntime runs a cascaded position→velocity→acceleration→thrust controller
that reads mc.target_pos (cm, z-up) as the target. mc's PID controller output is
NOT used to drive physics (Q3=A: keep SimRuntime cascaded control as-is).
"""

import time
import numpy as np

from backend.utils.units import m_to_cm, cm_to_m, mps_to_cmps, mps2_to_cmps2
from backend.simulation.drone_adapter import SimDroneAdapter


HOVER_HEIGHT = 1.2       # meters (z-up)
CRUISE_SPEED = 1.5       # m/s horizontal
VERTICAL_SPEED = 0.8     # m/s vertical
BATTERY_DRAIN = 0.05     # percent per second when flying
TURBINE_POS = np.array([9.0, 0.0, 0.0])   # turbine base center, z-up (z=0 地面)
INSPECT_TIMEOUT = 8.0    # seconds (overrides mc's config 30s for faster sim demo)

# 级联控制参数 (位置环 → 速度环 → 加速度/姿态指令)
POS_TAU = 0.5            # 位置环时间常数 (s): 误差→期望速度
VEL_TAU = 0.25           # 速度环时间常数 (s): 速度误差→期望加速度
MAX_SPEED = 2.0          # 水平最大速度 (m/s)
MAX_VSPEED = 1.0         # 垂直最大速度 (m/s)
MAX_ACCEL = 3.0          # 最大加速度 (m/s²)

# 触地判定阈值 (m)
TOUCHDOWN_HEIGHT = 0.05  # 5cm: 低于此高度认为已触地
GROUND_CLAMP_HEIGHT = 0.02  # 2cm: 低于此高度强制归零


class SimRuntime:
    """Single simulation control loop.

    Wraps MissionController.update_with_external_data() with
    key handling, physics stepping, and state management.

    State management: fully delegated to mc.state (Rule 4).
    SimRuntime never maintains its own state string.

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

        # Replace mc's MockTello with SimDroneAdapter (is_flying reflects physics).
        # SimDroneAdapter.land()/emergency() defer is_flying=False until mark_landed(),
        # so mc's LAND/EMERGENCY handlers wait for physics touch-down.
        adapter = SimDroneAdapter(quad)
        adapter.connect()
        mc.drone = adapter

        # Override EKF dt to match simulation rate (50Hz, not mc config's 10Hz).
        # mc.dt=0.1 would cause EKF predict to over-extrapolate 5x per step.
        _sim_dt = 0.02
        mc.ekf.dt = _sim_dt
        mc.ekf.F = mc.ekf._build_state_transition_matrix(_sim_dt)

        # #6 修复: 启动 mc 子系统 (logger + video_stream)
        # 仿真路径不调 mc.start() (那会进入 mc 自己的 while 循环), 但需要 logger 和 video
        if not mc.logger.is_recording:
            mc.logger.start_session()
        mc.video_stream.start()

        # Internal state (NOT a task state machine — just timers and logs)
        self._mission_timer = 0.0
        self._flight_log = []

        self._add_log("SIM_INIT", "Runtime started, state delegated to mc.state")

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

        # ---- Key handling -> mc state transitions ----
        self._process_keys(keys)

        # ---- State-specific target updates (WASD, INSPECT timeout, touch-down) ----
        pos = self.quad.get_position()
        self._update_state(sim_dt, pos, keys)

        # ---- Physics: 级联控制 (位置→速度→加速度→推力+期望姿态) ----
        # 风在本帧只采样一次, 既作用于机体也用于前端显示
        wind_f = self.wind.sample(sim_dt)
        a_des = np.zeros(3)  # 本帧加速度命令 (m/s²), 供 EKF 分离扰动
        if self.mc.state != "IDLE":
            vel = self.quad.get_velocity()
            # 读 mc.target_pos (cm, z-up) → 转米, 作为级联控制目标
            target_m = cm_to_m(self.mc.target_pos)
            err = target_m - pos
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

        # 把实际加速度命令回喂 EKF (cm/s²), 让 EKF 能区分"控制加速度"和"扰动"
        # 不做这一步, EKF 会把全部 IMU 读数归因于扰动, 导致速度/位置估计膨胀
        self.mc._last_control_accel = mps2_to_cmps2(a_des)

        # ---- Sensors + MissionController pipeline ----
        # mc.update_with_external_data 内部运行:
        #   EKF predict/update → 安全检查 → _handle_state_machine (含自动状态转换)
        #   → 控制器 compute → 日志 → 消息总线
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

        # ---- Battery drain (N3: 用 mc.state 而非已删除的 _sim_state) ----
        battery = self.mc.get_battery()
        if self.mc.state not in ("IDLE", "EMERGENCY"):
            battery = max(0, battery - BATTERY_DRAIN * sim_dt)
            self.mc.set_battery(battery)

        # ---- Detections (mock near turbine) ----
        # z-up: 水平面是 x-y, 距离不应混入高度 z
        dist_t = float(np.linalg.norm(pos[:2] - TURBINE_POS[:2]))
        detections = []
        if self.mc.state in ("INSPECT", "NAVIGATE") and dist_t < 15:
            detections = [
                {"cls": "crack", "conf": 0.82, "bbox": [100, 30, 50, 25]},
                {"cls": "corrosion", "conf": 0.71, "bbox": [140, 70, 55, 30]},
            ]
            if dist_t < 6:
                detections.append({"cls": "rust", "conf": 0.65, "bbox": [120, 120, 40, 22]})

        # N4 修复: 检测结果回喂 mc (供 INSPECT 状态的 _last_detection_count)
        self.mc.set_detection_count(len(detections))

        # ---- Build result ----
        ep_m = self.arm.get_endpoint()

        return {
            "pos": pos.tolist(),
            "vel": vel.tolist(),
            "state": self.mc.state,  # 规范名: IDLE/TAKEOFF/HOVERING/NAVIGATE/INSPECT/RETURN/LAND/EMERGENCY
            "battery": round(battery, 1),
            "wind": wind_f.tolist(),
            "arm_angles": self.arm.angles.tolist(),
            "arm_endpoint": [round(float(v) * 1000, 1) for v in ep_m],
            "ekf_mahal": round(float(self.mc.ekf.mahalanobis_distance), 1),
            "safety_tier": (
                "EMERGENCY" if self.mc.state == "EMERGENCY"
                else "WARN" if battery < 30 else "NOMINAL"
            ),
            "detections": detections,
            "flight_log": list(self._flight_log[-100:]),
        }

    def _process_keys(self, keys):
        """Translate key presses to mc state transitions.

        All transitions go through mc methods (takeoff/request_state/trigger_emergency).
        Return values of request_state are checked; fallback to trigger_emergency
        if the transition is rejected by the transition table.
        """
        if not keys:
            return

        # Space: takeoff / manual land
        if "Space" in keys:
            if self.mc.state == "IDLE":
                self.mc.takeoff(height=HOVER_HEIGHT * 100)
                self._add_log("TAKEOFF", "Target: {}m".format(HOVER_HEIGHT))
            elif self.mc.state in ("HOVERING", "NAVIGATE", "INSPECT", "RETURN"):
                if self.mc.request_state("LAND", "manual"):
                    self._add_log("LAND", "Manual")
                else:
                    # 转换表拒绝时 fallback 到 emergency (不应发生, TRANSITIONS 已扩展)
                    self.mc.trigger_emergency("manual land fallback")
                    self._add_log("EMERGENCY", "Land fallback")

        # KeyR: reset (trigger_emergency → 下一帧 EMERGENCY→IDLE)
        if "KeyR" in keys:
            self.mc.reset_mission()
            self.quad.state[:] = 0.0
            self.quad.set_velocity(np.zeros(3))
            self.arm.set_angles([90.0, 90.0, 45.0])
            self._mission_timer = 0.0
            self._flight_log.clear()
            self._add_log("RESET", "Full reset")

        # KeyE: emergency stop
        if "KeyE" in keys:
            self.mc.trigger_emergency("manual")
            self.mc.target_pos[2] = 0.0  # 立即设下降目标 (不等下一帧 mc handler)
            self._add_log("EMERGENCY", "Manual")

        # KeyM: start mission (HOVERING → NAVIGATE, 飞向风机)
        if "KeyM" in keys and self.mc.state == "HOVERING":
            start_cm = m_to_cm(self.quad.get_position())
            target_cm = m_to_cm(TURBINE_POS)
            # 设置直飞路径 (2 点), mc NAVIGATE 处理器会跟随并自动转 INSPECT
            self.mc.path = np.array([start_cm, target_cm])
            self.mc.path_idx = 0
            if self.mc.request_state("NAVIGATE", "mission"):
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
        """State-specific target position updates.

        mc handles automatic state transitions inside update_with_external_data():
          - TAKEOFF → HOVERING (height check)
          - NAVIGATE → INSPECT (path complete)
          - INSPECT → RETURN (30s config timeout)
          - RETURN → LAND (distance to home)
          - LAND → IDLE (is_flying False after mark_landed)
          - EMERGENCY → IDLE (is_flying False after mark_landed)

        SimRuntime only handles:
          1. HOVERING: WASD/PgUp/PgDn target updates (writes mc.target_pos in cm)
          2. INSPECT: 8s timeout override (faster than mc's 30s config)
          3. LAND/EMERGENCY: touch-down detection → mark_landed()
        """
        state = self.mc.state

        # 1. HOVERING: WASD 目标更新 (mc.target_pos 单位 cm)
        if state == "HOVERING":
            step_cm = CRUISE_SPEED * dt * 100  # m → cm
            vstep_cm = VERTICAL_SPEED * dt * 100
            if "KeyW" in keys: self.mc.target_pos[0] += step_cm
            if "KeyS" in keys: self.mc.target_pos[0] -= step_cm
            if "KeyA" in keys: self.mc.target_pos[1] -= step_cm
            if "KeyD" in keys: self.mc.target_pos[1] += step_cm
            if "PageUp" in keys:   self.mc.target_pos[2] += vstep_cm
            if "PageDown" in keys: self.mc.target_pos[2] -= vstep_cm
            # 限幅: 30cm-500cm (z 轴安全边界)
            self.mc.target_pos[2] = max(30, min(500, self.mc.target_pos[2]))

        # 2. INSPECT: 8s 超时覆盖 (mc config 默认 30s, 仿真用 8s 加快演示)
        if state == "INSPECT":
            self._mission_timer += dt
            if self._mission_timer > INSPECT_TIMEOUT:
                if self.mc.request_state("RETURN", "inspect done (sim 8s)"):
                    self._mission_timer = 0.0
                    self._add_log("RETURN", "Inspection done")

        # 3. LAND/EMERGENCY: 触地检测 → mark_landed (让 mc 能转 IDLE)
        if state in ("LAND", "EMERGENCY"):
            if pos[2] < TOUCHDOWN_HEIGHT:
                drone = self.mc.drone
                if hasattr(drone, "mark_landed") and drone.is_flying:
                    drone.mark_landed()
                    self._add_log("TOUCHDOWN", "Physics reached ground")
            if pos[2] < GROUND_CLAMP_HEIGHT:
                self.quad.state[:] = 0.0
                self.quad.set_velocity(np.zeros(3))
