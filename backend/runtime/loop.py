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

例外: velocity_command_mode=True 时改走"真机同源"的速度指令链路 —— 物理只消费
SimDroneAdapter.get_commanded_velocity() (mc 控制器输出经 set_velocity 下发),
位置级联完全不参与。默认 False, 旧数值行为逐位不变 (已用 HEAD 版本对比验证)。
"""

import time
import numpy as np

from backend.utils.units import m_to_cm, cm_to_m, mps_to_cmps, mps2_to_cmps2
from backend.simulation.drone_adapter import SimDroneAdapter
from backend.simulation.transport_model import (
    ActuatorLag,
    CommandTransportModel,
    SensorTransportModel,
)


HOVER_HEIGHT = 1.2       # meters (z-up)
CRUISE_SPEED = 1.5       # m/s horizontal
VERTICAL_SPEED = 0.8     # m/s vertical
BATTERY_DRAIN = 0.05     # percent per second when flying
TURBINE_POS = np.array([9.0, 0.0, 0.0])   # turbine base center, z-up (z=0 地面)
INSPECT_TIMEOUT = 8.0    # seconds (overrides mc's config 30s for faster sim demo)

# 遥控上行"超时归零"时限 (秒)。来源: backend/drone/rc_manager.py 的
# RCManager.ZERO_TIMEOUT = 0.5 —— 真机在超过该时限没有**新指令**时自动下发零速度
# (防失控飞丢)。无头仿真此前在上行丢包时无限期保持上一条指令, 结果比真机乐观。
# 只在启用上行传输模型 (uplink_latency_s / uplink_drop_rate > 0) 时生效: 未启用时
# 适配器的指令每帧都被控制器刷新, 根本不存在"链路断了还保持旧指令"的失效模式。
RC_ZERO_TIMEOUT = 0.5

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

    def __init__(self, mc, quad, wind_model, arm, sensor,
                 velocity_command_mode: bool = False,
                 sensor_latency_s: float = 0.0,
                 sensor_drop_rate: float = 0.0,
                 actuator_tau_s: float = 0.0,
                 transport_seed: int = 0,
                 sensor_loss_model: str = "iid",
                 sensor_mean_burst_len: float = 1.0,
                 uplink_latency_s: float = 0.0,
                 uplink_drop_rate: float = 0.0,
                 uplink_loss_model: str = "iid",
                 uplink_mean_burst_len: float = 1.0):
        """velocity_command_mode: True = 物理由 adapter 的速度指令驱动 (真机同源链路)。

        默认 False (硬要求): 论文已发表的高度/悬停精度数字是在旧的
        "位置级联"路径 (读 mc.target_pos → 位置环 → 速度环 → 推力) 上测的。
        打开本开关会换掉物理驱动方式, 数值随之改变; 因此默认值绝不能翻转,
        需要新链路的调用方必须显式传入 True。

        传输层 (Phase 3 保真度, 默认全 0 = 完全关闭):
          sensor_latency_s: 遥测单程延迟 (s), 离散延迟线, 不 sleep;
          sensor_drop_rate: 遥测丢包率 [0,1], 序列由 transport_seed 决定 (可复现);
          actuator_tau_s:   速度指令→机体速度的一阶滞后时间常数 (s);
          transport_seed:   丢包随机序列种子。
        全 0 时两个模型对象都不创建, 构造与 step() 路径与加这些开关之前逐位一致。
        """
        self.mc = mc
        self.quad = quad
        self.wind = wind_model
        self.arm = arm
        self.sensor = sensor
        self.velocity_command_mode = bool(velocity_command_mode)

        # ---- Phase 3 传输层 (默认全 0 = 不创建对象, 对旧数值零影响) ----
        self._transport_enabled = (sensor_latency_s > 0.0 or sensor_drop_rate > 0.0)
        self._sensor_transport = (
            SensorTransportModel(latency_s=sensor_latency_s,
                                 drop_rate=sensor_drop_rate,
                                 seed=transport_seed,
                                 loss_model=sensor_loss_model,
                                 mean_burst_len=sensor_mean_burst_len)
            if self._transport_enabled else None)
        # 上行指令链路 (真机 = 控制器输出 → RCManager 20Hz 下发): 同样有延迟与丢包,
        # 而且丢包帧在真机上是"保持上一条指令直到 0.5s 超时归零"。
        self._uplink_enabled = (uplink_latency_s > 0.0 or uplink_drop_rate > 0.0)
        self._command_transport = (
            CommandTransportModel(latency_s=uplink_latency_s,
                                  drop_rate=uplink_drop_rate,
                                  seed=transport_seed,
                                  loss_model=uplink_loss_model,
                                  mean_burst_len=uplink_mean_burst_len)
            if self._uplink_enabled else None)
        self._cmd_time = 0.0           # 上行链路自己的仿真时钟 (秒)
        self._last_arrived_cmd = None  # 最近一条**到达机体**的指令 (丢包帧保持它)
        # 最近一条指令**到达机体**的仿真时刻 (秒); None = 还没有任何指令到达过。
        # 归零计时以它为基准 (RC_ZERO_TIMEOUT), 而不是以"上次调用 poll"为基准 ——
        # 丢包帧 poll 仍会返回上一条指令, 计时器必须靠**真正的交付时刻**前进。
        self._last_cmd_arrival_t = None
        self._actuator = (ActuatorLag(tau_s=actuator_tau_s)
                          if actuator_tau_s > 0.0 else None)
        self._last_delivered_z = None  # 最近一次真正交付的遥测向量 z (丢包帧保持它)
        # 整包反馈 (z, pos_cm, vel_cmps, att): 真机的状态包是**整体**到达的, 所以
        # 三者必须走同一条延迟/丢包路径 —— 只延迟 z 而让 pos/vel/att 保持瞬时真值,
        # 会系统性地低估延迟。
        self._last_delivered_feedback = None
        self._sim_time = 0.0           # 延迟线用的仿真时钟 (秒), 不是墙钟
        self._last_sensor_age_s = 0.0  # 最近一次交付测量的年龄 (供 EKF 使用)

        # Replace mc's MockTello with SimDroneAdapter (is_flying reflects physics).
        # SimDroneAdapter.land()/emergency() defer is_flying=False until mark_landed(),
        # so mc's LAND/EMERGENCY handlers wait for physics touch-down.
        # 速度模式下, 若启用了**上行传输模型**, 机体速度通道必须由 runtime 独占:
        # 否则适配器的直写会绕过上行延迟/丢包("界面在发速度"直接变成机体运动)。
        # 未启用上行模型时保留历史行为(直写), 以免改动已被验证的速度模式数值。
        adapter = SimDroneAdapter(
            quad, write_velocity_channel=not (velocity_command_mode and self._uplink_enabled))
        adapter.connect()
        mc.drone = adapter
        self.adapter = adapter  # 速度指令模式下物理指令的来源

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
        if self.velocity_command_mode:
            print("[SIM] velocity-command mode: command path == real RC path")

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
            if self.velocity_command_mode:
                # 速度指令模式: 物理由控制器下发的速度指令驱动 (真机同源链路)
                a_des = self._step_velocity_command(sim_dt, wind_f)
            else:
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

        # 遥测**整包**先过传输模型 (延迟/丢包)。默认关闭时原样返回且无任何副作用。
        feedback = (z, m_to_cm(pos), mps_to_cmps(vel), att)
        feedback_fed, dropped = self._transport_feedback(feedback, sim_dt)
        z_fed, pos_fed, vel_fed, att_fed = feedback_fed
        guard = hb_before = None
        if dropped:
            # 丢包帧需要在调用后回退心跳时间戳, 先记下本帧之前的值
            guard = getattr(self.mc, "safety_guard", None)
            hb_before = getattr(guard, "_last_heartbeat", None)

        ctrl_cmps, state_dict = self.mc.update_with_external_data(
            z_fed, pos_fed, vel_fed, att_fed,
            telemetry_fresh=(not dropped),
            sensor_age_s=self._last_sensor_age_s,
        )

        if dropped:
            # 丢包帧: 显式向 mc 表达"本帧没有新遥测"(已通过 telemetry_fresh 参数传入)。
            # 但 update_with_external_data 在同一帧的 _check_safety 里已经消费过一次
            # 心跳, 所以还必须把心跳时间戳退回本帧之前 —— 否则 FailsafeMonitor 的
            # timeout_land/timeout_kill 永远算不出中断。
            # 与既有风格一致: 本文件本就直写 mc._last_control_accel 这类内部字段。
            self.mc._sensor_fresh = False
            if hb_before is not None:
                guard._last_heartbeat = hb_before

        # 速度指令模式: 把控制器输出接回真机同款链路 (controller → drone.set_velocity)。
        # 真机路径里 main.py 的 _send_control() 会把控制输出交给 drone.set_velocity,
        # 由 RCManager 以 20Hz 持续下发; mock 模式下 main.py 只做 current_pos 积分,
        # 这一步因此缺失, 这里显式补上, 让无头仿真与真机共用同一条指令链路。
        if self.velocity_command_mode:
            self._issue_velocity_command(ctrl_cmps, pos)

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

    def _transport_feedback(self, feedback, sim_dt):
        """把本帧**整包反馈**送进延迟/丢包模型, 返回 (喂给 mc 的反馈, 本帧是否丢包)。

        feedback = (z, pos_cm, vel_cmps, att)。真机的状态包是整体到达的, 所以
        z 与 pos/vel/att 必须走同一条延迟/丢包路径 (只延迟 z 会低估延迟)。

        约定 (仿真时钟, 由 sim_dt 累加, 不用墙钟):
          * 每帧 push 本帧原始反馈, 再 poll 同一时刻;
          * poll 拿到样本 -> 本帧"有新遥测", 交付它;
          * poll 为 None  -> 本帧未交付 (延迟未到期 或 被丢包):
            **继续喂上一帧交付的反馈** (HOLD)。若改喂空/零向量, EKF 会直接
            崩掉或发散, 仿真卡死; 保持旧样本才是"接收端没有新数据"的正确物理。
            延迟线暖机期 (还没交付过任何样本) 用本帧原始反馈兜底, 避免 EKF 的
            第一次 update 吃到非测量值。

        关闭时 (latency=0 且 drop_rate=0) 直接返回原对象, 逐位不变。
        """
        if not self._transport_enabled:
            return feedback, False
        self._sim_time += sim_dt
        self._sensor_transport.push(feedback, self._sim_time)
        delivered = self._sensor_transport.poll(self._sim_time)
        dropped = delivered is None
        if not dropped:
            self._last_delivered_feedback = delivered
        elif self._last_delivered_feedback is None:
            self._last_delivered_feedback = feedback
        self._last_delivered_z = self._last_delivered_feedback[0]
        # 测量年龄 = 现在 - 最近一次**成功交付**样本的采样时刻。EKF 用它来放大 R:
        # 延迟到达的测量本来就更不可信, 不该被当成"刚到的新测量"。
        age = self._sensor_transport.last_age(self._sim_time)
        self._last_sensor_age_s = 0.0 if age is None else float(age)
        return self._last_delivered_feedback, dropped

    def _step_velocity_command(self, sim_dt, wind_f):
        """速度指令模式的一帧物理: 语义与 backend/simulation/simulation.py 的 step() 对齐。

        真机链路 = 控制器输出速度指令 → RCManager 20Hz 持续下发 → 机体速度环。
        这里用 adapter 记录的速度指令 (m/s) 驱动同一个物理模型:
          1) 对 (v_cmd - vel) 做加速度限幅 MAX_ACCEL, 速度不瞬变 (推力饱和手感);
          2) 叠加风扰 (与 simulation.py 同为 F/m·dt·0.3);
          3) quad.set_velocity(vel_new) 并积分位置 p += v·dt (z 不低于 0)。

        返回本帧**控制**加速度 (m/s², 不含风), 供 EKF 区分控制与扰动:
        若不回喂, EKF 会把全部 IMU 读数归因于扰动, 速度/位置估计会膨胀。
        """
        vel = self.quad.get_velocity()
        v_cmd = self.adapter.get_commanded_velocity()
        if self._command_transport is not None:
            # 上行链路: 指令先经延迟/丢包。丢包帧保持**最近已到达**的指令, 但保持
            # 有时间上限 —— 真机 RCManager 在 ZERO_TIMEOUT(0.5s) 内没有**新指令**
            # 就自动下发零速度(防飞丢)。计时基准是"上一条指令到达机体的时刻":
            # poll() 在丢包帧仍会返回上一条指令, 所以只有 last_delivery_time()
            # (内部仅在真正交付时推进) 能区分"新指令到了"与"还在吃旧指令"。
            # 超时后本帧用**零**指令, 不是保持上一条 —— 否则仿真比真机乐观。
            self._cmd_time += sim_dt
            self._command_transport.push(v_cmd, self._cmd_time)
            arrived = self._command_transport.poll(self._cmd_time)
            if arrived is not None:
                self._last_arrived_cmd = arrived
                self._last_cmd_arrival_t = self._command_transport.last_delivery_time()
            if (self._last_arrived_cmd is None or self._last_cmd_arrival_t is None
                    or self._cmd_time - self._last_cmd_arrival_t > RC_ZERO_TIMEOUT):
                v_cmd = np.zeros(3)          # 超时归零 (还没有指令到达过时同样是零)
            else:
                v_cmd = self._last_arrived_cmd
        if self._actuator is not None:
            # 执行器一阶滞后 (PT1): 机体速度环无法瞬时跟上指令。tau=0 时本对象
            # 根本不存在 (构造处为 None), v_cmd 原样使用 —— 逐位不变。
            v_cmd = self._actuator.update(v_cmd, sim_dt)
        dv = v_cmd - vel
        dv_norm = float(np.linalg.norm(dv))
        if dv_norm > MAX_ACCEL * sim_dt:
            dv = dv * ((MAX_ACCEL * sim_dt) / dv_norm)
        a_ctrl = dv / sim_dt  # 本帧实际控制加速度 (m/s²)

        vel_new = vel + dv
        vel_new = vel_new + (wind_f / self.quad.mass) * sim_dt * 0.3

        self.quad.set_velocity(vel_new)
        self.quad.state[0:3] += vel_new * sim_dt  # p += v·dt
        self.quad.state[2] = max(0.0, self.quad.state[2])
        # 姿态可视化: 由速度反推倾角 (与 simulation.py 一致)
        self.quad.state[6] = float(np.clip(-vel_new[1] * 0.12, -0.4, 0.4))  # roll
        self.quad.state[7] = float(np.clip(vel_new[0] * 0.12, -0.4, 0.4))   # pitch
        return a_ctrl

    def _issue_velocity_command(self, ctrl_cmps, pos):
        """把速度指令下发到 adapter —— 与真机 main.py._send_control() 同口径。

        命令来源按状态分两类:
        1) HOVERING/NAVIGATE/INSPECT/RETURN: mc 控制器输出 (cm/s), 直接下发;
           死区 (三轴都 <1cm/s) 与 main.py._send_control 一致: **立即归零**
           (真机调 drone.stop_velocity()), 不保持上一条。
        2) TAKEOFF/LAND/EMERGENCY: mc 在这些状态**不调用 controller.compute**
           (main.py._handle_state_machine 只在上面 4 个状态算控制量), 因为真机上
           起飞爬升/降落是机体自主完成的平台原语 (Tello SDK takeoff()/land())。
           仿真没有那个平台, 必须自己补一段垂直速度, 否则飞机永远离不开地面、
           也降不下去。这是"补平台原语", 不是把位置级联搬进来: 水平两轴在这些
           状态下仍然是零指令。
        """
        state = self.mc.state
        if state == "IDLE":
            self.adapter.clear_velocity_command()  # 落地/复位后不许残留指令
            return

        if state in ("TAKEOFF", "LAND", "EMERGENCY"):
            target_z = float(cm_to_m(self.mc.target_pos)[2])
            vz = float(np.clip((target_z - pos[2]) / POS_TAU,
                               -MAX_VSPEED, MAX_VSPEED))
            cmd = np.array([0.0, 0.0, mps_to_cmps(vz)])
        else:
            if ctrl_cmps is None:
                # 与 main.py._send_control 对齐: output=None 也走归零分支 (不是保持)。
                self.adapter.clear_velocity_command()
                return
            out = np.asarray(ctrl_cmps, dtype=float).ravel()
            if out.size < 3 or np.all(np.abs(out[:3]) < 1):
                # 死区: **立即归零**, 不是保持上一条。main.py._send_control 的死区
                # 分支已经改成调用 drone.stop_velocity(); 老注释"与 main.py 一致"
                # 早已不成立 —— 保持上一条会让小指令多活到 RCManager 的 0.5s 超时。
                # adapter 没有 stop_velocity(); clear_velocity_command() 就是它的
                # 同义实现 (见 SimDroneAdapter.hover 的注释: "与真机 stop_velocity
                # 同义")。这里**不**调 set_velocity(0,0,0): 未启用上行模型时它会直写
                # 机体速度通道, 把"指令归零"变成"速度瞬时归零", 不是真机语义。
                self.adapter.clear_velocity_command()
                return
            cmd = out[:3]

        self.adapter.set_velocity(float(cmd[0]), float(cmd[1]), float(cmd[2]))

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
            self.adapter.clear_velocity_command()
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
        if "ArrowLeft" in keys:
            angles[0] = (angles[0] - delta) % 180
        if "ArrowRight" in keys:
            angles[0] = (angles[0] + delta) % 180
        if "ArrowUp" in keys:
            angles[1] = min(150, angles[1] + delta)
        if "ArrowDown" in keys:
            angles[1] = max(30, angles[1] - delta)
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
            if "KeyW" in keys:
                self.mc.target_pos[0] += step_cm
            if "KeyS" in keys:
                self.mc.target_pos[0] -= step_cm
            if "KeyA" in keys:
                self.mc.target_pos[1] -= step_cm
            if "KeyD" in keys:
                self.mc.target_pos[1] += step_cm
            if "PageUp" in keys:
                self.mc.target_pos[2] += vstep_cm
            if "PageDown" in keys:
                self.mc.target_pos[2] -= vstep_cm
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
                self.adapter.clear_velocity_command()  # 落地后不许残留速度指令
