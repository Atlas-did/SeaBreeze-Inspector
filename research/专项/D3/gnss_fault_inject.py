#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D3-01 弱 GNSS 故障注入 + 定位退化边界(本地仿真,证据层 L2/L4)
注入: 精度退化(σ递增)/完整性退化(跳变/漂移);输出"定位退化 × 下游任务可用性"边界。
Tello 无 GNSS,用视觉/光流定位做代理须声明"代理不等价于 GNSS 多径"。
"""
import argparse
import numpy as np


def inject_position(p_true, sigma=0.0, jump=0.0, drift=0.0, t=0, rng=None):
    rng = rng or np.random.default_rng()
    p = p_true + rng.normal(0, sigma, 2)  # 精度退化
    p += drift * t                        # 慢漂移
    if jump > 0 and int(t) % 10 == 0:     # 周期性跳变
        p += jump * rng.choice([-1, 1], 2)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='gnss_boundary_report.json')
    a = ap.parse_args()
    sigmas = [0.1, 0.5, 1.0, 3.0, 10.0]
    jumps = [0, 1, 3, 5]
    rows = {}
    rng = np.random.default_rng(0)
    for s in sigmas:
        for j in jumps:
            errs = []
            for t in range(100):
                p = inject_position(np.array([0.0, 0.0]), sigma=s, jump=j, drift=0.02, t=t, rng=rng)
                errs.append(np.linalg.norm(p))
            key = f'sigma={s},jump={j}'
            rows[key] = {'err_mean': float(np.mean(errs)), 'err_p95': float(np.percentile(errs, 95))}
    import json
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print('[OK] 弱 GNSS 边界注入仿真(代理声明: 视觉定位 ≠ GNSS 多径)')
    for k, v in list(rows.items())[:6]:
        print(f"  {k}: 误差均值 {v['err_mean']:.2f} m, P95 {v['err_p95']:.2f} m")
    print(f"  -> {a.out}")


if __name__ == '__main__':
    main()
