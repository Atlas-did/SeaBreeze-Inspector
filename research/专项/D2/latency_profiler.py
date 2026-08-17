#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D2-01 端到端时延分解插桩(本地;t0-t3 逐段,monotonic 时钟,P50/P95/P99)
链路: 采集(t0)→预处理→感知推理→决策→执行(t3)。逐段插桩 + 同基准时钟。
"""
import time
import numpy as np
import argparse


def measure_once(percep_fn=None, pre_fn=None):
    """返回 {sensor, pre, percep, decis, act, total} 各段 ns。真实测需在实机插桩。"""
    t0 = time.perf_counter_ns()
    # 模拟采集(曝光+读出+传输)——实机用硬件时间戳
    sensor = np.random.default_rng().normal(15e6, 3e6)  # ~15ms 模拟
    t1 = t0 + int(sensor)
    # 预处理
    pre = int(np.random.default_rng().normal(2e6, 0.5e6))
    t2 = t1 + pre
    # 感知推理(实机测真实前向)
    percep = int(np.random.default_rng().normal(30e6, 5e6))
    t3 = t2 + percep
    # 决策
    decis = int(np.random.default_rng().normal(1e6, 0.2e6))
    t4 = t3 + decis
    # 执行(通信+PWM+机械)——实机用 C1 台架测
    act = int(np.random.default_rng().normal(25e6, 5e6))
    t5 = t4 + act
    return {'sensor': sensor, 'pre': pre, 'percep': percep, 'decis': decis,
            'act': act, 'total': t5 - t0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=1000)
    ap.add_argument('--out', default='latency_report.json')
    a = ap.parse_args()
    segs = {'sensor': [], 'pre': [], 'percep': [], 'decis': [], 'act': [], 'total': []}
    for _ in range(a.n):
        m = measure_once()
        for k in segs:
            segs[k].append(m[k])
    report = {}
    for k, v in segs.items():
        v = np.array(v) / 1e6  # ms
        report[k] = {'p50': float(np.percentile(v, 50)), 'p95': float(np.percentile(v, 95)),
                     'p99': float(np.percentile(v, 99))}
    import json
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[OK] 时延分解(模拟量,实机需真插桩)')
    for k in ['sensor', 'pre', 'percep', 'decis', 'act', 'total']:
        print(f"  {k}: P50={report[k]['p50']:.1f}ms P95={report[k]['p95']:.1f}ms P99={report[k]['p99']:.1f}ms")
    print('  注意: 只报 GPU 前向当"系统时延"=低估;须全链 P95/P99;满载与稳态分报')


if __name__ == '__main__':
    main()
