"""OmniSim 驱动 — AltitudeHoldDriver 的 OmniSim 实现（Stage 3：真实 HTTP）。

把 OmniSim 的 mavic_omnilink_bridge 落成 commands.AltitudeHoldDriver：
  set_target_altitude(meters) → POST /action {"action":"takeoff","altitude":m,"wait":true}
  settle(seconds, dt)         → 每 dt 秒轮询 GET /state 的 z，返回稳态高度统计。

测量口径与自家仿真一致：稳态取最后 5 秒高度均值。
诚实声明：z 一律来自 bridge 的实测遥测；若 bridge 报 fault 或未到达，
绝不拿目标值冒充测量，而是显式抛错（见 commands.CommandResult 约定）。

未配置 OMNISIM_BASE_URL 时抛 OmniSimNotConfigured，提示先启动 Mavic bridge。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional
from statistics import mean, pstdev


class OmniSimNotConfigured(RuntimeError):
    """未配置 OMNISIM_BASE_URL 时抛出，提示先启动 Mavic bridge。"""


class OmniSimBridgeError(RuntimeError):
    """bridge 拒绝、超时或不可达时抛出，携带可读信息与 HTTP 状态码。"""

    def __init__(self, message: str, status: Optional[int] = None,
                 body: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status = status
        self.body = body or {}


class OmniSimDriver:
    """实现 AltitudeHoldDriver 协议（协议见 backend.drone.commands）。"""

    def __init__(self, base_url: Optional[str] = None, timeout_s: float = 90.0):
        self._base_url = (base_url or os.environ.get("OMNISIM_BASE_URL", "")).rstrip("/")
        self._timeout = timeout_s

    def backend_name(self) -> str:
        return "omnisim"

    # ------------------------------------------------------------------
    # AltitudeHoldDriver 协议
    # ------------------------------------------------------------------

    def set_target_altitude(self, meters: float) -> bool:
        """向 Mavic bridge 下发"爬升/保持到目标高度"，等待到达。

        用 takeoff（会在当前 x/y 垂直爬升到目标高度）而不是 goto_waypoint：
        高度保持实验只关心 z，不改变水平位置。

        返回 True = bridge 接受并已到达目标高度；409 busy = 被拒绝（返回 False）；
        到达超时 / fault / 不可达 → 抛 OmniSimBridgeError。
        """
        self._require_ready()
        payload = {
            "action": "takeoff",
            "altitude": float(meters),
            "wait": True,
            "timeout_s": 60.0,
        }
        try:
            body = self._post("/action", payload)
        except OmniSimBridgeError as exc:
            if exc.status == 409:
                return False
            raise

        fault = body.get("fault")
        if fault:
            # 有 fault 且未完成(done 缺省/False)→ 502；有 fault 但已 done → 不标状态码
            status = 502 if not body.get("done", False) else None
            raise OmniSimBridgeError(
                f"Mavic bridge 报告 fault={fault!r}，未到达目标高度 {meters}m。",
                status=status,
                body=body,
            )
        return True

    def settle(self, seconds: float, dt: float = 0.02) -> Dict[str, Any]:
        """按 dt 间隔轮询 bridge 遥测 seconds 秒，返回稳态高度统计。

        与自家仿真口径一致：最后 5 秒高度均值 = altitude_m。
        mode 取最后一次轮询的 bridge 模式（hover/takeoff/goto/...）供参考。
        """
        self._require_ready()
        n = max(1, int(seconds / dt))
        poll_dt = max(dt, 0.01)
        z_trace: list[float] = []
        modes: list[str] = []

        for _ in range(n):
            st = self._get_state()
            z_trace.append(float(st.get("z", 0.0)))
            modes.append(str(st.get("mode", "")))
            time.sleep(poll_dt)

        tail = z_trace[-max(1, int(5.0 / poll_dt)):]
        return {
            "altitude_m": float(mean(tail)),
            "std_m": float(pstdev(tail)) if len(tail) > 1 else 0.0,
            "final_m": float(z_trace[-1]),
            "state": modes[-1] if modes else "",
            "n_steps": n,
        }

    # ------------------------------------------------------------------
    # HTTP 传输层
    # ------------------------------------------------------------------

    def _get_state(self) -> Dict[str, Any]:
        return self._request("GET", "/state")

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self._perform(req)

    def _request(self, method: str, path: str) -> Dict[str, Any]:
        req = urllib.request.Request(self._base_url + path, method=method)
        return self._perform(req)

    def _perform(self, req: urllib.request.Request) -> Dict[str, Any]:
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8"))
            except Exception:
                body = {}
            msg = body.get("message") or body.get("error") or exc.reason
            raise OmniSimBridgeError(
                f"Mavic bridge {req.full_url} 返回 {exc.code}: {msg}",
                status=exc.code,
                body=body,
            ) from exc
        except urllib.error.URLError as exc:
            raise OmniSimBridgeError(
                f"无法连接 Mavic bridge {self._base_url}: {exc.reason}"
            ) from exc
        except (OSError, ValueError) as exc:
            raise OmniSimBridgeError(
                f"与 Mavic bridge {self._base_url} 通信失败: {exc}"
            ) from exc

    def _require_ready(self) -> None:
        if not self._base_url:
            raise OmniSimNotConfigured(
                "未配置 OMNISIM_BASE_URL。请先在 Windows 上启动 Mavic 仿真：\n"
                "  D:\\OmniSim\\launch.bat D:\\OmniSim\\projects\\samples\\demos\\worlds\\chat\\omnilink_mavic.omniworld\n"
                "确认 mavic_omnilink_bridge 在 127.0.0.1:6090 起服务后，再设置\n"
                "  $env:OMNISIM_BASE_URL='http://127.0.0.1:6090'"
            )
