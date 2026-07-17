"""
Pygame仿真主循环 — 增强版: 3栏布局 + EKF/Controller/SafetyGuard集成
"""

import os
import sys
import random as _random

os.environ["SDL_IME_SHOW_UI"] = "0"

import numpy as np
import pygame

from backend.simulation.models import (
    Quadrotor3D, VirtualSensor, WindDisturbance, RobotArm3DOF, WindTurbine,
)
from backend.simulation.renderer import (
    draw_arm_panel,
    SKY_BLUE, Renderer, draw_ground, draw_turbine, draw_drone, draw_arm,
    draw_path, draw_wind_particles, draw_hud, draw_telemetry_panel,
    WHITE, BLACK, GREEN, RED, DARK_GRAY, PANEL_BG,
)
from backend.main import MissionController
from backend.utils.units import (m_to_cm, cm_to_m, mps_to_cmps, cmps_to_mps,
                                  mps2_to_cmps2)
from backend.utils.config import ConfigLoader


class Simulation:
    """Pygame 3D仿真 — 三栏布局 + 完整算法集成

    布局: 左(遥测250px) | 中(3D场景) | 右(摄像机320x240)
    控制: 空格=起飞  WASD=移动  方向键=升降  R=重置  Q=退出
    """

    PANEL_W = 250      # 左侧遥测面板宽度
    CAMERA_W = 320     # 右侧摄像机窗口宽度
    CAMERA_H = 240

    def __init__(self, width=1200, height=700, fps=30):
        pygame.init()
        try:
            pygame.key.stop_text_input()
        except Exception:
            pass

        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("SeaBreeze Inspector — UAV Simulation")
        self.clock = pygame.time.Clock()
        self.fps = fps
        self.width = width
        self.height = height

        # 字体
        try:
            self.font = pygame.font.SysFont("monospace", 14)
            self.font_sm = pygame.font.SysFont("monospace", 12)
        except Exception:
            self.font = pygame.font.Font(None, 16)
            self.font_sm = pygame.font.Font(None, 14)

        # 渲染器
        self.renderer = Renderer(screen_width=width, screen_height=height)

        # ---- 从配置加载仿真参数 ----
        try:
            sim_cfg = ConfigLoader.load("drone_config")
            w = sim_cfg["simulation"]["wind"]
            t = sim_cfg["simulation"]["turbine"]
            b = sim_cfg["simulation"]["battery"]
            n = sim_cfg["imu_noise"]
        except Exception:
            # 配置缺失时回退硬编码默认值
            w = {"base_x": 0.05, "base_y": 0.02, "frequency": 0.5, "gust_amplitude": 0.03}
            t = {"radius": 3.0, "height": 30.0}
            b = {"hover_drain": 1.5, "idle_drain": 0.1}
            n = {"accel_noise_std": 0.05, "optical_flow_noise_std": 2.0, "barometer_noise_std": 10.0}

        self._battery_hover_drain = float(b["hover_drain"])
        self._battery_idle_drain = float(b["idle_drain"])

        # ---- 仿真对象 ----
        self.quad = Quadrotor3D()
        self.wind = WindDisturbance(
            base_wind=np.array([float(w["base_x"]), float(w["base_y"]), 0.0]),
            freq=float(w["frequency"]),
            gust_amp=float(w["gust_amplitude"]),
        )
        self.sensor = VirtualSensor(
            imu_noise=float(n["accel_noise_std"]),
            opt_noise=float(n["optical_flow_noise_std"]),
            bar_noise=float(n["barometer_noise_std"]),
        )
        self.arm = RobotArm3DOF()
        self.turbine = WindTurbine(
            # N8: 风机位置从config读取 (有position字段用position, 否则fallback)
            center_xy=(float(t.get("position", [t["radius"], 0.0])[0]),
                       float(t.get("position", [t["radius"], 0.0])[1])),
            radius=float(t["radius"]),
            height=float(t["height"]),
        )

        # ---- FSM统一: 委托给MissionController (不再复制EKF/Controller/SafetyGuard) ----
        self.mc = MissionController(mode="simulation", mock=True)
        self.mc.safety_guard.THRESHOLDS["timeout"] = 10.0  # 仿真放宽超时

        # ---- 状态 (读取自 MissionController) ----
        self.running = True
        self.hover_height = 1.0
        self._target_pos = np.array([3.0, 1.0, 15.0])  # 默认巡检目标 (m)
        self._last_control = np.zeros(3)

        # 路径
        self.path = None
        self.path_idx = -1

        # 叶片动画
        self._blade_angle = 0.0

        # 按键
        self._keys_held = set()
        self._scan_held = set()
        self._frame_count = 0
        self._sim_time = 0.0

        # 检测模拟
        self._mock_detections = []

    # =========================================================================
    # 主循环
    # =========================================================================

    def run(self):
        print("[SIM] 仿真启动 — 3栏布局 + EKF/Controller/SafetyGuard")
        print("  空格=起飞  WASD=移动  方向键=升降  R=重置  Q=退出")
        print("  左面板=遥测数据  中=3D场景  右=摄像机画面")

        while self.running:
            dt = min(self.clock.tick(self.fps) / 1000.0, 0.05)  # 限最大dt
            self._frame_count += 1
            self._sim_time += dt
            self.renderer.tick(dt)
            self._blade_angle += dt * 1.5  # 叶片旋转

            # 1. 事件
            self._handle_events()
            # 2. 键盘 → 目标位置
            self._update_target_from_keys()
            # 3. 物理步进: 用 MissionController 的 velocity 更新位置
            vel = self.quad.get_velocity()
            self.quad.state[0:3] += vel * dt  # p += v*dt (简单的欧拉积分)
            self.quad.state[2] = max(0, self.quad.state[2])
            # 4. 传感器 + 委托MissionController运行完整流水线 (EKF/安全检查/状态机/控制器)
            sensor_data = self.sensor.read_all(self.quad)
            imu = sensor_data["imu"]
            opt = sensor_data["optical"]
            bar = sensor_data["barometer"]
            z = np.array([imu[0], imu[1], imu[2], opt[0], opt[1], bar])
            pos = self.quad.get_position()
            att = self.quad.get_attitude()
            ctrl_cmps, state_dict = self.mc.update_with_external_data(
                z, m_to_cm(pos), mps_to_cmps(vel), att)
            self._last_control = cmps_to_mps(ctrl_cmps)
            self.quad.set_velocity(self._last_control)
            # 5. 电池消耗
            self.mc._battery -= dt * (
            self._battery_hover_drain if self.mc.state == "HOVERING"
            else self._battery_idle_drain)
            self.mc._battery = max(0, self.mc._battery)
            # 7. 渲染
            self._render()

        pygame.quit()
        print("[SIM] 仿真结束")

    # =========================================================================
    # 事件
    # =========================================================================

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                    self._handle_arm_keys(event)
                    return
                name = pygame.key.name(event.key)
                sc = getattr(event, "scancode", 0)
                if event.key not in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                    print("  [KEY] k={} s={} '{}'".format(event.key, sc, name))
                self._keys_held.add(event.key)
                if sc:
                    self._scan_held.add(sc)
                self._on_key_down(event)
            elif event.type == pygame.KEYUP:
                self._keys_held.discard(event.key)
                if hasattr(event, "scancode") and event.scancode:
                    self._scan_held.discard(event.scancode)

    def _on_key_down(self, event):
        key = event.key
        scan = getattr(event, "scancode", 0)
        if key == pygame.K_ESCAPE or scan == 1:
            self.running = False
        elif key == pygame.K_q or scan == 16:
            self.running = False
        elif key == pygame.K_SPACE or scan == 57:
            if self.mc.state == "IDLE":
                self._do_takeoff()
            else:
                self._do_land()
        elif key == pygame.K_r or scan == 19:
            self._do_reset()

    def _do_takeoff(self):
        self.mc.takeoff(height=self.hover_height * 100)  # m→cm for MissionController
        # 仿真: 直接设四旋翼到悬停高度, 模拟起飞完成
        self.quad.state[2] = self.hover_height
        self.quad.set_velocity(np.zeros(3))
        self._target_pos = self.quad.get_position().copy()
        print("  [SIM] Took off to {:.0f}m".format(self.hover_height))

    def _do_land(self):
        self.mc.request_state("LAND", "仿真降落")
        self.quad.set_velocity(np.zeros(3))
        self.quad.state[2] = 0.0  # 重置高度到地面
        self._last_control = np.zeros(3)
        self.mc.safety_guard.reset()
        print("  [SIM] Landed")

    def _handle_arm_keys(self, event):
        """机械臂手动控制 — 方向键+Shift"""
        delta = 5 if event.mod & pygame.KMOD_SHIFT else 1
        if event.key == pygame.K_LEFT:
            self.arm.angles[0] = (self.arm.angles[0] - delta) % 180
        elif event.key == pygame.K_RIGHT:
            self.arm.angles[0] = (self.arm.angles[0] + delta) % 180
        elif event.key == pygame.K_UP:
            self.arm.angles[1] = min(150, self.arm.angles[1] + delta)
        elif event.key == pygame.K_DOWN:
            self.arm.angles[1] = max(30, self.arm.angles[1] - delta)
        self.arm.set_angles(self.arm.angles)

    def _do_reset(self):
        # 重置直接设状态 (不经过转换表, reset 总是合法)
        self.mc.state = "IDLE"
        self.mc.ekf.reset()
        self.mc.controller.reset()
        self.mc.safety_guard.reset()
        self.quad.state[:] = 0.0
        self.quad.set_velocity(np.zeros(3))
        self._last_control = np.zeros(3)
        self.mc._battery = 100.0
        self.mc.ekf.reset()
        self._keys_held.clear()
        self._scan_held.clear()
        self.path = None
        self.path_idx = -1
        print("  [SIM] 已重置")
    # =========================================================================
    # 键盘 → 目标位置
    # =========================================================================

    def _update_target_from_keys(self):
        if self.mc.state != "HOVERING":
            return
        step = 0.05  # m/frame
        tgt = self._target_pos.copy()
        vstep = 0.03
        if self._is_held(pygame.K_w, 17):   tgt[1] += step
        if self._is_held(pygame.K_s, 31):   tgt[1] -= step
        if self._is_held(pygame.K_a, 30):   tgt[0] -= step
        if self._is_held(pygame.K_d, 32):   tgt[0] += step
        if self._is_held(pygame.K_UP, 72):  tgt[2] += vstep
        if self._is_held(pygame.K_DOWN, 80): tgt[2] -= vstep
        tgt[2] = max(0.3, tgt[2])
        self._target_pos = tgt
        # 同步到 MissionController (Simulation用m, MissionController用cm)
        self.mc.target_pos = m_to_cm(tgt)

    def _is_held(self, keycode, scancode):
        return keycode in self._keys_held or scancode in self._scan_held

    # =========================================================================
    # Controller + EKF (P0-5: 集成到仿真)
    # =========================================================================
    # 渲染
    # =========================================================================

    def _render(self):
        self.screen.fill(SKY_BLUE)

        # ---- 中栏: 3D 场景 ----
        scene_x = self.PANEL_W
        scene_w = self.width - self.PANEL_W - self.CAMERA_W

        # 地面
        draw_ground(self.screen, y_ground=self.height - 100,
                    w=self.width, h=100)

        # 风机
        draw_turbine(self.screen, cx=scene_x + scene_w // 2,
                     cy=self.height // 2, height=280, radius=50,
                     blade_angle=self._blade_angle)

        # 风粒子
        wind_vec = self.wind.sample(0.1) * 5
        draw_wind_particles(self.screen, wind_vec[:2])

        # 路径
        draw_path(self.screen, self.path, current_idx=self.path_idx)

        # 无人机
        pos = m_to_cm(self.quad.get_position())
        draw_drone(self.screen, pos, self.quad.get_attitude(),
                   scale=0.35, rotor_phase=self._sim_time * 20)

        # 机械臂
        draw_arm(self.screen, pos, self.arm.angles, scale=0.35)

        # HUD (场景内)
        ekf_state = self.mc.ekf.get_state()
        state_dict = {
            "flight_state": self.mc.state,
            "position": pos.tolist(),
            "velocity": self.quad.get_velocity().tolist(),
            "disturbance": ekf_state["disturbance"].tolist(),
            "battery": int(self.mc._battery),
            "detection_count": len(self._mock_detections),
            "ekf_mahalanobis": self.mc.ekf.mahalanobis_distance,
            "target": self.mc.target_pos.tolist(),
            "arm_angles": "[{:.0f}, {:.0f}, {:.0f}]".format(*self.arm.angles),
            "arm_endpoint": "[{:.0f}, {:.0f}, {:.0f}] mm".format(*(np.array(self.arm.get_endpoint()) * 1000)),
            "path_length": len(self.path) if self.path else 0,
            "fps": self.clock.get_fps(),
            "emergency_reason": self.mc._emergency_reason,
        }
        # 中栏上方的HUD文字
        draw_hud(self.screen, self.font_sm, state_dict, self._mock_detections,
                 width=scene_w)

        # ---- 左栏: 遥测面板 ----
        draw_telemetry_panel(self.screen, self.font_sm,
                             0, 0, self.PANEL_W, state_dict)

        # ---- 右栏: 摄像机画面 ----
        cam_x = self.width - self.CAMERA_W
        pygame.draw.rect(self.screen, BLACK,
                         (cam_x, 0, self.CAMERA_W, self.CAMERA_H))
        pygame.draw.rect(self.screen, DARK_GRAY,
                         (cam_x, 0, self.CAMERA_W, self.CAMERA_H), 2)
        cam_label = self.font_sm.render("CAMERA", True, WHITE)
        self.screen.blit(cam_label, (cam_x + 10, 8))

        # 模拟摄像机画面 (接近风机时显示检测框)
        drone_pos = self.quad.get_position()
        dist_to_turbine = np.linalg.norm(
            drone_pos[:2] - self.turbine.center
        ) - self.turbine.radius
        if self.mc.state == "HOVERING" and dist_to_turbine < 2.0:
            # 生成 mock 检测
            if self._frame_count % 30 == 0:  # 每秒更新
                self._mock_detections = [
                    {"class_name": "crack", "confidence": 0.82, "bbox": [80, 40, 180, 70]},
                    {"class_name": "corrosion", "confidence": 0.71, "bbox": [200, 100, 280, 130]},
                ]
            # 画模拟框
            for d in self._mock_detections:
                x1, y1, x2, y2 = [v + 30 for v in d["bbox"]]  # 偏移
                pygame.draw.rect(self.screen, RED,
                                 (cam_x + x1, y1 - 15, x2 - x1, y2 - y1), 2)
                l = self.font_sm.render(d["class_name"], True, RED)
                self.screen.blit(l, (cam_x + x1, y1 - 32))
        else:
            self._mock_detections = []

        # 右栏下半: 检测日志
        log_y = self.CAMERA_H + 10
        log_h = self.height - self.CAMERA_H - 20
        pygame.draw.rect(self.screen, PANEL_BG,
                         (cam_x, self.CAMERA_H, self.CAMERA_W, log_h))
        log_title = self.font_sm.render("DETECTIONS", True, WHITE)
        self.screen.blit(log_title, (cam_x + 10, log_y))
        if self._mock_detections:
            for i, d in enumerate(self._mock_detections):
                t = "{}: {:.0f}%".format(d["class_name"], d["confidence"] * 100)
                s = self.font_sm.render(t, True, GREEN)
                self.screen.blit(s, (cam_x + 15, log_y + 22 + i * 18))

                # ---- 右栏: 机械臂面板 ----
        arm_panel_y = self.height - 180
        draw_arm_panel(self.screen, self.font_sm,
                       cam_x, arm_panel_y, self.CAMERA_W, 160,
                       self.arm.angles,
                       "[{:.0f}, {:.0f}, {:.0f}]".format(*np.array(self.arm.get_endpoint()) * 1000))  # m→mm

        pygame.display.flip()


if __name__ == "__main__":
    sim = Simulation()
    sim.run()
