"""
主调度程序 — 整合所有模块的主循环

架构: 主线程调度, 传感器/视频子线程, 100ms周期

状态机:
    IDLE → TAKEOFF → NAVIGATE → INSPECT → RETURN → LAND
    任意状态 → EMERGENCY (电池低/通信断/人工急停)
"""

import time

import numpy as np
from typing import Optional     # 注解在 Python 3.11/3.12 上是**定义时求值**的(3.14 起才延迟)

from backend.core.disturbance_observer import DisturbanceObserverEKF
from backend.core.feedforward_controller import FeedforwardController
from backend.core.trajectory_planning import RRTStarPlanner
from backend.vision.detect import DefectDetector
from backend.mission.safety import FailsafeMonitor, SafetyLevel
from backend.drone.tello_basic import TelloController
from backend.drone.tello_video import TelloVideoStream
from backend.utils.logger import FlightLogger
from backend.utils.config import ConfigLoader
from backend.utils.bus import create_message_bus
from backend.utils.bus import TOPIC_MISSION_STATUS, TOPIC_DRONE_COMMAND
from backend.mission.states import TERMINAL_STATES, MissionState, can_transition


class MissionController:
    """
    任务主调度器 — 有限状态机(FSM)驱动。

    状态机:
      IDLE → TAKEOFF → NAVIGATE → INSPECT → RETURN → LAND
      任意状态 → EMERGENCY (电池低/通信断/人工急停)

    用法:
      python backend/main.py --mode simulation --target "10,0,20"
    """

    def __init__(self, mode: str = "simulation", mock: bool = True,
                 config_dir: str = None):
        self.mode = mode  # "simulation" | "hardware"
        self.mock = mock

        # =====================================================================
        # 加载配置 (P2-5: 代码真正读取config YAML)
        # =====================================================================
        try:
            self.cfg = ConfigLoader.load("drone_config", config_dir=config_dir)
        except Exception as e:
            # 硬件模式: 配置缺失必须 fail-fast, 不能用默认值飞行
            if mode == "hardware":
                raise RuntimeError(
                    "[MAIN] FATAL: 硬件模式下配置加载失败, 拒绝用默认值飞行。"
                    "请确认 config/drone_config.yaml 存在且格式正确。"
                    "\n原始错误: {}".format(e)
                ) from e
            # 仿真/开发模式: 允许回退到默认值
            import logging
            logging.warning("[MAIN] 配置加载失败, 使用硬编码默认值: %s", e)
            self.cfg = None

        # 从配置读取参数, 配置缺失时回退到硬编码默认值
        # P0-C: dt 从 control_rate_hz 计算, 默认 10Hz → 0.1s
        rate = self._cfg_val("flight.control_rate_hz", 10)
        self.dt = 1.0 / rate if rate > 0 else 0.1

        # =====================================================================
        # 子模块 — 算法层 (从配置读取参数)
        # =====================================================================
        self.ekf = DisturbanceObserverEKF(dt=self.dt)
        self.controller = self._build_controller()
        self.planner = RRTStarPlanner()
        self.detector = DefectDetector(mock=mock)

        # =====================================================================
        # 安全守护 (P0-1: 集成SafetyGuard) — 从配置读取阈值
        # =====================================================================
        self.safety_guard = self._build_safety_guard()
        # =====================================================================
        # 无人机控制器 (P0-5: 组合TelloController)
        # =====================================================================
        self.drone = TelloController(mock=mock)
        # P0-2a 修复(审计): 删除这里多余的 RCManager。
        # 它把 TelloController 当作底层对象传入, 而 RCManager 调用的是
        # send_rc_control —— TelloController 并没有这个方法, 所以那条 20Hz
        # 线程自始至终空转, 而且 stop() 也从不停止它。
        # 真正生效的 RC 管理器是 TelloController._rc (在 connect() 里 attach+start)。
        if self.mock:
            # P0-D: mock模式自动连接, 避免TAKEOFF死锁
            self.drone.connect()

        # ---- 安全闸门与终态 (本轮新增) ----
        # 真机默认**没有**可信外部定位: 位置观测是"上一帧估计的自我循环",
        # 因此 NAVIGATE / INSPECT / RETURN 这些依赖位置的自动状态一律禁止进入,
        # 直到显式调用 enable_external_localization() 声明已接入真实定位源。
        self._external_localization = False
        self._localization_source = None
        self._localization_source_obj = None   # 真正的外部定位源对象 (见 attach_...)
        self._last_localization = None         # 最近一次可用观测 (供状态汇报)
        self._telemetry_stale = False          # 本帧遥测是否陈旧 (供状态汇报, 不被消费)
        self._fault_descent_started = False    # FAULT 时是否已发起受控下降
        self._fault_land_requested = False     # FAULT 收尾: 是否已成功下发 land()
        self._fault_land_failures = 0          # FAULT 收尾: land() 未成功的次数
        self._fault_land_retry = 0             # FAULT 收尾: 重试帧计数
        self._fault_descent_failures = 0       # 终态下降"未推进"的计数(限频告警)
        self._terminal_latched = False         # 终态闩锁: 只能 clear_fault() 解锁
        self._video_last_obj = None            # 视频冻结检测: 上一帧对象
        self._video_last_change_t = None       # 视频冻结检测: 最近一次换帧的时刻
        self._video_seen_change = False        # 是否曾观察到换帧(避免启动瞬间误判)
        self._video_seen_frame = False         # 是否**拿到过任何帧**(零帧也算不可用)
        self._fault_reason = None
        self._mission_failed_reason = None

        # =====================================================================
        # 状态机 (P0-2: 完整8状态)
        # =====================================================================
        self.state = "IDLE"
        default_hover = self._cfg_val("flight.default_hover_height", 100)
        self.target_pos = np.array([0.0, 0.0, float(default_hover)])
        self.current_pos = np.zeros(3)
        self.current_vel = np.zeros(3)
        # P1-9: mock 模式 IMU 用速度差分估加速度，需保存上一帧速度
        self._prev_vel_for_imu = np.zeros(3)
        self.current_attitude = np.zeros(3)
        self._battery = 100

        # 路径跟踪
        self.path = None
        self.path_idx = 0

        # 状态计时
        self._last_detection_count = 0
        self._state_entry_time = time.time()
        self._hover_stabilize_start = 0.0

        # 安全监控
        self._emergency_reason = ""
        self._emergency_sent = False  # P0-1: 紧急下降是否已下发(防每帧重复)
        self._ekf_honesty_warned = False  # P0-3: EKF 假观测告警只打一次

        # 上一次的控制输出 (用于EKF predict时传入已知控制输入)
        self._last_control_output = np.zeros(3)
        self._last_control_accel = np.zeros(3)  # N6: 真实加速度 (cm/s²) 供EKF预测

        # 视频流 (P1-12: 集成视频采集)
        self.video_stream = TelloVideoStream(tello_controller=self.drone, mock=mock)

        # 飞行日志 (P1-12: 集成FlightLogger)
        self.logger = FlightLogger()

        # 消息总线 (Dashboard集成 — pub-sub 每条 topic 独立队列)
        self.bus = create_message_bus()
        self._cmd_sub = self.bus.subscribe(TOPIC_DRONE_COMMAND)
        self._status_sub = self.bus.subscribe(TOPIC_MISSION_STATUS)  # 预留

        # 子线程控制
        self._running = False
        self._video_frame = None

    # =========================================================================
    # 配置辅助方法 (P2-5: 消除硬编码)
    # =========================================================================

    def _cfg_val(self, path: str, default):
        """从配置读取嵌套值, 缺失时返回默认值"""
        if self.cfg is None:
            return default
        try:
            keys = path.split(".")
            val = self.cfg
            for k in keys:
                val = getattr(val, k)
            return val
        except (AttributeError, KeyError):
            return default

    def _build_controller(self):
        """从配置构建 FeedforwardController"""
        return FeedforwardController(
            Kp=self._cfg_val("controller.Kp", 2.0),
            Ki=self._cfg_val("controller.Ki", 0.1),
            Kd=self._cfg_val("controller.Kd", 1.0),
            Kff=-1.0,  # 前馈补偿固定为负
            dt=self.dt,
            max_speed=self._cfg_val("flight.max_speed", 50),
        )

    def _build_safety_guard(self):
        """构建分层 FailsafeMonitor (N1: 替换旧SafetyGuard)"""
        monitor = FailsafeMonitor()
        T = monitor.THRESHOLDS
        # P1-1 修复: 阈值优先读 config/drone_config.yaml 的 safety.tiers.*。
        # 此前读的是 safety.battery_warn / safety.battery_kill 等 YAML 中并不存在的键,
        # 导致 battery_warn 实际取硬编码 30(而非 YAML 的 20), 且 timeout_* 从未被读取。
        # 旧键保留为向后兼容回退。
        T["battery_warn"] = self._cfg_val(
            "safety.tiers.battery_warn", self._cfg_val("safety.battery_warn", T["battery_warn"]))
        T["battery_land"] = self._cfg_val(
            "safety.tiers.battery_land",
            self._cfg_val("safety.low_battery_land_threshold", T["battery_land"]))
        T["battery_kill"] = self._cfg_val(
            "safety.tiers.battery_kill", self._cfg_val("safety.battery_kill", T["battery_kill"]))
        T["attitude_land"] = self._cfg_val("safety.tiers.attitude_land", T["attitude_land"])
        T["attitude_kill"] = self._cfg_val("safety.tiers.attitude_kill", T["attitude_kill"])
        T["height_land"] = self._cfg_val(
            "safety.tiers.height_land", self._cfg_val("safety.boundary.z_max", T["height_land"]))
        T["height_kill"] = self._cfg_val(
            "safety.tiers.height_kill", self._cfg_val("safety.boundary.z_kill", T["height_kill"]))
        T["timeout_land"] = self._cfg_val("safety.tiers.timeout_land", T["timeout_land"])
        T["timeout_kill"] = self._cfg_val("safety.tiers.timeout_kill", T["timeout_kill"])
        return monitor

    # =========================================================================
    # 主循环
    # =========================================================================

    def start(self):
        """启动主循环"""
        self._running = True
        print("[MAIN] 主循环启动, dt={:.0f}ms".format(self.dt * 1000))

        # 启动日志记录 (P1-12)
        self.logger.start_session()

        # 启动视频流 (P1-12)
        self.video_stream.start()

        if not self.mock:
            # 真机模式: 连接Tello
            if not self.drone.connect():
                # P1-3: 硬件连接失败绝不降级为模拟 —— 直接进故障态并停任务。
                # 此前会静默 self.mock = True 换一个模拟控制器, 让"根本没连上"
                # 在日志和界面上看起来像正常运行。
                self._hardware_fault = "Tello 连接失败"
                self._running = False
                print("[ERROR] HARDWARE_FAULT: Tello 连接失败, 任务不启动 "
                      "(不会降级为模拟模式)")
                return False
        self._hardware_fault = None

        while self._running:
            loop_start = time.time()

            self._update()

            # 维持固定周期
            elapsed = time.time() - loop_start
            sleep_time = self.dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        return True

    def _update(self):
        """单次控制循环 (带故障保护层, 审计 P0-C)。

        此前 _update() 是裸调用: 传感器/控制器一旦抛异常, 会一路冲穿 start()
        的主循环 —— 控制线程静默死掉, 而无人机还在空中按最后一条指令飞。
        现在任何异常都会: 停止速度指令 → 进入 FAULT 终态 → 记录原因。
        """
        try:
            self._update_inner()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.mark_fault("控制循环异常: {}".format(e))

    def _update_inner(self):
        """单次控制循环 (实际实现)"""

        # =====================================================================
        # 1. 处理 Dashboard 命令
        # =====================================================================
        self._process_bus_commands()

        # =====================================================================
        # 2. 获取传感器数据
        # =====================================================================
        z = self._get_sensor_data()

        # =====================================================================
        # 3. EKF预测+更新 (传入已知控制输入以分离扰动估计)
        # =====================================================================
        # 审计 D3(我方核验发现): 此处**不能**传 `_last_control_output` —— 它是控制器的
        # **速度指令(cm/s)**(见 _send_control 的注释), 而 EKF 的 u 语义是**控制加速度(cm/s²)**:
        # `predict` 会把加速度状态直接设成 u 并把其协方差压到 0.01, 量纲/语义错了会**静默**
        # 污染 d̂ = IMU − u。
        # 真机当前没有可用的"控制加速度"量 ⇒ 传 None, 让 EKF 自行估计 a 与 d(诚实);
        # 仿真/mock 由 SimRuntime 回喂真实控制加速度(见 update_with_external_data)。
        self.ekf.predict(u=self._last_control_accel if self.mock else None)
        if z is not None:
            # 真机路径同样带测量年龄: 遥测包可能已经"旧"了一段时间才被消费。
            self.ekf.update(z, age_s=self._telemetry_age_s())

        ekf_state = self.ekf.get_state()
        self.current_pos = ekf_state["position"]
        self.current_vel = ekf_state["velocity"]
        disturbance = ekf_state["disturbance"]

        # =====================================================================
        # 4. 更新视频帧 (P1-12: 从视频流获取)
        # =====================================================================
        self._video_frame = self.video_stream.get_frame()
        self._feed_localization_frame()

        # =====================================================================
        # 5. 安全检查 (P0-1: SafetyGuard集成)
        # =====================================================================
        self._check_safety()

        # 审计第 4 条: 任务期逐帧有效性检查 (定位/视觉/视频中途失效当场处置)
        self._check_task_validity()

        # =====================================================================
        # 6. 状态机处理 — EMERGENCY 时也必须运行 (执行紧急降落逻辑)
        # =====================================================================
        detections = self._handle_state_machine(disturbance)

        # =====================================================================
        # 7. 记录飞行日志 (P1-12)
        # =====================================================================
        self._log_frame(disturbance, detections if detections else [])

        # =====================================================================
        # 8. 发布状态到消息总线 (Dashboard集成)
        # =====================================================================
        # pub-sub: publish 到独立 topic, 不影响 Dashboard 命令通道
        self.bus.publish(TOPIC_MISSION_STATUS, self.get_state_dict(), source="main")

    # =========================================================================
    # 状态机 (P0-2: 完整实现)
    # =========================================================================

    def _handle_state_machine(self, disturbance):
        """处理当前状态的行为, 返回 (detections, control_output)

        P0-B: controller.compute() 统一在此调用一次, 各状态处理器设置
        self._pending_control 而非直接调用 _send_control()
        """
        self._pending_control = np.zeros(3)
        detections = []

        # ---------- FAULT / MISSION_FAILED: 终态, 但**安全动作必须继续执行** ----------
        # 第三轮审计: 终态不等于"什么都不做"。
        # 第四轮审计 D1: 判"是否还在空中"**不能只看 is_flying** —— 真机 land() 失败会转入
        # EMERGENCY, 而 is_flying 在 EMERGENCY 下是 False, 于是整套下降/收尾逻辑被跳过。
        # 这里改为 **fail-closed**:
        #   高度不可信(None) 或 >30cm  ⇒ 一律当作"仍在空中", 继续推进下降;
        #   高度可信且 <=30cm          ⇒ 请求 land() 收尾, 且**必须检查返回值**。
        if self.state in self.FAILURE_STATES:
            self._pending_control = np.zeros(3)
            height = self._safe_height_cm()
            low = (height is not None and height <= self.FAULT_LAND_HEIGHT_CM)
            if not low:
                # 高度未知或仍偏高: fail-closed 当作**仍在空中**, 继续推进下降
                self._fault_descend_step()
                self._maybe_retry_fault_landing(height)
                return detections, self._pending_control
            if self._grounded_confirmed():
                return detections, self._pending_control          # 正面确认已落地 -> 停手
            if self._adapter_accepts_land():
                if not getattr(self, "_fault_land_requested", False):
                    self._request_fault_landing(height)           # 低空 + 可降落 -> 收尾
                return detections, self._pending_control          # 已下发: 等触地, 不叠加下降
            # 低空但适配器**不接受** land()(真机 EMERGENCY/LANDING 等): 只能继续 RC 下降。
            # (第五轮审计 D17: 此处若"重试 land()"是空转 —— 它只会 return False 不下发命令)
            self._note_land_unavailable()
            self._fault_descend_step()
            return detections, self._pending_control

        # ---------- IDLE: 等待指令 ----------
        if self.state == "IDLE":
            pass  # 等待外部 set_target / plan_path / takeoff 调用

        # ---------- TAKEOFF: 起飞到悬停高度 ----------
        elif self.state == "TAKEOFF":
            if self.drone.is_flying:
                if self.current_pos[2] >= self.target_pos[2] - 20:
                    # 达到目标高度, 进入悬停
                    self._set_state("HOVERING", "起飞完成", automatic=True)
                    print("[MAIN] 起飞完成, 进入悬停")
            else:
                # 发送起飞指令
                self.drone.takeoff()

        # ---------- HOVERING: 悬停等待 ----------
        elif self.state == "HOVERING":
            # P0-B: 计算控制输出一次, 缓存待发送
            self._pending_control, _ = self.controller.compute(
                self.target_pos, self.current_pos,
                disturbance_est=disturbance, current_vel=self.current_vel,
            )
            if self.path is not None and self.path_idx < len(self.path):
                # 无外部定位时会被闸门拦下 -> MISSION_FAILED (不做假成功)
                self._set_state("NAVIGATE", "进入导航", automatic=True)
                print("[MAIN] 悬停→导航, 路径点数={}".format(len(self.path)))

        # ---------- NAVIGATE: 沿路径点移动 ----------
        elif self.state == "NAVIGATE":
            if self.path is not None and self.path_idx < len(self.path):
                self.target_pos = self.path[self.path_idx]
                dist_to_waypoint = np.linalg.norm(
                    self.current_pos - self.target_pos
                )
                if dist_to_waypoint < self._cfg_val("flight.waypoint_reach_radius", 30):  # 到达当前路径点
                    self.path_idx += 1
                    print(
                        "[MAIN] 路径点 {}/{} 到达".format(
                            self.path_idx, len(self.path)
                        )
                    )
                else:
                    self._pending_control, _ = self.controller.compute(
                        self.target_pos, self.current_pos,
                        disturbance_est=disturbance, current_vel=self.current_vel,
                    )
            else:
                # 路径走完, 进入巡检 —— 这里是审计 P0-A 的要害:
                # 必须走统一闸门; 视觉不可用时进入 MISSION_FAILED,
                # 绝不能显示"导航完成, 进入巡检"然后按巡检超时假装完成。
                self._set_state("INSPECT", "导航完成", automatic=True)
                if self.state == "INSPECT":
                    print("[MAIN] 导航完成, 进入巡检")

        # ---------- INSPECT: 巡检 + 缺陷检测 ----------
        elif self.state == "INSPECT":
            # 悬停在巡检点
            self._pending_control, _ = self.controller.compute(
                self.target_pos, self.current_pos,
                disturbance_est=disturbance, current_vel=self.current_vel,
            )

            # 缺陷检测
            if self._video_frame is not None:
                detections = self.detector.detect(self._video_frame)
                if len(detections) > 0:
                    print("[DETECT] 发现 {} 个缺陷".format(len(detections)))
                    for d in detections:
                        print(
                            "  - {} (conf={:.2f})".format(
                                d.get("class_name", "unknown"),
                                d.get("confidence", 0),
                            )
                        )

            # 巡检完成后自动返航 (超时或手动触发)
            inspect_elapsed = time.time() - self._state_entry_time
            if inspect_elapsed > self._cfg_val("mission.inspect_timeout_s", 30):  # 30秒巡检超时
                # 审计 P0-A 第 3 条: 巡检期间视觉掉线(模型连续失败/无有效帧)时,
                # 不能按"巡检完成"返航 —— 那会产生假的"任务成功"。
                if not getattr(self.detector, "is_available", True):
                    self._set_state(
                        "MISSION_FAILED",
                        "巡检期间 VISION_UNAVAILABLE: {}".format(
                            getattr(self.detector, "unavailable_reason", "unknown")),
                        force=True)
                    print("[MISSION_FAILED] 巡检期间视觉不可用, 任务失败(不算完成)")
                else:
                    self._set_state("RETURN", "巡检超时", automatic=True)
                    print("[MAIN] 巡检超时, 开始返航")

        # ---------- RETURN: 返航到起飞点 ----------
        elif self.state == "RETURN":
            # 从配置读取安全返航点 (默认起飞点上空100cm)
            home = np.array([
                self._cfg_val("safety.safe_point.x", 0),
                self._cfg_val("safety.safe_point.y", 0),
                self._cfg_val("safety.safe_point.z", 100),
            ], dtype=float)
            self.target_pos = home

            self._pending_control, _ = self.controller.compute(
                self.target_pos, self.current_pos,
                disturbance_est=disturbance, current_vel=self.current_vel,
            )

            # 到达返航点后降落
            if np.linalg.norm(self.current_pos - home) < 30:
                self._set_state("LAND", "返航完成", automatic=True)
                print("[MAIN] 返航完成, 开始降落")

        # ---------- LAND: 降落 ----------
        elif self.state == "LAND":
            # 下降目标: 地面 (SimRuntime 级联控制读 mc.target_pos 驱动物理下降)
            self.target_pos[2] = 0.0
            # 发送降落指令
            if self.drone.is_flying:
                self.drone.land()
            # 等待降落完成 (SimDroneAdapter 延迟 is_flying=False 直到物理触地)
            if not self.drone.is_flying or self.current_pos[2] < 20:
                self._set_state("IDLE", "降落完成", automatic=True)
                print("[MAIN] 降落完成, 进入IDLE")

        # ---------- EMERGENCY: 紧急状态 ----------
        elif self.state == "EMERGENCY":
            # 紧急下降目标: 地面 (触发紧急时 trigger_emergency 已打印入口日志)
            self.target_pos[2] = 0.0
            # 审计 P0-D 补完: 改为**分帧小脉冲**下降。
            # 此前一次性 emergency() 在真机上最多阻塞 0.5s(约等于 10Hz 回路的 5 帧)。
            # 有 emergency_descent 时每帧只推一小步(0.1s); 老适配器(如仿真)回退为
            # "只下发一次 emergency()"。
            descent = getattr(self.drone, "emergency_descent", None)
            if callable(descent):
                try:
                    descent(timeout_s=0.1, poll_s=0.05, release_velocity=False)
                except TypeError:          # 旧签名
                    descent(timeout_s=0.1)
            elif not getattr(self, "_emergency_sent", False):
                self.drone.emergency()
                self._emergency_sent = True
            # 审计 P0-D: 不再把"高度 <3m"当成通用安全证明(高度可能是陈旧/无效值)。
            # 真机只有高度**确实已知**且 <=30cm 才允许真正停桨;
            # 没有该能力的适配器(如 SimDroneAdapter)保留旧行为, 以免改动
            # 已经过验证的仿真数值。
            if self.drone.is_flying:
                known = getattr(self.drone, "height_is_known", None)
                if callable(known):
                    if known() and float(self.current_pos[2]) < 30.0:
                        self.drone.motor_cutoff("controlled_touchdown")
                elif float(self.current_pos[2]) < 300:
                    self.drone.kill()
            # 转为降落状态 (SimDroneAdapter 延迟 is_flying=False 直到物理触地)
            if not self.drone.is_flying:
                self._set_state("IDLE", "紧急降落完成", automatic=True)
                self._emergency_sent = False
                print("[MAIN] 紧急降落完成")

        # P0-B: 统一发送控制指令 (一帧只发一次)
        self._send_control(self._pending_control)
        self._last_detection_count = len(detections) if detections else 0
        return detections, self._pending_control

    # =========================================================================
    # Dashboard 命令处理
    # =========================================================================

    def _process_bus_commands(self):
        """处理来自 Dashboard 的命令消息 (pub-sub: 独立队列不竞争)"""
        while True:
            msg = self._cmd_sub.read_latest()
            if msg is None:
                break
            if isinstance(msg.data, dict):
                cmd = msg.data.get("command", "")
                if cmd == "takeoff":
                    self.takeoff()
                elif cmd == "land":
                    if self.state != "IDLE":
                        self.request_state("LAND", "Dashboard降落")
                        print("[MAIN] Dashboard: 降落指令")
                elif cmd == "emergency":
                    self.trigger_emergency("Dashboard紧急停止")

    # =========================================================================
    # 传感器数据获取
    # =========================================================================

    def _get_sensor_data(self):
        """获取传感器数据, 返回EKF观测向量 [ax, ay, az, x_opt, y_opt, z_bar]"""
        if self.mock:
            # 模拟传感器: 位置渐近于真实位置 + 噪声
            # IMU观测 = 真实加速度 + 扰动 + 噪声
            # P1-9 修复 (2026-10-06 评审): 原实现把 current_vel(速度, cm/s) 直接当
            # 加速度(cm/s²) 注入 IMU —— 注释本就写着"用速度差分近似加速度"，
            # 实现却没做差分。现改为真正的速度差分，量纲为 cm/s²。
            dt_imu = max(float(self.dt), 1e-6)
            accel = (self.current_vel - self._prev_vel_for_imu) / dt_imu
            self._prev_vel_for_imu = self.current_vel.copy()
            imu_x = accel[0] + np.random.normal(0, 5)
            imu_y = accel[1] + np.random.normal(0, 5)
            imu_z = accel[2] + np.random.normal(0, 5)

            # P1-2: 本帧确实取到了传感器数据 -> 允许刷新安全心跳
            self._sensor_fresh = True
            return np.array([
                imu_x, imu_y, imu_z,                    # IMU加速度
                self.current_pos[0] + np.random.normal(0, 2),  # 光流X
                self.current_pos[1] + np.random.normal(0, 2),  # 光流Y
                self.current_pos[2] + np.random.normal(0, 10),  # 气压计高度
            ])
        else:
            # 真机模式: 从TelloController获取
            drone_state = self.drone.get_state_dict()
            self._battery = drone_state.get("battery", 100)
            height = drone_state.get("height", 0)
            # P0-C 补完: 新鲜度必须以**状态包到达**为准, 而不是"getter 没抛异常"。
            # djitellopy 的 get_battery/get_height 读的是缓存字段, 链路断了照样返回
            # 旧值且不抛异常 —— 只要还信任"没抛异常", 通信超时保护就形同虚设。
            fresh_fn = getattr(self.drone, "has_fresh_telemetry", None)
            if callable(fresh_fn):
                try:
                    max_age = self.safety_guard.THRESHOLDS.get("timeout_land", 1.0)
                    self._sensor_fresh = bool(fresh_fn(max_age))
                except Exception:
                    self._sensor_fresh = False
            else:
                self._sensor_fresh = True
            # 供状态汇报用的"陈旧"闩锁: _sensor_fresh 会被 _check_safety 每帧消费掉,
            # 不能直接拿来对外汇报(否则健康链路也会显示陈旧)。
            self._telemetry_stale = not self._sensor_fresh

            # P0-2b 修复: 真机姿态从 get_attitude() 接线(此前 current_attitude 恒 0,
            # 姿态保护是摆设)。Tello 真机不提供姿态, 返回空 dict 时回退 [0,0,0]。
            att = self.drone.get_attitude()
            if isinstance(att, dict) and att:
                self.current_attitude = np.array(
                    [att.get("roll", 0), att.get("pitch", 0), att.get("yaw", 0)],
                    dtype=float)
            elif isinstance(att, (list, tuple)) and len(att) >= 3:
                self.current_attitude = np.asarray(att[:3], dtype=float)
            else:
                # Tello SDK 不提供姿态 -> 诚实回退, 不与假值混淆
                self.current_attitude = np.zeros(3)

            # P0-B: 若已接入外部定位且观测当下可用, 用**真实位置**替代自我循环假观测。
            obs = self.read_localization()
            # 审计第 5 条: 分通道记录新鲜度 —— 定位新鲜 ≠ 气压高度新鲜。
            self._localization_fresh = obs is not None
            self._barometer_fresh = bool(self._sensor_fresh)
            if obs is not None:
                pos = np.asarray(obs.position, dtype=float)
                self._last_localization = obs
                if self._sensor_fresh:
                    z_bar = float(height)          # 气压计新鲜: 直接用
                else:
                    # 气压高度陈旧 -> 用**同一观测里**的定位高度(ArUco 也测 z), 而
                    # 不是把 Tello 缓存值当新测量, 也不是把整包丢掉(那会白扔新鲜定位)。
                    z_bar = float(pos[2]) if np.isfinite(pos[2]) else None
                    if z_bar is None:
                        print("[WARN] 气压陈旧且定位无有效高度 -> 本帧不注入观测")
                        return None
                    print("[WARN] 气压高度陈旧 -> 本帧高度改用同源定位观测(拒绝新旧混包)")
                return np.array([
                    0, 0, 0,                     # IMU (Tello SDK不直接提供)
                    pos[0], pos[1],              # 光流X/Y <- 外部定位(带时间戳/质量分数)
                    z_bar,                       # 气压计高度(新鲜气压 或 同源定位高度)
                ])

            # P0-C 补完: 遥测陈旧时**不得**把缓存值当作新观测注入 EKF ——
            # 否则位置会被"冻住"却看起来一切正常(最危险的一类假成功)。
            # 返回 None 表示"本帧没有可用测量", _update 里已有 `if z is not None` 保护,
            # EKF 只做预测, 不拿旧值当新值。
            if not self._sensor_fresh:
                print("[WARN] 遥测陈旧: 本帧不注入传感器观测 (EKF 仅预测)")
                return None

            # P0-3 诚实化: **未接**外部定位时, 真机 IMU 三轴与光流位置均为假观测
            # (Tello SDK 不提供加速度; 光流用上一帧 EKF 估计 = 自我循环)。
            # 此处显式告警一次, 避免把"自我循环"误当作定位能力。
            if not getattr(self, "_ekf_honesty_warned", False):
                print("[WARN] 真机 EKF 定位是自我循环假观测 "
                      "(IMU=0, 光流=上一帧估计); 需外部定位输入方为有效定位。")
                self._ekf_honesty_warned = True

            return np.array([
                0, 0, 0,                     # IMU (Tello SDK不直接提供)
                self.current_pos[0],         # 光流X (近似, 自我循环)
                self.current_pos[1],         # 光流Y (近似, 自我循环)
                float(height),               # 气压计高度
            ])

    def _telemetry_age_s(self) -> float:
        """本机遥测的年龄(秒)。

        以"状态包到达时间戳"(见 TelloController.telemetry_packet_timestamp)为基准,
        而不是"现在"—— 延迟到达的测量本来就旧, EKF 必须知道这一点。
        拿不到时间戳(如仿真适配器)返回 0.0, 等价于旧行为。
        """
        ts_fn = getattr(self.drone, "telemetry_packet_timestamp", None)
        if not callable(ts_fn):
            return 0.0
        try:
            ts = ts_fn()
        except Exception:
            return 0.0
        if ts is None:
            return 0.0
        return max(0.0, time.monotonic() - float(ts))

    # =========================================================================
    # 控制指令发送 (P0-7: 实现控制输出)
    # =========================================================================

    def _send_control(self, output):
        """发送控制指令到无人机

        output: [vx, vy, vz] 速度指令 (cm/s), 范围 [-100, 100]

        P0-2 修复: 此前真机分支调用 drone.move_to(), 而 move_to() 的实现其实是
        一次性相对位移(move_left/forward/..., 还带 >20cm 死区, speed 参数被忽略)。
        主循环每 100ms 调一次, 会造成过冲/阻塞/控制频率失真, 而且小修正被静默丢弃。
        现在统一走速度控制: 真机 = RCManager 以 20Hz 持续下发 rc_control;
        模拟 = 记录速度指令 + 主循环积分位置(与真机速度语义一致)。
        """
        # 保存控制输出供下一帧EKF使用
        self._last_control_output = np.asarray(output, dtype=float)

        if output is None or np.all(np.abs(output) < 1):
            # 审计 P1 修复: 死区不能"什么都不做" —— 否则上一条非零 RC 指令会
            # 一直生效到 RCManager 的 0.5s 超时归零, 等于指令多活半秒。
            # 死区时应立即归零速度。
            if not self.mock:
                stop = getattr(self.drone, "stop_velocity", None)
                if callable(stop):
                    stop()
            return

        vx, vy, vz = output

        if self.mock:
            # 模拟模式: 由主循环积分位置。
            # 注意: 仿真有自己的控制器/被控对象架构, 这里**不**注入速度,
            # 否则会绕过仿真飞控直接改写四旋翼速度通道。
            self.current_pos += output * self.dt
            return

        # 真机模式: P0-2 修复 —— 走 RC 速度控制。
        # 此前调用 drone.move_to(), 而它的实现是一次性相对位移(move_left/forward/...)
        # 且带 >20cm 死区: 与"每 100ms 一次的速度指令"语义不符。
        # 用 getattr 防御: 第三方/旧适配器可能还没实现 set_velocity。
        set_velocity = getattr(self.drone, "set_velocity", None)
        if callable(set_velocity):
            # 审计 P1: 检查返回值 —— 此前返回值被直接丢弃, 指令被拒绝也无人知晓
            if not set_velocity(float(vx), float(vy), float(vz)):
                self._velocity_reject_count = getattr(
                    self, "_velocity_reject_count", 0) + 1
                if self._velocity_reject_count in (1, 10, 100):
                    print("[WARN] set_velocity 被拒绝 (第 {} 次): drone.state={}".format(
                        self._velocity_reject_count,
                        getattr(self.drone, "state", "?")))

    # =========================================================================
    # 安全检查 (P0-1: 集成SafetyGuard)
    # =========================================================================

    def _check_safety(self) -> bool:
        """
        N1修复: 分层Failsafe — WARN告警/LAND自动降落/KILL急停
        返回 True 表示触发了 KILL 级紧急状态。
        """
        # P1-2 修复: 此前每帧无条件 heartbeat(), 使 monitor 的 timeout_land /
        # timeout_kill 永远算不出超时(通信中断也检测不到)。
        # 现在心跳只由"本帧真的取到了传感器数据"驱动: _get_sensor_data 成功时
        # 置 _sensor_fresh, 这里消费一次。既保留 A1 的"避免创建初期误报",
        # 又恢复了通信超时检测能力。
        if getattr(self, "_sensor_fresh", False):
            self.safety_guard.heartbeat()
            self._sensor_fresh = False

        # EMERGENCY 状态下允许状态机继续运行 (用于降落后的 IDLE 恢复)
        event = self.safety_guard.check(
            battery=int(self._battery),
            attitude=self.current_attitude.tolist(),
            height=float(self.current_pos[2]))
        if event.level == SafetyLevel.WARN:
            if not getattr(self, "_warned", False):
                print("[SAFETY] {}".format(event.reason))
                self._warned = True
        elif event.level == SafetyLevel.LAND:
            print("[SAFETY] {} — 自动降落".format(event.reason))
            self.request_state("LAND", "安全: " + event.reason)
        elif event.level == SafetyLevel.KILL:
            if self.state != "EMERGENCY":
                self.trigger_emergency(event.reason)
            return True
        if event.level == SafetyLevel.OK:
            self._warned = False
            # P1: _last_heartbeat 已由 FailsafeMonitor.heartbeat() 替代
        return False

    def update_with_external_data(self, sensor_z, position, velocity, attitude,
                                  telemetry_fresh: bool = True,
                                  sensor_age_s: float = 0.0):
        """供仿真调用: 注入外部传感器数据并运行一帧控制循环

        仿真器提供虚拟传感器数据, MissionController 运行完整的
        EKF→安全检查→状态机→控制器→日志→消息总线 流水线。

        telemetry_fresh: 本帧是否真的拿到了**新**遥测。仿真可以注入丢包
        (见 backend/simulation/transport_model.py) 并传 False —— 此时不得刷新
        安全心跳, 否则"丢包 → failsafe"这条链在仿真里永远走不通。
        默认 True 保持既有行为不变。

        返回: (control_output, state_dict)
        """
        self.current_pos = np.asarray(position, dtype=float)
        self.current_vel = np.asarray(velocity, dtype=float)
        self.current_attitude = np.asarray(attitude, dtype=float)

        # P1-2 补漏: 这条"外部注入"路径才是仿真/HIL 的传感器来源, 它不经过
        # _get_sensor_data —— 所以必须在这里表达"本帧是否拿到新遥测"。
        # 默认 True 保持既有行为; 丢包帧由调用方传 False。
        self._sensor_fresh = bool(telemetry_fresh)
        self._telemetry_stale = not bool(telemetry_fresh)

        # #5 修复: 仿真路径也更新视频帧, 使 INSPECT 状态的检测管线能跑通
        self._video_frame = self.video_stream.get_frame()
        self._feed_localization_frame()

        # EKF (N6: 仿真传真实加速度, 真机传 None)
        self.ekf.predict(u=self._last_control_accel if self.mock else None)
        if sensor_z is not None:
            # 测量年龄: 延迟到达的测量不应被当作"刚到的新测量"(否则延迟被系统性低估)。
            # age_s=0 时 EKF 行为与加这个参数之前逐位一致。
            self.ekf.update(np.asarray(sensor_z, dtype=float), age_s=sensor_age_s)
        ekf_state = self.ekf.get_state()
        self.current_pos = ekf_state["position"]
        self.current_vel = ekf_state["velocity"]
        disturbance = ekf_state["disturbance"]

        # 安全检查 — 记录但不跳过状态机 (EMERGENCY 降落逻辑在状态机内)
        self._check_safety()

        # 审计第 4 条: 任务期**逐帧**有效性检查 (定位/视觉/视频中途失效当场处置)。
        # 不提前 return: 处置已把状态改成 MISSION_FAILED/EMERGENCY, 紧接着的状态机
        # 会走终态分支执行安全动作, 同一帧内完成。
        self._check_task_validity()

        # 状态机 (P0-B: compute 已在 _handle_state_machine 中调用一次, 此处复用)
        detections, control_output = self._handle_state_machine(disturbance)

        self._last_control_output = np.asarray(control_output, dtype=float)

        # 日志
        self._log_frame(disturbance, detections if detections else [])

        # 消息总线 (pub-sub: publish 到独立 topic)
        try:
            self.bus.publish(TOPIC_MISSION_STATUS, self.get_state_dict(), source="main")
        except Exception:
            import logging
            logging.warning("[MAIN] 消息总线发布失败", exc_info=True)

        return control_output, self.get_state_dict()

    # =========================================================================
    # 公共接口
    # =========================================================================

    def set_target(self, x, y, z):
        """设置目标位置 (cm)"""
        self.target_pos = np.array([x, y, z])
        print("[MAIN] 目标已更新: ({:.0f}, {:.0f}, {:.0f}) cm".format(x, y, z))

    # =========================================================================
    # 状态转换唯一入口 + 安全闸门 (审计 P0-A)
    # =========================================================================
    # 终态 (不参与闸门): 与 backend/mission/states.py 的 TERMINAL_STATES **同源**,
    # 不再各自维护字符串常量 (审计第 1 条: 枚举与字符串分叉会让转换表校验失效)
    FAILURE_STATES = tuple(sorted(s.name for s in TERMINAL_STATES))
    # 依赖"可信位置"的状态: 真机缺少外部定位时禁止进入
    LOCALIZATION_DEPENDENT_STATES = ("NAVIGATE", "INSPECT", "RETURN")
    #: 任务期必须**逐帧**检查有效性的状态 (审计第 4 条)
    VALIDITY_MONITORED_STATES = ("NAVIGATE", "INSPECT", "RETURN")
    #: 视频连续多久没有新帧即视为冻结
    VIDEO_STALL_MAX_AGE_S = 2.0

    #: 终态下降的收尾高度(cm): 确认低于它以后改为请求 land() 收尾
    FAULT_LAND_HEIGHT_CM = 30.0
    #: land() 失败后, 每隔多少帧重试一次收尾(而不是永久放弃)
    FAULT_LAND_RETRY_FRAMES = 25
    #: 适配器处于这些状态**且** is_flying=False 时, 才可**正面确认已落地**
    #: (真机 FlightState: IDLE/CONNECTED 是干净的落地态; EMERGENCY/LANDING 不是)
    GROUNDED_ADAPTER_STATES = ("IDLE", "CONNECTED")
    #: 适配器处于这些状态时 land() 才会真的下发底层命令(见 tello_basic.land 的前置条件)
    LANDABLE_ADAPTER_STATES = ("HOVERING", "MOVING")
    #: 触地带(cm): 高度可信且连续 N 帧 <= 此值 ⇒ 视为已触地。
    #: 依据: 低于该高度继续下压对降落没有帮助(反而可能翻倒/打桨), 而真机一旦 land() 失败
    #: 转入 EMERGENCY 就再也回不到干净落地态 —— 没有这条, 终态会一直往地面压。
    FAULT_TOUCHDOWN_CM = 5.0
    FAULT_TOUCHDOWN_CONFIRM_FRAMES = 3

    def height_is_known(self) -> bool:
        """当前高度是否可信。

        仿真: 物理模型给出的高度恒可信。
        真机: **必须由适配器证明** —— 适配器未实现 height_is_known() 时按"不可信"
        处理(fail-closed)。此前是返回 True(fail-open), 与"任何真机适配器都必须
        证明高度可信"的契约不符(第三轮审计 P1)。
        """
        if self.mock:
            return True
        fn = getattr(self.drone, "height_is_known", None)
        if not callable(fn):
            print("[WARN] 适配器未实现 height_is_known(): 按高度不可信处理(fail-closed)")
            return False
        try:
            return bool(fn())
        except Exception:
            return False

    def _safe_height_cm(self):
        """尽量安全地读一次高度(cm); 不可信/读不到一律返回 None(绝不猜)。"""
        if self.mock:
            try:
                return float(self.current_pos[2])
            except Exception:
                return None
        if not self.height_is_known():
            return None
        getter = getattr(self.drone, "get_height", None)
        if not callable(getter):
            return None
        try:
            return float(getter())
        except Exception:
            return None

    def _note_fault_descent_failure(self, why: str) -> None:
        """终态下降"未推进"的限频告警(第 1 次与每 50 次各报一次)。"""
        self._fault_descent_failures = getattr(self, "_fault_descent_failures", 0) + 1
        if self._fault_descent_failures == 1 or self._fault_descent_failures % 50 == 0:
            print("[FAULT] 受控下降未推进(第 {} 次): {} "
                  "—— 需要飞控级 failsafe 或外部急停".format(
                      self._fault_descent_failures, why))

    def _fault_descend_step(self) -> bool:
        """终态期间推进一次受控下降, 返回是否**确实推进**。

        第三轮审计 P0: 原实现直接调用 emergency_descent() 并**忽略返回值**。而
        emergency_descent() 返回 False 明确表示"根本没有下降能力(无底层链路)",
        且它本身**不会**自动 land() —— 所以"持续推进直到触地"当时只是描述, 没有
        代码保证。现在: 返回 False 时计入失败并限频升级告警。
        """
        descent = getattr(self.drone, "emergency_descent", None)
        if not callable(descent):
            self._note_fault_descent_failure("适配器无 emergency_descent")
            return False
        try:
            ok = descent(timeout_s=0.05, poll_s=0.01, release_velocity=False)
        except TypeError:
            try:
                ok = descent()
            except Exception as e:
                self._note_fault_descent_failure(str(e))
                return False
        except Exception as e:
            self._note_fault_descent_failure(str(e))
            return False
        if ok is False:
            self._note_fault_descent_failure("emergency_descent 返回 False(无下降能力)")
            return False
        self._fault_descent_started = True
        return True

    @staticmethod
    def _adapter_state_name(drone) -> Optional[str]:
        """取适配器状态机的状态名(没有状态机的适配器返回 None)。"""
        state = getattr(drone, "state", None)
        if state is None:
            return None
        return (getattr(state, "name", None) or str(state)).upper()

    def _adapter_accepts_land(self) -> bool:
        """适配器当前是否会**真的执行**降落指令。

        真机 `TelloController.land()` 仅在 HOVERING/MOVING 下才下发底层命令, 其它状态
        (含 EMERGENCY)直接 `return False` 且**不下发任何命令**(tello_basic.py:277/290)。
        没有状态机的适配器(仿真/mock)交给它自己判定。
        """
        name = self._adapter_state_name(self.drone)
        if name is None:
            return True
        return name in self.LANDABLE_ADAPTER_STATES

    def _grounded_confirmed(self, update_touchdown: bool = True) -> bool:
        """是否**正面确认已落地**(第五轮审计 D17 + 衍生缺口②)。

        判据(任一成立):
          A. 高度可信且 <=30cm, 不再飞行, **且**适配器处于干净的落地态(IDLE/CONNECTED);
          B. **触地带**: 高度可信且连续 `FAULT_TOUCHDOWN_CONFIRM_FRAMES` 帧 <= 5cm
             —— 此时继续下压没有帮助, 而真机 EMERGENCY 后回不到干净态(否则终态会一直往地面压)。
        EMERGENCY / LANDING / DISCONNECTED 下的 25cm 读数**不算**落地(fail-closed)。
        """
        height = self._safe_height_cm()
        if update_touchdown:
            if height is not None and height <= self.FAULT_TOUCHDOWN_CM:
                self._fault_touchdown_frames = getattr(self, "_fault_touchdown_frames", 0) + 1
            else:
                self._fault_touchdown_frames = 0
        if (height is not None and height <= self.FAULT_TOUCHDOWN_CM
                and getattr(self, "_fault_touchdown_frames", 0)
                >= self.FAULT_TOUCHDOWN_CONFIRM_FRAMES):
            return True                                     # 触地带(连续 N 帧确认)
        if height is None or height > self.FAULT_LAND_HEIGHT_CM:
            return False
        if bool(getattr(self.drone, "is_flying", False)):
            return False
        name = self._adapter_state_name(self.drone)
        if name is None:
            return True                      # 无状态机: is_flying 即权威
        return name in self.GROUNDED_ADAPTER_STATES

    def _grounding_refusal_reason(self) -> str:
        """为什么不能确认落地(用于拒绝复位时给出可读理由)。"""
        height = self._safe_height_cm()
        if height is None:
            return "高度不可信(遥测缺失或陈旧)"
        if height > self.FAULT_LAND_HEIGHT_CM:
            return "高度 {:.0f}cm 仍高于 {:.0f}cm".format(height, self.FAULT_LAND_HEIGHT_CM)
        if bool(getattr(self.drone, "is_flying", False)):
            return "适配器仍报告在飞行"
        return "适配器状态 {} 不能证明触地(如 EMERGENCY/LANDING)".format(
            self._adapter_state_name(self.drone))

    def _note_land_unavailable(self) -> None:
        """限频告警: 适配器处于不接受 land() 的状态, 软件已无降落手段。"""
        self._fault_land_unavailable = getattr(self, "_fault_land_unavailable", 0) + 1
        if self._fault_land_unavailable == 1 or self._fault_land_unavailable % 50 == 0:
            print("[FAULT] 适配器状态 {} 不接受 land()(不会下发任何命令) —— "
                  "只能继续 RC 下降; 需要飞控级 failsafe 或外部急停".format(
                      self._adapter_state_name(self.drone)))

    def _maybe_retry_fault_landing(self, height) -> None:
        """`land()` 曾失败时按帧数限频重试。

        第五轮审计 D17: 仅在适配器**真的会执行** land() 时才重试 —— 真机 EMERGENCY 下
        调用只会 `return False` 且不下发命令, 重试是空转。
        """
        self._fault_land_retry = getattr(self, "_fault_land_retry", 0) + 1
        if (getattr(self, "_fault_land_failures", 0) > 0
                and self._adapter_accepts_land()
                and self._fault_land_retry % self.FAULT_LAND_RETRY_FRAMES == 0):
            self._request_fault_landing(height)

    def _request_fault_landing(self, height) -> bool:
        """终态收尾: 请求降落。返回**是否成功下发**(不代表已触地)。

        第四轮审计 D1: 原实现不看 `land()` 返回值就置 `_fault_land_requested = True`。
        真机 `land()` 失败时**返回 False 并转入 EMERGENCY**(tello_basic.py:287-289),
        于是"降落失败"被记成"已收尾", 之后永远不再尝试。

        第五轮审计 D17: 真机在 EMERGENCY 下 land() **只 return False 且不下发任何命令**
        (tello_basic.py:277/290), 所以"重试 land()"是空转 —— 这里先判适配器是否接受
        land(), 不接受就直接报"无降落能力", 由调用方改走 RC 下降(emergency_descent)。
        """
        if not self._adapter_accepts_land():
            self._note_land_unavailable()
            return False
        land = getattr(self.drone, "land", None)
        if not callable(land):
            self._fault_land_failures = getattr(self, "_fault_land_failures", 0) + 1
            return False
        try:
            ok = land()
        except Exception as e:
            ok = False
            print("[FAULT] land() 抛异常: {}".format(e))
        if ok is False:
            self._fault_land_failures = getattr(self, "_fault_land_failures", 0) + 1
            self._fault_land_requested = False        # 关键: 失败不记为成功
            if self._fault_land_failures == 1 or self._fault_land_failures % 5 == 0:
                print("[FAULT] land() 未成功(第 {} 次) -> 继续尝试受控下降".format(
                    self._fault_land_failures))
            return False
        self._fault_land_requested = True
        print("[FAULT] 已确认低空({}) -> land() 已下发".format(
            "未知" if height is None else "{:.0f}cm".format(height)))
        return True

    def _note_video_frame(self) -> None:
        """观察视频帧是否在更新。

        get_frame() 有新帧时从队列返回**新对象**, 队列空时回退到缓存的最新帧
        (同一对象) —— 所以对象身份变化就是"确实收到新帧"的可用判据。
        另外记录"是否**拿到过任何帧**": 零帧与"曾经有帧后冻结"是两种不同失效。
        """
        frame = self._video_frame
        if frame is None:
            return
        self._video_seen_frame = True
        if frame is not getattr(self, "_video_last_obj", None):
            self._video_last_obj = frame
            self._video_last_change_t = time.time()
            self._video_seen_change = True

    def video_stalled(self, max_age_s: float = None) -> bool:
        """视频是否不可用(冻结, 或**从未拿到任何帧**)。

        第三轮审计 P1: 原实现要求"此前至少见过一帧", 于是零视频帧时**永远不触发**。
        而检测器"模型可用"不等于"视频可用" —— 若定位来自 UWB 等独立来源, INSPECT
        就能在零视频帧的情况下白等到超时, 再当作"巡检完成"去返航。
        现在分两种情形:
          (1) 从未拿到帧 -> 以**进入当前受监控状态的时刻**起算;
          (2) 拿到过帧但已停止更新 -> 用对象身份判据。
        """
        limit = self.VIDEO_STALL_MAX_AGE_S if max_age_s is None else max_age_s
        if not getattr(self, "_video_seen_frame", False):
            entry = getattr(self, "_state_entry_time", None)
            return entry is not None and (time.time() - entry) > limit
        last = getattr(self, "_video_last_change_t", None)
        if last is None:
            return False
        return (time.time() - last) > limit

    def _check_task_validity(self) -> bool:
        """任务期**逐帧**有效性检查 (审计第 4 条)。返回 True 表示本帧已触发处置。

        此前只在"进入状态"时过闸门: 导航到一半定位过期、巡检中视频冻结, 都要等到
        下一个转换点或巡检超时才暴露 —— 这期间飞机仍在按旧指令继续飞。
        """
        if self.state not in self.VALIDITY_MONITORED_STATES:
            return False
        self._note_video_frame()
        problems = []
        if not self.localization_available():
            problems.append("LOCALIZATION_LOST_MIDMISSION")
        if self.state == "INSPECT" and not getattr(self.detector, "is_available", True):
            problems.append("VISION_LOST_MIDMISSION:{}".format(
                getattr(self.detector, "unavailable_reason", "unknown")))
        if self.video_stalled():
            problems.append("VIDEO_STALLED>{:.0f}s".format(self.VIDEO_STALL_MAX_AGE_S))
        if not problems:
            return False

        reason = " + ".join(problems)
        # (1) 先停水平速度, 不再继续任务输出
        try:
            self.drone.stop_velocity()
        except Exception:
            pass
        self._pending_control = np.zeros(3)
        # (2) 高度不可信 -> 连稳定悬停都无法保证, 直接受控下降;
        #     否则进终态等待人工处置(不再继续任务, 也不假装成功)。
        if not self.height_is_known():
            self._set_state("EMERGENCY", reason + " (高度未知)", force=True)
            print("[EMERGENCY] 任务期失效且高度未知, 执行受控下降: {}".format(reason))
        else:
            self._set_state("MISSION_FAILED", reason, force=True)
            print("[MISSION_FAILED] 任务期失效: {}".format(reason))
        return True

    def attach_localization_source(self, source) -> None:
        """接入外部定位源 (审计 P0-B)。

        与旧 `enable_external_localization("名字")` 的关键区别: 那时只给一个字符串
        就宣称"有定位了", 闸门形同虚设。现在必须真的接一个能 `read()` 出
        **带时间戳/质量分数且未过期**观测的源 (见 backend/localization/)。
        """
        self._localization_source_obj = source
        self._localization_source = getattr(source, "name", type(source).__name__)
        print("[SAFETY] 外部定位源已接入: {}".format(self._localization_source))

    def read_localization(self):
        """读一次外部定位观测; 不可用则返回 None。

        不可用包括: 未接源 / 读取抛异常 / 观测为 None / 观测自身 is_usable() 为假
        (时间戳过期、质量低于阈值、位置非有限、未来时间戳)。
        """
        src = getattr(self, "_localization_source_obj", None)
        if src is None:
            return None
        try:
            obs = src.read()
        except Exception as e:
            print("[WARN] 定位源读取异常: {}".format(e))
            return None
        if obs is None:
            return None
        usable = getattr(obs, "is_usable", None)
        if callable(usable):
            try:
                if not usable():
                    return None
            except Exception as e:
                # 定位源自身判定抛异常 = 不可用 (fail-closed)。此前异常会抛穿闸门,
                # 让状态机拿到一个"看起来没问题"的观测或直接炸掉。
                print("[WARN] 定位源可用性判定异常, 按不可用处理: {}".format(e))
                return None
        return obs

    def _feed_localization_frame(self) -> None:
        """把当前视频帧喂给**被动推帧式**定位源 (审计第 3 条)。

        ArUcoLocalizationSource 是 read_frame(frame) 推帧式: 不喂帧, read() 永远
        拿不到新观测 —— 真机上 attach_localization_source() 之后定位根本不会更新,
        闸门会一直判不可用。这里在每帧取到视频帧后统一推给定位源。
        没有 read_frame 的源(如注入式真值源)保持原样, 不报错。
        """
        src = getattr(self, "_localization_source_obj", None)
        feeder = getattr(src, "read_frame", None)
        if src is None or not callable(feeder):
            return
        frame = getattr(self, "_video_frame", None)
        if frame is None:
            return
        try:
            feeder(frame)
        except Exception as e:
            print("[WARN] 定位源推帧异常: {}".format(e))

    def localization_available(self) -> bool:
        """位置观测是否可信 —— 真机必须有**已接入且当前健康**的外部定位源。

        仿真(mock)由物理模型给出真值 -> True;
        真机默认 False: 光流观测是"上一帧 EKF 估计"的自我循环, 不能作为
        导航/返航/巡检依据。接入 ArUco/塔筒特征/RTK/UWB/VIO 等真实源后,
        只有观测**当下可用**才放行 (过期或低质量立即重新变为不可用)。
        """
        if self.mock:
            return True
        return self.read_localization() is not None

    def _state_gate_reason(self, new_state: str):
        """返回阻止进入 new_state 的原因; 允许时返回 None。"""
        if new_state == "INSPECT" and not getattr(self.detector, "is_available", True):
            return "VISION_UNAVAILABLE: {}".format(
                getattr(self.detector, "unavailable_reason", "unknown"))
        if (new_state in self.LOCALIZATION_DEPENDENT_STATES
                and not self.localization_available()):
            return ("LOCALIZATION_UNAVAILABLE: 真机缺少外部定位(位置观测为自我循环), "
                    "禁止进入依赖位置的 {} 状态".format(new_state))
        return None

    def _set_state(self, new_state: str, reason: str = "", *,
                   automatic: bool = False, force: bool = False,
                   allow_terminal_exit: bool = False) -> bool:
        """全系统唯一的状态转换入口。

        - 闸门在这里统一生效, **包括自动转换** —— 此前自动路径直接赋值,
          可以绕过 request_state() 里的视觉闸门 (审计 P0-A);
        - automatic=True: 状态机自己推进, 被闸门拦下时进入 MISSION_FAILED 终态,
          而不是静默留在原地假装任务正常;
        - automatic=False: 外部请求, 被拦下时保持原状态并返回 False;
        - force=True: 故障/紧急等必须立即生效的路径。

        **终态闩锁**(第三轮审计 P0): 一旦进过 FAULT/MISSION_FAILED, 之后只允许再进
        终态或 EMERGENCY(为了继续执行安全动作), 其余一律拒绝 —— **包括 force=True**。
        唯一出口是 clear_fault()(它显式传 allow_terminal_exit=True)。
        实测漏洞: 安全检查的 KILL 分支会 trigger_emergency()(force=True) 把 FAULT 改成
        EMERGENCY, 而 EMERGENCY 又能回 IDLE —— "只能人工复位"因此名不副实。
        """
        if getattr(self, "_terminal_latched", False) and not allow_terminal_exit:
            if new_state not in self.FAILURE_STATES and new_state != "EMERGENCY":
                print("[ERROR] 拒绝离开终态: {} → {} (已闩锁, 只能 clear_fault() 人工复位)".format(
                    self.state, new_state))
                return False
        if not force:
            blocked = self._state_gate_reason(new_state)
            if blocked:
                print("[ERROR] 状态转换被拒绝: {} → {} ({})".format(
                    self.state, new_state, blocked))
                if automatic:
                    self.state = "MISSION_FAILED"
                    self._terminal_latched = True
                    self._mission_failed_reason = "{} (目标状态 {})".format(
                        blocked, new_state)
                    self._state_entry_time = time.time()
                    print("[MISSION_FAILED] {}".format(self._mission_failed_reason))
                return False

        self.state = new_state
        if new_state in self.FAILURE_STATES:
            self._terminal_latched = True
            # 终态原因必须可观测(否则"为什么失败"只能靠翻日志)
            if new_state == "MISSION_FAILED" and reason:
                self._mission_failed_reason = reason
            elif new_state == "FAULT" and reason:
                self._fault_reason = reason
        self._state_entry_time = time.time()
        if new_state not in self.FAILURE_STATES and new_state != "EMERGENCY":
            self._mission_failed_reason = None
        return True

    def mark_fault(self, reason: str) -> None:
        """进入 FAULT 终态 (控制循环/硬件异常)。

        审计第 2 条: **光停速度不等于安全**。异常发生时飞机还在空中, 只停 RC 指令
        只会让它悬停/漂移, 甚至依赖 Tello 自己的超时。所以这里:
          1) 先停速度(切断任务逻辑输出);
          2) 若仍在上空 -> 立即发起**受控下降**(优先 emergency_descent, 否则 land),
             并置 `_fault_descent_started`; 每帧的 FAULT 分支持续推进直到触地;
          3) 无法下降时打印明确告警(需要飞控级 failsafe / 外部急停)。
        """
        stop = getattr(self.drone, "stop_velocity", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                pass
        self._fault_reason = reason
        self._fault_descent_started = False
        self._fault_land_requested = False
        # 衍生缺口④: 二次 mark_fault 不得继承上一次的失败计数/触地计数
        self._fault_land_failures = 0
        self._fault_land_retry = 0
        self._fault_touchdown_frames = 0
        self._fault_land_unavailable = 0

        flying = bool(getattr(self.drone, "is_flying", False))
        if flying:
            # 复用闭环下降步(含返回值检查与限频升级告警), 不再各写一份
            if not self._fault_descend_step():
                print("[FAULT] !! 无法发起受控下降: 需要飞控级 failsafe 或外部急停")

        self._set_state("FAULT", reason, force=True)
        print("[FAULT] {} (空中={}, 受控下降={})".format(
            reason, flying, self._fault_descent_started))

    def clear_fault(self, reason: str = "人工复位",
                    operator_confirmed: bool = False) -> bool:
        """**唯一**离开 FAULT/MISSION_FAILED 终态的入口 (审计第 1 条)。

        第四轮审计 D2: 原实现用 `not is_flying` 当作"已落地"的证据, 但真机降落失败后
        状态是 EMERGENCY, 而 `is_flying` 在 EMERGENCY 下**也是 False** —— 判据失效。
        现在要求**正面的落地证据**:
          * 高度可信且 <= 30cm  ⇒ 允许复位;
          * 否则必须由操作员显式确认(`operator_confirmed=True`, 例如目视/称重确认)。
        """
        if not (self.state in self.FAILURE_STATES
                or getattr(self, "_terminal_latched", False)):
            print("[WARN] 当前状态 {} 不是终态(且未闩锁), 无需复位".format(self.state))
            return False
        height = self._safe_height_cm()
        if not self._grounded_confirmed() and not operator_confirmed:
            print("[ERROR] 拒绝复位终态: {} —— 需要操作员确认 "
                  "clear_fault(operator_confirmed=True)".format(self._grounding_refusal_reason()))
            return False
        prev = self.state
        if operator_confirmed:
            # 衍生缺口①: 真机 land() 失败会停在 EMERGENCY, 而 EMERGENCY→IDLE 的 "reset" 边
            # 此前无人触发 ⇒ 适配器永远回不到干净落地态。操作员确认落地后这里顺手复位它。
            reset = getattr(self.drone, "reset_from_emergency", None)
            if callable(reset):
                try:
                    if reset():
                        print("[SAFETY] 适配器已离开 EMERGENCY 回到 IDLE(操作员确认)")
                except Exception as e:
                    print("[WARN] 适配器复位失败: {}".format(e))
        self._fault_reason = None
        self._mission_failed_reason = None
        self._fault_descent_started = False
        self._fault_land_requested = False
        self._fault_land_failures = 0
        self._fault_land_retry = 0
        self._fault_touchdown_frames = 0
        self._fault_descent_failures = 0
        self._terminal_latched = False          # 先解锁, 再走统一入口
        self._set_state("IDLE", reason, force=True, allow_terminal_exit=True)
        print("[MAIN] 终态复位: {} → IDLE ({}, 高度={})".format(
            prev, reason, "未知" if height is None else "{:.0f}cm".format(height)))
        return True

    def takeoff(self, height: float = 100.0):
        """起飞到指定高度 (cm)"""
        if self.state != "IDLE":
            print("[WARN] 当前状态 {} 不允许起飞".format(self.state))
            return False
        self.target_pos = np.array([0.0, 0.0, height])
        self._set_state("TAKEOFF", "起飞指令")
        print("[MAIN] 起飞指令, 目标高度={:.0f}cm".format(height))
        return True

    def plan_path(self, start, goal, obstacles=None):
        """规划路径并切换到导航状态"""
        self.path = self.planner.plan(
            np.array(start), np.array(goal), obstacles
        )
        self.path_idx = 0
        if self.path is not None:
            print(
                "[MAIN] 路径规划成功, {} 个路径点".format(len(self.path))
            )
            if self.state in ("HOVERING", "IDLE"):
                # 无外部定位时拒绝进入 NAVIGATE (返回 False, 不做假成功)
                return self._set_state("NAVIGATE", "路径规划完成")
            return True
        print("[MAIN] 路径规划失败")
        return False

    def trigger_emergency(self, reason: str):
        """触发紧急状态 (直接进入 EMERGENCY, 不经过闸门)"""
        self._emergency_reason = reason
        self._emergency_sent = False  # P0-1: 重新武装受控降落
        self._set_state("EMERGENCY", reason, force=True)
        print("[EMERGENCY] {}".format(reason))

    def request_state(self, new_state: str, reason: str = "") -> bool:
        """外部请求状态转换。

        审计 P0-A: 闸门已统一收口到 _set_state —— 视觉不可用拒绝 INSPECT、
        真机无外部定位拒绝 NAVIGATE/INSPECT/RETURN, 手工与自动路径走同一套。
        这里只保留"手工请求"的转换表校验语义。
        """
        try:
            cur = MissionState[self.state]
        except KeyError:
            # 审计第 1 条: 这里原本是 `except KeyError: pass`(兼容旧代码), 后果是
            # **整张转换表被跳过** —— 实测在 FAULT 状态下 request_state("TAKEOFF")
            # 返回 True 并真的复活起飞。现在起点不在权威枚举里 -> fail-closed 拒绝。
            print("[ERROR] 状态转换被拒绝: 当前状态 {!r} 不在 MissionState 枚举内 "
                  "(终态必须用 clear_fault() 人工复位)".format(self.state))
            return False
        try:
            nxt = MissionState[new_state]
        except KeyError:
            print("[ERROR] 状态转换被拒绝: 目标状态 {!r} 不是合法任务状态".format(new_state))
            return False
        if not can_transition(cur, nxt):
            print("[WARN] 非法状态转换: {} → {} ({})".format(
                self.state, new_state, reason))
            return False
        return self._set_state(new_state, reason)

    def stop(self):
        """优雅关闭 (P1-11): 降落→轮询触地→保存日志→停止线程→关闭连接
        P0-1 修复: 原来的 land()+sleep(2) 对高空降落无效(50m 远超 2s)且无兜底,
        改为轮询高度直到触地或超时, 超时才升级 hard kill。"""
        print("[MAIN] 正在执行优雅关闭...")

        # 1. 尝试降落并轮询触地
        if self.drone.is_flying:
            print("[MAIN] 无人机降落中...")
            self.drone.land()
            # P0-1: 轮询高度直至触地或超时(默认 30s), 而非固定 sleep(2)
            timeout_s = float(self._cfg_val("safety.land_timeout_s", 30.0))
            t0 = time.time()
            while time.time() - t0 < timeout_s:
                try:
                    h = float(self.drone.get_height())
                except Exception:
                    h = float("nan")
                if not self.drone.is_flying or (h < 20):
                    break
                time.sleep(0.1)
            # 超时仍未触地 -> 按 P0-D 收紧后的规则处理。
            # kill()/motor_cutoff 现在只在"高度已知且 <=30cm"时才真正停桨, 高空调用
            # 会被**拒绝**。所以这里改为: 先做受控紧急下降, 再尝试停桨; 被拒时明确
            # 报告"需要外部急停/飞控级 failsafe", 而不是盲目砍桨造成空中自由落体。
            if self.drone.is_flying:
                descent = getattr(self.drone, "emergency_descent", None)
                if callable(descent):
                    print("[WARN] 降落超时 -> 受控紧急下降 (绝不盲目停桨)")
                    try:
                        descent(timeout_s=2.0, release_velocity=False)
                    except TypeError:
                        descent()
                cutoff = getattr(self.drone, "motor_cutoff", None)
                if callable(cutoff):
                    if not cutoff("touchdown_after_timeout"):
                        print("[WARN] 停桨被拒(高度未知或仍偏高) —— "
                              "需要外部急停或飞控级 failsafe")
                else:
                    self.drone.kill()

        # 2. 停止主循环
        self._running = False

        # 2b. P0-2: 停止 RC 速度发送线程并归零速度。
        # 不释放的话, 20Hz 线程会在主循环退出后继续下发最后一条速度指令。
        release = getattr(self.drone, "release", None)
        if callable(release):
            release()

        # 3. 停止视频流线程
        self.video_stream.stop()

        # 4. 保存飞行日志 (P1-12)
        self.logger.stop()

        # 5. 停止消息总线
        self.bus.stop()

        print("[MAIN] 优雅关闭完成")

    def _log_frame(self, disturbance, detections):
        """记录一帧飞行数据 (P1-12)"""
        try:
            self.logger.log_frame(
                position=(self.current_pos[0], self.current_pos[1], self.current_pos[2]),
                disturbance=(disturbance[0], disturbance[1], disturbance[2]),
                detections=detections,
                extra={"state": self.state, "battery": self._battery},
            )
        except Exception:
            # 日志错误不应中断飞行, 但需记录以便排查
            import logging
            logging.warning("[MAIN] FlightLogger.log_frame 失败", exc_info=True)

    def update_video_frame(self, frame: np.ndarray):
        """外部注入视频帧 (供视频线程调用)"""
        self._video_frame = frame

    # =========================================================================
    # 公共访问器 (Phase 3: 消除 SimRuntime/simulation.py 对 _battery/_emergency_reason
    # 等私有属性的直接访问)
    # =========================================================================

    def get_battery(self) -> float:
        """获取当前电量百分比 (0-100)"""
        return self._battery

    def set_battery(self, pct: float) -> None:
        """设置电量 (供仿真电池消耗使用, 自动限幅 0-100)"""
        self._battery = max(0.0, min(100.0, float(pct)))

    def get_emergency_reason(self) -> str:
        """获取紧急状态原因字符串 (无紧急时为空串)"""
        return self._emergency_reason

    def get_detection_count(self) -> int:
        """获取最近一帧的检测框数量"""
        return self._last_detection_count

    def set_detection_count(self, count: int) -> None:
        """设置检测框数量 (供仿真 mock 检测回喂)"""
        self._last_detection_count = int(count)

    def reset_mission(self) -> None:
        """安全重置任务 (供仿真 KeyR 调用):
        trigger_emergency → 清空 EKF/控制器/安全监控/电量/原因
        mc.state 在下一帧 update_with_external_data() 中由 EMERGENCY→IDLE 自动恢复
        """
        self.trigger_emergency("reset")
        self.target_pos = np.array([0.0, 0.0, 0.0])
        self.ekf.reset()
        self.controller.reset()
        self.safety_guard.reset()
        self._battery = 100.0
        self._emergency_reason = ""
        self.path = None
        self.path_idx = 0

    def get_state_dict(self) -> dict:
        """返回完整状态字典 (供Dashboard/logging使用)"""
        return {
            "flight_state": self.state,
            "state": self.state,
            "battery": self._battery,
            "height": float(self.current_pos[2]),
            "position": self.current_pos.tolist(),
            "velocity": self.current_vel.tolist(),
            "disturbance": self.ekf.get_disturbance().tolist(),
            "target": self.target_pos.tolist(),
            "detection_count": self._last_detection_count,
            "emergency_reason": self._emergency_reason,
            "ekf_mahalanobis": float(self.ekf.mahalanobis_distance),
            # P1-3: 暴露"系统是否真的具备感知/硬件能力", 供 Dashboard 与日志判定,
            # 避免故障被误读为正常运行。
            "vision_status": getattr(self.detector, "status", "UNKNOWN"),
            "vision_reason": getattr(self.detector, "unavailable_reason", None),
            "hardware_fault": getattr(self, "_hardware_fault", None),
            # 审计 P0-A / P0-B / P0-C: 终态与能力必须可观测
            "fault_reason": getattr(self, "_fault_reason", None),
            "mission_failed_reason": getattr(self, "_mission_failed_reason", None),
            "localization_available": self.localization_available(),
            "localization_source": getattr(self, "_localization_source", None),
            # P0-B: 定位观测的质量与新鲜度必须可观测(便于判定"能不能用")
            "localization_quality": (
                float(self._last_localization.quality)
                if getattr(self, "_last_localization", None) is not None else None),
            "localization_age_s": (
                float(self._last_localization.age())
                if getattr(self, "_last_localization", None) is not None else None),
            "telemetry_fresh": (self.drone.has_fresh_telemetry(1.0)
                                if hasattr(self.drone, "has_fresh_telemetry") else None),
            # 审计 §14.4: 遥测陈旧必须可观测(否则"估计被冻住"看起来一切正常)
            "telemetry_stale": bool(getattr(self, "_telemetry_stale", False)),
            # 审计第 5 条: 分通道新鲜度, 不让"不同时刻的观测"伪装成一包同步测量
            "localization_fresh": getattr(self, "_localization_fresh", None),
            "barometer_fresh": getattr(self, "_barometer_fresh", None),
            "video_stalled": self.video_stalled(),
            "measurement_age_s": getattr(self.ekf, "last_measurement_age_s", None),
        }


# MainController = MissionController 别名 (兼容角色文档)
MainController = MissionController


def main():
    """命令行入口: python main.py --mode simulation --target '10,0,20'"""
    import argparse

    parser = argparse.ArgumentParser(
        description="海上风电巡检无人机-机械臂协同系统"
    )
    parser.add_argument(
        "--mode",
        choices=["simulation", "hardware"],
        default="simulation",
        help="运行模式: simulation=仿真, hardware=真机",
    )
    parser.add_argument(
        "--target",
        type=str,
        default="0,0,100",
        help="目标位置 'x,y,z' (单位cm)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Mock mode (no real hardware)",
    )
    args = parser.parse_args()

    target = [float(x) for x in args.target.split(",")]
    controller = MissionController(mode=args.mode, mock=args.mock)
    controller.set_target(*target)

    print("[MAIN] 模式={}, 目标={}".format(args.mode, target))
    try:
        controller.start()
    except KeyboardInterrupt:
        print("\n[MAIN] 用户中断, 执行安全退出...")
        controller.trigger_emergency("用户中断(Ctrl+C)")
    except Exception as e:
        print("\n[MAIN] 异常: {}, 执行安全退出...".format(e))
        controller.trigger_emergency("异常: {}".format(e))
    finally:
        controller.stop()  # P1-11: 保证优雅关闭


if __name__ == "__main__":
    main()
