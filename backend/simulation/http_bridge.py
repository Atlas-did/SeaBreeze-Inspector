#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SeaBreeze HTTP Bridge v3 - Thin API shell around SimRuntime.

Run: python backend/simulation/http_bridge.py
Open: http://localhost:8811

N5 修复: 所有模块级单例 (quad/mc/runtime/recorder/sim_thread/server) 移入 main()。
         模块导入不再有副作用 (不创建文件、不启动线程、不连串口)。
N7 修复: sim_loop 不再吞掉 KeyboardInterrupt/SystemExit。
"""

import http.server
import json
import os
import sys
import threading
import time
import urllib.parse
import traceback
import logging
import atexit
from logging.handlers import RotatingFileHandler

import numpy as np

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from backend.simulation.models import Quadrotor3D, WindDisturbance, RobotArm3DOF, VirtualSensor
from backend.main import MissionController
from backend.runtime.loop import SimRuntime

# ---- 日志配置 (模块级, 无副作用: 仅配置 logger, 不创建文件) ----
_LOG_DIR = os.path.join(_PROJ_ROOT, "logs")
os.makedirs(_LOG_DIR, exist_ok=True)  # 确保目录存在 (幂等, 不创建文件)

logger = logging.getLogger("seabreeze.bridge")
logger.setLevel(logging.INFO)
_fh = RotatingFileHandler(os.path.join(_LOG_DIR, "sim_bridge.log"),
                          maxBytes=1 << 20, backupCount=3, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_fh)
logger.addHandler(logging.StreamHandler(sys.stdout))

# ---- 常量 (模块级, 无副作用) ----
KEY_TTL = 0.6  # 秒; 前端按住期间约每 80ms 刷新一次
_STATIC_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "seabreeze-3d-sim"))


class FlightRecorder:
    """黑盒飞行记录器: 每 100ms 落一行 CSV, 供事后 pandas 分析."""

    COLUMNS = "t,state,x,y,z,vx,vy,vz,battery,ekf_mahal\n"

    def __init__(self, log_dir, interval=0.1):
        self._interval = interval
        self._last = 0.0
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "flight_" + time.strftime("%Y%m%d_%H%M%S") + ".csv")
        self._f = open(path, "w", encoding="utf-8")
        self._f.write(self.COLUMNS)
        self._f.flush()
        logger.info("FlightRecorder -> %s", path)

    def record(self, data):
        now = time.time()
        if now - self._last < self._interval:
            return
        self._last = now
        p = data.get("pos", [0, 0, 0])
        v = data.get("vel", [0, 0, 0])
        row = "{:.2f},{},{:.3f},{:.3f},{:.3f},{:.3f},{:.3f},{:.3f},{:.1f},{:.2f}\n".format(
            now, data.get("state", "?"), p[0], p[1], p[2],
            v[0], v[1], v[2], data.get("battery", 0), data.get("ekf_mahal", 0))
        try:
            self._f.write(row)
            self._f.flush()
        except Exception:
            pass

    def close(self):
        """N6 修复: 显式关闭文件, 注册到 atexit."""
        if self._f:
            try:
                self._f.flush()
                self._f.close()
            except Exception:
                pass
            self._f = None


class BridgeContext:
    """所有共享状态 — 替代模块级全局变量.

    在 main() 中创建, 传递给 BridgeServer 和 sim_loop.
    导入本模块不会创建任何实例。
    """

    def __init__(self):
        self.state = {"pos": [0, 0, 0], "state": "IDLE", "battery": 100, "fps": 0}
        self.lock = threading.Lock()
        self.pending_keys = {}
        self.key_lock = threading.Lock()
        self.recorder = None      # FlightRecorder, 在 main() 中创建
        self.runtime = None       # SimRuntime, 在 main() 中创建
        self.arm = None           # RobotArm3DOF, 在 main() 中创建


class BridgeServer(http.server.HTTPServer):
    """携带 BridgeContext 的 HTTP server."""

    def __init__(self, addr, handler_cls, ctx):
        super().__init__(addr, handler_cls)
        self.ctx = ctx


class BridgeHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files + API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=_STATIC_DIR, **kwargs)

    @property
    def ctx(self):
        return self.server.ctx

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)

            if parsed.path == "/api/state":
                with self.ctx.lock:
                    self._json(200, dict(self.ctx.state))
                return

            if parsed.path == "/api/command":
                params = urllib.parse.parse_qs(parsed.query)
                key = params.get("key", [None])[0]
                if key == "arm":
                    try:
                        a0 = float(params.get("a0", [90])[0])
                        a1 = float(params.get("a1", [90])[0])
                        a2 = float(params.get("a2", [45])[0])
                        self.ctx.arm.set_angles([a0, a1, a2])
                    except Exception:
                        pass
                    self._json(200, {"ok": True})
                    return
                if key:
                    with self.ctx.key_lock:
                        if key.endswith("_UP"):
                            self.ctx.pending_keys.pop(key[:-3], None)
                        else:
                            self.ctx.pending_keys[key] = time.time()
                self._json(200, {"ok": True})
                return

            if parsed.path == "/api/log":
                self._json(200, self.ctx.state.get("flight_log", []))
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


def sim_loop(ctx):
    """Background thread: run SimRuntime.step() at ~50Hz with real dt.

    N7 修复: KeyboardInterrupt/SystemExit 重抛, 不吞掉致命异常。
    """
    fps_acc = 0.0
    fps_n = 0
    last_t = time.time()
    last_log_n = len(ctx.runtime._flight_log)

    while True:
        try:
            t0 = time.time()
            dt = min(0.05, t0 - last_t)
            last_t = t0

            now = time.time()
            with ctx.key_lock:
                # TTL 过滤: 超过 KEY_TTL 未刷新的按键自动释放
                keys = {k for k, ts in ctx.pending_keys.items() if now - ts < KEY_TTL}
                expired = [k for k, ts in ctx.pending_keys.items() if now - ts >= KEY_TTL]
                for k in expired:
                    del ctx.pending_keys[k]
                    logger.info("key expired (TTL): %s", k)

            data = ctx.runtime.step(dt, keys)
            # Toggle keys are one-shot: consume after processing
            for k in ("Space", "KeyR", "KeyE", "KeyM"):
                if k in keys:
                    with ctx.key_lock:
                        ctx.pending_keys.pop(k, None)

            # 事件层日志: 把 runtime flight_log 的新条目落盘
            fl = ctx.runtime._flight_log
            if len(fl) != last_log_n:
                for entry in fl[last_log_n:]:
                    logger.info("%s | %s", entry["event"], entry["detail"])
                last_log_n = len(fl)

            # 黑盒层: CSV 记录
            ctx.recorder.record(data)

            fps_acc += time.time() - t0
            fps_n += 1
            if fps_acc >= 0.5:
                data["fps"] = round(fps_n / fps_acc)
                fps_acc = 0.0
                fps_n = 0
            else:
                data["fps"] = 0

            with ctx.lock:
                ctx.state = data

            elapsed = time.time() - t0
            time.sleep(max(0.001, 0.02 - elapsed))
        except (KeyboardInterrupt, SystemExit):
            logger.info("sim_loop received exit signal, stopping.")
            raise
        except Exception:
            logger.exception("[SIM-LOOP CRASH]")
            time.sleep(0.5)


def main():
    """入口: 创建所有对象, 启动 sim 线程, serve HTTP.

    N5 修复: 所有实例化移到此函数, 模块导入零副作用。
    """
    os.makedirs(_LOG_DIR, exist_ok=True)

    ctx = BridgeContext()
    ctx.recorder = FlightRecorder(_LOG_DIR)
    atexit.register(ctx.recorder.close)

    quad = Quadrotor3D()
    wind = WindDisturbance(base_wind=np.array([0.08, 0.03, 0.05]), freq=0.3, gust_amp=0.06)
    ctx.arm = RobotArm3DOF()
    sensor = VirtualSensor()
    mc = MissionController(mode="simulation", mock=True)
    ctx.runtime = SimRuntime(mc, quad, wind, ctx.arm, sensor)

    sim_thread = threading.Thread(target=sim_loop, args=(ctx,), daemon=True, name="sim")
    sim_thread.start()
    time.sleep(0.3)

    _PORT = 8811
    print("", flush=True)
    print("=" * 60, flush=True)
    print("  SeaBreeze Inspector - HTTP Bridge v3 (SimRuntime)", flush=True)
    print("  Open: http://localhost:{}".format(_PORT), flush=True)
    print("=" * 60, flush=True)
    print("  [Space] Takeoff/Land  [WASD] Move  [PgUp/PgDn] Up/Down", flush=True)
    print("  [M] Mission  [E] Emergency  [R] Reset  [Arrows] Arm", flush=True)
    print("  Logs: {}  (sim_bridge.log + flight_*.csv)".format(_LOG_DIR), flush=True)
    print("=" * 60, flush=True)
    print("", flush=True)

    server = BridgeServer(("127.0.0.1", _PORT), BridgeHandler, ctx)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[BRIDGE] Shutting down...")
    finally:
        ctx.recorder.close()


if __name__ == "__main__":
    main()
