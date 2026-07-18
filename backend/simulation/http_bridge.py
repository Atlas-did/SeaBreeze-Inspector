#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SeaBreeze HTTP Bridge v3 - Thin API shell around SimRuntime.

Run: python backend/simulation/http_bridge.py
Open: http://localhost:8811
"""

import http.server, json, os, sys, threading, time, urllib.parse, traceback
import numpy as np

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from backend.simulation.models import Quadrotor3D, WindDisturbance, RobotArm3DOF, VirtualSensor
from backend.main import MissionController
from backend.runtime.loop import SimRuntime

# ---- Shared state ----
_state = {"pos": [0, 0, 0], "state": "IDLE", "battery": 100, "fps": 0}
_lock = threading.Lock()
_pending_keys = set()
_key_lock = threading.Lock()

# ---- Backend objects ----
quad = Quadrotor3D()
wind = WindDisturbance(base_wind=np.array([0.08, 0.03, 0.05]), freq=0.3, gust_amp=0.06)
arm = RobotArm3DOF()
sensor = VirtualSensor()
mc = MissionController(mode="simulation", mock=True)
runtime = SimRuntime(mc, quad, wind, arm, sensor)


def sim_loop():
    """Background thread: run SimRuntime.step() at 50Hz."""
    global _state
    fps_acc = 0.0
    fps_n = 0

    while True:
        try:
            t0 = time.time()

            with _key_lock:
                keys = _pending_keys.copy()  # read without clearing; keys removed on _UP

            data = runtime.step(0.02, keys)
            # Toggle keys are one-shot: consume after processing
            for k in ("Space", "KeyR", "KeyE", "KeyM"):
                if k in keys:
                    with _key_lock:
                        _pending_keys.discard(k)

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
        except Exception:
            print("[SIM-LOOP CRASH]", flush=True)
            traceback.print_exc()
            time.sleep(0.5)


# ---- HTTP Handler ----
_STATIC_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "seabreeze-3d-sim"))


class BridgeHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files + API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=_STATIC_DIR, **kwargs)

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)

            if parsed.path == "/api/state":
                with _lock:
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
                        if key.endswith("_UP"):
                            _pending_keys.discard(key[:-3])  # remove held key
                        else:
                            _pending_keys.add(key)
                self._json(200, {"ok": True})
                return

            if parsed.path == "/api/log":
                self._json(200, _state.get("flight_log", []))
                return

            super().do_GET()
        except Exception:
            traceback.print_exc()
            try:
                self.send_error(500, "Internal Server Error")
            except Exception:
                pass

    def _json(self, code, data):
        def _convert(obj):
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_convert(v) for v in obj]
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            if isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            if isinstance(obj, np.bool_):
                return bool(obj)
            return obj
        data = _convert(data)
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # suppress all log noise


# ---- Signal the server is ready by printing ----
sim_thread = threading.Thread(target=sim_loop, daemon=True, name="sim")
sim_thread.start()
time.sleep(0.3)

_PORT = 8811
print("", flush=True)
print("=" * 60, flush=True)
print("  SeaBreeze Inspector - HTTP Bridge v3 (SimRuntime)", flush=True)
print(f"  Open: http://localhost:{_PORT}", flush=True)
print("=" * 60, flush=True)
print("  [Space] Takeoff/Land  [WASD] Move  [M] Mission", flush=True)
print("  [E] Emergency  [R] Reset  [Arrows] Arm", flush=True)
print("=" * 60, flush=True)
print("", flush=True)

server = http.server.HTTPServer(("127.0.0.1", _PORT), BridgeHandler)
server.serve_forever()