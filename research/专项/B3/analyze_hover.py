#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B3-01 相对漂移测量与统计: RMSE/p95/CI(本地,输入 telemetry CSV)
输入每 run 的 (t, x_m, y_m) 序列;输出按 run 的漂移统计 + 组间改善率(绝对+比例+CI)。
用法: python analyze_hover.py --csv telemetry.csv --group-col config --x x_m --y y_m
"""
import argparse, csv
import numpy as np


def drift_stats(x, y):
    x0, y0 = x[0], y[0]
    r = np.hypot(x - x0, y - y0)
    return {'rmse': float(np.sqrt((r ** 2).mean())), 'p95': float(np.percentile(r, 95)),
            'max': float(r.max())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', required=True)
    ap.add_argument('--run-col', default='run_id')
    ap.add_argument('--group-col', default='config')
    ap.add_argument('--x', default='x_m')
    ap.add_argument('--y', default='y_m')
    ap.add_argument('--out', default='hover_report.csv')
    a = ap.parse_args()

    data = {}
    with open(a.csv, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            key = (r[a.run_col], r.get(a.group_col, 'group'))
            data.setdefault(key, []).append((float(r[a.x]), float(r[a.y])))

    rows = []
    for (run, grp), pts in data.items():
        xs = np.array([p[0] for p in pts]); ys = np.array([p[1] for p in pts])
        s = drift_stats(xs, ys)
        rows.append([grp, run, len(pts), s['rmse'], s['p95'], s['max']])

    with open(a.out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['group', 'run', 'n_pts', 'rmse_m', 'p95_m', 'max_m'])
        w.writerows(rows)

    # 组间汇总(以 run 为单位)
    print(f'[OK] 相对漂移统计: {len(rows)} runs -> {a.out}')
    import itertools
    for grp, g in itertools.groupby(sorted(rows, key=lambda r: r[0]), key=lambda r: r[0]):
        g = list(g)
        rmses = [r[3] for r in g]
        mu, sd = np.mean(rmses), np.std(rmses, ddof=1) if len(rmses) > 1 else 0
        ci = 1.96 * sd / np.sqrt(len(rmses))
        print(f'  {grp}: N={len(g)}, RMSE mean={mu:.3f}±{sd:.3f} m, 95%CI=±{ci:.3f}')
    print('  注意: 改善率须同时给绝对差(mm/cm)与比例(%),CI 不重叠才算显著')


if __name__ == '__main__':
    main()
