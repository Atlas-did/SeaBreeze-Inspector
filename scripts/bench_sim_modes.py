#!/usr/bin/env python3
"""速度模式专项基准（审计 Phase 3）。

在**同一套协议**下比较两条执行路径:
  * ``legacy``   —— 默认位置级联（``velocity_command_mode=False``，论文已发表数字所用路径）
  * ``velocity`` —— 速度指令模式（``velocity_command_mode=True``，与真机 RC 同源）

协议（版本化，任何改动都应提升 PROTOCOL_VERSION）:
  P1 HOVER_HOLD   起飞到 100cm 后保持
  P2 WAYPOINT     从悬停点飞向前方 100cm 的航点并稳定
  P3 RETURN_HOME  返回起飞点上方并稳定
每种工况各跑 calm(0 m/s) 与 windy(2 m/s) 两种风况。

输出: ``docs/bench/velocity_mode_bench.json`` + 控制台对比表。

**诚实声明**：两种模式是**不同的实验协议**，指标用于对比与回归（"换链路后差多少"），
**不能当作真机性能证明**。真机性能必须靠拆桨桌面测试 / 系留低空 / SITL 得到
（见 docs/HIL_PROTOCOL.md，目前尚未执行）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402

from backend.main import MissionController  # noqa: E402
from backend.runtime.loop import SimRuntime  # noqa: E402
from backend.simulation.models import (  # noqa: E402
    Quadrotor3D,
    RobotArm3DOF,
    VirtualSensor,
    WindDisturbance,
)
from backend.utils.units import m_to_cm  # noqa: E402

DT = 0.02                 # 50Hz，与 SimRuntime 的 sim_dt 一致
PROTOCOL_VERSION = 1
HOVER_TARGET_CM = 100.0
WAYPOINT_CM = (0.0, 100.0)     # 前向 100cm（y 正 = 前）
REACH_RADIUS_CM = 30.0
P1_SETTLE_FRAMES = 250     # 5s 稳定段(不计入 P1 指标, 去掉爬升瞬态)
P1_FRAMES = 1000          # 20s
P2_FRAMES = 750           # 15s
P3_FRAMES = 750           # 15s
SEED = 0


def _silence_logger(mc):
    """短路日志落盘：基准只测物理与指令链路，不碰磁盘。"""
    mc.logger.start_session = lambda *a, **k: None
    mc.logger.log_frame = lambda *a, **k: None


def _make_runtime(mode: str, wind_speed: float):
    mc = MissionController(mode="simulation", mock=True)
    _silence_logger(mc)
    if wind_speed > 0:
        wind = WindDisturbance(base_wind=np.array([wind_speed, 0.0, 0.0]),
                               freq=0.5, gust_amp=0.3)
    else:
        wind = WindDisturbance(base_wind=np.zeros(3), freq=0.0, gust_amp=0.0)
    sensor = VirtualSensor(imu_noise=0.0, opt_noise=0.0, bar_noise=0.0,
                           bias_drift_rate=0.0, rw_std=0.0)
    rt = SimRuntime(mc, Quadrotor3D(), wind, RobotArm3DOF(), sensor,
                    velocity_command_mode=(mode == "velocity"))
    return mc, rt


def _hover(rt, limit=600):
    rt.step(DT, {"Space"})
    for i in range(limit):
        data = rt.step(DT, set())
        if data["state"] == "HOVERING":
            return i
    raise AssertionError("未进入 HOVERING（state=%s）" % data["state"])


def _pos_cm(data):
    """step() 返回的 pos 是**米**(quad.get_position()); 基准统一用厘米比较。"""
    return np.asarray(m_to_cm(np.asarray(data["pos"], dtype=float)), dtype=float)


def _hold(rt, frames, target_xy, target_z, settle=0):
    """步进并采集指标; settle 帧只步进不计入指标(去掉爬升瞬态)。

    target_z 必须传**实际悬停高度**(起飞后从 mc.target_pos 读), 不能硬编码 ——
    配置里的默认悬停高度会变, 硬编码会量出一个假的"稳态误差"。
    """
    alt_errs, xy_errs = [], []
    for i in range(frames):
        data = rt.step(DT, set())
        if i < settle:
            continue
        pos = _pos_cm(data)
        alt_errs.append(abs(pos[2] - target_z))
        xy_errs.append(float(np.linalg.norm(pos[:2] - np.asarray(target_xy))))
    return {
        "alt_err_mean_cm": float(np.mean(alt_errs)),
        "alt_err_max_cm": float(np.max(alt_errs)),
        "xy_err_mean_cm": float(np.mean(xy_errs)),
        "xy_err_max_cm": float(np.max(xy_errs)),
        "final_xy_err_cm": float(xy_errs[-1]),
        "final_alt_err_cm": float(alt_errs[-1]),
    }


def _reach(rt, target_xy, frames):
    """飞向航点，返回到达帧数与稳定段误差。"""
    reach_frame = None
    errs = []
    for i in range(frames):
        data = rt.step(DT, set())
        pos = _pos_cm(data)
        err = float(np.linalg.norm(pos[:2] - np.asarray(target_xy)))
        errs.append(err)
        if reach_frame is None and err <= REACH_RADIUS_CM:
            reach_frame = i
    tail = errs[len(errs) // 2:]
    return {
        "reach_frames": reach_frame,
        "reach_time_s": (reach_frame * DT) if reach_frame is not None else None,
        "ss_err_mean_cm": float(np.mean(tail)),
        "ss_err_max_cm": float(np.max(tail)),
        "min_err_cm": float(np.min(errs)),
    }


def run_case(mode: str, wind_speed: float) -> dict:
    mc, rt = _make_runtime(mode, wind_speed)
    hover_frames = _hover(rt)
    # 实际悬停高度由配置/起飞流程决定, 必须读出来而不是硬编码
    hover_z = float(mc.target_pos[2])

    # P1: 悬停保持（先稳定 settle 帧, 再测稳态误差, 去掉爬升瞬态）
    p1 = _hold(rt, P1_SETTLE_FRAMES + P1_FRAMES, (0.0, 0.0), hover_z,
               settle=P1_SETTLE_FRAMES)

    # P2: 飞向前方航点（高度沿用实际悬停高度）
    mc.set_target(WAYPOINT_CM[0], WAYPOINT_CM[1], hover_z)
    p2 = _reach(rt, WAYPOINT_CM, P2_FRAMES)

    # P3: 返回起飞点
    mc.set_target(0.0, 0.0, hover_z)
    p3 = _reach(rt, (0.0, 0.0), P3_FRAMES)

    return {
        "mode": mode,
        "wind_mps": wind_speed,
        "hover_frames": hover_frames,
        "hover_target_cm_actual": hover_z,
        "P1_hover_hold": p1,
        "P2_waypoint": p2,
        "P3_return_home": p3,
    }


def _fmt(v, unit=""):
    if v is None:
        return "  n/a"
    return "{:7.2f}{}".format(v, unit)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="速度模式专项基准")
    ap.add_argument("--out", default="docs/bench/velocity_mode_bench.json")
    ap.add_argument("--quick", action="store_true", help="只跑 calm（快速自检）")
    args = ap.parse_args(argv)

    cases = []
    for mode in ("legacy", "velocity"):
        for wind in ((0.0,) if args.quick else (0.0, 2.0)):
            cases.append(run_case(mode, wind))

    print("=" * 78)
    print("  速度模式专项基准 (protocol v{})  DT={}s  航点前向={}cm  到达半径={}cm"
          .format(PROTOCOL_VERSION, DT, WAYPOINT_CM[1], REACH_RADIUS_CM))
    print("  悬停高度由配置决定, 实际值见下表 hover_target 列(不要硬编码)")
    print("  注意: legacy 与 velocity 是**不同实验协议**, 指标仅用于对比/回归")
    print("=" * 78)
    header = "{:<9} {:<6} {:>9} {:>10} {:>10} {:>10} {:>10}".format(
        "mode", "wind", "P1 altErr", "P1 xyMax", "P2 reach", "P2 ssErr", "P3 ssErr")
    print(header)
    print("-" * 78)
    for c in cases:
        print("{:<9} {:<6} {:>9} {:>10} {:>10} {:>10} {:>10}".format(
            c["mode"], c["wind_mps"],
            _fmt(c["P1_hover_hold"]["alt_err_mean_cm"]),
            _fmt(c["P1_hover_hold"]["xy_err_max_cm"]),
            ("{:7.2f}s".format(c["P2_waypoint"]["reach_time_s"])
             if c["P2_waypoint"]["reach_time_s"] is not None else "    n/a"),
            _fmt(c["P2_waypoint"]["ss_err_mean_cm"]),
            _fmt(c["P3_return_home"]["ss_err_mean_cm"]),
        ))
    print("=" * 78)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "dt_s": DT,
        "hover_target_note": ("每个用例的 hover_target_cm_actual 是起飞后读到的真实悬停高度; "
                              "HOVER_TARGET_CM 只是参考常量, 不参与指标计算"),
        "hover_target_cm_reference": HOVER_TARGET_CM,
        "waypoint_cm": list(WAYPOINT_CM),
        "reach_radius_cm": REACH_RADIUS_CM,
        "frames": {"P1": P1_FRAMES, "P2": P2_FRAMES, "P3": P3_FRAMES},
        "seed": SEED,
        "cases": cases,
        "honesty_note": ("legacy 与 velocity 是不同实验协议; 指标用于对比与回归, "
                         "不能当作真机性能证明(真机需拆桨/系留/SITL, 见 docs/HIL_PROTOCOL.md)"),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[OK] 结果已写入 {}".format(out.as_posix()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
