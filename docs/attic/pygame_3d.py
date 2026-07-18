#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SeaBreeze Inspector - Pygame 3D Simulation
Zero extra dependencies. Uses pygame-ce for rendering + perspective projection.
Connects directly to backend: MissionController + EKF + SafetyGuard + Arm FK.

Run: venv/Scripts/python backend/simulation/pygame_3d.py
"""
import math
import os
import sys
import time
import numpy as np
import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.simulation.models import Quadrotor3D, WindDisturbance, RobotArm3DOF, VirtualSensor
from backend.main import MissionController
from backend.utils.units import m_to_cm, cm_to_m, mps_to_cmps, cmps_to_mps

# ============================================================
# Colors
# ============================================================
SKY_TOP = (25, 50, 80)
SKY_BOT = (80, 150, 200)
SEA = (10, 40, 70)
WHITE = (240, 245, 255)
GRAY = (160, 170, 180)
DARK = (60, 65, 70)
RED = (255, 60, 60)
GREEN = (60, 255, 100)
ORANGE = (255, 160, 40)
BLUE = (60, 140, 255)
YELLOW = (255, 220, 40)
CYAN = (60, 220, 255)
PANEL_BG = (15, 25, 40, 200)

# ============================================================
# 3D Math
# ============================================================
class Camera3D:
    def __init__(self):
        self.eye = np.array([8.0, 3.0, 8.0])
        self.target = np.array([0.0, 1.5, 0.0])
        self.up = np.array([0.0, 1.0, 0.0])
        self.fov = 60
        self.near = 0.1
        self.far = 200
        self._yaw = 45
        self._pitch = 20
        self._dist = 12
        self._update()

    def _update(self):
        yr = math.radians(self._yaw)
        pr = math.radians(self._pitch)
        self.eye = self.target + np.array([
            self._dist * math.cos(pr) * math.sin(yr),
            self._dist * math.sin(pr),
            self._dist * math.cos(pr) * math.cos(yr)
        ])

    def orbit(self, dyaw, dpitch):
        self._yaw = (self._yaw + dyaw) % 360
        self._pitch = max(5, min(80, self._pitch + dpitch))
        self._update()

    def zoom(self, dz):
        self._dist = max(3, min(40, self._dist + dz))
        self._update()

    def follow(self, target_pos):
        self.target = np.array(target_pos) + np.array([0, 1, 0])
        self._update()

    def project(self, point_3d, screen_w, screen_h):
        """Perspective projection: 3D world -> 2D screen"""
        p = np.array(point_3d) - self.eye
        fwd = self.target - self.eye
        fwd = fwd / np.linalg.norm(fwd)
        right = np.cross(fwd, self.up)
        right = right / np.linalg.norm(right)
        up = np.cross(right, fwd)

        cam_z = np.dot(p, fwd)
        if cam_z < self.near:
            return None
        cam_x = np.dot(p, right)
        cam_y = np.dot(p, up)

        scale = screen_h / (2 * cam_z * math.tan(math.radians(self.fov / 2)))
        sx = screen_w / 2 + cam_x * scale
        sy = screen_h / 2 - cam_y * scale
        return (int(sx), int(sy), cam_z)


# ============================================================
# 3D Primitives (wireframe)
# ============================================================
def draw_cube(surface, cam, center, size, color, screen_w, screen_h):
    x, y, z = center
    hw, hh, hd = size[0] / 2, size[1] / 2, size[2] / 2
    verts = [
        (x - hw, y - hh, z - hd), (x + hw, y - hh, z - hd),
        (x + hw, y + hh, z - hd), (x - hw, y + hh, z - hd),
        (x - hw, y - hh, z + hd), (x + hw, y - hh, z + hd),
        (x + hw, y + hh, z + hd), (x - hw, y + hh, z + hd),
    ]
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
             (0, 4), (1, 5), (2, 6), (3, 7)]
    pts = {}
    for i, v in enumerate(verts):
        p = cam.project(v, screen_w, screen_h)
        if p: pts[i] = p
    for a, b in edges:
        if a in pts and b in pts:
            pygame.draw.line(surface, color, (pts[a][0], pts[a][1]), (pts[b][0], pts[b][1]), 1)

    # Fill faces for solid look
    faces = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (0, 3, 7, 4), (1, 2, 6, 5)]
    face_colors = [
        (min(255, color[0] + 40), min(255, color[1] + 40), min(255, color[2] + 40)),
        (max(0, color[0] - 40), max(0, color[1] - 40), max(0, color[2] - 40)),
        color, color, color, color
    ]
    for fi, face in enumerate(faces):
        poly = []
        for vi in face:
            if vi in pts:
                poly.append((pts[vi][0], pts[vi][1]))
        if len(poly) >= 3:
            pygame.draw.polygon(surface, face_colors[fi % len(face_colors)], poly)
            pygame.draw.polygon(surface, color, poly, 1)


def draw_cylinder(surface, cam, base_center, radius, height, color, screen_w, screen_h, segments=12):
    bx, by, bz = base_center
    r, h = radius, height
    top_pts, bot_pts = [], []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        cx = bx + r * math.cos(angle)
        cz = bz + r * math.sin(angle)
        tp = cam.project((cx, by + h, cz), screen_w, screen_h)
        bp = cam.project((cx, by, cz), screen_w, screen_h)
        if tp: top_pts.append(tp)
        if bp: bot_pts.append(bp)

    # Fill
    if len(top_pts) >= 3:
        pygame.draw.polygon(surface, (min(255, color[0] + 20), min(255, color[1] + 20), min(255, color[2] + 20)), [(p[0], p[1]) for p in top_pts])
        pygame.draw.polygon(surface, color, [(p[0], p[1]) for p in top_pts], 1)
    if len(bot_pts) >= 3:
        pygame.draw.polygon(surface, (max(0, color[0] - 20), max(0, color[1] - 20), max(0, color[2] - 20)), [(p[0], p[1]) for p in bot_pts])

    # Sides
    for i in range(len(top_pts)):
        j = (i + 1) % len(top_pts)
        if i < len(bot_pts) and j < len(bot_pts):
            pts = [(top_pts[i][0], top_pts[i][1]), (top_pts[j][0], top_pts[j][1]),
                   (bot_pts[j][0], bot_pts[j][1]), (bot_pts[i][0], bot_pts[i][1])]
            shade = color if i < segments // 2 else (max(0, color[0] - 30), max(0, color[1] - 30), max(0, color[2] - 30))
            pygame.draw.polygon(surface, shade, pts)
            pygame.draw.polygon(surface, color, pts, 1)


def draw_sphere(surface, cam, center, radius, color, screen_w, screen_h):
    p = cam.project(center, screen_w, screen_h)
    if not p: return
    dist = p[2]
    r = max(3, int(radius * 20 / max(0.5, dist)))
    pygame.draw.circle(surface, color, (p[0], p[1]), r)
    # Highlight
    hl = (min(255, color[0] + 80), min(255, color[1] + 80), min(255, color[2] + 80))
    pygame.draw.circle(surface, hl, (p[0] - r // 3, p[1] - r // 3), r // 3)


def draw_line_3d(surface, cam, p1, p2, color, screen_w, screen_h, width=1):
    a = cam.project(p1, screen_w, screen_h)
    b = cam.project(p2, screen_w, screen_h)
    if a and b:
        pygame.draw.line(surface, color, (a[0], a[1]), (b[0], b[1]), width)


# ============================================================
# Scene objects
# ============================================================
def draw_sea(surface, cam, screen_w, screen_h):
    for y in range(screen_h // 2, screen_h):
        t = (y - screen_h // 2) / (screen_h // 2)
        r = int(SEA[0] + (10 - SEA[0]) * t)
        g = int(SEA[1] + (30 - SEA[1]) * t)
        b = int(SEA[2] + (60 - SEA[2]) * t)
        pygame.draw.line(surface, (r, g, b), (0, y), (screen_w, y))

    # Grid lines
    for i in range(-10, 11):
        for j in range(-10, 11):
            p = cam.project((i * 2, -0.1, j * 2), screen_w, screen_h)
            if p and 0 <= p[0] < screen_w and 0 <= p[1] < screen_h:
                surface.set_at((p[0], p[1]), (30, 60, 80))


def draw_turbine_3d(surface, cam, screen_w, screen_h, blade_angle):
    # Tower - segmented cylinder
    H, R = 12.0, 0.6
    tower_pos = (9.0, H / 2, -2.0)
    segs = 6
    for s in range(segs):
        r = R * (1 - s * 0.08)
        bh = s * H / segs
        color = WHITE if s % 2 == 0 else (200, 40, 40)
        draw_cylinder(surface, cam, (9.0, bh, -2.0), r, H / segs, color, screen_w, screen_h, 12)

    # Nacelle
    draw_cube(surface, cam, (9.0, H + 0.3, -2.0), (1.6, 0.9, 0.9), GRAY, screen_w, screen_h)

    # Blades
    BL = 3.2
    for i in range(3):
        angle = blade_angle + i * 2 * math.pi / 3
        tx = 9.0 + BL * math.cos(angle) * 0.5
        ty = H + 0.3 + BL * math.sin(angle) * 0.3
        tz = -2.0
        draw_line_3d(surface, cam, (9.0, H + 0.3, -2.0), (tx, ty, tz), WHITE, screen_w, screen_h, 3)
    draw_sphere(surface, cam, (9.0, H + 0.3, -2.0), 0.3, GRAY, screen_w, screen_h)


def draw_drone_3d(surface, cam, pos, attitude, screen_w, screen_h):
    """Draw Tello drone at world position"""
    x, y, z = pos
    # Body
    draw_cube(surface, cam, (x, y, z), (0.098, 0.041, 0.093), WHITE, screen_w, screen_h)
    # Arms (4 motor arms)
    for dx, dz in [(0.06, 0.06), (0.06, -0.06), (-0.06, 0.06), (-0.06, -0.06)]:
        draw_line_3d(surface, cam, (x, y + 0.008, z), (x + dx, y + 0.014, z + dz), DARK, screen_w, screen_h, 2)
        draw_sphere(surface, cam, (x + dx, y + 0.014, z + dz), 0.015, DARK, screen_w, screen_h)
    # Propeller discs
    for dx, dz in [(0.06, 0.06), (0.06, -0.06), (-0.06, 0.06), (-0.06, -0.06)]:
        draw_sphere(surface, cam, (x + dx, y + 0.024, z + dz), 0.038, (200, 200, 210), screen_w, screen_h)


def draw_arm_3d(surface, cam, drone_pos, angles, screen_w, screen_h):
    """Draw 3DOF arm using FK from arm_kinematics"""
    L1, L2, L3 = 0.055, 0.045, 0.035  # meters
    BASE_H = 0.025

    t1 = math.radians(angles[0])
    t2 = math.radians(angles[1])
    t3 = math.radians(angles[2])
    L23 = L2 + L3

    # FK calculations (from arm_kinematics.py)
    r_h = L1 * math.cos(t2) + L23 * math.cos(t2 + t3)
    z_h = L1 * math.sin(t2) + L23 * math.sin(t2 + t3)
    x_h = r_h * math.cos(t1)
    y_h = r_h * math.sin(t1)

    # Base position (below drone)
    bx = drone_pos[0]
    by = drone_pos[2] - 0.041 / 2  # bottom of drone body (z-up)
    bz = drone_pos[2]

    # Joint positions
    j0 = (bx, by, bz)
    j1 = (bx, by - BASE_H, bz)  # shoulder
    ee_x = bx + x_h
    ee_y = by - BASE_H - z_h  # z_h is downward from base
    ee_z = bz + y_h
    ee = (ee_x, ee_y, ee_z)

    # Draw links
    draw_line_3d(surface, cam, j0, j1, ORANGE, screen_w, screen_h, 3)
    # Shoulder to elbow (approximate)
    sh_x = bx + L1 * math.cos(t2) * math.cos(t1) * 0.5
    sh_y = by - BASE_H - L1 * math.sin(t2) * 0.3
    sh_z = bz + L1 * math.cos(t2) * math.sin(t1) * 0.5
    draw_line_3d(surface, cam, j1, ee, (60, 200, 60), screen_w, screen_h, 4)

    # Joints
    draw_sphere(surface, cam, j0, 0.012, ORANGE, screen_w, screen_h)
    draw_sphere(surface, cam, j1, 0.01, (255, 120, 0), screen_w, screen_h)
    draw_sphere(surface, cam, ee, 0.008, RED, screen_w, screen_h)


# ============================================================
# HUD
# ============================================================
def draw_hud_panel(surface, font, x, y, w, h, state):
    """Left telemetry panel"""
    panel = pygame.Surface((w, h), pygame.SRCALPHA)
    panel.fill(PANEL_BG)
    surface.blit(panel, (x, y))

    items = [
        ("STATE", state.get("state", "IDLE")),
        ("BATT", f"{state.get('battery', 100):.0f}%"),
        ("POS", f"[{state.get('pos', [0,0,0])[0]:.1f}, {state.get('pos', [0,0,0])[1]:.1f}, {state.get('pos', [0,0,0])[2]:.1f}]"),
        ("VEL", f"[{state.get('vel', [0,0,0])[0]:.2f}, {state.get('vel', [0,0,0])[1]:.2f}, {state.get('vel', [0,0,0])[2]:.2f}]"),
        ("WIND", f"[{state.get('wind', [0,0,0])[0]:.2f}, {state.get('wind', [0,0,0])[2]:.2f}]"),
        ("EKF D", f"{state.get('ekf_mahal', 0):.1f}"),
        ("SAFETY", state.get("safety_tier", "NOMINAL")),
        ("FPS", f"{state.get('fps', 0)}"),
    ]

    hdr = font.render("TELEMETRY", True, CYAN)
    surface.blit(hdr, (x + 10, y + 8))

    for i, (label, value) in enumerate(items):
        ly = y + 30 + i * 18
        lb = font.render(f"{label}:", True, (150, 180, 210))
        vl = font.render(value, True, WHITE)
        surface.blit(lb, (x + 12, ly))
        surface.blit(vl, (x + w - 120, ly))

    # Battery bar
    bat = state.get("battery", 100)
    bar_y = y + 30 + len(items) * 18 + 5
    pygame.draw.rect(surface, (40, 50, 60), (x + 12, bar_y, w - 24, 12))
    bat_color = GREEN if bat > 30 else ORANGE if bat > 10 else RED
    pygame.draw.rect(surface, bat_color, (x + 12, bar_y, int((w - 24) * bat / 100), 12))


def draw_arm_panel_3d(surface, font, x, y, w, h, angles, endpoint):
    """Right arm control panel"""
    panel = pygame.Surface((w, h), pygame.SRCALPHA)
    panel.fill(PANEL_BG)
    surface.blit(panel, (x, y))

    hdr = font.render("ARM CONTROL", True, CYAN)
    surface.blit(hdr, (x + 10, y + 8))

    labels = ["Base t1", "Shoulder t2", "Elbow t3"]
    for i, (label, angle) in enumerate(zip(labels, angles)):
        ly = y + 30 + i * 22
        lb = font.render(f"{label}: {angle:.0f} deg", True, WHITE)
        surface.blit(lb, (x + 12, ly))
        bar_w = w - 100
        fill = int(bar_w * angle / 180.0)
        pygame.draw.rect(surface, (40, 50, 60), (x + 12, ly + 14, bar_w, 5))
        pygame.draw.rect(surface, CYAN, (x + 12, ly + 14, fill, 5))

    ep_y = y + 30 + 3 * 22 + 10
    ep_lb = font.render(f"END-EFF: [{endpoint[0]:.0f}, {endpoint[1]:.0f}, {endpoint[2]:.0f}] mm", True, WHITE)
    surface.blit(ep_lb, (x + 12, ep_y))


def draw_camera_panel(surface, font, x, y, w, h, state):
    """Right camera simulation panel"""
    panel = pygame.Surface((w, h), pygame.SRCALPHA)
    panel.fill(PANEL_BG)
    surface.blit(panel, (x, y))

    hdr = font.render("CAMERA", True, CYAN)
    surface.blit(hdr, (x + 10, y + 8))

    # Camera viewport
    cam_vp_x, cam_vp_y = x + 10, y + 28
    cam_vp_w, cam_vp_h = w - 20, h - 80
    pygame.draw.rect(surface, (5, 5, 5), (cam_vp_x, cam_vp_y, cam_vp_w, cam_vp_h))

    # Crosshair
    cx, cy = cam_vp_x + cam_vp_w // 2, cam_vp_y + cam_vp_h // 2
    pygame.draw.line(surface, (30, 80, 30), (cam_vp_x, cy), (cam_vp_x + cam_vp_w, cy), 1)
    pygame.draw.line(surface, (30, 80, 30), (cx, cam_vp_y), (cx, cam_vp_y + cam_vp_h), 1)
    pygame.draw.circle(surface, (30, 80, 30), (cx, cy), 15, 1)

    # Mock detections when close to turbine
    dets = state.get("detections", [])
    if dets:
        for d in dets:
            bx, by, bw, bh = d.get("bbox", [100, 80, 40, 30])
            pygame.draw.rect(surface, RED, (cam_vp_x + bx, cam_vp_y + by, bw, bh), 2)
            txt = font.render(f"{d.get('cls', '?')} {int(d.get('conf', 0) * 100)}%", True, RED)
            surface.blit(txt, (cam_vp_x + bx + 2, cam_vp_y + by - 16))

    # Status
    dist = state.get("dist_to_turbine", 999)
    st = font.render(f"DIST: {dist:.1f}m | {state.get('state', 'IDLE')}", True, GREEN)
    surface.blit(st, (x + 12, y + h - 18))

    # Detection log
    if dets:
        for i, d in enumerate(dets[:3]):
            txt = font.render(f"  {d.get('cls', '?')} ({int(d.get('conf', 0) * 100)}%)", True, GREEN)
            surface.blit(txt, (x + 12, y + h - 40 + i * 14))


# ============================================================
# Main Simulation
# ============================================================
class Pygame3DSim:
    def __init__(self, width=1280, height=720):
        pygame.init()
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("SeaBreeze Inspector - 3D Simulation")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 13)
        self.font_sm = pygame.font.SysFont("consolas", 11)
        self.w, self.h = width, height
        self.running = True

        # Camera
        self.cam = Camera3D()

        # Backend
        self.quad = Quadrotor3D()
        self.wind = WindDisturbance(np.array([0.05, 0.02, 0.0]), freq=0.5, gust_amp=0.03)
        self.arm = RobotArm3DOF()
        self.sensor = VirtualSensor()
        self.mc = MissionController(mode="simulation", mock=True)
        # A1 fixed: heartbeat called every frame, no need for timeout workaround

        # State
        self.hover_height = 1.2
        self._target = np.array([3.0, self.hover_height, 15.0])
        self._last_ctrl = np.zeros(3)
        self._blade_angle = 0.0
        self._sim_time = 0.0
        self._detections = []
        self._flight_log = []
        self._log_timer = 0.0
        self._demo_mode = False
        self._demo_phase = 0
        self._demo_timer = 0.0

    def run(self):
        print("\n" + "=" * 60)
        print("  SeaBreeze Inspector - Pygame 3D Simulation")
        print("  Backend: MissionController + EKF + SafetyGuard + FK")
        print("=" * 60)
        print("  [Space]=Takeoff/Land  [WASD]=Move  [M]=Mission")
        print("  [E]=Emergency  [R]=Reset  [Arrows]=Arm  [D]=Demo")
        print("  [Mouse drag]=Orbit  [Scroll]=Zoom  [C]=Chase\n")

        dt = 0.02
        keys_held = set()

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    keys_held.add(event.key)
                    self._handle_key(event.key)
                elif event.type == pygame.KEYUP:
                    keys_held.discard(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 4:  # scroll up
                        self.cam.zoom(-1)
                    elif event.button == 5:  # scroll down
                        self.cam.zoom(1)

            # Mouse drag for orbit
            if pygame.mouse.get_pressed()[0]:
                dx, dy = pygame.mouse.get_rel()
                self.cam.orbit(-dx * 0.3, -dy * 0.3)

            # WASD movement
            state_str = str(self.mc.state)
            if state_str == "HOVERING":
                step = 0.04
                if pygame.K_w in keys_held: self._target[0] += step
                if pygame.K_s in keys_held: self._target[0] -= step
                if pygame.K_a in keys_held: self._target[2] += step
                if pygame.K_d in keys_held: self._target[2] -= step

            # Arrow keys for arm
            delta = 5
            angles = self.arm.angles.copy()
            if pygame.K_LEFT in keys_held: angles[0] = (angles[0] - delta) % 180
            if pygame.K_RIGHT in keys_held: angles[0] = (angles[0] + delta) % 180
            if pygame.K_UP in keys_held: angles[1] = min(150, angles[1] + delta)
            if pygame.K_DOWN in keys_held: angles[1] = max(30, angles[1] - delta)
            if not np.array_equal(angles, self.arm.angles):
                self.arm.set_angles(angles)

            # Demo mode
            if self._demo_mode:
                self._run_demo(dt)

            # Physics step
            wind_vec = self.wind.sample(dt)
            if state_str not in ("IDLE", "EMERGENCY", "MissionState.IDLE"):
                v_des = self._last_ctrl
                v_cur = self.quad.get_velocity()
                a_des = (v_des - v_cur) / 0.3
                thrust = self.quad.mass * (a_des[1] + self.quad.g)
                self.quad.step(np.array([thrust, 0.0, 0.0, 0.0]), disturbance=wind_vec)

            # EKF + Controller
            if state_str not in ("IDLE", "EMERGENCY", "MissionState.IDLE"):
                sensor_data = self.sensor.read_all(self.quad)
                z = np.array([sensor_data["imu"][0], sensor_data["imu"][1], sensor_data["imu"][2],
                              sensor_data["optical"][0], sensor_data["optical"][1], sensor_data["barometer"]])
                pos = self.quad.get_position()
                vel = self.quad.get_velocity()
                att = self.quad.get_attitude()
                ctrl_cmps, state_dict = self.mc.update_with_external_data(
                    z, m_to_cm(pos), mps_to_cmps(vel), att)
                _last_ctrl = cmps_to_mps(ctrl_cmps)
                self.quad.set_velocity(_last_ctrl)

            # Battery
            self.mc._battery -= dt * (1.5 if state_str == "HOVERING" else 0.1)
            self.mc._battery = max(0, self.mc._battery)

            # Render
            self._render()
            self.clock.tick(60)
            self._sim_time += dt

        pygame.quit()

    def _handle_key(self, key):
        state_str = str(self.mc.state)
        if key == pygame.K_SPACE:
            if state_str in ("IDLE", "MissionState.IDLE"):
                self.mc.takeoff(height=self.hover_height * 100)
                self.quad.state[2] = self.hover_height
                self._target = self.quad.get_position().copy()
                self._flight_log.append(f"[{self._sim_time:.1f}s] TAKEOFF -> hover at {self.hover_height}m")
            else:
                self.mc.request_state("LAND", "manual")
                self._target[2] = 0.0  # z-up: height=Z
                self._flight_log.append(f"[{self._sim_time:.1f}s] LAND")
        elif key == pygame.K_r:
            self.mc.request_state("IDLE", "reset")
            self.quad.state[:] = 0.0
            self.quad.set_velocity(np.zeros(3))
            self._target = np.array([3.0, self.hover_height, 15.0])
            self.arm.set_angles([90.0, 90.0, 45.0])
            self.mc.ekf.reset()
            self._demo_mode = False
            self._demo_phase = 0
            self._flight_log = []
            self._flight_log.append(f"[{self._sim_time:.1f}s] RESET")
        elif key == pygame.K_e:
            self.mc.request_state("EMERGENCY", "manual")
            self._flight_log.append(f"[{self._sim_time:.1f}s] EMERGENCY")
        elif key == pygame.K_m and state_str == "HOVERING":
            self.mc.request_state("NAVIGATE", "mission")
            self._target = np.array([7.0, self.hover_height + 2, -2.0])
            self._flight_log.append(f"[{self._sim_time:.1f}s] MISSION START - navigating to turbine")
        elif key == pygame.K_d:
            self._demo_mode = not self._demo_mode
            self._demo_phase = 0
            self._demo_timer = 0
            if self._demo_mode:
                self._flight_log.append(f"[{self._sim_time:.1f}s] DEMO MODE ON")
            else:
                self._flight_log.append(f"[{self._sim_time:.1f}s] DEMO MODE OFF")
        elif key == pygame.K_c:
            self.cam.follow(self.quad.get_position())

    def _run_demo(self, dt):
        """Auto-play intelligent inspection workflow"""
        self._demo_timer += dt
        pos = self.quad.get_position()
        state_str = str(self.mc.state)

        if self._demo_phase == 0:
            # Takeoff
            if state_str in ("IDLE", "MissionState.IDLE"):
                self.mc.takeoff(height=self.hover_height * 100)
                self.quad.state[2] = self.hover_height
                self._target = self.quad.get_position().copy()
                self._flight_log.append(f"[{self._sim_time:.1f}s] DEMO: Takeoff")
                self._demo_phase = 1
                self._demo_timer = 0

        elif self._demo_phase == 1:
            # Wait for hover, then start mission
            if state_str == "HOVERING" and self._demo_timer > 1.5:
                self.mc.request_state("NAVIGATE", "mission")
                self._target = np.array([7.0, self.hover_height + 2, -2.0])
                self._flight_log.append(f"[{self._sim_time:.1f}s] DEMO: Starting inspection mission")
                self._demo_phase = 2
                self._demo_timer = 0

        elif self._demo_phase == 2:
            # Navigate to turbine
            if np.linalg.norm(pos[:2] - np.array([7.0, -2.0])) < 1.5:
                self._detections = [
                    {"cls": "crack", "conf": 0.82, "bbox": [100, 80, 40, 30]},
                    {"cls": "corrosion", "conf": 0.71, "bbox": [180, 120, 50, 35]},
                    {"cls": "rust", "conf": 0.68, "bbox": [140, 160, 35, 25]},
                ]
                self._flight_log.append(f"[{self._sim_time:.1f}s] DEMO: Detecting defects near turbine")
                self._demo_phase = 3
                self._demo_timer = 0

        elif self._demo_phase == 3:
            # Inspect for 5 seconds
            self.cam.follow(pos)
            if self._demo_timer > 5.0:
                self.mc.request_state("RETURN", "mission_complete")
                self._target = np.array([0.0, self.hover_height, 0.0])
                self._detections = []
                self._flight_log.append(f"[{self._sim_time:.1f}s] DEMO: Inspection complete, returning")
                self._demo_phase = 4
                self._demo_timer = 0

        elif self._demo_phase == 4:
            # Return and land
            if np.linalg.norm(pos[:2]) < 0.5 and pos[2] < 0.1:  # z-up: height=pos[2]
                self.mc.request_state("LAND", "auto")
                self._flight_log.append(f"[{self._sim_time:.1f}s] DEMO: Landing")
                self._demo_phase = 5
                self._demo_timer = 0

        elif self._demo_phase == 5:
            # Done
            if self._demo_timer > 2.0:
                self._demo_phase = 0
                self._demo_timer = 0
                self._flight_log.append(f"[{self._sim_time:.1f}s] DEMO: Cycle complete. Press D to replay")

        # Log periodically
        self._log_timer += dt
        if self._log_timer > 3.0:
            self._log_timer = 0
            self._flight_log.append(f"[{self._sim_time:.1f}s] State={state_str} Bat={self.mc._battery:.0f}% H={pos[2]:.1f}m  # z-up height")
        if len(self._flight_log) > 50:
            self._flight_log = self._flight_log[-50:]

    def _render(self):
        self.screen.fill(SKY_TOP)
        draw_sea(self.screen, self.cam, self.w, self.h)

        # 3D scene
        self._blade_angle += 0.02
        draw_turbine_3d(self.screen, self.cam, self.w, self.h, self._blade_angle)

        pos = self.quad.get_position()
        att = self.quad.get_attitude()
        draw_drone_3d(self.screen, self.cam, pos, att, self.w, self.h)
        draw_arm_3d(self.screen, self.cam, pos, self.arm.angles, self.w, self.h)

        # Turbo position marker
        dist = np.linalg.norm(pos[:2] - np.array([9.0, -2.0]))
        dets = self._detections if dist < 3 else []

        # State dict for HUD
        ep = self.arm.get_endpoint()
        state_dict = {
            "state": str(self.mc.state).replace("MissionState.", ""),
            "battery": self.mc._battery,
            "pos": pos.tolist(),
            "vel": self.quad.get_velocity().tolist(),
            "wind": self.wind.sample(0.1).tolist(),
            "ekf_mahal": self.mc.ekf.mahalanobis_distance,
            "safety_tier": "EMERGENCY" if self.mc._emergency_reason else (
                "WARN" if self.mc._battery < 30 else "NOMINAL"),
            "fps": int(self.clock.get_fps()),
            "detections": dets,
            "dist_to_turbine": dist,
        }

        # HUD panels
        draw_hud_panel(self.screen, self.font_sm, 5, 5, 240, self.h - 10, state_dict)
        draw_arm_panel_3d(self.screen, self.font_sm, self.w - 250, self.h - 160, 245, 155,
                          self.arm.angles, np.array(ep) * 1000)
        draw_camera_panel(self.screen, self.font_sm, self.w - 260, 5, 255, 200, state_dict)

        # Title
        title = self.font.render("SeaBreeze Inspector - 3D Inspection Simulation", True, (180, 220, 255))
        self.screen.blit(title, (self.w // 2 - title.get_width() // 2, 10))

        # Help bar
        help_text = "[Space]=Fly [WASD]=Move [M]=Mission [E]=Emerg [R]=Reset [Arrows]=Arm [D]=Demo [C]=Chase [Mouse]=Orbit"
        help_surf = self.font_sm.render(help_text, True, (150, 180, 210))
        pygame.draw.rect(self.screen, (10, 20, 35), (0, self.h - 22, self.w, 22))
        self.screen.blit(help_surf, (self.w // 2 - help_surf.get_width() // 2, self.h - 18))

        # Flight log
        log_y = self.h - 24
        for i, entry in enumerate(reversed(self._flight_log[-5:])):
            txt = self.font_sm.render(entry, True, (100, 200, 150))
            self.screen.blit(txt, (5, log_y - (i + 1) * 14))

        # Demo mode indicator
        if self._demo_mode:
            demo_txt = self.font.render(">>> DEMO MODE - AUTO INSPECTION <<<", True, YELLOW)
            self.screen.blit(demo_txt, (self.w // 2 - demo_txt.get_width() // 2, 30))

        pygame.display.flip()


if __name__ == "__main__":
    sim = Pygame3DSim()
    sim.run()
