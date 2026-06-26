"""
主调度程序 — 整合所有模块的主循环

架构: 主线程调度, 传感器/视频子线程, 100ms周期

状态机:
    IDLE → TAKEOFF → NAVIGATE → INSPECT → RETURN → LAND
    任意状态 → EMERGENCY (电池低/通信断/人工急停)
"""

import time
import threading

import numpy as np

from backend.core.disturbance_observer import DisturbanceObserverEKF
from backend.core.feedforward_controller import FeedforwardController
from backend.core.trajectory_planning import RRTStarPlanner
from backend.vision.detect import DefectDetector
from backend.safety_guard import SafetyGuard
from backend.drone.tello_basic import TelloController, FlightState
from backend.drone.tello_video import TelloVideoStream
from backend.utils.logger import FlightLogger


# MissionController: 任务主调度器 (别名为兼容角色文档)
MainController = None  # 将在类定义后设置


class MissionController:
    """
    任务主调度器 — 有限状态机(FSM)驱动。

    状态机:
      IDLE → TAKEOFF → NAVIGATE → INSPECT → RETURN → LAND
      任意状态 → EMERGENCY (电池低/通信断/人工急停)

    用法:
      python backend/main.py --mode simulation --target "10,0,20"
    """

    def __init__(self, mode: str = "simulation", mock: bool = True):
        self.mode = mode  # "simulation" | "hardware"
        self.mock = mock
        self.dt = 0.1  # 100ms控制周期

        # =====================================================================
        # 子模块 — 算法层
        # =====================================================================
        self.ekf = DisturbanceObserverEKF(dt=self.dt)
        self.controller = FeedforwardController(dt=self.dt)
        self.planner = RRTStarPlanner()
        self.detector = DefectDetector(mock=mock)

        # =====================================================================
        # 安全守护 (P0-1: 集成SafetyGuard)
        # =====================================================================
        self.safety_guard = SafetyGuard()

        # =====================================================================
        # 无人机控制器 (P0-5: 组合TelloController)
        # =====================================================================
        self.drone = TelloController(mock=mock)

        # =====================================================================
        # 状态机 (P0-2: 完整6状态)
        # =====================================================================
        self.state = "IDLE"
        self.target_pos = np.array([0.0, 0.0, 100.0])
        self.current_pos = np.zeros(3)
        self.current_vel = np.zeros(3)
        self.current_attitude = np.zeros(3)
        self._battery = 100

        # 路径跟踪
        self.path = None
        self.path_idx = 0

        # 状态计时
        self._state_entry_time = time.time()
        self._hover_stabilize_start = 0.0

        # 安全监控
        self._emergency_reason = ""

        # 上一次的控制输出 (用于EKF predict时传入已知控制输入)
        self._last_control_output = np.zeros(3)

        # 视频流 (P1-12: 集成视频采集)
        self.video_stream = TelloVideoStream(tello_controller=self.drone, mock=mock)

        # 飞行日志 (P1-12: 集成FlightLogger)
        self.logger = FlightLogger()

        # 子线程控制
        self._running = False
        self._video_frame = None

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
                print("[MAIN] Tello连接失败, 切换到模拟模式")
                self.mock = True
                self.drone = TelloController(mock=True)

        while self._running:
            loop_start = time.time()

            self._update()

            # 维持固定周期
            elapsed = time.time() - loop_start
            sleep_time = self.dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _update(self):
        """单次控制循环"""

        # =====================================================================
        # 1. 获取传感器数据
        # =====================================================================
        z = self._get_sensor_data()

        # =====================================================================
        # 2. EKF预测+更新 (传入已知控制输入以分离扰动估计)
        # =====================================================================
        self.ekf.predict(u=self._last_control_output)
        if z is not None:
            self.ekf.update(z)

        ekf_state = self.ekf.get_state()
        self.current_pos = ekf_state["position"]
        self.current_vel = ekf_state["velocity"]
        disturbance = ekf_state["disturbance"]

        # =====================================================================
        # 3. 更新视频帧 (P1-12: 从视频流获取)
        # =====================================================================
        self._video_frame = self.video_stream.get_frame()

        # =====================================================================
        # 4. 安全检查 (P0-1: SafetyGuard集成)
        # =====================================================================
        if self._check_safety():
            self._log_frame(disturbance, [])  # 紧急状态也记录
            return  # 已触发紧急状态, 跳过正常控制

        # =====================================================================
        # 5. 状态机处理 (P0-2: 完整6+1状态)
        # =====================================================================
        detections = self._handle_state_machine(disturbance)

        # =====================================================================
        # 6. 记录飞行日志 (P1-12)
        # =====================================================================
        self._log_frame(disturbance, detections if detections else [])

    # =========================================================================
    # 状态机 (P0-2: 完整实现)
    # =========================================================================

    def _handle_state_machine(self, disturbance):
        """处理当前状态的行为, 返回本轮检测结果列表"""

        detections = []

        # ---------- IDLE: 等待指令 ----------
        if self.state == "IDLE":
            pass  # 等待外部 set_target / plan_path / takeoff 调用

        # ---------- TAKEOFF: 起飞到悬停高度 ----------
        elif self.state == "TAKEOFF":
            if self.drone.is_flying:
                if self.current_pos[2] >= self.target_pos[2] - 20:
                    # 达到目标高度, 进入悬停
                    self.state = "HOVERING"
                    self._state_entry_time = time.time()
                    print("[MAIN] 起飞完成, 进入悬停")
            else:
                # 发送起飞指令
                self.drone.takeoff()

        # ---------- HOVERING: 悬停等待 ----------
        elif self.state == "HOVERING":
            # 维持当前位置悬停
            control_output, _ = self.controller.compute(
                self.target_pos,
                self.current_pos,
                disturbance_est=disturbance,
                current_vel=self.current_vel,
            )
            self._send_control(control_output)

            # 如果有规划好的路径, 自动进入导航
            if self.path is not None and self.path_idx < len(self.path):
                self.state = "NAVIGATE"
                print("[MAIN] 悬停→导航, 路径点数={}".format(len(self.path)))

        # ---------- NAVIGATE: 沿路径点移动 ----------
        elif self.state == "NAVIGATE":
            if self.path is not None and self.path_idx < len(self.path):
                self.target_pos = self.path[self.path_idx]
                dist_to_waypoint = np.linalg.norm(
                    self.current_pos - self.target_pos
                )
                if dist_to_waypoint < 30:  # 到达当前路径点
                    self.path_idx += 1
                    print(
                        "[MAIN] 路径点 {}/{} 到达".format(
                            self.path_idx, len(self.path)
                        )
                    )
                else:
                    # 向路径点飞行
                    control_output, _ = self.controller.compute(
                        self.target_pos,
                        self.current_pos,
                        disturbance_est=disturbance,
                        current_vel=self.current_vel,
                    )
                    self._send_control(control_output)
            else:
                # 路径走完, 进入巡检
                self.state = "INSPECT"
                self._state_entry_time = time.time()
                print("[MAIN] 导航完成, 进入巡检")

        # ---------- INSPECT: 巡检 + 缺陷检测 ----------
        elif self.state == "INSPECT":
            # 悬停在巡检点
            control_output, _ = self.controller.compute(
                self.target_pos,
                self.current_pos,
                disturbance_est=disturbance,
                current_vel=self.current_vel,
            )
            self._send_control(control_output)

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
            if inspect_elapsed > 30:  # 30秒巡检超时
                self.state = "RETURN"
                self._state_entry_time = time.time()
                print("[MAIN] 巡检超时, 开始返航")

        # ---------- RETURN: 返航到起飞点 ----------
        elif self.state == "RETURN":
            home = np.array([0.0, 0.0, 100.0])  # 起飞点上空100cm
            self.target_pos = home

            control_output, _ = self.controller.compute(
                self.target_pos,
                self.current_pos,
                disturbance_est=disturbance,
                current_vel=self.current_vel,
            )
            self._send_control(control_output)

            # 到达返航点后降落
            if np.linalg.norm(self.current_pos - home) < 30:
                self.state = "LAND"
                self._state_entry_time = time.time()
                print("[MAIN] 返航完成, 开始降落")

        # ---------- LAND: 降落 ----------
        elif self.state == "LAND":
            # 发送降落指令
            if self.drone.is_flying:
                self.drone.land()
            # 等待降落完成
            if not self.drone.is_flying or self.current_pos[2] < 20:
                self.state = "IDLE"
                self._state_entry_time = time.time()
                print("[MAIN] 降落完成, 进入IDLE")

        # ---------- EMERGENCY: 紧急状态 ----------
        elif self.state == "EMERGENCY":
            # 立即停止所有运动并降落
            print("[EMERGENCY] {} — 触发紧急降落".format(self._emergency_reason))
            self.drone.emergency()
            # 转为降落状态
            if not self.drone.is_flying:
                self.state = "IDLE"
                print("[MAIN] 紧急降落完成")

        return detections

    # =========================================================================
    # 传感器数据获取
    # =========================================================================

    def _get_sensor_data(self):
        """获取传感器数据, 返回EKF观测向量 [ax, ay, az, x_opt, y_opt, z_bar]"""
        if self.mock:
            # 模拟传感器: 位置渐近于真实位置 + 噪声
            # IMU观测 = 真实加速度 + 扰动 + 噪声
            # 简化: 使用速度差分近似加速度
            imu_x = (self.current_vel[0] + np.random.normal(0, 5)) if self.current_vel[0] != 0 else np.random.normal(0, 5)
            imu_y = (self.current_vel[1] + np.random.normal(0, 5)) if self.current_vel[1] != 0 else np.random.normal(0, 5)
            imu_z = np.random.normal(0, 5)

            return np.array([
                imu_x, imu_y, imu_z,                    # IMU加速度
                self.current_pos[0] + np.random.normal(0, 2),  # 光流X
                self.current_pos[1] + np.random.normal(0, 2),  # 光流Y
                self.current_pos[2] + np.random.normal(0, 10), # 气压计高度
            ])
        else:
            # 真机模式: 从TelloController获取
            drone_state = self.drone.get_state_dict()
            self._battery = drone_state.get("battery", 100)
            height = drone_state.get("height", 0)

            return np.array([
                0, 0, 0,                     # IMU (Tello SDK不直接提供)
                self.current_pos[0],         # 光流X (近似)
                self.current_pos[1],         # 光流Y (近似)
                float(height),               # 气压计高度
            ])

    # =========================================================================
    # 控制指令发送 (P0-7: 实现控制输出)
    # =========================================================================

    def _send_control(self, output):
        """发送控制指令到无人机

        output: [vx, vy, vz] 速度指令 (cm/s), 范围 [-100, 100]
        """
        # 保存控制输出供下一帧EKF使用
        self._last_control_output = np.asarray(output, dtype=float)

        if output is None or np.all(np.abs(output) < 1):
            return  # 死区, 不发送

        vx, vy, vz = output

        if self.mock:
            # 模拟模式: 更新内部位置估计
            self.current_pos += output * self.dt
            return

        # 真机模式: 通过TelloController发送RC控制
        if self.drone.state in (FlightState.HOVERING, FlightState.MOVING):
            self.drone.move_to(float(vx), float(vy), float(vz), speed=30)

    # =========================================================================
    # 安全检查 (P0-1: 集成SafetyGuard)
    # =========================================================================

    def _check_safety(self) -> bool:
        """
        安全检查 — 电池/姿态/高度/失联检测。
        返回 True 表示触发了紧急状态。
        """
        if self.state == "EMERGENCY":
            return True  # 已在紧急状态

        state_dict = {
            "battery": self._battery,
            "attitude": self.current_attitude.tolist(),
            "height": float(self.current_pos[2]),
        }

        if not self.safety_guard.check(state_dict):
            self.trigger_emergency(self.safety_guard.emergency_reason)
            return True

        self._last_heartbeat = time.time()
        return False

    # =========================================================================
    # 公共接口
    # =========================================================================

    def set_target(self, x, y, z):
        """设置目标位置 (cm)"""
        self.target_pos = np.array([x, y, z])
        print("[MAIN] 目标已更新: ({:.0f}, {:.0f}, {:.0f}) cm".format(x, y, z))

    def takeoff(self, height: float = 100.0):
        """起飞到指定高度 (cm)"""
        if self.state != "IDLE":
            print("[WARN] 当前状态 {} 不允许起飞".format(self.state))
            return False
        self.target_pos = np.array([0.0, 0.0, height])
        self.state = "TAKEOFF"
        self._state_entry_time = time.time()
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
                self.state = "NAVIGATE"
            return True
        print("[MAIN] 路径规划失败")
        return False

    def trigger_emergency(self, reason: str):
        """触发紧急状态"""
        self._emergency_reason = reason
        self.state = "EMERGENCY"
        self._state_entry_time = time.time()
        print("[EMERGENCY] {}".format(reason))

    def stop(self):
        """优雅关闭 (P1-11): 降落→保存日志→停止线程→关闭连接"""
        print("[MAIN] 正在执行优雅关闭...")

        # 1. 尝试降落
        if self.drone.is_flying:
            print("[MAIN] 无人机降落中...")
            self.drone.land()
            time.sleep(2)

        # 2. 停止主循环
        self._running = False

        # 3. 停止视频流线程
        self.video_stream.stop()

        # 4. 保存飞行日志 (P1-12)
        self.logger.stop()

        # 5. 断开硬件连接
        if not self.mock and hasattr(self.drone, 'disconnect'):
            # TelloController没有disconnect方法, 安全起见留空
            pass

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
            pass  # 日志错误不影响飞行

    def update_video_frame(self, frame: np.ndarray):
        """外部注入视频帧 (供视频线程调用)"""
        self._video_frame = frame

    def get_state_dict(self) -> dict:
        """返回完整状态字典 (供Dashboard/logging使用)"""
        return {
            "state": self.state,
            "position": self.current_pos.tolist(),
            "velocity": self.current_vel.tolist(),
            "disturbance": self.ekf.get_disturbance().tolist(),
            "target": self.target_pos.tolist(),
            "battery": self._battery,
            "emergency_reason": self._emergency_reason,
            "ekf_mahalanobis": float(self.ekf.mahalanobis_distance),
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
        default=True,
        help="使用Mock模式(无真实硬件)",
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
