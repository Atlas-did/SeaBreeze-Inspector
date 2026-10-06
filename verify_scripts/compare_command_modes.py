#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compare_command_modes.py — P1-12 对照实验：两种物理驱动模式各出一组数。

背景（2026-10-06 评审 P1-12）: `SimRuntime(velocity_command_mode=...)` 默认 False，
即"演示路径 ≠ 真机链路"。评审建议二选一：翻默认值，或跑一组对照实验并写进 README。
本仓库选择后者 —— 因为 loop.py 明确警告翻默认值会改变全部已发表数值。

两种模式:
  A. cascade（默认, velocity_command_mode=False）
     物理由 SimRuntime 自己的级联环读 mc.target_pos 驱动。
  B. velocity（velocity_command_mode=True）
     物理由控制器输出 → adapter.set_velocity → 机体速度环驱动（真机同源链路）。

用法:
    venv\\Scripts\\python.exe verify_scripts\\compare_command_modes.py
输出: command_mode_comparison.json（仓库根目录）
"""
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import MissionController            # noqa: E402
from backend.runtime.loop import SimRuntime           # noqa: E402
from backend.simulation.models import (               # noqa: E402
    Quadrotor3D, RobotArm3DOF, VirtualSensor, WindDisturbance,
)

DT = 0.02
WIND = np.array([0.05, 0.04, 0.0])
GUST = 0.02
SEED = 11


def run(mode: str):
    np.random.seed(SEED)
    quad = Quadrotor3D()
    wind = WindDisturbance(base_wind=WIND, freq=0.3, gust_amp=GUST)
    arm = RobotArm3DOF()
    sensor = VirtualSensor()
    mc = MissionController(mode="simulation", mock=True)
    rt = SimRuntime(mc, quad, wind, arm, sensor,
                    velocity_command_mode=(mode == "velocity"))
    mc.video_stream.stop()
    mc.video_stream._running = False

    speeds = []
    for i in range(500):                 # 起飞 + 悬停
        rt.step(DT, {"Space"} if i == 50 else set())
        speeds.append(float(np.linalg.norm(quad.get_velocity())))

    tgt = np.array(mc.target_pos) / 100.0
    xy, z = [], []
    for _ in range(300):                 # 稳态窗口
        rt.step(DT, set())
        p = quad.get_position()
        xy.append(float(np.linalg.norm(p[:2] - tgt[:2])))
        z.append(float(abs(p[2] - tgt[2])))
        speeds.append(float(np.linalg.norm(quad.get_velocity())))

    return {
        "mode": mode,
        "state": mc.state,
        "final_pos_m": [round(float(v), 4) for v in quad.get_position()],
        "hover_xy_err_mean_m": round(float(np.mean(xy)), 5),
        "hover_z_err_mean_m": round(float(np.mean(z)), 5),
        "max_speed_mps": round(float(np.max(speeds)), 4),
    }


def main():
    a = run("cascade")
    b = run("velocity")
    out = {
        "protocol": "P1-12 command-mode comparison (simulation-only)",
        "note": ("两种模式驱动方式不同，数值不可混用；cascade 为默认且已发表数字来自该路径。"
                 "本对照只用于诚实披露差异，不改变默认值。"),
        "wind": {"base_wind": WIND.tolist(), "gust_amp": GUST},
        "seed": SEED,
        "cascade_default": a,
        "velocity_command": b,
    }
    p = PROJECT_ROOT / "command_mode_comparison.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in (a, b):
        print("%-16s state=%-9s hover_xy=%.5f m  hover_z=%.5f m  max_v=%.3f m/s"
              % (r["mode"], r["state"], r["hover_xy_err_mean_m"],
                 r["hover_z_err_mean_m"], r["max_speed_mps"]))
    print("[OK] ->", p.name)


if __name__ == "__main__":
    main()
