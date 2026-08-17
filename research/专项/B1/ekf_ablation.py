#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B1-02 EKF 扰动观测 Q/R 消融仿真(本地,证据层 L1)
在合成"恒定风+阶跃阵风+正弦阵风+传感器噪声"上,扫 Q/R 三档(保守/适中/激进),
输出扰动跟踪误差 + 静风基线(观测器应≈0) + 新息诊断。
"""
import argparse, json
import numpy as np


def run_ekf(Q_d, R_pos, R_acc, dt=0.1, n=1000, scenario='step', seed=0):
    """12 状态简化版: 只仿真 x 轴 [pos, vel, acc, d]。"""
    rng = np.random.default_rng(seed)
    # 真值扰动
    if scenario == 'static':
        d_true = np.zeros(n)
    elif scenario == 'step':
        d_true = np.full(n, 1.0); d_true[n // 2:] = 2.0
    elif scenario == 'sine':
        d_true = 2.0 * np.sin(2 * np.pi * 0.1 * np.arange(n) * dt)
    else:
        d_true = np.full(n, 1.0)

    x = np.zeros((n, 4))  # pos, vel, acc, d
    x[:, 3] = d_true
    F = np.array([[1, dt, 0.5 * dt ** 2, 0.5 * dt ** 2],
                  [0, 1, dt, dt],
                  [0, 0, 1, 0],
                  [0, 0, 0, 1.0]])
    H = np.array([[0, 0, 1, 1],   # IMU 观测 acc+d
                  [1, 0, 0, 0]])  # 位置观测
    Q = np.diag([0.01, 0.1, Q_d, Q_d])
    R = np.diag([R_acc, R_pos])

    xh = np.zeros(4); P = np.eye(4) * 100
    d_hat = np.zeros(n)
    innovations = np.zeros(n)
    for k in range(n):
        # 真值推进
        if k > 0:
            x[k, 0] = x[k - 1, 0] + x[k - 1, 1] * dt + 0.5 * (x[k - 1, 2] + x[k - 1, 3]) * dt ** 2
            x[k, 1] = x[k - 1, 1] + (x[k - 1, 2] + x[k - 1, 3]) * dt
            x[k, 2] = x[k - 1, 2]
        z = H @ x[k] + rng.normal(0, np.sqrt(np.diag(R)))
        # 预测
        xh = F @ xh; P = F @ P @ F.T + Q
        # 更新
        y = z - H @ xh
        S = H @ P @ H.T + R
        K = P @ H.T @ np.linalg.inv(S)
        xh = xh + K @ y
        P = (np.eye(4) - K @ H) @ P
        d_hat[k] = xh[3]
        innovations[k] = y[0]
    return d_true, d_hat, innovations


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='ekf_ablation_report.json')
    a = ap.parse_args()

    configs = {'conservative': (0.1, 4.0, 0.05), 'moderate': (0.5, 4.0, 0.05), 'aggressive': (2.0, 4.0, 0.05)}
    report = {}
    for name, (Qd, Rp, Ra) in configs.items():
        d_true, d_hat, inno = run_ekf(Qd, Rp, Ra, scenario='step')
        err = np.sqrt(((d_hat - d_true) ** 2).mean())
        report[name] = {'step_rmse': float(err), 'innovation_std': float(inno.std()),
                        'innovation_mean': float(inno.mean())}
    # 静风基线(应≈0)
    _, d_hat_static, _ = run_ekf(0.5, 4.0, 0.05, scenario='static')
    report['static_baseline'] = {'d_hat_std': float(d_hat_static.std())}

    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[OK] EKF Q/R 消融仿真')
    for name, r in report.items():
        if name != 'static_baseline':
            print(f"  {name}: 阶跃跟踪 RMSE={r['step_rmse']:.3f}, 新息 std={r['innovation_std']:.3f}")
    print(f"  静风基线 d_hat std={report['static_baseline']['d_hat_std']:.4f} (应≈0)")
    print(f"  -> {a.out}")


if __name__ == '__main__':
    main()
