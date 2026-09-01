#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_latency.py — 系统闭环时延测量（评分项：≤100ms，5 分）

用法（Windows，PowerShell）：
    venv\\Scripts\\python.exe verify_scripts\\measure_latency.py --n 50 --out latency_result

测量两个口径（报告里都写清楚，别混）：
  T1 命令往返  = HTTP 命令发出 → 收到应答   （反映命令通道时延）
  T2 闭环生效  = HTTP 命令发出 → /state 观察到该命令生效（如 z 开始变化 / 模式翻转）
  "系统闭环时延" 报告取 T2 的口径更接近真实闭环；T1 单独列出作参考。

真实声明：
    - 这是"命令→状态"往返时延，不含视觉推理（检测 fps 由 bench_detection_fps.py 单独测）。
    - 仿真中数字不代表真机；报告里写明"OmniSim 仿真口径，真机待实测"。
依赖：仅标准库。
"""
import argparse
import csv
import json
import time
import urllib.request
import urllib.error

def http_json(url, payload=None):
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:6090")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--out", default="latency_result")
    args = ap.parse_args()

    # 探测 state 里可观测的"生效证据"字段：z 变化、mode、或任意数值字段
    print(f"[1/3] 探测 /state 找生效证据字段")
    st, body = http_json(args.base + "/state")
    if st != 200:
        print(f"!! /state 不可用: status={st}。确认 bridge 已起服。")
        return 2
    keys = sorted(body.keys()) if isinstance(body, dict) else []
    print(f"    /state keys: {keys[:30]}")
    # 生效证据：优先 z/altitude（命令后高度会变），否则取任意一个数值字段做差分
    evid_key = next((k for k in ("z", "altitude", "height") if k in body), None)
    num_keys = [k for k in keys if isinstance(body.get(k), (int, float))]
    if evid_key is None and num_keys:
        evid_key = num_keys[0]
    if evid_key is None:
        print("!! /state 无任何数值字段，无法判生效。报告 T1（往返）即可。")
        evid_key = None

    print(f"[2/3] 测量 {args.n} 轮（每轮发一次高度微调命令）")
    t1s, t2s = [], []
    # 用 z 微调作为命令：目标 = 当前 + 小步长，命令往返后回读生效。
    # 高度微调走 OmniLink 动作契约 POST /action {"action":"takeoff",...}——
    # SeaBreeze tello bridge 与官方桥都认；/command 仅作 fallback。
    def nudge_alt(z):
        st, _ = http_json(args.base + "/action",
                          {"action": "takeoff", "altitude": round(z, 3)})
        if st in (200, 202):
            return True
        st, _ = http_json(args.base + "/command",
                          {"command": "set_alt", "z": round(z, 3)})
        return st in (200, 202)

    def get_z():
        _, b = http_json(args.base + "/state")
        if evid_key and evid_key in b:
            try:
                return float(b[evid_key])
            except Exception:
                pass
        return None

    for i in range(args.n):
        z0 = get_z()
        if z0 is None:
            # 没有 z 就不发变化命令，只测往返（用真实 GET /state 往返计 T1——
            # 对着不存在的 /command POST 出来的 404 往返不是有效口径）
            t0 = time.perf_counter()
            http_json(args.base + "/state")
            t1s.append((time.perf_counter() - t0) * 1000)
            continue
        t0 = time.perf_counter()
        st = nudge_alt(round(z0 + 0.02, 3))
        t1s.append((time.perf_counter() - t0) * 1000)
        if not st:
            print(f"  轮 {i}: 命令未受理（契约不匹配）——T2 本轮不计")
            time.sleep(0.3)
            continue
        # 轮询直到 z 变化（生效）
        t_start = time.perf_counter()
        detected = False
        while time.perf_counter() - t_start < 2.0:
            z1 = get_z()
            if z1 is not None and abs(z1 - z0) > 1e-4:
                detected = True
                break
            time.sleep(0.02)
        if detected:
            t2s.append((time.perf_counter() - t0) * 1000)
        else:
            print(f"  轮 {i}: 未观察到 z 变化（可能命令名不对或已到限位）——T2 本轮跳过")
        time.sleep(0.3)

    print("[3/3] 统计并写文件")
    import statistics
    summary = {
        "protocol": "closed-loop latency (OmniSim sim, 命令→状态生效口径 T2; 往返口径 T1)",
        "n_rounds": args.n,
        "t1_command_roundtrip_ms": {"n": len(t1s),
                                     "mean_ms": round(statistics.mean(t1s), 2) if t1s else None,
                                     "max_ms": round(max(t1s), 2) if t1s else None,
                                     "p95_ms": round(sorted(t1s)[int(len(t1s) * 0.95) - 1], 2) if t1s else None},
        "t2_closed_loop_ms": {"n": len(t2s),
                               "mean_ms": round(statistics.mean(t2s), 2) if t2s else None,
                               "max_ms": round(max(t2s), 2) if t2s else None,
                               "p95_ms": round(sorted(t2s)[int(len(t2s) * 0.95) - 1], 2) if t2s else None},
        "evidence_key": evid_key,
        "target_ms": 100.0,
        "caveat": "仿真口径，真机待实测；不含视觉推理时延",
    }
    print(f"  T1 往返: mean={summary['t1_command_roundtrip_ms']['mean_ms']}ms "
          f"p95={summary['t1_command_roundtrip_ms']['p95_ms']}ms")
    print(f"  T2 闭环: mean={summary['t2_closed_loop_ms']['mean_ms']}ms "
          f"p95={summary['t2_closed_loop_ms']['p95_ms']}ms")

    with open(args.out + "_summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    with open(args.out + "_trace.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["round", "t1_ms", "t2_ms"])
        for i, (a, b) in enumerate(zip(t1s, t2s + [None] * (len(t1s) - len(t2s)))):
            w.writerow([i, round(a, 2), round(b, 2) if b else ""])
    print(f"  输出: {args.out}_summary.json / {args.out}_trace.csv")
    print("\n→ 填进报告草稿 5.2：T2（闭环生效）对照 ≤100ms。")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
