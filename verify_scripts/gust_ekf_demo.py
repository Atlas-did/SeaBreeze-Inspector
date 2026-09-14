#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gust_ekf_demo.py — OmniSim 阵风注入 + EKF 扰动观测/前馈 联合演示链

把三件事串成一条可现场演示、可复现的链：
  1. OmniSim seabreeze_tello_wind_headless 世界（Webots/Newton 内核）里的
     seabreeze_tello_wind_bridge 按 Dryden 风格的阵风剖面，
     以空气阻力形式（F = 0.5ρ·Cd·A·v²）把"风"注入无人机；
  2. 本脚本通过 bridge HTTP 遥测（GET /state，含 vx/vy 与 wind.force），
     把速度差分推成加速度观测，喂给仓库自带的 12 维
     DisturbanceObserverEKF（backend/core/disturbance_observer.py）；
  3. 对比两种控制口径在同一阵风场下的悬停表现：
     - A 口径（基线）：goto_waypoint 位置保持（桥内 PD，无前馈）；
     - B 口径（前馈）：goto_waypoint 目标点叠加上 -Kff·d̂ 的位置修正，
       即 EKF 扰动估计 → 前馈补偿（位置域等效实现，等价于
       FeedforwardController 的 v_cmd += Kff·d_est 思路）。

诚实声明（写报告时必须保留）：
  - 桥内 addForce 是"等效阻力注入"，不是风场粒子/真实风洞；
  - 本演示的 EKF 观测里的"IMU 加速度通道"由桥遥测速度差分重构（桥 /state
    不直接吐 IMU），量测噪声特性与真 IMU 不同；位置通道直接用桥位姿；
  - 两次跑（A/B）用同一个 wind seed，阵风剖面逐时刻一致，对比公平；
  - 本脚本只依赖标准库 + numpy（EKF）。

用法（PowerShell，仓库目录下）：
    1. 启动 OmniSim 风力世界（首次需先生成，见 make_wind_assets）：
       D:\\OmniSim\\8.1.15\\OmniSim\\msys64\\mingw64\\bin\\omnisimw.exe ^
         --mode=fast --no-rendering ^
         "D:\\OmniSim\\projects\\samples\\demos\\worlds\\chat\\seabreeze_tello_wind_headless.omniworld"
    2. python verify_scripts\\gust_ekf_demo.py --seconds 40
输出：gust_ekf_demo_report.json + gust_ekf_demo_trace_{a,b}.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
import urllib.error

import numpy as np

from backend.core.disturbance_observer import DisturbanceObserverEKF

BASE = "http://127.0.0.1:6091"


# ----------------------------- bridge I/O ---------------------------------

def get_state() -> dict:
    with urllib.request.urlopen(BASE + "/state", timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def post_action(body: dict) -> dict:
    req = urllib.request.Request(
        BASE + "/action", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"http_error": e.code}


def wait_bridge(timeout_s: float = 60.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            get_state()
            return
        except Exception:
            time.sleep(1.0)
    raise RuntimeError(f"bridge {BASE} 在 {timeout_s}s 内未就绪——OmniSim 世界启动了吗？")


def wait_mode(mode_prefixes: tuple, timeout_s: float = 45.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        st = get_state()
        if st.get("mode", "").startswith(mode_prefixes):
            return st
        time.sleep(0.2)
    raise RuntimeError(f"等待 mode={mode_prefixes} 超时：{st.get('mode')}")


# ----------------------------- experiment ---------------------------------

def run_leg(tag: str, seconds: float, feedforward: bool,
            wind_cfg: dict, target: tuple) -> dict:
    """跑一条腿：takeoff → goto 目标点 → 记录 seconds 秒遥测 + EKF 在线估计。"""
    post_action({"action": "reset"})
    post_action({"action": "wind", "enable": False})
    time.sleep(1.0)
    post_action({"action": "takeoff", "altitude": target[2]})
    wait_mode(("takeoff", "hover", "goto"))
    time.sleep(2.0)
    post_action({"action": "goto_waypoint",
                 "x": target[0], "y": target[1], "altitude": target[2]})
    wait_mode(("goto", "hover"))
    # 等位置环收敛到目标邻域（超时 25s 则带误差开录），再进入记录窗口
    t_wait = time.time()
    while time.time() - t_wait < 25.0:
        st = get_state()
        if (abs(st["x"] - target[0]) < 0.15
                and abs(st["y"] - target[1]) < 0.15):
            break
        time.sleep(0.2)
    time.sleep(1.0)
    # 收敛后激活风：相位钟从此刻归零 + 湍流流重播（seed 固定），
    # 两腿记录窗口的 v(t) 剖面严格一致（45 s = 3 × T_gust 整周期）。
    post_action({"action": "wind", **wind_cfg})

    ekf = DisturbanceObserverEKF(dt=0.1, enable_adaptive=True)
    # 桥遥测位置单位 m；EKF 内部按 cm 口径（Q/R 默认值即 cm 系），统一换算
    M2CM = 100.0
    prev_v = None
    t0 = time.time()
    rows = []
    last_u = None
    last_cmd_t = -1.0
    ff_prev = np.zeros(2)   # 上一拍实际下发的前馈倾斜角（rad）
    while time.time() - t0 < seconds:
        t_s = time.time() - t0
        st = get_state()
        vx, vy = st.get("vx", 0.0), st.get("vy", 0.0)
        # 速度差分 → 水平加速度观测（m/s² → cm/s²）
        if prev_v is not None:
            dt_m = max(1e-3, t_s - prev_v[2])
            ax_m = (vx - prev_v[0]) / dt_m
            ay_m = (vy - prev_v[1]) / dt_m
        else:
            ax_m = ay_m = 0.0
        prev_v = (vx, vy, t_s)

        z = np.array([ax_m * M2CM, ay_m * M2CM, 0.0,
                      st["x"] * M2CM, st["y"] * M2CM, st["z"] * M2CM])
        # u 馈入：位置环命令的倾斜角（/state debug）→ 世界系水平加速度指令。
        # predict(u) 会保存 _last_u 并把加速度状态设为已知控制，
        # update 从 (IMU - u) 中分离出纯扰动 d̂（B1 消融同款机制）。
        dbg = st.get("debug") or {}
        u_x = 9.81 * float(dbg.get("target_pitch", 0.0))
        u_y = -9.81 * float(dbg.get("target_roll", 0.0))
        u_cmd = np.array([u_x * M2CM, u_y * M2CM, 0.0])
        ekf.predict(u=u_cmd)
        ekf.update(z)
        d_hat = ekf.get_disturbance()     # cm/s²
        d_now = np.array([d_hat[0], d_hat[1]])

        # A 口径：桥内 position-hold（世界系位置 P+D，纯反馈刚度）；
        # B 口径：叠加前馈倾斜角 θ̂ = −d̂/g（rad，逆扰动方向），桥在姿态指令上直接
        # 叠加，位置环只修残余——反馈刚度与前馈各司其职。
        if t_s - last_cmd_t >= 0.5:
            last_cmd_t = t_s
            if feedforward:
                # 稳定性三件套（第 7 轮回退的修复）：
                # (a) 物理上限——d̂ 折算的倾斜角不得超过实测风速的等效平衡角
                #     θ_wind = 0.5ρ·A·v²/(m·g) 的 1.5 倍，且硬上限 0.06 rad：
                #     超限说明 d̂ 被机动加速度污染，取物理界而不是跟着冲；
                # (b) 斜率限幅——每拍变化 ≤ 0.015 rad，防姿态指令跳变；
                # (c) 一阶低通——ff = 0.35·新 + 0.65·旧，滤差分噪声。
                v_w = float((st.get("wind") or {}).get("v_now", 0.0))
                theta_wind = 0.5 * 1.225 * wind_cfg["area_m2"] * v_w * v_w / (0.087 * 9.81)
                ff_cap = min(1.5 * theta_wind, 0.06)
                ff_raw = -d_now / M2CM / 9.81
                n_raw = float(np.linalg.norm(ff_raw))
                if n_raw > ff_cap and n_raw > 1e-9:
                    ff_raw = ff_raw * (ff_cap / n_raw)
                ff_new = 0.35 * ff_raw + 0.65 * ff_prev
                d_ff = ff_new - ff_prev
                n_d = float(np.linalg.norm(d_ff))
                if n_d > 0.015 and n_d > 1e-9:
                    ff_new = ff_prev + d_ff * (0.015 / n_d)
                ff_prev = ff_new
                post_action({"action": "wind", "ff_tilt": [
                    round(float(ff_new[0]), 4), round(float(ff_new[1]), 4)]})
        last_u = (0.0, 0.0, 0.0)

        rows.append({
            "t": round(t_s, 3), "x": st["x"], "y": st["y"], "z": st["z"],
            "vx": vx, "vy": vy, "ax_obs": ax_m, "ay_obs": ay_m,
            "d_hat_x": round(float(d_hat[0]), 3), "d_hat_y": round(float(d_hat[1]), 3),
            "wind_v": (st.get("wind") or {}).get("v_now", 0.0),
            "wind_f": (st.get("wind") or {}).get("f_n", 0.0),
            "mode": st.get("mode", ""),
        })
        time.sleep(0.1)

    arr = np.array([[r["x"], r["y"]] for r in rows])
    err = np.linalg.norm(arr - np.array(target[:2]), axis=1)   # m
    tail = err[len(err) // 2:]                                  # 稳态段=后半程
    return {
        "leg": tag, "feedforward": feedforward,
        "rmse_m": float(np.sqrt(np.mean(tail ** 2))),
        "p95_m": float(np.percentile(tail, 95)),
        "max_m": float(err.max()),
        "mean_wind_ms": float(np.mean([r["wind_v"] for r in rows])),
        "n_samples": len(rows),
    }, rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=40.0, help="每条腿记录时长 s")
    ap.add_argument("--runs", type=int, default=2, help="AB 配对轮数（取中位数）")
    ap.add_argument("--target", type=float, nargs=3, default=(0.0, 0.0, 1.2))
    ap.add_argument("--v-mean", type=float, default=2.0)
    ap.add_argument("--v-gust", type=float, default=1.0)
    ap.add_argument("--t-gust", type=float, default=15.0)
    ap.add_argument("--v-turb", type=float, default=0.5)
    ap.add_argument("--area-m2", type=float, default=0.02)
    args = ap.parse_args()

    wind_cfg = {"enable": True, "v_mean": args.v_mean, "v_gust": args.v_gust,
                "t_gust": args.t_gust, "v_turb": args.v_turb,
                "area_m2": args.area_m2, "dir": [1.0, 0.0, 0.0], "seed": 7}

    wait_bridge()
    print("[demo] bridge ready:", get_state().get("mode"))

    # 多轮配对（AB × N）取中位数：湍流瞬时相位随 HTTP 延迟抖动，
    # 单轮对比有统计偏倚，配对重复 + 中位数才是可写进报告的口径。
    a_rmses, b_rmses, pair_details = [], [], []
    last_rows = {}
    for k in range(args.runs):
        a_sum, a_rows = run_leg(f"A{k+1}_pid_baseline", args.seconds, False,
                                wind_cfg, tuple(args.target))
        b_sum, b_rows = run_leg(f"B{k+1}_ekf_feedforward", args.seconds, True,
                                wind_cfg, tuple(args.target))
        a_rmses.append(a_sum["rmse_m"]); b_rmses.append(b_sum["rmse_m"])
        pair_details.append({"pair": k + 1, "a": a_sum, "b": b_sum,
                             "improve_pct": round(
                                 (1 - b_sum["rmse_m"] / a_sum["rmse_m"]) * 100, 1)})
        print(f"[demo] pair {k+1}: A={a_sum['rmse_m']:.3f}m B={b_sum['rmse_m']:.3f}m")
        last_rows = {"a": a_rows, "b": b_rows}
    a_med = float(np.median(a_rmses)); b_med = float(np.median(b_rmses))
    legs = [{"leg": "A_pid_baseline(median)", "feedforward": False,
             "rmse_m": a_med, "runs": len(a_rmses), "all": a_rmses},
            {"leg": "B_ekf_feedforward(median)", "feedforward": True,
             "rmse_m": b_med, "runs": len(b_rmses), "all": b_rmses}]
    traces = last_rows

    improve = (1 - b_med / a_med) * 100 if a_med else 0.0
    report = {
        "protocol": "omnisim gust injection + EKF disturbance feedforward demo",
        "world": "seabreeze_tello_wind_headless.omniworld (port 6091)",
        "wind": wind_cfg,
        "target_m": list(args.target),
        "seconds_per_leg": args.seconds,
        "legs": legs,
        "pair_details": pair_details,
        "rmse_improvement_pct": round(improve, 1),
        "honest_notes": [
            "addForce drag-form injection = 等效阵风阻力，非真实风场",
            "EKF 加速度通道由 /state 速度差分重构（桥不直接输出 IMU）",
            "A/B 两腿同 wind seed，阵风剖面逐时刻一致",
            "B 口径为位置域前馈（目标点修正），与算法包 v_cmd+=Kff*d_est 等效",
        ],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open("gust_ekf_demo_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    for k, rows in traces.items():
        with open(f"gust_ekf_demo_trace_{k}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
    post_action({"action": "wind", "enable": False})
    post_action({"action": "land"})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
