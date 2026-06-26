#!/usr/bin/env python3
"""
机械臂控制器 mock 测试 — 角度解析、IK、duration
"""

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.arm.arm_controller import ArmController
from backend.arm.arm_kinematics import FK, IK


def test_arm_controller_mock():
    """Mock模式下机械臂控制器基本功能"""
    print("[TEST] ArmController Mock 模式")

    arm = ArmController(port="")  # 空端口 = Mock模式

    # 设置关节角度
    result = arm.set_joint_angles([90, 45, 30], duration=500)
    assert result is True, "Mock模式应返回True"
    angles = arm.get_current_angles()
    assert np.allclose(angles, [90, 45, 30], atol=0.1), \
        "角度应更新为 (90,45,30), 实际={}".format(angles.tolist())
    print("  角度设置: ({:.0f},{:.0f},{:.0f})".format(angles[0], angles[1], angles[2]))

    print("  [PASS]")


def test_arm_move_to_position():
    """通过位置移动 (IK + 发送)"""
    print("[TEST] ArmController move_to_position")

    arm = ArmController(port="")

    # 前向位置
    pos = FK(90, 60, 90)
    result = arm.move_to_position(pos[0], pos[1], pos[2])
    assert result is True
    angles = arm.get_current_angles()
    print("  目标位置: ({:.0f},{:.0f},{:.0f}), IK结果: ({:.1f},{:.1f},{:.1f})".format(
        pos[0], pos[1], pos[2], angles[0], angles[1], angles[2]
    ))
    # IK 应送回正确位置
    pos_back = FK(angles[0], angles[1], angles[2])
    err = np.linalg.norm(pos - pos_back)
    assert err < 5, "IK误差应<5mm, 实际={:.2f}".format(err)

    print("  [PASS]")


def test_arm_reset():
    """归位测试"""
    print("[TEST] ArmController reset")
    arm = ArmController(port="")

    # 先移到非默认位置
    arm.set_joint_angles([45, 120, 60])
    # 归位
    arm.reset()
    angles = arm.get_current_angles()
    assert np.allclose(angles, [90, 90, 90], atol=0.1), \
        "归位后应为(90,90,90), 实际={}".format(angles.tolist())

    print("  [PASS]")


def test_arm_duration_wait():
    """duration参数产生正确的等待时间"""
    print("[TEST] ArmController duration 等待")
    import time

    arm = ArmController(port="")
    arm.set_joint_angles([90, 90, 90], duration=100)  # 初始位置

    # 大幅度移动到180° (max 90°差 = 90*20ms = 1800ms)
    t0 = time.perf_counter()
    arm.set_joint_angles([90, 90, 180], duration=2000)
    elapsed = (time.perf_counter() - t0) * 1000

    # 90°差 * 20ms/度 = 1800ms, duration上限=2000ms
    # 实际取 min(1800, 2000) = 1800ms
    assert elapsed > 500, "大角度移动应有显著延时, 实际={:.0f}ms".format(elapsed)
    print("  90°移动耗时: {:.0f}ms (期望~1800ms)".format(elapsed))
    print("  [PASS]")


def test_get_current_angles_initial():
    """检查初始角度"""
    print("[TEST] ArmController 初始状态")
    arm = ArmController(port="")
    angles = arm.get_current_angles()
    assert np.allclose(angles, [90, 90, 90], atol=0.1), \
        "初始角度应为(90,90,90)"
    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  机械臂控制器测试套件")
    print("=" * 50)
    test_arm_controller_mock()
    test_arm_move_to_position()
    test_arm_reset()
    test_arm_duration_wait()
    test_get_current_angles_initial()
    print("\n[OK] 所有机械臂控制器测试通过!")
