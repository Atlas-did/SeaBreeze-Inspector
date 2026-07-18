#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SeaBreeze HTTP Bridge - Python backend drives Three.js frontend
Run: python backend/simulation/http_bridge.py
Then open: http://localhost:8800
"""
import http.server
import json
import os
import sys
import threading
import time
import urllib.parse
import numpy as np

# Ensure project root is on path
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from backend.simulation.models import Quadrotor3D, WindDisturbance, RobotArm3DOF, VirtualSensor
from backend.main import MissionController
from backend.utils.units import m_to_cm, cm_to_m, mps_to_cmps, cmps_to_mps

# ---- Config ----
HOVER_HEIGHT = 1.2
SIM_DT = 0.02
STATE_UPDATE_HZ = 20

# ---- Simulation State (shared between threads) ----
sim_state = {
    "pos": [0.0, 0.0, 0.0],
    "vel": [0.0, 0.0, 0.0],
    "state": "IDLE",
    "battery": 100,
    "wind": [0.0, 0.0, 0.0],
    "arm_angles": [90.0, 90.0, 45.0],
    "arm_endpoint": [0.0, 0.0, 0.0],
    "ekf_mahal": 0.0,
    "safety_tier": "NOMINAL",
    "detections": [],
    "fps": 0,
    "flight_log": [],
}
sim_lock = threading.Lock()
pending_keys = set()
key_lock = threading.Lock()

# ---- Backend objects ----
quad = Quadrotor3D()
wind = WindDisturbance(
    base_wind=np.array([0.05, 0.02, 0.0]),
    freq=0.5, gust_amp=0.03
)
arm = RobotArm3DOF()
sensor = VirtualSensor()
mc = MissionController(mode="simulation", mock=True)
mc.safety_guard.THRESHOLDS["timeout_land"] = 3600.0
mc.safety_guard.THRESHOLDS["timeout_kill"] = 3600.0

_target = np.array([3.0, HOVER_HEIGHT, 15.0])
_last_ctrl = np.zeros(3)
_log = []

def run_simulation():
    """Background thread: physics + EKF + controller loop"""
    global _target, _last_ctrl, sim_state
    fps_acc = 0.0
    fps_n = 0
    log_timer = 0.0

    while True:
        t0 = time.time()

        # Process pending keys
        with key_lock:
            keys = pending_keys.copy()
            pending_keys.clear()

        state_str = str(mc.state)

        # Key handling
        if "Space" in keys:
            if state_str == "IDLE" or state_str == "MissionState.IDLE":
                mc.takeoff(height=HOVER_HEIGHT * 100)
                quad.state[2] = HOVER_HEIGHT
                quad.set_velocity(np.zeros(3))
                _target = quad.get_position().copy()
                _log.append({"t": time.time(), "event": "TAKEOFF", "detail": "Hover at %.1fm" % HOVER_HEIGHT})
            else:
                mc.request_state("LAND", "manual")
                _target[1] = 0.0
                _log.append({"t": time.time(), "event": "LAND"})

        if "KeyR" in keys:
            mc.request_state("IDLE", "reset")
            quad.state[:] = 0.0
            quad.set_velocity(np.zeros(3))
            quad.state[2] = 0.0
            _target = np.array([3.0, HOVER_HEIGHT, 15.0])
            arm.set_angles([90.0, 90.0, 45.0])
            mc.ekf.reset()
            _log.clear()
            _log.append({"t": time.time(), "event": "RESET"})

        if "KeyE" in keys:
            mc.request_state("EMERGENCY", "manual")
            _log.append({"t": time.time(), "event": "EMERGENCY"})

        if "KeyM" in keys and state_str in ("HOVERING",):
            mc.request_state("NAVIGATE", "mission")
            _target = np.array([3.0, HOVER_HEIGHT, 15.0])
            _log.append({"t": time.time(), "event": "MISSION_START", "detail": "Inspecting turbine"})

        # WASD control (only in HOVERING)
        if state_str == "HOVERING":
            step = 0.03
            if "KeyW" in keys: _target[0] += step
            if "KeyS" in keys: _target[0] -= step
            if "KeyA" in keys: _target[2] += step
            if "KeyD" in keys: _target[2] -= step

        # Arrow keys for arm
        delta = 3
        angles = arm.angles.copy()
        if "ArrowLeft" in keys: angles[0] = (angles[0] - delta) % 180
        if "ArrowRight" in keys: angles[0] = (angles[0] + delta) % 180
        if "ArrowUp" in keys: angles[1] = min(150, angles[1] + delta)
        if "ArrowDown" in keys: angles[1] = max(30, angles[1] - delta)
        if not np.array_equal(angles, arm.angles):
            arm.set_angles(angles)

        # Physics
        wind_vec = wind.sample(SIM_DT)
        if state_str not in ("IDLE", "EMERGENCY", "MissionState.IDLE"):
            v_des = _last_ctrl
            v_cur = quad.get_velocity()
            a_des = (v_des - v_cur) / 0.3
            thrust = quad.mass * (a_des[1] + quad.g)
            quad.step(np.array([thrust, 0.0, 0.0, 0.0]), disturbance=wind_vec)

        # EKF + Controller
        if state_str not in ("IDLE", "EMERGENCY", "MissionState.IDLE"):
            sensor_data = sensor.read_all(quad)
            z = np.array([sensor_data["imu"][0], sensor_data["imu"][1], sensor_data["imu"][2],
                          sensor_data["optical"][0], sensor_data["optical"][1], sensor_data["barometer"]])
            pos = quad.get_position()
            vel = quad.get_velocity()
            att = quad.get_attitude()
            ctrl_cmps, state_dict = mc.update_with_external_data(
                z, m_to_cm(pos), mps_to_cmps(vel), att
            )
            _last_ctrl = cmps_to_mps(ctrl_cmps)
            quad.set_velocity(_last_ctrl)

        # Battery
        mc._battery -= SIM_DT * (1.5 if state_str == "HOVERING" else 0.1)
        mc._battery = max(0, mc._battery)

        # Emergency check
        if mc._battery < 20 and state_str not in ("EMERGENCY", "IDLE"):
            mc.request_state("EMERGENCY", "low_battery")
            _log.append({"t": time.time(), "event": "LOW_BATTERY", "detail": "%.0f%%" % mc._battery})

        # Update shared state
        pos = quad.get_position()
        vel = quad.get_velocity()
        ep = arm.get_endpoint()

        with sim_lock:
            sim_state["pos"] = pos.tolist()
            sim_state["vel"] = vel.tolist()
            sim_state["state"] = str(mc.state).replace("MissionState.", "")
            sim_state["battery"] = float(mc._battery)
            sim_state["wind"] = wind_vec.tolist()
            sim_state["arm_angles"] = arm.angles.tolist()
            sim_state["arm_endpoint"] = (np.array(ep) * 1000).tolist()  # m -> mm
            sim_state["ekf_mahal"] = float(mc.ekf.mahalanobis_distance)
            sim_state["safety_tier"] = (
                "EMERGENCY" if mc._emergency_reason else
                "WARN" if mc._battery < 30 else "NOMINAL"
            )
            sim_state["flight_log"] = list(_log[-100:])

        # FPS
        fps_acc += time.time() - t0
        fps_n += 1
        if fps_acc >= 0.5:
            with sim_lock:
                sim_state["fps"] = round(fps_n / fps_acc)
            fps_acc = 0.0
            fps_n = 0

        # Sleep to maintain rate
        elapsed = time.time() - t0
        sleep_time = max(0, SIM_DT - elapsed)
        time.sleep(sleep_time)


class BridgeHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files + API endpoints"""

    def __init__(self, *args, **kwargs):
        # Serve from seabreeze-3d-sim directory
        self.directory = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                      "seabreeze-3d-sim")
        super().__init__(*args, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/state":
            # Return simulation state as JSON
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            with sim_lock:
                data = dict(sim_state)
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if parsed.path == "/api/command":
            # Handle keyboard command
            params = urllib.parse.parse_qs(parsed.query)
            key = params.get("key", [None])[0]

            # Arm angle preset from sliders
            if key == "arm":
                try:
                    a0 = float(params.get("a0", [90])[0])
                    a1 = float(params.get("a1", [90])[0])
                    a2 = float(params.get("a2", [45])[0])
                    arm.set_angles([a0, a1, a2])
                except Exception:
                    pass
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
                return
            if key:
                with key_lock:
                    pending_keys.add(key)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
            return

        if parsed.path == "/api/log":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with sim_lock:
                log_data = sim_state.get("flight_log", [])
            self.wfile.write(json.dumps(log_data).encode("utf-8"))
            return

        # Serve static files
        super().do_GET()

    def log_message(self, format, *args):
        # Suppress default logging noise
        if "/api/" in str(args[0]) or "200" in str(args[0]):
            return
        super().log_message(format, *args)


def main():
    # Start simulation thread
    sim_thread = threading.Thread(target=run_simulation, daemon=True)
    sim_thread.start()
    time.sleep(0.5)  # Let simulation init

    # Start HTTP server
    port = 8800
    server = http.server.HTTPServer(("0.0.0.0", port), BridgeHandler)
    print(f"\n{'='*60}")
    print(f"  SeaBreeze Inspector - HTTP Bridge")
    print(f"  Backend: MissionController + EKF + SafetyGuard")
    print(f"  Frontend: Three.js 3D Visualization")
    print(f"  Open: http://localhost:{port}")
    print(f"{'='*60}\n")
    print(f"  [Space]=Takeoff/Land  [WASD]=Move  [M]=Mission")
    print(f"  [E]=Emergency  [R]=Reset  [Arrows]=Arm")
    print(f"  Flight log: http://localhost:{port}/api/log\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
