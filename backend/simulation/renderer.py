# -*- coding: utf-8 -*-
"""
Pygame 3D渲染器 — 等轴测投影 + 增强可视化
"""

import math

import numpy as np
import pygame

# =========================================================================
# 颜色定义
# =========================================================================
WHITE      = (255, 255, 255)
BLACK      = (0, 0, 0)
GRAY       = (200, 200, 200)
DARK_GRAY  = (100, 100, 100)
RED        = (255, 0, 0)
GREEN      = (0, 255, 0)
BLUE       = (0, 100, 255)
LIGHT_BLUE = (100, 180, 255)
ORANGE     = (255, 165, 0)
YELLOW     = (255, 255, 0)
SKY_BLUE   = (135, 206, 235)
GRASS      = (34, 139, 34)
STEEL      = (180, 190, 200)
DARK_STEEL = (140, 150, 160)
WHITE_SMOKE = (220, 225, 230)

# 面板颜色
PANEL_BG   = (30, 40, 50)
PANEL_FG   = (180, 200, 220)
PANEL_HL   = (100, 200, 255)


# =========================================================================
# 等轴测投影
# =========================================================================

def to_isometric(x, y, z, cx=400, cy=300, scale=0.5):
    """3D世界坐标 → 2D屏幕坐标 (等轴测投影)"""
    iso_x = (x - y) * math.cos(math.radians(30)) * scale
    iso_y = (x + y) * math.sin(math.radians(30)) * scale - z * scale
    return int(cx + iso_x), int(cy + iso_y)


class Renderer:
    """等轴测投影渲染器"""

    def __init__(self, screen_width=800, screen_height=600):
        self.screen_w = screen_width
        self.screen_h = screen_height
        self.cx = screen_width // 2
        self.cy = screen_height // 3
        self.scale = 0.5
        self._time = 0.0  # 动画时间

    def tick(self, dt: float):
        self._time += dt

    def project(self, x, y, z):
        """3D → 2D 投影"""
        iso_x = (x - y) * math.cos(math.radians(30))
        iso_y = (x + y) * math.sin(math.radians(30)) - z
        return int(iso_x * self.scale + self.cx), int(iso_y * self.scale + self.cy)


# =========================================================================
# 地面
# =========================================================================

def draw_ground(surface, y_ground=500, w=800, h=100):
    """绘制地面 + 网格线"""
    pygame.draw.rect(surface, GRASS, (0, y_ground, w, h))
    # 网格
    for x in range(0, w, 50):
        pygame.draw.line(surface, (50, 120, 50), (x, y_ground), (x, y_ground + h), 1)
    for y in range(y_ground, y_ground + h, 50):
        pygame.draw.line(surface, (50, 120, 50), (0, y), (w, y), 1)


# =========================================================================
# 风机塔筒 + 叶片
# =========================================================================

def draw_turbine(surface, cx=400, cy=300, height=350, radius=40, blade_angle=0.0):
    """绘制风机: 塔筒 + 机舱 + 3叶片"""
    # --- 塔筒 (分段圆柱) ---
    segments = 6
    seg_height = height // segments
    base_points_list = []
    top_points_list = []

    for s in range(segments):
        r = radius - s * (radius * 0.15 / segments)  # 上细下粗
        base_y = cy + 100 - s * seg_height
        top_y = base_y - seg_height
        bp = []
        tp = []
        for i in range(12):
            angle = math.radians(i * 30)
            bx = cx + int(r * math.cos(angle))
            by = base_y + int(r * math.sin(angle) * 0.3)
            tx = cx + int(r * math.cos(angle))
            ty = top_y + int(r * math.sin(angle) * 0.3)
            bp.append((bx, by))
            tp.append((tx, ty))
        # 塔筒段
        for i in range(12):
            j = (i + 1) % 12
            shade = DARK_STEEL if i < 6 else STEEL
            pygame.draw.polygon(surface, shade, [bp[i], bp[j], tp[j], tp[i]])
    # 顶部平台
    pygame.draw.ellipse(surface, GRAY, (cx - radius, cy + 100 - height - 8, radius * 2, 16))

    # --- 机舱 ---
    nacelle_y = cy + 100 - height - 10
    nacelle_points = [
        (cx - 20, nacelle_y - 5),
        (cx + 25, nacelle_y - 5),
        (cx + 30, nacelle_y + 10),
        (cx - 15, nacelle_y + 10),
    ]
    pygame.draw.polygon(surface, WHITE_SMOKE, nacelle_points)
    pygame.draw.polygon(surface, DARK_GRAY, nacelle_points, 1)

    # --- 旋转叶片 (3片, 120°间隔) ---
    blade_center = (cx, nacelle_y)
    blade_len = 80
    blade_width = 12
    for i in range(3):
        angle = blade_angle + math.radians(i * 120)
        # 叶片尖端
        tip_x = blade_center[0] + int(blade_len * math.cos(angle))
        tip_y = blade_center[1] + int(blade_len * math.sin(angle) * 0.5)
        # 叶片根部
        root_x = blade_center[0] + int(15 * math.cos(angle))
        root_y = blade_center[1] + int(15 * math.sin(angle) * 0.5)
        # 叶片线
        pygame.draw.line(surface, WHITE_SMOKE, blade_center, (tip_x, tip_y), blade_width)
        pygame.draw.line(surface, DARK_GRAY, (root_x, root_y), (tip_x, tip_y), 2)
        # 尖端标记
        pygame.draw.circle(surface, RED, (tip_x, tip_y), 3)


# =========================================================================
# 无人机
# =========================================================================

def draw_drone(surface, pos, attitude, scale=0.5, rotor_phase=0.0):
    """绘制四旋翼: 十字机架 + 4旋翼动画 + 倾角"""
    x, y, z = pos
    sx, sy = to_isometric(x, y, z, scale=scale)

    roll, pitch, _yaw = attitude

    # 倾角偏移
    tilt_x = int(pitch * 20)
    tilt_y = int(roll * 20)

    # 十字机架
    arm_len = 18
    arm_w = 3
    # 水平臂
    pygame.draw.line(surface, DARK_GRAY,
                     (sx - arm_len + tilt_x, sy),
                     (sx + arm_len + tilt_x, sy + tilt_y), arm_w + 2)
    # 垂直臂
    pygame.draw.line(surface, DARK_GRAY,
                     (sx, sy - arm_len + tilt_y),
                     (sx, sy + arm_len + tilt_y), arm_w + 2)

    # 机身
    body_w = 14
    body_h = 8
    pygame.draw.ellipse(surface, BLUE,
                        (sx - body_w//2, sy - body_h//2, body_w, body_h))
    pygame.draw.ellipse(surface, LIGHT_BLUE,
                        (sx - body_w//4, sy - body_h//4, body_w//2, body_h//2))

    # 4个旋翼
    rotor_radius = 7
    arm_offsets = [(arm_len, 0), (-arm_len, 0), (0, arm_len), (0, -arm_len)]
    for ox, oy in arm_offsets:
        rx = sx + ox + tilt_x
        ry = sy + oy + tilt_y
        # 旋翼圆盘 (半透明感)
        alpha_surf = pygame.Surface((rotor_radius * 2, rotor_radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(alpha_surf, (*LIGHT_BLUE, 60), (rotor_radius, rotor_radius), rotor_radius)
        surface.blit(alpha_surf, (rx - rotor_radius, ry - rotor_radius))
        # 旋翼动画线
        for j in range(4):
            ang = rotor_phase + math.radians(j * 90)
            lx = rx + int(rotor_radius * 0.8 * math.cos(ang))
            ly = ry + int(rotor_radius * 0.8 * math.sin(ang))
            pygame.draw.line(surface, RED, (rx, ry), (lx, ly), 1)

    return sx, sy


# =========================================================================
# 机械臂
# =========================================================================

def draw_arm(surface, drone_pos, joint_angles, scale=0.5):
    """绘制3-DOF机械臂: 关节球 + 连杆 + 末端锥形"""
    x, y, z = drone_pos
    t1, t2, t3 = joint_angles

    base_x, base_y = to_isometric(x, y, z - 12, scale=scale)

    # 臂1
    arm1_len = 30
    end1_x = base_x + int(arm1_len * math.cos(math.radians(t2 - 90)))
    end1_y = base_y - int(arm1_len * math.sin(math.radians(t2 - 90)))
    pygame.draw.line(surface, ORANGE, (base_x, base_y), (end1_x, end1_y), 5)
    pygame.draw.circle(surface, DARK_GRAY, (base_x, base_y), 5)
    pygame.draw.circle(surface, GRAY, (end1_x, end1_y), 4)

    # 臂2
    arm2_len = 25
    end2_x = end1_x + int(arm2_len * math.cos(math.radians(t2 + t3 - 90)))
    end2_y = end1_y - int(arm2_len * math.sin(math.radians(t2 + t3 - 90)))
    pygame.draw.line(surface, GREEN, (end1_x, end1_y), (end2_x, end2_y), 4)
    pygame.draw.circle(surface, GRAY, (end2_x, end2_y), 3)

    # 末端执行器 (相机锥形)
    cone_len = 10
    cone_w = 6
    tip_x = end2_x + int(cone_len * math.cos(math.radians(t2 + t3 - 90)))
    tip_y = end2_y - int(cone_len * math.sin(math.radians(t2 + t3 - 90)))
    pygame.draw.polygon(surface, YELLOW, [
        (end2_x - cone_w, end2_y - 2),
        (end2_x + cone_w, end2_y - 2),
        (tip_x, tip_y),
    ])
    # 相机FOV示意线
    fov_len = 20
    fov_lx = tip_x + int(fov_len * math.cos(math.radians(t2 + t3 - 110)))
    fov_ly = tip_y - int(fov_len * math.sin(math.radians(t2 + t3 - 110)))
    fov_rx = tip_x + int(fov_len * math.cos(math.radians(t2 + t3 - 70)))
    fov_ry = tip_y - int(fov_len * math.sin(math.radians(t2 + t3 - 70)))
    pygame.draw.line(surface, (255, 255, 100), (tip_x, tip_y), (fov_lx, fov_ly), 1)
    pygame.draw.line(surface, (255, 255, 100), (tip_x, tip_y), (fov_rx, fov_ry), 1)


# =========================================================================
# 路径 + 风场
# =========================================================================

def draw_path(surface, path, scale=0.5, current_idx=-1):
    """绘制RRT*路径: 虚线=已规划, 实线=已走过, 高亮=当前目标"""
    if path is None or len(path) < 2:
        return
    path = np.array(path)
    for i in range(len(path) - 1):
        x1, y1 = to_isometric(path[i][0], path[i][1], path[i][2], scale=scale)
        x2, y2 = to_isometric(path[i+1][0], path[i+1][1], path[i+1][2], scale=scale)
        if i < current_idx:
            # 已走过: 绿色实线
            pygame.draw.line(surface, GREEN, (x1, y1), (x2, y2), 2)
        else:
            # 未走过: 白色虚线
            draw_dashed_line(surface, WHITE, (x1, y1), (x2, y2), dash_len=8, gap=6)
    # 当前目标高亮
    if 0 <= current_idx < len(path):
        hx, hy = to_isometric(path[current_idx][0], path[current_idx][1], path[current_idx][2], scale=scale)
        pygame.draw.circle(surface, YELLOW, (hx, hy), 8, 2)
        pygame.draw.circle(surface, YELLOW, (hx, hy), 3)


def draw_dashed_line(surface, color, start, end, dash_len=8, gap=6):
    """绘制虚线"""
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 1:
        return
    dx, dy = dx / dist, dy / dist
    pos = 0.0
    on = True
    while pos < dist:
        seg_end = min(pos + (dash_len if on else gap), dist)
        if on:
            sx, sy = int(x1 + dx * pos), int(y1 + dy * pos)
            ex, ey = int(x1 + dx * seg_end), int(y1 + dy * seg_end)
            pygame.draw.line(surface, color, (sx, sy), (ex, ey), 1)
        pos = seg_end
        on = not on


def draw_wind_particles(surface, wind_vector, scale=0.5):
    """风粒子流: 沿风向移动的小点"""
    import random as _random
    _random.seed(int(wind_vector[0] * 100 + wind_vector[1] * 50))
    strength = math.sqrt(wind_vector[0]**2 + wind_vector[1]**2)
    if strength < 0.01:
        return
    n_particles = min(int(strength * 100), 30)
    for _ in range(n_particles):
        x = _random.randint(50, 750)
        y = _random.randint(50, 450)
        dx = int(wind_vector[0] * 200)
        dy = int(wind_vector[1] * 200)
        pygame.draw.line(surface, (*WHITE, 80),
                         (x, y), (x + dx, y + dy), 1)
        pygame.draw.circle(surface, (*WHITE, 120), (x + dx, y + dy), 2)


# =========================================================================
# HUD 遥测面板
# =========================================================================

def draw_hud(surface, font, state, detections, width=800):
    """绘制HUD遥测面板 (半透明底)"""
    pos = state.get("position", [0, 0, 0])
    vel = state.get("velocity", [0, 0, 0])
    dist = state.get("disturbance", [0, 0, 0])

    texts = [
        "State:  {}".format(state.get("flight_state", "UNKNOWN")),
        "Pos:    ({:6.0f}, {:6.0f}, {:6.0f}) cm".format(pos[0], pos[1], pos[2]),
        "Vel:    ({:5.1f}, {:5.1f}, {:5.1f}) m/s".format(vel[0], vel[1], vel[2]),
        "Dist:   ({:5.1f}, {:5.1f}, {:5.1f}) cm/s2".format(dist[0], dist[1], dist[2]),
        "Dets:   {}".format(len(detections)),
    ]
    for i, text in enumerate(texts):
        surf = font.render(text, True, WHITE)
        surface.blit(surf, (10, 10 + i * 22))


def draw_telemetry_panel(surface, font, x, y, w, state):
    """左侧遥测面板"""
    # 半透明背景
    panel = pygame.Surface((w, surface.get_height()))
    panel.set_alpha(200)
    panel.fill(PANEL_BG)
    surface.blit(panel, (x, 0))

    pos = state.get("position", [0, 0, 0])
    vel = state.get("velocity", [0, 0, 0])
    dist = state.get("disturbance", [0, 0, 0])

    title = font.render("TELEMETRY", True, PANEL_HL)
    surface.blit(title, (x + 10, y + 10))

    # Stage 4: 扩展至15行HUD
    items = [
        ("STATE", str(state.get("flight_state", "-")).upper()),
        ("BATT", "{}%".format(state.get("battery", 100))),
        ("HEIGHT", "{:.0f} cm".format(pos[2])),
        ("POS", "[{:.0f}, {:.0f}, {:.0f}]".format(pos[0], pos[1], pos[2])),
        ("POS_RAW", "[{:.0f}, {:.0f}, {:.0f}]".format(
            state.get("position", [0,0,0])[0],
            state.get("position", [0,0,0])[1],
            state.get("position", [0,0,0])[2])),
        ("VEL", "[{:.1f}, {:.1f}, {:.1f}]".format(vel[0], vel[1], vel[2])),
        ("ERROR", "[{:.0f}, {:.0f}, {:.0f}]".format(
            state.get("target", [0,0,0])[0] - pos[0],
            state.get("target", [0,0,0])[1] - pos[1],
            state.get("target", [0,0,0])[2] - pos[2])),
        ("DIST", "[{:.1f}, {:.1f}, {:.1f}]".format(dist[0], dist[1], dist[2])),
        ("EKF", "OK (D={:.1f})".format(state.get("ekf_mahalanobis", 0))),
        ("ARM", state.get("arm_angles", "[-, -, -]")),
        ("ENDEFF", state.get("arm_endpoint", "[-, -, -]")),
        ("DET", str(state.get("detection_count", 0))),
        ("PATH", "{} pts".format(state.get("path_length", 0))),
        ("SAFETY", "OK" if state.get("emergency_reason", "") == "" else "FAIL"),
        ("FPS", "{:.0f}".format(state.get("fps", 0))),
    ]
    for i, (label, value) in enumerate(items):
        ly = y + 32 + i * 17
        surf_label = font.render(label + ":", True, PANEL_FG)
        surf_value = font.render(value, True, WHITE)
        surface.blit(surf_label, (x + 12, ly))
        surface.blit(surf_value, (x + w - 80, ly))

    # 电池条
    bat = state.get("battery", 100)
    bar_x, bar_y = x + 12, y + 32 + len(items) * 17 + 6
    bar_w, bar_h = w - 24, 14
    color = GREEN if bat > 30 else RED if bat > 10 else (200, 0, 0)
    pygame.draw.rect(surface, DARK_GRAY, (bar_x, bar_y, bar_w, bar_h))
    pygame.draw.rect(surface, color, (bar_x, bar_y, int(bar_w * bat / 100), bar_h))
    pygame.draw.rect(surface, WHITE, (bar_x, bar_y, bar_w, bar_h), 1)

    # 高度条
    hgt = min(pos[2] / 300.0, 1.0) if pos[2] > 0 else 0
    hbar_h = 100
    hx, hy = x + 12, bar_y + 22
    pygame.draw.rect(surface, DARK_GRAY, (hx, hy, 12, hbar_h))
    fill_h = int(hbar_h * hgt)
    pygame.draw.rect(surface, LIGHT_BLUE, (hx, hy + hbar_h - fill_h, 12, fill_h))
    pygame.draw.rect(surface, WHITE, (hx, hy, 12, hbar_h), 1)

    

    # EKF 状态灯
    mahal = state.get("ekf_mahalanobis", 0)
    status_color = GREEN if mahal < 8 else YELLOW if mahal < 15 else RED
    pygame.draw.circle(surface, status_color, (x + 30, hy + hbar_h + 20), 6)
    ekf_text = font.render("EKF", True, PANEL_FG)
    surface.blit(ekf_text, (x + 42, hy + hbar_h + 12))


#
# ---- 机械臂控制面板 (Stage 4) ----
#

def draw_arm_panel(surface, font, x, y, w, h, arm_angles, endpoint):
    """右侧机械臂信息面板"""
    panel = pygame.Surface((w, h))
    panel.set_alpha(200)
    panel.fill(PANEL_BG)
    surface.blit(panel, (x, y))
    pygame.draw.rect(surface, (70, 90, 110), (x, y, w, h), 1)

    title = font.render("ARM CONTROL", True, PANEL_HL)
    surface.blit(title, (x + 10, y + 8))

    labels = ["Base", "Shoulder", "Elbow"]
    for i, (label, angle) in enumerate(zip(labels, arm_angles)):
        ly = y + 32 + i * 24
        t = font.render("{}: {:.0f} deg".format(label, angle), True, WHITE)
        surface.blit(t, (x + 12, ly))
        # Bar
        bar_w = w - 100
        fill = int(bar_w * angle / 180.0)
        pygame.draw.rect(surface, DARK_GRAY, (x + 12, ly + 14, bar_w, 6))
        pygame.draw.rect(surface, LIGHT_BLUE, (x + 12, ly + 14, fill, 6))

    ep_y = y + 32 + 3 * 24 + 12
    ep_t = font.render("ENDEFF: {}".format(endpoint), True, WHITE)
    surface.blit(ep_t, (x + 12, ep_y))

    keys_t = font.render("Ctrl+<- -> Base  Ctrl+^ v Arm", True, PANEL_FG)
    surface.blit(keys_t, (x + 12, ep_y + 20))
    shift_t = font.render("+Shift: fast", True, PANEL_FG)
    surface.blit(shift_t, (x + 12, ep_y + 38))

