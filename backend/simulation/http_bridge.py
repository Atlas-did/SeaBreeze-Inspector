#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SeaBreeze HTTP Bridge v2 — Python backend driving Three.js frontend

Run:   python backend/simulation/http_bridge.py
Open:  http://localhost:8800
Press: SPACE=takeoff, WASD=move, Arrows=arm, M=mission, R=reset, E=emergency
"""

import http.server
import json
import os
import sys
import threading
import time
import urllib.parse
import numpy as np

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from backend.simulation.models import Quadrotor3D, WindDisturbance, RobotArm3DOF, VirtualSensor
from backend.main import MissionController

# ---- Config ----
HOVER_HEIGHT = 1.2
CRUISE_SPEED = 1.5
VERTICAL_SPEED = 0.8
SIM_DT = 0.02
BATTERY_DRAIN = 0.05
TURBINE_POS = np.array([9.0, 0.0, -2.0])

# ---- Shared state ----
sim_state = {
    "pos": [0, 0, 0], "vel": [0, 0, 0], "state": "IDLE",
    "battery": 100, "wind": [0, 0, 0], "arm_angles": [90, 90, 45],
    "arm_endpoint": [0, 0, 0], "ekf_mahal": 0, "safety_tier": "NOMINAL",
    "detections": [], "fps": 0, "flight_log": [],
}
sim_lock = threading.Lock()
pending_keys = set()
key_lock = threading.Lock()

# ---- Backend objects ----
quad = Quadrotor3D(dt=SIM_DT)  # match sim loop rate
wind_model = WindDisturbance(base_wind=np.array([0.08, 0.03, 0.05]), freq=0.3, gust_amp=0.06)
arm = RobotArm3DOF()
sensor = VirtualSensor()

mc = MissionController(mode="simulation", mock=True)
mc.safety_guard.THRESHOLDS["timeout_land"] = 3600.0
mc.safety_guard.THRESHOLDS["timeout_kill"] = 3600.0

_sim_state = "IDLE"
_target_pos = np.array([0.0, 0.0, 0.0])
_flight_log = []
_mission_timer = 0.0
_last_time = time.time()


def _add_log(event, detail=""):
    _flight_log.append({"t": time.time(), "event": event, "detail": detail})
    if len(_flight_log) > 200:
        _flight_log.pop(0)


def run_simulation():
    global _sim_state, _target_pos, _mission_timer, _last_time
    _last_time = time.time()  # reset on start, not module load
    fps_n, fps_t = 0, time.time()
    _add_log("SIM_INIT", "Bridge started")

    while True:
        t_start = time.time()
        dt_real = t_start - _last_time
        _last_time = t_start
        dt = min(SIM_DT, max(0.001, dt_real))  # cap at SIM_DT to prevent first-frame explosion

        # ---- Drain pending keys ----
        with key_lock:
            keys = pending_keys.copy()
            pending_keys.clear()

        # ---- State machine ----
        if "Space" in keys:
            if _sim_state == "IDLE":
                _sim_state = "TAKING_OFF"
                _target_pos = quad.get_position().copy()
                _target_pos[1] = HOVER_HEIGHT
                _add_log("TAKEOFF", "Target: {}m".format(HOVER_HEIGHT))
            elif _sim_state in ("HOVERING", "NAVIGATE", "INSPECT"):
                _sim_state = "LANDING"
                _target_pos = quad.get_position().copy()
                _target_pos[1] = 0.0
                _add_log("LAND", "Manual land")

        if "KeyR" in keys:
            _sim_state = "IDLE"
            quad.state[:] = 0.0
            quad.set_velocity(np.zeros(3))
            _target_pos = np.array([0.0, 0.0, 0.0])
            arm.set_angles([90, 90, 45])
            _flight_log.clear()
            _add_log("RESET", "Reset")

        if "KeyE" in keys:
            _sim_state = "EMERGENCY"
            _add_log("EMERGENCY", "Manual trigger")

        if "KeyM" in keys and _sim_state == "HOVERING":
            _sim_state = "NAVIGATE"
            _target_pos = TURBINE_POS.copy()
            _target_pos[1] = HOVER_HEIGHT + 3.0
            _mission_timer = 0.0
            _add_log("MISSION", "Navigating")

        # Arm control
        delta = 3.0
        angles = arm.angles.copy()
        if "ArrowLeft" in keys:  angles[0] = (angles[0] - delta) % 180
        if "ArrowRight" in keys: angles[0] = (angles[0] + delta) % 180
        if "ArrowUp" in keys and "ArrowLeft" not in keys and "ArrowRight" not in keys:
            angles[1] = min(150, angles[1] + delta)
        if "ArrowDown" in keys and "ArrowLeft" not in keys and "ArrowRight" not in keys:
            angles[1] = max(30, angles[1] - delta)
        if not np.array_equal(angles, arm.angles):
            arm.set_angles(angles)

        # ---- State logic ----
        pos = quad.get_position()
        vel = quad.get_velocity()

        if _sim_state == "TAKING_OFF":
            if pos[1] >= HOVER_HEIGHT - 0.05:
                _sim_state = "HOVERING"
                quad.set_velocity(np.zeros(3))
                _add_log("HOVERING", "Hover achieved")
            else:
                _target_pos = pos.copy()
                _target_pos[1] = HOVER_HEIGHT

        elif _sim_state == "HOVERING":
            step = CRUISE_SPEED * dt
            if "KeyW" in keys: _target_pos[0] += step
            if "KeyS" in keys: _target_pos[0] -= step
            if "KeyA" in keys: _target_pos[2] -= step
            if "KeyD" in keys: _target_pos[2] += step
            # Clamp height
            if "KeyU" in keys:      # U = up (alternative to PgUp)
                _target_pos[1] += VERTICAL_SPEED * dt
            if "KeyJ" in keys:      # J = down (alternative to PgDn)
                _target_pos[1] -= VERTICAL_SPEED * dt
            _target_pos[1] = max(0.3, min(5.0, _target_pos[1]))

        elif _sim_state == "NAVIGATE":
            _mission_timer += dt
            diff = _target_pos - pos
            dist = float(np.linalg.norm(diff))
            if dist < 0.5:
                _sim_state = "INSPECT"
                _mission_timer = 0.0
                _add_log("INSPECT", "Arrived")
            elif dist > 0:
                _target_pos = pos + (diff / dist) * CRUISE_SPEED * dt * 0.8

        elif _sim_state == "INSPECT":
            _mission_timer += dt
            if _mission_timer > 8.0:
                _sim_state = "RETURNING"
                _target_pos = np.array([0.0, HOVER_HEIGHT, 0.0])
                _add_log("RETURN", "Done")

        elif _sim_state == "RETURNING":
            diff = np.array([0.0, HOVER_HEIGHT, 0.0]) - pos
            dist = float(np.linalg.norm(diff))
            if dist < 0.5:
                _sim_state = "LANDING"
                _target_pos = np.array([0.0, 0.0, 0.0])
                _add_log("LAND", "Home reached")
            elif dist > 0:
                _target_pos = pos + (diff / dist) * CRUISE_SPEED * dt * 0.8

        elif _sim_state == "LANDING":
            if pos[1] <= 0.05:
                _sim_state = "IDLE"
                quad.state[:] = 0.0
                quad.set_velocity(np.zeros(3))
                _target_pos = np.array([0.0, 0.0, 0.0])
                _add_log("IDLE", "Landed")
            else:
                _target_pos = pos.copy()
                _target_pos[1] = max(0.0, pos[1] - VERTICAL_SPEED * dt)

        elif _sim_state == "EMERGENCY":
            _target_pos = pos.copy()
            _target_pos[1] = max(0.0, pos[1] - 3.0 * dt)
            if pos[1] <= 0.02:
                _sim_state = "IDLE"
                quad.state[:] = 0.0
                quad.set_velocity(np.zeros(3))
                _add_log("IDLE", "Emergency done")

        # ---- Physics: PD-like control ----
        if _sim_state != "IDLE":
            v_des = (_target_pos - pos) / 0.3
            a_des = (v_des - vel) / 0.3
            thrust = quad.mass * (a_des[1] + quad.g)
            quad.step(np.array([thrust, 0.0, 0.0, 0.0]))

            # EKF — use correct predict signature
            if _sim_state not in ("EMERGENCY",):
                try:
                    sd = sensor.read_all(quad)
                    mc.ekf.predict(u=np.zeros(3))
                    z = np.array([sd["imu"][0], sd["imu"][1], sd["imu"][2],
                                  sd["optical"][0], sd["optical"][1], sd["barometer"]])
                    mc.ekf.update(z)
                except Exception:
                    pass

        # ---- Battery ----
        bat = float(mc._battery)
        if _sim_state not in ("IDLE", "EMERGENCY"):
            bat = max(0, bat - BATTERY_DRAIN * dt)
            mc._battery = bat

        # ---- Wind ----
        w = wind_model.sample(dt)

        # ---- Mock detections ----
        dist_t = float(np.linalg.norm(np.array([pos[0], 0, pos[2]]) -
                                       np.array([TURBINE_POS[0], 0, TURBINE_POS[2]])))
        dets = []
        if _sim_state in ("INSPECT", "NAVIGATE") and dist_t < 15:
            dets = [{"cls": "crack", "conf": 0.82, "bbox": [100, 30, 50, 25]},
                     {"cls": "corrosion", "conf": 0.71, "bbox": [140, 70, 55, 30]}]
            if dist_t < 6:
                dets.append({"cls": "rust", "conf": 0.65, "bbox": [120, 120, 40, 22]})

        # ---- Endpoint ----
        ep = np.array(arm.get_endpoint()) * 1000  # m -> mm

        # ---- Publish ----
        with sim_lock:
            sim_state["pos"] = pos.tolist()
            sim_state["vel"] = vel.tolist()
            sim_state["state"] = _sim_state
            sim_state["battery"] = round(bat, 1)
            sim_state["wind"] = w.tolist()
            sim_state["arm_angles"] = arm.angles.tolist()
            sim_state["arm_endpoint"] = [round(float(v), 1) for v in ep]
            sim_state["ekf_mahal"] = round(float(mc.ekf.mahalanobis_distance), 1)
            sim_state["safety_tier"] = "EMERGENCY" if _sim_state == "EMERGENCY" else \
                                       "WARN" if bat < 30 else "NOMINAL"
            sim_state["detections"] = dets
            sim_state["flight_log"] = list(_flight_log[-100:])

        # ---- FPS ----
        fps_n += 1
        if time.time() - fps_t >= 0.5:
            with sim_lock:
                sim_state["fps"] = round(fps_n / (time.time() - fps_t))
            fps_n, fps_t = 0, time.time()

        # ---- Sleep ----
        elapsed = time.time() - t_start
        time.sleep(max(0.001, SIM_DT - elapsed))


# ---- HTTP Handler ----
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_STATIC_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "..", "seabreeze-3d-sim"))


class BridgeHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=_STATIC_DIR, **kwargs)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)

        if p.path == "/api/state":
            with sim_lock:
                data = dict(sim_state)
            self._json(data)
            return

        if p.path == "/api/command":
            qs = urllib.parse.parse_qs(p.query)
            key = qs.get("key", [None])[0]
            if key:
                with key_lock:
                    pending_keys.add(key)
                # Handle arm sliders via URL params
                try:
                    a0 = float(qs.get("a0", [90])[0])
                    a1 = float(qs.get("a1", [90])[0])
                    a2 = float(qs.get("a2", [45])[0])
                    arm.set_angles([a0, a1, a2])
                except Exception:
                    pass
            self._json({"ok": True})
            return

        if p.path == "/api/log":
            with sim_lock:
                log = sim_state.get("flight_log", [])
            self._json(log)
            return

        # Static file
        super().do_GET()

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if args and "/api/" in str(args[0]):
            return
        super().log_message(fmt, *args)


def main():
    t = threading.Thread(target=run_simulation, daemon=True, name="sim")
    t.start()
    time.sleep(0.3)

    port = 8800
    srv = http.server.HTTPServer(("0.0.0.0", port), BridgeHandler)
    print("=" * 60)
    print("  SeaBreeze Inspector — HTTP Bridge v2")
    print("  Open: http://localhost:{}".format(port))
    print("  [SPACE] Takeoff [WASD] Move [M] Mission [R] Reset [E] Emergency")
    print("=" * 60)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
        print("\nBridge stopped.")


if __name__ == "__main__":
    main()
