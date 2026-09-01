#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wind_gust_injector.py — 6 级阵风扰动注入（评分项：抗风 6 级，5 分）

OmniSim（Webots 内核）没有原生风场；本控制器作为独立 Supervisor 节点，
用 addForce 把"风"以空气阻力形式作用到无人机 base_link 上，模拟海面阵风。

蒲福风级换算（取中值）：
    6 级  强风  10.8–13.8 m/s  → 标称 12.3 m/s
    7 级  疾风  13.9–17.1 m/s  → 标称 15.5 m/s
    8 级  大风  17.2–20.7 m/s  → 标称 19.0 m/s

阻力模型：  F_wind = 0.5 · ρ · Cd · A · v² · dir
    ρ = 1.225 kg/m³（海平面空气密度）
    Cd = 1.0（小四旋翼简化）
    A  = 迎风面积 m²（默认 0.05，Tello 级；工业级按实际改）
阵风模型：  v(t) = v_mean + v_gust · sin(2π t / T_gust) + 白噪 ±v_turb

用法（Windows）：
    1. 把本文件放进 OmniSim 的 controllers\\wind_gust_injector\\ 目录
    2. 在 omniworld 文件里加一个 Supervisor 节点（见主清单 §4 示例）
    3. 启动 world，观察 /state 的 z 漂移与姿态角

诚实声明：
    - addForce 是引擎物理力，不是"风场粒子"；结果能证明控制器在持续外力下
      的悬停能力，报告里写"等效 6 级风的阻力注入"，不写成"真实风洞/风场"。
    - force 施加到 base_link 的力点；若有吊挂载荷，可加 offset 参数。
    - 引擎里 addForce 的方向是世界系（relative=False）。
"""
import math
import os
import random
import sys
import time

try:
    from controller import Supervisor, AnsiCodes  # Webots/OmniSim 控制器 API
except ImportError:
    print("!! 无法导入 controller。请把本文件放进 OmniSim controllers 目录运行。")
    sys.exit(1)

# ── 从环境变量读取配置（都有默认值）──────────────────────────────
V_MEAN  = float(os.environ.get("WIND_V_MEAN", 12.3))    # m/s，默认 6 级中值
V_GUST  = float(os.environ.get("WIND_V_GUST", 4.0))     # 阵风振幅 m/s
T_GUST  = float(os.environ.get("WIND_T_GUST", 20.0))    # 阵风周期 s
V_TURB  = float(os.environ.get("WIND_V_TURB", 1.0))     # 湍流 ±m/s
WIND_DIR = os.environ.get("WIND_DIR", "1,0,0")          # 世界系风向单位向量
BASE_DEF = os.environ.get("WIND_BASE_DEF", "tello")     # 受力 base_link 的 DEF
A_M2    = float(os.environ.get("WIND_AREA_M2", 0.05))   # 迎风面积
SAMPLE_HZ = int(os.environ.get("WIND_SAMPLE_HZ", 62))   # 控制步长

def parse_vec(s):
    parts = [float(x) for x in s.replace("(", "").replace(")", "").split(",")]
    n = math.sqrt(sum(p * p for p in parts)) or 1.0
    return [p / n for p in parts]

def force_for_speed(v):
    rho, Cd, A = 1.225, 1.0, A_M2
    return 0.5 * rho * Cd * A * v * v

def main():
    random.seed(int(os.environ.get("WIND_SEED", 1)))     # 可复现
    print(f"[wind] 6 级阵风注入: v_mean={V_MEAN} m/s, 阵风±{V_GUST}@{T_GUST}s, "
          f"湍流±{V_TURB}, 风向[{WIND_DIR}], A={A_M2} m²")
    print(f"[wind] 等效平均阻力 = {force_for_speed(V_MEAN):.3f} N")
    print(f"[wind] 阵风峰值阻力 = {force_for_speed(V_MEAN + V_GUST):.3f} N")

    super = Supervisor()
    robot_node = super.getFromDef(BASE_DEF)
    if robot_node is None:
        print(f"!! 找不到 DEF '{BASE_DEF}'，请核对 world 里的 base_link DEF 名。")
        sys.exit(2)
    print(f"[wind] 已找到节点 {BASE_DEF}，开始每 tick 施加风力。")
    print("[wind] 状态: 运行中。按 Ctrl+C 或关闭 world 停止。")

    step = int(1000.0 / SAMPLE_HZ)  # ms
    dirv = parse_vec(WIND_DIR)
    t = 0.0
    while super.step(step) != -1:
        gust = V_GUST * math.sin(2 * math.pi * t / T_GUST)
        turb = random.uniform(-V_TURB, V_TURB)
        v = max(0.0, V_MEAN + gust + turb)
        f = force_for_speed(v)
        fx, fy, fz = (f * d for d in dirv)
        robot_node.addForce([fx, fy, fz], False)   # 世界系
        t += step / 1000.0

if __name__ == "__main__":
    main()
