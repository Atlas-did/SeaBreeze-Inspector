#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_hover_3d.py — 悬停定位精度测量（评分项：≤±5cm，10 分）

用法（Windows，PowerShell，在 SeaBreeze 仓库目录下）：
    venv\\Scripts\\python.exe verify_scripts\\measure_hover_3d.py ^
        --target-x 0 --target-y 0 --target-z 1.5 ^
        --seconds 30 --out hover_result

过程：
    1. 连接 Tello bridge（默认 http://127.0.0.1:6090）
    2. takeoff → goto 目标点 → 等待模式进入 hover
    3. 记录 --seconds 秒的三维位置（每 100ms 一次）
    4. 输出 hover_result_summary.json + hover_result_trace.csv

诚实原则：
    - /state 里有哪些坐标维就用哪些；取不到的维标注"未测量"。
    - 若 bridge 的 HTTP 命令路由与本脚本候选不同，会打印探测结果并提示改哪里。
    - 本脚本只依赖标准库（urllib/json/time/csv），无需额外安装。
"""
import argparse
import csv
import json
import time
import urllib.request
import urllib.error

def probe(base, paths):
    """依次尝试候选路由，返回第一个 200/JSON 的响应体字典。"""
    for p in paths:
        try:
            with urllib.request.urlopen(base + p, timeout=3) as r:
                raw = r.read().decode("utf-8", errors="replace")
                try:
                    return json.loads(raw)
                except Exception:
                    return {"_raw": raw[:400]}
        except Exception:
            continue
    return None

def http_json(url, payload=None):
    """GET 或 POST，返回 (status, body_dict)。payload=None 时 GET。"""
    req = urllib.request.Request(url)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=5) as r:
            raw = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, {"_raw": raw[:400]}
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return -1, {}

ACTION_CONTRACTS = (
    # SeaBreeze tello bridge and OmniSim's official OmniLink bridges all use
    # POST /action with an "action" key — try it first.
    ("/action", "action"),
    # generic bridge shapes, kept as fallbacks
    ("/command", "command"),
    ("/cmd", "command"),
    ("/api/command", "command"),
)


def send_cmd(base, name, params=None, dry=False):
    """发命令：按已知契约逐个尝试（优先 POST /action {"action": ...}）。"""
    for p, key in ACTION_CONTRACTS:
        body = {key: name}
        if params:
            body.update(params)
        st, resp = http_json(base + p, body)
        if st in (200, 202):
            return True, resp
        if st != -1 and st < 500:  # 有明确非成功应答，说明路由存在
            pass
    if dry:
        return True, {"_dry": "路由未探测，用 --dry 只测状态"}
    return False, {"_err": "候选命令路由均失败，请检查 bridge 路由"}

def extract_pos(state):
    """从 /state 中尽力提取 (x, y, z)。返回 (values, present_mask, avail_keys)。"""
    avail = {k: v for k, v in state.items()
             if k.lower() in ("x", "y", "z", "position", "pos", "local_position",
                              "px", "py", "pz", "altitude", "height", "z_est",
                              "x_est", "y_est")}
    vals = {}
    for key, v in state.items():
        k = key.lower()
        if k == "position" and isinstance(v, (list, tuple)) and len(v) >= 3:
            vals["x"], vals["y"], vals["z"] = float(v[0]), float(v[1]), float(v[2])
        elif k in ("x", "px", "x_est"):
            vals["x"] = float(v)
        elif k in ("y", "py", "y_est"):
            vals["y"] = float(v)
        elif k in ("z", "pz", "altitude", "height", "z_est"):
            vals["z"] = float(v)
    present = {ax: (ax in vals) for ax in ("x", "y", "z")}
    return vals, present, sorted(avail.keys())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:6090")
    ap.add_argument("--target-x", type=float, default=0.0)
    ap.add_argument("--target-y", type=float, default=0.0)
    ap.add_argument("--target-z", type=float, default=1.5)
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--settle", type=float, default=5.0, help="进入 hover 后再等的稳定时间")
    ap.add_argument("--out", default="hover_result")
    ap.add_argument("--dry", action="store_true",
                    help="不发命令，只探测 /state 结构与候选路由")
    args = ap.parse_args()

    print(f"[1/5] 连接 bridge: {args.base}")
    state = probe(args.base, ("/state", "/status", "/"))
    if state is None:
        print("!! 无法获取 /state。请确认 OmniSim world 已启动、bridge 已起服（6090）。")
        return 2
    print(f"    /state 可用键({len(state)}): {sorted(state.keys())[:30]}")
    vals, present, avail_keys = extract_pos(state)
    print(f"    可提取坐标维: {present}  候选键: {avail_keys}")
    if not any(present.values()):
        print("!! /state 中没有可识别的坐标维（x/y/z/position/altitude 等）。")
        print("   本脚本无法测量悬停精度——请把 bridge /state 里的位置字段名发给我，我改 extract_pos()。")
        return 3

    if args.dry:
        print("[dry] 仅探测完成，未发命令。正式跑请去掉 --dry。")
        return 0

    print("[2/5] takeoff")
    ok, resp = send_cmd(args.base, "takeoff", {"altitude": args.target_z})
    if not ok:
        print(f"!! takeoff 失败: {resp}（用 --dry 先探测路由）")
        return 4
    time.sleep(3.0)

    print(f"[3/5] goto ({args.target_x},{args.target_y},{args.target_z})")
    ok, _ = send_cmd(args.base, "goto_waypoint",
                     {"x": args.target_x, "y": args.target_y,
                      "altitude": args.target_z})
    if not ok:
        print("!! goto 路由失败，脚本跳过 goto 直接在当前点悬停测量。")

    # 收敛门：等所有可测轴距目标 ≤0.05 m 且连续 3 次满足（≈1s 内保持）再开始
    # 采样——既排除 goto 转场，也排除爬升瞬态（实测：仅"一次 ≤0.08"的松门
    # 会把 ±10cm 爬升瞬态放进行窗，把 max_abs_err 抬到 0.10 m）。超时则如实
    # 标注后仍采样。
    tgt_map = {"x": args.target_x, "y": args.target_y, "z": args.target_z}
    gate_t0, gate_timeout = time.time(), max(args.settle, 30.0)
    gate_tol = 0.05
    converged, streak = False, 0
    while time.time() - gate_t0 < gate_timeout:
        st, s = http_json(args.base + "/state")
        if st == 200 and s:
            v, _, _ = extract_pos(s)
            axes = [ax for ax in ("x", "y", "z") if present.get(ax)]
            if axes and all(abs(v.get(ax, 1e9) - tgt_map[ax]) <= gate_tol
                            for ax in axes):
                streak += 1
                if streak >= 3:
                    converged = True
                    break
            else:
                streak = 0
        time.sleep(0.3)
    print(f"    收敛={'是' if converged else '否(超时)'}"
          f"（门限 {gate_tol} m 连续 3 次,用时 {round(time.time() - gate_t0, 1)}s）")
    time.sleep(3.0 if converged else args.settle)

    print(f"[4/5] 记录 {args.seconds}s（每 100ms）…")
    rows, t0 = [], time.time()
    while time.time() - t0 < args.seconds:
        st, state_now = http_json(args.base + "/state")
        if st == 200 and state_now:
            v, _, _ = extract_pos(state_now)
            row = {"t_abs": round(time.time() - t0, 3)}
            for ax in ("x", "y", "z"):
                row[ax] = v.get(ax) if present.get(ax) else None
            rows.append(row)
        time.sleep(0.1)

    # 统计：只统计 present 的维；缺的维如实标注未测量
    print("[5/5] 统计并写文件")
    summary = {
        "protocol": "hover precision measurement",
        "base": args.base,
        "target": {"x": args.target_x, "y": args.target_y, "z": args.target_z},
        "samples": len(rows),
        "duration_s": args.seconds,
        "axes_measured": present,
        "per_axis": {},
        "note": "未测到的维 = /state 无该坐标源，未测量",
    }
    trace = [dict(r) for r in rows]
    for ax in ("x", "y", "z"):
        tgt = {"x": args.target_x, "y": args.target_y, "z": args.target_z}[ax]
        if not present[ax]:
            summary["per_axis"][ax] = {"measured": False}
            continue
        errs = [abs(r[ax] - tgt) for r in rows if r[ax] is not None]
        if not errs:
            summary["per_axis"][ax] = {"measured": False, "reason": "无有效样本"}
            continue
        import statistics
        summary["per_axis"][ax] = {
            "measured": True,
            "mean_abs_err_m": round(statistics.mean(errs), 4),
            "max_abs_err_m": round(max(errs), 4),
            "rms_err_m": round((sum(e * e for e in errs) / len(errs)) ** 0.5, 4),
            "target_m": tgt,
        }
    # 三维合成误差（仅当 x/y/z 都测到时）
    if all(present.values()):
        errs3d = [
            ((r["x"] - args.target_x) ** 2 + (r["y"] - args.target_y) ** 2
             + (r["z"] - args.target_z) ** 2) ** 0.5
            for r in rows
        ]
        summary["euclidean_3d_rms_m"] = round(
            (sum(e * e for e in errs3d) / len(errs3d)) ** 0.5, 4)
        summary["euclidean_3d_max_m"] = round(max(errs3d), 4)
        print(f"    三维 RMS = {summary['euclidean_3d_rms_m']} m, "
              f"max = {summary['euclidean_3d_max_m']} m")
    for ax in ("x", "y", "z"):
        s = summary["per_axis"][ax]
        print(f"    {ax}: " + ("未测量" if not s.get("measured")
                               else f"mean|err|={s['mean_abs_err_m']}m "
                                    f"max={s['max_abs_err_m']}m "
                                    f"RMS={s['rms_err_m']}m"))

    with open(args.out + "_summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    with open(args.out + "_trace.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["t_abs", "x", "y", "z"])
        w.writeheader()
        w.writerows(trace)
    print(f"    输出: {args.out}_summary.json / {args.out}_trace.csv")
    print("\n→ 填进报告草稿 5.2：mean_abs_err 与 max_abs_err（逐轴），对照目标 ≤±5cm。")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
