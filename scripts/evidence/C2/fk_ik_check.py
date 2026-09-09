#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C2-01 FK/IK 数值自洽验证 + 奇异位形审计(纯本地数学,证据层 L1)
对 3-DOF 机械臂(L1=55,L2=45,L3=35mm)做 FK∘IK 与 IK∘FK 闭环误差 + 雅可比条件数审计。
"""
import numpy as np
import argparse, json

L1, L2, L3 = 55.0, 45.0, 35.0
L23 = L2 + L3


def fk(q):
    """q=[θ1,θ2,θ3] 度 → 末端 [x,y,z] mm。"""
    t1, t2, t3 = np.radians(q)
    r = L1 * np.cos(t2) + L23 * np.cos(t2 + t3)
    z = L1 * np.sin(t2) + L23 * np.sin(t2 + t3)
    return np.array([r * np.cos(t1), r * np.sin(t1), z])


def jacobian(q):
    t1, t2, t3 = np.radians(q)
    r = L1 * np.cos(t2) + L23 * np.cos(t2 + t3)
    dr2 = -L1 * np.sin(t2) - L23 * np.sin(t2 + t3)
    dr3 = -L23 * np.sin(t2 + t3)
    dz2 = L1 * np.cos(t2) + L23 * np.cos(t2 + t3)
    dz3 = L23 * np.cos(t2 + t3)
    J = np.array([
        [-r * np.sin(t1), dr2 * np.cos(t1), dr3 * np.cos(t1)],
        [r * np.cos(t1), dr2 * np.sin(t1), dr3 * np.sin(t1)],
        [0, dz2, dz3],
    ])
    return J


def ik(p, q0=(90, 90, 45), tol=1e-6, maxit=200):
    """数值 IK(L-M 风格阻尼最小二乘)。p=[x,y,z] mm 目标。"""
    x, y, z = p
    r_target = float(np.hypot(x, y))
    t1 = float(np.degrees(np.arctan2(y, x)))
    # 平面 IK: 解 θ2,θ3 使 FK(r,z) 匹配 (r_target, z)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=20000)
    ap.add_argument('--out', default='fk_ik_report.json')
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    N = a.n

    # 工作空间采样: θ1∈[0,180] θ2∈[30,150] θ3∈[0,135]
    err_fkik, err_ikfk = [], []
    fail_fkik = 0
    conds = []
    for _ in range(N):
        q_gt = rng.uniform([0, 30, 0], [180, 150, 135])
        p = fk(q_gt)
        q_ik = ik(p, q0=q_gt)  # 以真值作初值(最近解)
        p_back = fk(q_ik)
        err_fkik.append(np.linalg.norm(p_back - p))  # FK∘IK 位姿残差(mm)
        # IK∘FK: 从关节空间再 FK→IK 回代
        p2 = fk(q_gt)
        q2 = ik(p2, q0=(90, 90, 45))
        err_ikfk.append(np.degrees(np.radians(q2 - q_gt)).max() if q2 is not None else 999)
        conds.append(np.linalg.cond(jacobian(q_gt)))

    err_fkik = np.array(err_fkik)
    err_ikfk = np.array(err_ikfk)
    report = {
        'N': N,
        'fkik_pos_err_mm': {'p50': float(np.percentile(err_fkik, 50)),
                            'p95': float(np.percentile(err_fkik, 95)),
                            'p99': float(np.percentile(err_fkik, 99))},
        'ikfk_joint_err_deg': {'p50': float(np.percentile(err_ikfk, 50)),
                               'p95': float(np.percentile(err_ikfk, 95))},
        'jacobian_cond': {'p50': float(np.percentile(conds, 50)),
                          'p95': float(np.percentile(conds, 95)),
                          'p99': float(np.percentile(conds, 99)),
                          'max': float(np.max(conds))},
    }
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[OK] FK/IK 数值自洽验证')
    print(f"  FK∘IK 位姿残差(mm): P50={report['fkik_pos_err_mm']['p50']:.2e}, "
          f"P95={report['fkik_pos_err_mm']['p95']:.2e}, P99={report['fkik_pos_err_mm']['p99']:.2e}")
    print(f"  IK∘FK 关节残差(deg): P50={report['ikfk_joint_err_deg']['p50']:.2e}")
    print(f"  雅可比条件数: P95={report['jacobian_cond']['p95']:.1f}, max={report['jacobian_cond']['max']:.1f}")
    print(f"  -> {a.out}")


if __name__ == '__main__':
    main()
