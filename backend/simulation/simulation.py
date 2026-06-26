"""
Pygame仿真主循环
"""

import sys

import numpy as np
import pygame

from backend.simulation.models import Quadrotor3D, VirtualSensor, WindDisturbance
from backend.simulation.renderer import (
    SKY_BLUE, Renderer, draw_arm, draw_drone, draw_hud, draw_turbine,
)


class Simulation:
    """Pygame 3D仿真主类"""

    def __init__(self, width=800, height=600, fps=30):
        pygame.init()
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("无人机-机械臂协同系统仿真")
        self.clock = pygame.time.Clock()
        self.fps = fps
        self.width = width
        self.height = height
        self.font = pygame.font.SysFont("monospace", 16)

        # P1-18: 统一使用Renderer类进行等轴测投影
        self.renderer = Renderer(screen_width=width, screen_height=height)

        # 仿真对象
        self.quad = Quadrotor3D()
        self.wind = WindDisturbance()
        self.sensor = VirtualSensor()

        # 状态
        self.running = True
        self.flight_state = "IDLE"
        self.arm_angles = [90, 90, 90]
        self.detections = []

    def run(self):
        """主循环"""
        print("[SIM] 仿真启动, 按空格起飞, W/A/S/D移动, Q退出")

        while self.running:
            dt = self.clock.tick(self.fps) / 1000.0

            # 事件处理
            self._handle_events()

            # 物理更新
            self._update_physics(dt)

            # 渲染
            self._render()

        pygame.quit()
        print("[SIM] 仿真结束")

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    self.running = False
                elif event.key == pygame.K_SPACE:
                    if self.flight_state == "IDLE":
                        self.flight_state = "HOVERING"
                        self.quad.state[2] = 1.0  # 起飞到1m
                elif event.key == pygame.K_r:
                    self.flight_state = "IDLE"
                    self.quad.state[:] = 0

        # 键盘控制: WASD移动, 上下箭头升降, 空格起飞, Q退出
        keys = pygame.key.get_pressed()
        if self.flight_state == "HOVERING":
            speed = 0.5  # m/s
            # 维持悬停推力 = mass * g (Tello 87g = 0.087kg)
            control = np.array([self.quad.mass * self.quad.g, 0, 0, 0])

            if keys[pygame.K_w]:
                self.quad.state[1] += speed * 0.1
            if keys[pygame.K_s]:
                self.quad.state[1] -= speed * 0.1
            if keys[pygame.K_a]:
                self.quad.state[0] -= speed * 0.1
            if keys[pygame.K_d]:
                self.quad.state[0] += speed * 0.1
            if keys[pygame.K_UP]:
                self.quad.state[2] += speed * 0.1
            if keys[pygame.K_DOWN]:
                self.quad.state[2] -= speed * 0.1

    def _update_physics(self, dt):
        if self.flight_state == "HOVERING":
            # 风扰动
            wind_force = self.wind.sample(dt)
            # 维持悬停
            thrust = self.quad.mass * self.quad.g  # 0.087kg * g
            control = np.array([thrust, 0, 0, 0])
            self.quad.step(control, wind_force)

    def _render(self):
        self.screen.fill(SKY_BLUE)

        # 绘制风机塔筒
        draw_turbine(self.screen, cx=400, cy=450, height=350, radius=40)

        # 绘制地面
        pygame.draw.rect(self.screen, (34, 139, 34), (0, 500, 800, 100))

        # 获取无人机位置 (m → 缩放)
        pos = self.quad.get_position()
        pos_cm = pos * 100  # m → cm

        # 绘制无人机
        draw_drone(self.screen, pos_cm, self.quad.get_attitude(), scale=0.3)

        # 绘制机械臂
        draw_arm(self.screen, pos_cm, self.arm_angles, scale=0.3)

        # 绘制HUD
        state_dict = {
            "position": pos_cm.tolist(),
            "flight_state": self.flight_state,
        }
        draw_hud(self.screen, self.font, state_dict, self.detections, self.width)

        pygame.display.flip()


if __name__ == "__main__":
    sim = Simulation()
    sim.run()
