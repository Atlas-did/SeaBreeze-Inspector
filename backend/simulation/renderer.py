"""
Pygame 3D渲染器 — 等轴测投影
"""

import math

import numpy as np
import pygame

# 颜色定义
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
DARK_GRAY = (100, 100, 100)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 100, 255)
ORANGE = (255, 165, 0)
SKY_BLUE = (135, 206, 235)


class Renderer:
    """
    Pygame 3D渲染器 — 等轴测投影。
    将3D世界坐标投影到2D屏幕坐标。
    """

    def __init__(self, screen_width=800, screen_height=600):
        self.screen_w = screen_width
        self.screen_h = screen_height
        self.cx = screen_width // 2
        self.cy = screen_height // 3
        self.scale = 0.5

    def project(self, x, y, z):
        """
        3D等轴测投影: (x,y,z) → (screen_x, screen_y)。
        使用标准等轴测投影公式。
        """
        iso_x = (x - y) * np.cos(np.radians(30))
        iso_y = (x + y) * np.sin(np.radians(30)) - z
        screen_x = int(iso_x * self.scale + self.cx)
        screen_y = int(iso_y * self.scale + self.cy)
        return screen_x, screen_y


def to_isometric(x, y, z, cx=400, cy=300, scale=0.5):
    """等轴测投影: (x,y,z) → (screen_x, screen_y)"""
    iso_x = (x - y) * math.cos(math.radians(30)) * scale
    iso_y = (x + y) * math.sin(math.radians(30)) * scale - z * scale
    return int(cx + iso_x), int(cy + iso_y)


def draw_turbine(surface, cx=400, cy=300, height=400, radius=60):
    """绘制风机塔筒 (圆柱体)"""
    # 塔筒底部和顶部
    base_points = []
    top_points = []
    for i in range(8):
        angle = math.radians(i * 45)
        bx = cx + int(radius * math.cos(angle))
        by = cy + int(radius * math.sin(angle) * 0.3)
        base_points.append((bx, by + 100))
        top_points.append((bx, by + 100 - height))

    # 绘制塔筒侧面
    for i in range(8):
        j = (i + 1) % 8
        color = DARK_GRAY if i < 4 else GRAY
        pygame.draw.polygon(surface, color, [
            base_points[i], base_points[j], top_points[j], top_points[i]
        ])

    # 塔筒顶部圆
    pygame.draw.polygon(surface, GRAY, top_points)
    pygame.draw.polygon(surface, BLACK, top_points, 2)


def draw_drone(surface, pos, attitude, scale=0.5):
    """绘制无人机 (四旋翼)"""
    x, y, z = pos
    sx, sy = to_isometric(x, y, z, scale=scale)

    # 机身
    body_size = 15
    pygame.draw.ellipse(surface, BLUE, (sx - body_size, sy - body_size//2, body_size*2, body_size))

    # 4个旋翼
    offsets = [(20, 0), (-20, 0), (0, 20), (0, -20)]
    for ox, oy in offsets:
        rx, ry = to_isometric(x + ox, y + oy, z, scale=scale)
        pygame.draw.circle(surface, RED, (rx, ry), 6)

    return sx, sy


def draw_arm(surface, drone_pos, joint_angles, scale=0.5):
    """绘制机械臂 (3DOF)"""
    x, y, z = drone_pos
    t1, t2, t3 = joint_angles

    # 简化的机械臂绘制
    base_x, base_y = to_isometric(x, y, z - 10, scale=scale)

    # 臂1
    import math
    arm1_len = 30
    end1_x = base_x + int(arm1_len * math.cos(math.radians(t2 - 90)))
    end1_y = base_y - int(arm1_len * math.sin(math.radians(t2 - 90)))
    pygame.draw.line(surface, ORANGE, (base_x, base_y), (end1_x, end1_y), 3)

    # 臂2
    arm2_len = 25
    end2_x = end1_x + int(arm2_len * math.cos(math.radians(t2 + t3 - 90)))
    end2_y = end1_y - int(arm2_len * math.sin(math.radians(t2 + t3 - 90)))
    pygame.draw.line(surface, GREEN, (end1_x, end1_y), (end2_x, end2_y), 3)

    # 末端
    pygame.draw.circle(surface, RED, (end2_x, end2_y), 4)


def draw_hud(surface, font, state, detections, width=800):
    """绘制HUD信息面板"""
    # 位置信息
    pos = state.get("position", [0, 0, 0])
    texts = [
        f"Position: ({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}) cm",
        f"State: {state.get('flight_state', 'UNKNOWN')}",
        f"Detections: {len(detections)}",
    ]
    for i, text in enumerate(texts):
        surf = font.render(text, True, WHITE)
        surface.blit(surf, (10, 10 + i * 25))
