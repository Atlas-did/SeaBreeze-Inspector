#!/usr/bin/env python3
"""
安全守护独立单元测试 — threshold 边界、reset、reason
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.safety_guard import SafetyGuard


def test_normal_state():
    """正常状态不应触发紧急"""
    print("[TEST] 正常状态检查")
    guard = SafetyGuard()

    result = guard.check({
        "battery": 80,
        "attitude": [5, 2, 1],
        "height": 200,
    })
    assert result is True, "正常状态应返回True(安全)"
    assert not guard.is_emergency
    print("  [PASS]")


def test_low_battery():
    """低电量检查"""
    print("[TEST] 低电量触发")
    guard = SafetyGuard()

    # 低于阈值10%
    result = guard.check({
        "battery": 5,
        "attitude": [0, 0, 0],
        "height": 100,
    })
    assert result is False, "低电量应返回False(不安全)"
    assert guard.is_emergency
    assert "低电量" in guard.emergency_reason
    print("  原因: {}".format(guard.emergency_reason))
    print("  [PASS]")


def test_attitude_anomaly():
    """姿态异常检查"""
    print("[TEST] 姿态异常触发")
    guard = SafetyGuard()

    # 姿态超过30度
    result = guard.check({
        "battery": 80,
        "attitude": [35, 10, 5],
        "height": 100,
    })
    assert result is False, "姿态异常应返回False"
    assert "姿态" in guard.emergency_reason
    print("  原因: {}".format(guard.emergency_reason))
    print("  [PASS]")


def test_height_limit():
    """高度超限检查"""
    print("[TEST] 高度超限触发")
    guard = SafetyGuard()

    # 超过500cm
    result = guard.check({
        "battery": 80,
        "attitude": [0, 0, 0],
        "height": 600,
    })
    assert result is False, "高度超限应返回False"
    assert "高度" in guard.emergency_reason
    print("  原因: {}".format(guard.emergency_reason))
    print("  [PASS]")


def test_timeout():
    """通信超时检查"""
    print("[TEST] 通信超时触发")
    guard = SafetyGuard()

    # 第一次check正常
    guard.check({"battery": 80, "attitude": [0, 0, 0], "height": 100})

    # 模拟超时 (SafetyGuard内部用time.time(), 我们手动设置_last_heartbeat)
    guard._last_heartbeat = time.time() - 2.0  # 2秒前

    result = guard.check({"battery": 80, "attitude": [0, 0, 0], "height": 100})
    assert result is False, "通信超时应返回False"
    assert "超时" in guard.emergency_reason
    print("  原因: {}".format(guard.emergency_reason))
    print("  [PASS]")


def test_reset():
    """紧急状态重置"""
    print("[TEST] 紧急状态重置")
    guard = SafetyGuard()

    # 触发紧急
    guard.check({"battery": 3, "attitude": [0, 0, 0], "height": 100})
    assert guard.is_emergency

    # 重置
    guard.reset()
    assert not guard.is_emergency
    assert guard.emergency_reason == ""
    print("  [PASS]")


def test_threshold_boundaries():
    """阈值边界测试"""
    print("[TEST] 阈值边界")
    guard = SafetyGuard()

    # 恰好等于阈值10% 电池
    assert guard.check({"battery": 10, "attitude": [0, 0, 0], "height": 100}), \
        "恰好等于阈值应安全 (battery=10% >= 10%)"
    # 低于阈值
    assert not guard.check({"battery": 9, "attitude": [0, 0, 0], "height": 100}), \
        "低于阈值应触发 (battery=9% < 10%)"

    guard.reset()

    # 恰好等于高度阈值500cm
    assert guard.check({"battery": 80, "attitude": [0, 0, 0], "height": 500}), \
        "恰好等于高度阈值应安全 (height=500 <= 500)"
    assert not guard.check({"battery": 80, "attitude": [0, 0, 0], "height": 501}), \
        "超过高度阈值应触发 (height=501 > 500)"

    guard.reset()

    # 恰好等于姿态阈值30度
    assert guard.check({"battery": 80, "attitude": [30, 0, 0], "height": 100}), \
        "恰好等于姿态阈值应安全 (att=30 <= 30)"
    assert not guard.check({"battery": 80, "attitude": [31, 0, 0], "height": 100}), \
        "超过姿态阈值应触发 (att=31 > 30)"

    print("  [PASS]")


def test_emergency_persists():
    """一旦触发紧急，后续check应持续返回False"""
    print("[TEST] 紧急状态持续")
    guard = SafetyGuard()

    # 触发
    assert not guard.check({"battery": 5, "attitude": [0, 0, 0], "height": 100})
    # 即使恢复正常条件，仍应保持紧急
    assert not guard.check({"battery": 90, "attitude": [0, 0, 0], "height": 100})
    assert guard.is_emergency
    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  安全守护测试套件")
    print("=" * 50)
    test_normal_state()
    test_low_battery()
    test_attitude_anomaly()
    test_height_limit()
    test_timeout()
    test_reset()
    test_threshold_boundaries()
    test_emergency_persists()
    print("\n[OK] 所有安全守护测试通过!")
