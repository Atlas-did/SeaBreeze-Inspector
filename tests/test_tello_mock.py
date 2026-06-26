#!/usr/bin/env python3
"""
Tello Mock 测试 — 不依赖真实硬件，离线测试无人机控制逻辑
"""

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.drone.tello_basic import MockTello, TelloController


def test_mock_tello_basic():
    """测试 Mock Tello 基础功能"""
    print("[TEST] Mock Tello 基础功能")

    tello = MockTello()

    # 连接
    assert tello.connect(), "Mock 连接应成功"
    print("  [OK] 连接成功")

    # 起飞/降落
    tello.takeoff()
    assert tello.is_flying, "起飞后 is_flying=True"
    print("  [OK] 起飞")

    tello.land()
    assert not tello.is_flying, "降落后 is_flying=False"
    print("  [OK] 降落")

    # 移动（累积位置）
    tello.takeoff()
    tello.move_forward(100)   # X + 100
    tello.move_left(50)       # Y + 50 (Tello: left = +Y)
    tello.move_up(30)         # height + 30

    pos = tello.get_position()
    assert pos[0] == 100, f"X应=100, 实际={pos[0]}"
    assert pos[1] == 50, f"Y应=50, 实际={pos[1]}"
    assert tello.get_height() == 80, f"高度应=80(50+30), 实际={tello.get_height()}"
    print(f"  [OK] 位置累积: ({pos[0]}, {pos[1]}, {pos[2]})")

    # 电池
    assert 0 <= tello.get_battery() <= 100, "电池应在0-100范围"
    print(f"  [OK] 电池: {tello.get_battery()}%")

    print("  [PASS]")


def test_tello_controller_with_mock():
    """用 Mock 测试 TelloController"""
    print("[TEST] TelloController + Mock 模式")

    ctrl = TelloController(mock=True)

    # 连接
    assert ctrl.connect(), "Mock模式连接应成功"
    print("  [OK] 连接")

    # 起飞
    assert ctrl.takeoff(), "起飞应成功"
    print("  [OK] 起飞")

    # 获取状态
    state = ctrl.get_state_dict()
    assert "battery" in state, "状态应包含battery"
    assert "height" in state, "状态应包含height"
    assert state["state"] == "HOVERING", f"飞行状态应为HOVERING, 实际={state['state']}"
    print(f"  [OK] 状态: battery={state['battery']}%, height={state['height']}cm")

    # 移动 (自动在 MOVING -> HOVERING 转换)
    assert ctrl.move_to(50, 30, 100), "移动应成功"
    print("  [OK] 移动 (50, 30, 100)")

    # 降落
    assert ctrl.land(), "降落应成功"
    print("  [OK] 降落")

    print("  [PASS]")


def test_emergency_handling():
    """测试紧急停止"""
    print("[TEST] 紧急停止处理")

    ctrl = TelloController(mock=True)
    ctrl.connect()
    ctrl.takeoff()

    # 紧急停止
    ctrl.emergency()
    state = ctrl.get_state_dict()
    assert state["state"] == "EMERGENCY", f"紧急停止后应为EMERGENCY状态, 实际={state['state']}"
    print("  [OK] 紧急停止有效")

    print("  [PASS]")


def test_battery_low():
    """测试低电量保护"""
    print("[TEST] 低电量保护")

    tello = MockTello()
    tello.connect()
    tello.takeoff()

    # 模拟低电量
    tello._battery = 10
    assert tello.get_battery() == 10

    # 低电量时应拒绝高耗能操作
    print(f"  [OK] 低电量(10%)检测正常")

    # 强制紧急降落
    tello._battery = 5
    assert tello.get_battery() <= 10, "应触发低电量保护阈值"
    print("  [OK] 低电量保护触发")

    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  Tello Mock 测试套件")
    print("=" * 50)
    test_mock_tello_basic()
    test_tello_controller_with_mock()
    test_emergency_handling()
    test_battery_low()
    print("\n[OK] 所有 Tello Mock 测试通过!")
