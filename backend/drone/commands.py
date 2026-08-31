"""单飞行指令执行层 — FlightCommand / CommandResult / 驱动协议。

把"一条飞行指令"（如：目标高度 1.5 m 悬停）表达成可复现的 FlightCommand，
在 mock / 内置仿真 / OmniSim / 真机 四种后端上执行，并输出统一 JSON 结果。

动机（2026-08-30）：OmniLink 的 OmniSim 公开测试邀请——"在仿真里测一条飞行
指令，不改飞机"。本模块让 SeaBreeze 自己先用可复现口径给出基准数，再拿
OmniSim 的数字做对比；证据等级统一标记为 simulation-only，不冒充实测。

分层约定：
  - 本模块只做 schema 与调度，不 import pygame / 不 import serial。
  - 瞬时指令（takeoff/land/emergency/kill/hover/move_to）面向 DroneInterface。
  - 动态指令（altitude_hold）需要能"设定绝对高度 + 步进到稳态"的驱动，
    见 backend.simulation.altitude_driver（自家仿真）与 backend.omnisim.adapter。
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# 指令与结果 schema
# ---------------------------------------------------------------------------


@dataclass
class FlightCommand:
    """一条可复现的飞行指令。

    op: 操作名。瞬时指令: connect/takeoff/land/emergency/kill/hover/move_to；
        动态指令: altitude_hold。
    params: 参数。单位约定(易混,务必注意):
        - move_to:        {"x","y","z"} 单位均为 **厘米(cm)**,speed 为 cm/s(默认 30)。
                          例: {"x":0,"y":0,"z":100,"speed":30} = 上升 1 m。
        - altitude_hold:  {"target_m"} 单位 **米(m)**。例: {"target_m": 1.5}。
        两者 z 语义差 100 倍,写统一脚本时切勿把 move_to 的 z 当米。
    note: 人可读备注（如天气/风况/实验编号），不参与执行。
    """

    op: str
    params: Dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"op": self.op, "params": self.params, "note": self.note}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FlightCommand":
        return cls(op=d["op"], params=d.get("params", {}), note=d.get("note", ""))


@dataclass
class CommandResult:
    """一次命令执行的统一结果，可直接 json.dumps。

    字段约定（跨后端一致，方便对比）：
      - target_m / measured_m / error_m 以米为单位；error = target - measured。
      - settled: 是否按设定时长完成了稳态观测。
      - state: 后端报告的任务状态（HOVERING 等），仅作参考。
      - accepted: 指令是否被后端接受。
    """

    op: str
    backend: str  # "mock" | "sim" | "omnisim" | "tello"
    accepted: bool
    target_m: Optional[float] = None
    measured_m: Optional[float] = None
    error_m: Optional[float] = None
    steady_std_m: Optional[float] = None
    settled: bool = False
    state: str = ""
    sim_seconds: float = 0.0
    seed: int = 0
    note: str = ""
    ts: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    extra: Dict[str, Any] = field(default_factory=dict)
    # F08: 证据等级,默认 simulation-only;真机首飞时显式传 "real-flight",
    # 避免真实数据被静默降格为仿真数据(to_dict 不再写死)。
    evidence_level: str = "simulation-only"

    def to_dict(self) -> Dict[str, Any]:
        """JSON 可序列化;证据等级由 evidence_level 字段决定(默认 simulation-only)。"""
        return {
            **asdict(self),
            "source": "SeaBreeze-Inspector",
        }


# ---------------------------------------------------------------------------
# 动态指令驱动协议
# ---------------------------------------------------------------------------


@runtime_checkable
class AltitudeHoldDriver(Protocol):
    """能执行 altitude_hold 的后端驱动。

    set_target_altitude: 设定绝对目标高度（米）。
    settle: 在设定的动力学步长下运行 seconds 秒，返回稳态统计。
    """

    def backend_name(self) -> str:
        ...

    def set_target_altitude(self, meters: float) -> bool:
        ...

    def settle(self, seconds: float, dt: float = 0.02) -> Dict[str, Any]:
        ...


# ---------------------------------------------------------------------------
# 瞬时指令执行（面向 DroneInterface）
# ---------------------------------------------------------------------------

INSTANT_OPS = {"connect", "takeoff", "land", "emergency", "kill", "hover", "move_to"}


def _read_state(drone: Any) -> Dict[str, Any]:
    """尽量读取后端状态；拿不到关键字段时给最小兜底，不让指令执行失败。"""
    getter = getattr(drone, "get_state_dict", None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            pass
    state: Dict[str, Any] = {}
    if hasattr(drone, "is_flying"):
        state["is_flying"] = bool(drone.is_flying)
    h = getattr(drone, "get_height", None)
    if callable(h):
        state["height"] = int(h())
    return state


def execute_instant(drone: Any, cmd: FlightCommand) -> CommandResult:
    """对任意 DroneInterface（真机/SimDroneAdapter/MockTello）执行一次性指令。

    不进行动力学 settle——真实 Tello 的指令是异步的，这里只报告
    "是否接受 + 立即状态"。需要稳态指标请用 altitude_hold 动态指令。
    """
    if cmd.op not in INSTANT_OPS:
        raise ValueError(f"不支持的瞬时指令 op={cmd.op!r}；可用的动态指令是 altitude_hold")

    fn = getattr(drone, cmd.op, None)
    if not callable(fn):
        raise AttributeError(f"{type(drone).__name__} 没有 {cmd.op}() 方法")

    if cmd.op == "move_to":
        p = cmd.params
        accepted = bool(fn(float(p.get("x", 0.0)), float(p.get("y", 0.0)),
                           float(p.get("z", 0.0)), int(p.get("speed", 30))))
    else:
        accepted = bool(fn())

    st = _read_state(drone)
    return CommandResult(
        op=cmd.op,
        backend=getattr(drone, "backend_name", lambda: type(drone).__name__)(),
        accepted=accepted,
        state=str(st.get("state", st.get("is_flying", ""))),
        note=cmd.note,
        extra={"post_state": st},
    )


# ---------------------------------------------------------------------------
# altitude_hold 通用运行器
# ---------------------------------------------------------------------------


def run_altitude_hold(
    driver: AltitudeHoldDriver,
    target_m: float,
    settle_s: float = 40.0,
    dt: float = 0.02,
    seed: int = 42,
    note: str = "",
) -> CommandResult:
    """在任意 AltitudeHoldDriver 上执行"目标高度保持"并输出统一结果。

    测量口径与 OmniSim 公共测试一致：
      设定目标高度 → 步进 settle_s 秒 → 稳态取最后 5 秒均值 → 误差 = 目标 - 稳态。
    """
    import numpy as np

    np.random.seed(seed)  # 保证可复现（文档约定：整次实验用同一种子）
    accepted = driver.set_target_altitude(float(target_m))
    # F01 修复: 指令被拒(如 bridge 409 busy)时不照常 settle,否则会产出
    # "accepted=False 与 settled=True 并存"的误导性证据(实测的其实是地面高度)。
    if not accepted:
        return CommandResult(
            op="altitude_hold",
            backend=driver.backend_name(),
            accepted=False,
            target_m=float(target_m),
            settled=False,
            sim_seconds=float(settle_s),
            seed=seed,
            note=note,
            extra={"reason": "set_target_altitude rejected (e.g. bridge busy)"},
        )
    stats = driver.settle(seconds=settle_s, dt=dt)

    measured = stats.get("altitude_m")
    return CommandResult(
        op="altitude_hold",
        backend=driver.backend_name(),
        accepted=accepted,
        target_m=float(target_m),
        measured_m=float(measured) if measured is not None else None,
        error_m=(float(target_m) - float(measured)) if measured is not None else None,
        steady_std_m=stats.get("std_m"),
        settled=True,
        state=str(stats.get("state", "")),
        sim_seconds=float(settle_s),
        seed=seed,
        note=note,
        extra={"final_m": stats.get("final_m"), "n_steps": stats.get("n_steps")},
    )
