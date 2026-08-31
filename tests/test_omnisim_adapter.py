#!/usr/bin/env python3
"""OmniSim 驱动测试 — 未配置防御 + 假 bridge 的 HTTP 集成行为。

Stage 3 之后 OmniSimDriver 走真实 HTTP：
  - 未配置 OMNISIM_BASE_URL → OmniSimNotConfigured（明确提示）
  - 配置后 → 对"假 Mavic bridge"做集成测试（takeoff / settle / 409 busy / fault）
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from backend.drone.commands import run_altitude_hold
from backend.omnisim.adapter import (
    OmniSimBridgeError,
    OmniSimDriver,
    OmniSimNotConfigured,
)


class FakeMavicBridge:
    """最小 Mavic bridge 桩：/action takeoff + /state。

    takeoff 立即把 z 设为目标高度（模拟爬升完成），mode=hover。
    /state 返回实测 z 与 mode，模拟遥测。
    """

    def __init__(self, z: float = 0.0, mode: str = "landed"):
        self.lock = threading.Lock()
        self.z = z
        self.mode = mode
        self.actions = []
        self.fault_next = None
        self._httpd = None
        self._thread = None

    def __enter__(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                with bridge.lock:
                    body = json.dumps({"z": bridge.z, "mode": bridge.mode}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                if payload.get("action") != "takeoff":
                    body = json.dumps({"status": "ok"}).encode()
                    self.send_response(200)
                elif bridge.fault_next:
                    bridge.fault_next = None
                    body = json.dumps({"status": "ok", "fault": "turbulence",
                                       "done": False}).encode()
                    self.send_response(200)
                else:
                    with bridge.lock:
                        bridge.actions.append(payload)
                        bridge.z = float(payload.get("altitude", bridge.z))
                        bridge.mode = "hover"
                    body = json.dumps({"status": "ok", "target_altitude": bridge.z,
                                       "fault": None, "done": True}).encode()
                    self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._thread.join(timeout=5)

    @property
    def base_url(self):
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}"


def test_omnisim_driver_unconfigured_raises_clear_error(monkeypatch):
    monkeypatch.delenv("OMNISIM_BASE_URL", raising=False)
    driver = OmniSimDriver()
    with pytest.raises(OmniSimNotConfigured) as exc:
        run_altitude_hold(driver, target_m=1.5, settle_s=5.0)
    msg = str(exc.value)
    assert "OMNISIM_BASE_URL" in msg
    assert "launch.bat" in msg


def test_omnisim_driver_altitude_hold_against_fake_bridge():
    with FakeMavicBridge() as bridge:
        driver = OmniSimDriver(base_url=bridge.base_url)
        r = run_altitude_hold(driver, target_m=1.5, settle_s=1.0, dt=0.05)
    assert r.backend == "omnisim"
    assert r.accepted is True
    assert r.target_m == 1.5
    assert r.measured_m is not None
    assert abs(r.measured_m - 1.5) < 1e-6
    assert r.error_m is not None and abs(r.error_m) < 1e-6
    assert r.state == "hover"
    assert bridge.actions and bridge.actions[-1]["action"] == "takeoff"


def test_omnisim_driver_set_target_returns_false_on_busy(monkeypatch):
    def _raise_busy(*a, **k):
        raise OmniSimBridgeError("busy", status=409, body={"error": "busy"})
    driver = OmniSimDriver(base_url="http://127.0.0.1:1")
    monkeypatch.setattr(driver, "_post", _raise_busy)
    assert driver.set_target_altitude(1.5) is False


def test_omnisim_driver_set_target_raises_on_fault():
    with FakeMavicBridge() as bridge:
        bridge.fault_next = True
        driver = OmniSimDriver(base_url=bridge.base_url)
        with pytest.raises(OmniSimBridgeError):
            driver.set_target_altitude(1.5)


def test_omnisim_driver_set_target_raises_on_unreachable():
    driver = OmniSimDriver(base_url="http://127.0.0.1:1")
    with pytest.raises(OmniSimBridgeError):
        driver.set_target_altitude(1.5)


def test_omnisim_backend_name():
    driver = OmniSimDriver(base_url="http://example.test")
    assert driver.backend_name() == "omnisim"


def test_settle_raises_when_z_never_present(monkeypatch):
    """F04: z 全程缺失时 settle 抛 OmniSimBridgeError,而非静默产出 z≈0 的伪稳态。

    直接 monkeypatch _get_state 返回无 z 键的遥测,并把 time.sleep 替换成 no-op,
    避免真实等待。
    """
    driver = OmniSimDriver(base_url="http://127.0.0.1:1")
    calls = {"n": 0}
    def fake_state():
        calls["n"] += 1
        return {"mode": "hover"}  # 无 "z" 键
    monkeypatch.setattr(driver, "_get_state", fake_state)
    monkeypatch.setattr("backend.omnisim.adapter.time.sleep", lambda _s: None)
    import pytest as _pytest
    from backend.omnisim.adapter import OmniSimBridgeError
    with _pytest.raises(OmniSimBridgeError) as exc:
        driver.settle(seconds=1.0, dt=0.2)
    assert "z" in str(exc.value) or "高度" in str(exc.value)
    assert calls["n"] >= 1


def test_settle_skips_missing_z_not_pollutes_mean(monkeypatch):
    """F04: 部分样本缺 z 时跳过,不把 0.0 混进均值。"""
    driver = OmniSimDriver(base_url="http://127.0.0.1:1")
    seq = iter([
        {"mode": "hover", "z": 1.0},
        {"mode": "hover"},                 # 缺 z,应跳过
        {"mode": "hover", "z": 3.0},
        {"mode": "hover"},                 # 缺 z,应跳过
    ])
    monkeypatch.setattr(driver, "_get_state", lambda: next(seq))
    monkeypatch.setattr("backend.omnisim.adapter.time.sleep", lambda _s: None)
    # dt=0.5, seconds=2.0 -> n=4 (2.0/0.5 整除,避免浮点截断)
    out = driver.settle(seconds=2.0, dt=0.5)
    # 只有 1.0 和 3.0 参与均值 -> 2.0;若把缺 z 当 0 则会偏到 1.0
    assert abs(out["altitude_m"] - 2.0) < 1e-9
