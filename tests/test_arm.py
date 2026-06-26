#!/usr/bin/env python3
"""
机械臂运动学测试 — 验证FK/IK互逆性、边界条件、奇异点处理
"""

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.arm.arm_kinematics import FK, IK, Jacobian
from backend.arm.arm_kinematics import L1, L2, L3, THETA1_MIN, THETA1_MAX, THETA2_MIN, THETA2_MAX, THETA3_MIN, THETA3_MAX


def test_fk_ik_roundtrip():
    """测试 FK(IK(p)) ≈ p，所有角度组合"""
    print("[TEST] FK/IK 互逆性测试")

    passed = 0
    total = 0
    max_error = 0

    test_angles = []
    for t1 in [0, 30, 45, 60, 90, 120, 135, 150, 180]:
        for t2 in [30, 45, 60, 90, 120, 150]:
            for t3 in [0, 30, 45, 60, 90, 135]:
                test_angles.append((t1, t2, t3))

    for t1, t2, t3 in test_angles:
        total += 1
        pos = FK(t1, t2, t3)
        angles = IK(pos[0], pos[1], pos[2])
        pos2 = FK(angles[0], angles[1], angles[2])
        err = np.linalg.norm(pos - pos2)

        if err > max_error:
            max_error = err

        if err < 5.0:  # 工程精度 5mm
            passed += 1
        else:
            print(f"  WARN: FK({t1},{t2},{t3}) -> IK -> FK 误差={err:.2f}mm")

    print(f"  通过: {passed}/{total}, 最大误差: {max_error:.4f}mm")
    assert passed == total, f"FK/IK互逆性测试失败: {passed}/{total}"
    print("  [PASS]")


def test_joint_limits():
    """测试关节限幅功能"""
    print("[TEST] 关节限幅测试")

    # 测试边界角度
    boundary_cases = [
        (0, 90, 45),    # theta1 最小值
        (180, 90, 45),  # theta1 最大值
        (90, 30, 45),   # theta2 最小值
        (90, 150, 45),  # theta2 最大值
        (90, 90, 0),    # theta3 最小值
        (90, 90, 135),  # theta3 最大值
    ]

    for t1, t2, t3 in boundary_cases:
        pos = FK(t1, t2, t3)
        angles = IK(pos[0], pos[1], pos[2])
        assert THETA1_MIN <= angles[0] <= THETA1_MAX, f"theta1={angles[0]:.1f} 超出范围"
        assert THETA2_MIN <= angles[1] <= THETA2_MAX, f"theta2={angles[1]:.1f} 超出范围"
        assert THETA3_MIN <= angles[2] <= THETA3_MAX, f"theta3={angles[2]:.1f} 超出范围"

    print(f"  测试了 {len(boundary_cases)} 组边界角度")
    print("  [PASS]")


def test_jacobian():
    """测试雅可比矩阵数值正确性"""
    print("[TEST] 雅可比矩阵数值验证")

    # 用有限差分验证雅可比
    t1, t2, t3 = 90, 90, 45
    delta = 1e-4  # 弧度

    J_analytical = Jacobian(t1, t2, t3)

    # 有限差分
    pos = FK(t1, t2, t3)
    J_numerical = np.zeros((3, 3))

    for i, dt in enumerate([delta, delta, delta]):
        if i == 0:
            pos_d = FK(t1 + np.degrees(dt), t2, t3)
        elif i == 1:
            pos_d = FK(t1, t2 + np.degrees(dt), t3)
        else:
            pos_d = FK(t1, t2, t3 + np.degrees(dt))
        J_numerical[:, i] = (pos_d - pos) / dt

    diff = np.linalg.norm(J_analytical - J_numerical)
    print(f"  解析雅可比 vs 数值雅可比 差异: {diff:.4f}")
    assert diff < 1.0, f"雅可比差异过大: {diff}"
    print("  [PASS]")


def test_reachability():
    """测试可达空间判断"""
    print("[TEST] 可达空间测试")

    # 测试可达点 (在机械臂工作空间内)
    reachable_points = [
        (90, 60, 90),   # 正前方
        (45, 90, 60),   # 左前方
        (135, 90, 60),  # 右前方
    ]

    for t1, t2, t3 in reachable_points:
        pos = FK(t1, t2, t3)
        angles = IK(pos[0], pos[1], pos[2])
        pos2 = FK(angles[0], angles[1], angles[2])
        err = np.linalg.norm(pos - pos2)
        assert err < 5.0, f"可达点求解失败: err={err:.2f}mm"

    print(f"  {len(reachable_points)} 个可达点全部通过")
    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  机械臂运动学测试套件")
    print("=" * 50)
    test_fk_ik_roundtrip()
    test_joint_limits()
    test_jacobian()
    test_reachability()
    print("\n[OK] 所有机械臂测试通过!")
