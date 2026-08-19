#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C2-01 FK/IK 数值自洽验证 + 奇异/边界位形审计(纯本地数学,证据层 L1)
根因修复:旧版用全 3×3 条件数查退化,但 θ3→0(手腕伸直)时平面(θ2,θ3)子雅可比秩亏,
3×3 的 t1 行仍满秩把奇异值撑住,导致 P95=123mm 的尾部灾难查不出。
本版:
  - 用平面 2×2 雅可比条件数 κ2 判退化(κ2>50 为退化/边界邻域);
  - IKFK 指标从「关节差」改为「位姿差 |FK(q_ik)-p_target|」,消除合法分支切换的假象;
  - 新增可用工作空间占比(中性初值 IK 收敛且位姿误差 <1mm 的比例);
  - 典型位形 vs 退化邻域分列统计,退化位形集中度(θ3≈0/最大伸程)单独报告。
输出: fk_ik_report.json
"""
import numpy as np
import argparse
import json

L1, L2, L3 = 55.0, 45.0, 35.0
L23 = L2 + L3
DEGEN_KAPPA = 50.0   # 平面雅可比条件数阈值(与全体 P95≈60 对齐)
POS_TOL_MM = 1.0     # 可用工作空间判定位姿误差阈值


def fk(q):
    """q=[θ1,θ2,θ3] 度 → 末端 [x,y,z] mm。"""
    t1, t2, t3 = np.radians(q)
    r = L1 * np.cos(t2) + L23 * np.cos(t2 + t3)
    z = L1 * np.sin(t2) + L23 * np.sin(t2 + t3)
    return np.array([r * np.cos(t1), r * np.sin(t1), z])


def planar_jac(q):
    """平面(θ2,θ3) 2×2 子雅可比。"""
    t2, t3 = np.radians(q[1:3])
    return np.array([[-L1 * np.sin(t2) - L23 * np.sin(t2 + t3), -L23 * np.sin(t2 + t3)],
                     [L1 * np.cos(t2) + L23 * np.cos(t2 + t3), L23 * np.cos(t2 + t3)]])


def planar_cond(q):
    """平面子雅可比条件数(退化检测:θ3→0 时秩亏 → 条件数爆炸)。"""
    return float(np.linalg.cond(planar_jac(q)))


def ik(p, q0=(90, 90, 45), tol=1e-6, maxit=200):
    """数值 IK(阻尼最小二乘)。p=[x,y,z] mm 目标。t1 解析解,θ2/θ3 平面迭代。"""
    x, y, z = p
    r_target = float(np.hypot(x, y))
    t1 = float(np.degrees(np.arctan2(y, x)))
    q = np.radians([q0[1], q0[2]]).astype(float)
    for _ in range(maxit):
        t2, t3 = q
        r = L1 * np.cos(t2) + L23 * np.cos(t2 + t3)
        zz = L1 * np.sin(t2) + L23 * np.sin(t2 + t3)
        e = np.array([r - r_target, zz - z])
        if np.linalg.norm(e) < tol:
            break
        J = np.array([[-L1 * np.sin(t2) - L23 * np.sin(t2 + t3), -L23 * np.sin(t2 + t3)],
                      [L1 * np.cos(t2) + L23 * np.cos(t2 + t3), L23 * np.cos(t2 + t3)]])
        lam = 1e-3
        try:
            dq = np.linalg.solve(J.T @ J + lam * np.eye(2), -J.T @ e)
        except np.linalg.LinAlgError:
            break
        q = q + dq
    t2, t3 = np.degrees(q)
    return np.array([t1, t2, t3])


def _stats(arr):
    return {'p50': float(np.percentile(arr, 50)),
            'p95': float(np.percentile(arr, 95)),
            'p99': float(np.percentile(arr, 99)),
            'max': float(np.max(arr))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=20000)
    ap.add_argument('--out', default='fk_ik_report.json')
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    N = a.n

    fkik_all, ikfk_all, kappa_all, theta3_all = [], [], [], []
    fkik_typ, fkik_deg = [], []
    ikfk_typ, ikfk_deg = [], []
    theta3_deg = []
    n_usable = 0
    for _ in range(N):
        q_gt = rng.uniform([0, 30, 0], [180, 150, 135])
        p = fk(q_gt)
        kappa = planar_cond(q_gt)
        degenerate = kappa > DEGEN_KAPPA
        theta3_all.append(q_gt[2])
        kappa_all.append(kappa)
        # FK->IK: 真值作初值(最近解),位姿残差
        q_ik = ik(p, q0=q_gt)
        e_fkik = float(np.linalg.norm(fk(q_ik) - p))
        fkik_all.append(e_fkik)
        # IK->FK: 中性初值,位姿误差(可用工作空间的判定量)
        q2 = ik(p, q0=(90, 90, 45))
        e_ikfk = float(np.linalg.norm(fk(q2) - p))
        ikfk_all.append(e_ikfk)
        if e_ikfk < POS_TOL_MM:
            n_usable += 1
        (fkik_deg if degenerate else fkik_typ).append(e_fkik)
        (ikfk_deg if degenerate else ikfk_typ).append(e_ikfk)
        if degenerate:
            theta3_deg.append(q_gt[2])

    n_deg = len(fkik_deg)
    report = {
        'N': N,
        'degenerate_ratio': n_deg / N,
        'degenerate_threshold_kappa': DEGEN_KAPPA,
        'fkik_pos_err_mm': {'overall': _stats(np.array(fkik_all)),
                            'typical': _stats(np.array(fkik_typ)),
                            'degenerate': _stats(np.array(fkik_deg))},
        'ikfk_pos_err_mm': {'overall': _stats(np.array(ikfk_all)),
                            'typical': _stats(np.array(ikfk_typ)),
                            'degenerate': _stats(np.array(ikfk_deg))},
        'planar_jac_cond': _stats(np.array(kappa_all)),
        'usable_workspace_ratio': n_usable / N,
        'usable_workspace_tol_mm': POS_TOL_MM,
        'degenerate_theta3_deg': {'mean': float(np.mean(theta3_deg)) if theta3_deg else None,
                                  'p50': float(np.percentile(theta3_deg, 50)) if theta3_deg else None,
                                  'max': float(np.max(theta3_deg)) if theta3_deg else None},
    }
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[OK] FK/IK 数值自洽验证(平面雅可比退化版)')
    print(f"  FK->IK 位姿残差(mm): P50={report['fkik_pos_err_mm']['overall']['p50']:.2e}, "
          f"P95={report['fkik_pos_err_mm']['overall']['p95']:.2e}, P99={report['fkik_pos_err_mm']['overall']['p99']:.2e}")
    print(f"  IK->FK 位姿残差(mm,中性初值): P50={report['ikfk_pos_err_mm']['overall']['p50']:.2e}, "
          f"P95={report['ikfk_pos_err_mm']['overall']['p95']:.2e}")
    print(f"  退化占比(κ2>{DEGEN_KAPPA}): {report['degenerate_ratio']:.1%}, "
          f"退化位形 θ3 均值={report['degenerate_theta3_deg']['mean']:.1f}°")
    print(f"  可用工作空间占比(位姿<{POS_TOL_MM}mm): {report['usable_workspace_ratio']:.1%}")
    print(f"  -> {a.out}")


if __name__ == '__main__':
    main()
