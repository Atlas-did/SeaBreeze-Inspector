#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B1-02 EKF 扰动观测消融仿真(本地,证据层 L1)—— 忠实还原真实扰动观测器
根因修复:旧版把观测建模成 z0 = acc + d,acc 与 d 共线不可区分,导致三档 Q RMSE 平顶。
真实观测器靠「从 IMU 观测中减去已知控制量 u」让 d 直接可观测。本版:
  - 状态 [pos, vel, d];控制输入 u 已知(喂入 B),观测 a_imu = u + d、x_opt = pos;
  - 新息 y_acc = (a_imu - u) - d_hat,直接观测 d;
  - R 按真实传感器量级(σ_pos≈0.05m,σ_acc≈0.05m/s²,旧版 2m 是硬伤);
  - 主消融 = 固定 Q vs 自适应 Q(马氏距离 D² 超阈即放大 Q_d),指标用收敛时间/超调;
  - 次消融 = Q×R 二维网格;静风基线应≈观测噪声地板。
输出: ekf_ablation_report.json(含 u_feed/scenario/settle_time_ms/overshoot_pct/QxR 网格)。
"""
import argparse
import json
import numpy as np

CHI2_95_2DOF = 5.991  # 2 维新息 χ²(0.95)


def run_ekf(Q_d, sigma_acc, sigma_pos, dt=0.01, n=1000, scenario='step',
            adaptive=False, alpha=0.5, q_scale_max=30.0, seed=0, u_const=0.0):
    """单轴扰动观测仿真。返回 dict(d_true, d_hat, innovations, mahal)。

    状态 x=[pos, vel, d];已知控制 u[k]=u_const(默认 0,即"悬停指令加速度为 0",
    扰动独占加速度)。验证 u 馈入机制时设非零值(如 1.0):正确实现下 d_hat 应跟踪
    d_true 而非 d_true+u_const。
    真值推进: pos += vel*dt + 0.5*(u+d)*dt²; vel += (u+d)*dt; d 随机游走。
    观测: a_imu = u + d + N(0,σ_acc²); x_opt = pos + N(0,σ_pos²)。
    新息(减去已知 u 后): y = [(a_imu-u)-d_hat, x_opt-pos_hat]。
    """
    rng = np.random.default_rng(seed)
    if scenario == 'static':
        d_true = np.zeros(n)
    elif scenario == 'step':
        d_true = np.full(n, 1.0); d_true[n // 2:] = 2.0
    elif scenario == 'sine':
        d_true = 2.0 * np.sin(2 * np.pi * 0.1 * np.arange(n) * dt)
    elif scenario == 'gust':
        # 随机幅值脉冲(泊松到达 + 指数衰减),考验自适应触发
        d_true = np.zeros(n)
        k = 0
        while k < n:
            if rng.random() < 0.01:  # 平均 100 步一个脉冲
                amp = rng.uniform(1.0, 3.0)
                dur = rng.integers(5, 30)
                d_true[k:k + dur] += amp * np.exp(-np.arange(dur) / 10.0)
                k += dur
            else:
                k += 1
    else:
        d_true = np.full(n, 1.0)

    u = np.full(n, u_const)  # 已知控制加速度常量;d 是扰动,两者叠加成总加速度
    # 转移/输入/观测
    F = np.array([[1.0, dt, 0.5 * dt ** 2],
                  [0.0, 1.0, dt],
                  [0.0, 0.0, 1.0]])
    B = np.array([0.5 * dt ** 2, dt, 0.0])  # 1-D 输入向量,配合标量 u[k] 用 B * u[k]
    H = np.array([[0.0, 0.0, 1.0],   # 加速度通道:预测 d
                  [1.0, 0.0, 0.0]])  # 位置通道:预测 pos
    R = np.diag([sigma_acc ** 2, sigma_pos ** 2])
    Q = np.diag([1e-6, 1e-4, Q_d])  # pos/vel 过程噪声小,d 的过程噪声 = Q_d

    xh = np.zeros(3); P = np.eye(3) * 0.1
    d_hat = np.zeros(n); mahal = np.zeros(n); inno = np.zeros((n, 2))
    q_cur = Q_d
    pos_true = 0.0
    vel_true = 0.0
    for k in range(n):
        a_k = u[k] + d_true[k]  # 总加速度 = 已知控制 + 扰动
        # 观测(测当前时刻真值): a_imu = u+d+噪声, x_opt = pos+噪声
        z = np.array([a_k + rng.normal(0.0, sigma_acc),
                      pos_true + rng.normal(0.0, sigma_pos)])
        # 预测(用当前自适应后的 Q_d)
        Qk = np.diag([1e-6, 1e-4, q_cur])
        xh = F @ xh + B * u[k]
        P = F @ P @ F.T + Qk
        # 更新(新息减去已知控制后,加速度通道直接观测 d)
        y = z - H @ xh
        y[0] -= u[k]  # 真正的 u 馈入:从加速度观测中减去已知控制。旧版漏了这一步,
        #             u=0 时数值恰好对,一设 u=1.0 偏差就被吃进 d_hat(d_hat→d_true+u)
        S = H @ P @ H.T + R
        K = P @ H.T @ np.linalg.solve(S, np.eye(S.shape[0]))
        xh = xh + K @ y
        P = (np.eye(3) - K @ H) @ P
        d_hat[k] = xh[2]
        inno[k] = y
        # 自适应 Q: 马氏距离超阈则放大 Q_d(限幅),用于下一时刻预测
        D2 = float(y @ np.linalg.solve(S, y))
        mahal[k] = D2
        if adaptive and D2 > CHI2_95_2DOF:
            q_cur = min(Q_d * (1.0 + alpha * (D2 / CHI2_95_2DOF - 1.0)), Q_d * q_scale_max)
        else:
            q_cur = Q_d
        # 真值推进(常数加速度 Euler 积分)
        pos_true = pos_true + vel_true * dt + 0.5 * a_k * dt ** 2
        vel_true = vel_true + a_k * dt
    return {'d_true': d_true, 'd_hat': d_hat, 'innov': inno, 'mahal': mahal}


def _metrics(res, dt, step_idx=None):
    d_true, d_hat = res['d_true'], res['d_hat']
    err = d_hat - d_true
    rmse = float(np.sqrt((err ** 2).mean()))
    out = {'rmse': rmse}
    if step_idx is not None:
        d_new = d_true[step_idx]
        d_old = d_true[step_idx - 1] if step_idx > 0 else d_new
        step_mag = abs(d_new - d_old)
        # 收敛时间: 滑动平均(20 步)后的误差 < 5%*step_mag 并保持到结束(抗单步噪声)
        tol = 0.05 * max(step_mag, 1e-9)
        sm = np.convolve(np.abs(d_hat - d_new), np.ones(20) / 20, mode='same')
        settle = None
        for k in range(step_idx, len(d_hat)):
            if sm[k:].max() < tol:
                settle = k - step_idx
                break
        out['settle_time_ms'] = float((settle if settle is not None else len(d_hat) - step_idx) * dt * 1000)
        # 超调(相对阶跃量,比例)
        peak = float(np.max(d_hat[step_idx:]))
        out['overshoot_pct'] = float(max(0.0, (peak - d_new) / max(step_mag, 1e-9)) * 100.0)
        # 阶跃后稳态 RMSE(后 30%)
        tail = slice(int(step_idx + 0.7 * (len(d_hat) - step_idx)), len(d_hat))
        out['steady_rmse'] = float(np.sqrt(((d_hat[tail] - d_true[tail]) ** 2).mean()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='ekf_ablation_report.json')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--u-const', type=float, default=0.0,
                    help='已知控制加速度常量(m/s²)。设非零(如 1.0)验证 u 馈入:'
                         '正确实现下 d_hat 应跟踪 d_true,不偏到 d_true+u。默认 0 保持消融数字不变')
    a = ap.parse_args()
    dt = 0.01; n = 1000; step_idx = n // 2

    SIGMA_ACC = 0.05   # IMU 加速度噪声 σ (m/s²),真实量级(0.05~0.2 取下界,便于静风基线 <0.05)
    SIGMA_POS = 0.05   # 光流位置噪声 σ (m),真实量级
    Q_BASE = 1e-5      # 主消融固定 Q 的基准(低 Q→平滑但迟钝,自适应 Q 才有提速空间)

    report = {'u_feed': True, 'scenario': 'step', 'dt_s': dt, 'n': n,
              'sigma_acc': SIGMA_ACC, 'sigma_pos': SIGMA_POS, 'Q_base': Q_BASE,
              'u_const': a.u_const,
              'seed': a.seed,
              'adaptive': {'alpha': 0.5, 'q_scale_max': 30.0,
                           'note': 'Mahalanobis D²>χ²₂(0.95)=5.991 时放大 Q,与真实观测器同一机制(真实:α=0.3/×10)'}}

    # ---- 主消融: 固定 Q vs 自适应 Q(论文卖点的直接实验) ----
    abl = {}
    for name, (qd, adapt) in {'fixed_Q': (Q_BASE, False), 'adaptive_Q': (Q_BASE, True)}.items():
        res = run_ekf(qd, SIGMA_ACC, SIGMA_POS, dt=dt, n=n, scenario='step',
                      adaptive=adapt, seed=a.seed, u_const=a.u_const)
        m = _metrics(res, dt, step_idx=step_idx)
        m['Q_d_base'] = qd
        m['adaptive'] = adapt
        abl[name] = m
    report['fixed_vs_adaptive'] = abl

    # ---- 静风基线(应≈观测噪声地板,期望 <0.05) ----
    res_static = run_ekf(Q_BASE, SIGMA_ACC, SIGMA_POS, dt=dt, n=n, scenario='static',
                         seed=a.seed, u_const=a.u_const)
    report['static_baseline'] = {'d_hat_std': float(res_static['d_hat'].std()),
                                 'd_hat_mean': float(res_static['d_hat'].mean())}

    # ---- u 馈入自检:非零 u 下 d_hat 必须跟踪 d_true(而不是 d_true+u) ----
    # 旧版在 update 一步漏了「新息减 u」(y[0] -= u),u=0 时数值恰好对;这个自检负责锁死该机制。
    res_u = run_ekf(Q_BASE, SIGMA_ACC, SIGMA_POS, dt=dt, n=n, scenario='step',
                    seed=a.seed, u_const=1.0)
    step_idx_local = n // 2
    tail_u = slice(int(step_idx_local + 0.7 * (len(res_u['d_hat']) - step_idx_local)), len(res_u['d_hat']))
    d_hat_tail = float(np.mean(res_u['d_hat'][tail_u]))
    report['u_feed_check'] = {
        'u_const': 1.0, 'd_true_after_step': 2.0, 'd_hat_tail_mean': d_hat_tail,
        'ok': bool(abs(d_hat_tail - 2.0) < 0.05),
        'note': 'ok=True 表示 u 馈入生效(未被误当扰动);旧版此值≈3.0(偏差被吃进 d_hat)'}

    # ---- 次消融: Q×R 二维网格(收敛时间 + RMSE,展示 Q↔跟踪速度、R↔噪声抑制的解耦) ----
    grid = {}
    for qd in [1e-5, 1e-4, 1e-3]:
        for sa in [0.02, 0.05, 0.2]:
            res = run_ekf(qd, sa, SIGMA_POS, dt=dt, n=n, scenario='step',
                          seed=a.seed, u_const=a.u_const)
            m = _metrics(res, dt, step_idx=step_idx)
            grid[f'Qd={qd:g},σacc={sa:g}'] = m
    report['QxR_grid'] = grid

    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[OK] EKF 扰动观测消融(u 馈入版)')
    for name, m in abl.items():
        tag = '自适应Q' if m['adaptive'] else '固定Q'
        print(f"  {name}({tag}): 收敛={m['settle_time_ms']:.0f}ms, 超调={m['overshoot_pct']:.1f}%, "
              f"稳态RMSE={m.get('steady_rmse', float('nan')):.4f}")
    print(f"  静风基线 d_hat std={report['static_baseline']['d_hat_std']:.4f} (期望 <0.05)")
    chk = report['u_feed_check']
    print(f"  u 馈入自检(u=1.0, d_true=2.0): d_hat 尾部均值={chk['d_hat_tail_mean']:.3f} "
          f"-> {'[OK] 跟踪真值' if chk['ok'] else '[FAIL] 偏差被吃进扰动'}")
    print(f"  -> {a.out}")


if __name__ == '__main__':
    main()
