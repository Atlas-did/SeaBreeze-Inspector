#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SeaBreeze HTTP Bridge v3 - Thin API shell around SimRuntime.

Phase 3: Deleted private FSM (TAKING_OFF/RETURNING/LANDING/NAVIGATE/INSPECT).
All simulation logic is in runtime.SimRuntime.
This file only: HTTP serving + key forwarding + state serialization.

Run: python backend/simulation/http_bridge.py
Open: http://localhost:8800
"""

import http.server, json, os, sys, threading, time, urllib.parse
import numpy as np

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from backend.simulation.models import Quadrotor3D, WindDisturbance, RobotArm3DOF, VirtualSensor
from backend.main import MissionController
from backend.runtime.loop import SimRuntime

# ---- Shared state ----
_state = {}
_lock = threading.Lock()
_pending_keys = set()
_key_lock = threading.Lock()

# ---- Backend objects ----
quad = Quadrotor3D()
wind = WindDisturbance(base_wind=np.array([0.08, 0.03, 0.05]), freq=0.3, gust_amp=0.06)
arm = RobotArm3DOF()
sensor = VirtualSensor()
mc = MissionController(mode="simulation", mock=True)
# A1 fix: heartbeat is now called every frame, no need for 3600s workaround

runtime = SimRuntime(mc, quad, wind, arm, sensor)


def sim_loop():
    """Background thread: run SimRuntime.step() at 50Hz."""
    global _state
    fps_acc = 0.0
    fps_n = 0

    while True:
        t0 = time.time()

        with _key_lock:
            keys = _pending_keys.copy()
            _pending_keys.clear()

        # Run one frame through SimRuntime
        data = runtime.step(0.02, keys)

        # Track FPS
        fps_acc += time.time() - t0
        fps_n += 1
        if fps_acc >= 0.5:
            data["fps"] = round(fps_n / fps_acc)
            fps_acc = 0.0
            fps_n = 0
        else:
            data["fps"] = 0

        with _lock:
            _state = data

        elapsed = time.time() - t0
        time.sleep(max(0.001, 0.02 - elapsed))


# ---- HTTP Handler ----
_STATIC_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "seabreeze-3d-sim"))


class BridgeHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files + API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=_STATIC_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/state":
            self._json(200, dict(_state))
            return

        if parsed.path == "/api/command":
            params = urllib.parse.parse_qs(parsed.query)
            key = params.get("key", [None])[0]

            if key == "arm":
                try:
                    a0 = float(params.get("a0", [90])[0])
                    a1 = float(params.get("a1", [90])[0])
                    a2 = float(params.get("a2", [45])[0])
                    arm.set_angles([a0, a1, a2])
                except Exception:
                    pass
                self._json(200, {"ok": True})
                return

            if key:
                with _key_lock:
                    _pending_keys.add(key)
            self._json(200, {"ok": True})
            return

        if parsed.path == "/api/log":
            self._json(200, _state.get("flight_log", []))
            return

        super().do_GET()

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        msg = args[0] if args else ""
        if "/api/" in str(msg):
            return
        super().log_message(fmt, *args)


def main():
    sim_thread = threading.Thread(target=sim_loop, daemon=True, name="sim")
    sim_thread.start()
    time.sleep(0.3)

    port = 8800
    server = http.server.HTTPServer(("0.0.0.0", port), BridgeHandler)
    print("")
    print("=" * 60)
    print("  SeaBreeze Inspector - HTTP Bridge v3 (SimRuntime)")
    print("  Open: http://localhost:" + str(port))
    print("=" * 60)
    print("  [Space] Takeoff/Land  [WASD] Move  [M] Mission")
    print("  [E] Emergency  [R] Reset  [Arrows] Arm")
    print("=" * 60)
    print("")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()