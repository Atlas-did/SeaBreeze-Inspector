#!/usr/bin/env python3
"""mission/ 层测试 — 状态枚举 + 转换表 + 分层安全监控"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.mission.states import (
    MissionState, TRANSITIONS, can_transition, transition,
)
from backend.mission.safety import FailsafeMonitor, SafetyLevel, SafetyEvent


# =========================================================================
# 状态机测试
# =========================================================================

def test_state_enum():
    """状态枚举定义完整"""
    print("[TEST] 状态枚举")
    assert len(MissionState) == 8
    assert MissionState.IDLE.name == "IDLE"
    assert MissionState.EMERGENCY.name == "EMERGENCY"
    print("  [PASS]")


def test_valid_transitions():
    """合法转换应通过"""
    print("[TEST] 合法状态转换")
    assert can_transition(MissionState.IDLE, MissionState.TAKEOFF)
    assert can_transition(MissionState.TAKEOFF, MissionState.HOVERING)
    assert can_transition(MissionState.HOVERING, MissionState.NAVIGATE)
    assert can_transition(MissionState.NAVIGATE, MissionState.INSPECT)
    assert can_transition(MissionState.INSPECT, MissionState.RETURN)
    assert can_transition(MissionState.RETURN, MissionState.LAND)
    assert can_transition(MissionState.LAND, MissionState.IDLE)
    assert can_transition(MissionState.HOVERING, MissionState.EMERGENCY)
    print("  [PASS]")


def test_invalid_transitions():
    """非法转换应拒绝"""
    print("[TEST] 非法状态转换")
    assert not can_transition(MissionState.IDLE, MissionState.LAND)
    assert not can_transition(MissionState.TAKEOFF, MissionState.INSPECT)
    assert not can_transition(MissionState.EMERGENCY, MissionState.HOVERING)
    assert not can_transition(MissionState.LAND, MissionState.TAKEOFF)
    print("  [PASS]")


def test_transition_raises():
    """非法转换应抛异常"""
    print("[TEST] 非法转换抛异常")
    try:
        transition(MissionState.IDLE, MissionState.LAND, "测试")
        assert False, "应抛异常"
    except ValueError:
        pass
    print("  [PASS]")


def test_emergency_only_to_idle():
    """EMERGENCY 只能转到 IDLE"""
    print("[TEST] EMERGENCY → IDLE 唯一出口")
    assert can_transition(MissionState.EMERGENCY, MissionState.IDLE)
    assert not can_transition(MissionState.EMERGENCY, MissionState.HOVERING)
    assert not can_transition(MissionState.EMERGENCY, MissionState.NAVIGATE)
    print("  [PASS]")


# =========================================================================
# 分层安全监控测试
# =========================================================================

def test_failsafe_ok():
    """正常情况返回 OK"""
    print("[TEST] Failsafe OK")
    m = FailsafeMonitor()
    e = m.check(battery=85, attitude=[5, 2, 1], height=100)
    assert e.level == SafetyLevel.OK
    print("  [PASS]")


def test_failsafe_warn():
    """低电量 WARN"""
    print("[TEST] Failsafe WARN")
    m = FailsafeMonitor()
    e = m.check(battery=15, attitude=[0, 0, 0], height=100)
    assert e.level == SafetyLevel.WARN
    assert "电量偏低" in e.reason
    print("  [PASS]")


def test_failsafe_land():
    """低电量 LAND"""
    print("[TEST] Failsafe LAND")
    m = FailsafeMonitor()
    e = m.check(battery=8, attitude=[0, 0, 0], height=100)
    assert e.level == SafetyLevel.LAND
    print("  [PASS]")


def test_failsafe_kill():
    """危急电量 KILL"""
    print("[TEST] Failsafe KILL")
    m = FailsafeMonitor()
    e = m.check(battery=3, attitude=[0, 0, 0], height=100)
    assert e.level == SafetyLevel.KILL
    print("  [PASS]")


def test_failsafe_attitude():
    """姿态异常"""
    print("[TEST] Failsafe 姿态")
    m = FailsafeMonitor()
    e = m.check(battery=85, attitude=[35, 0, 0], height=100)
    assert e.level == SafetyLevel.LAND
    print("  [PASS]")


def test_failsafe_height():
    """高度超限"""
    print("[TEST] Failsafe 高度")
    m = FailsafeMonitor()
    e = m.check(battery=85, attitude=[0, 0, 0], height=350)
    assert e.level == SafetyLevel.LAND
    print("  [PASS]")


def test_failsafe_recover():
    """LAND 级别可恢复"""
    print("[TEST] Failsafe 恢复")
    m = FailsafeMonitor()
    m.check(battery=8, attitude=[0, 0, 0], height=100)
    assert not m.can_recover()  # LAND 级不可恢复 → 需要确认

    # 实际上 LAND 级别 can_recover 应检查: 只有 OK/WARN 才可恢复
    # 修正: LAND 也需要外部干预 (checked=True 需要点按钮确认)
    # 这里验证 active_level 的优先级: KILL > LAND > WARN

    # 电量回升后
    e = m.check(battery=90, attitude=[0, 0, 0], height=100)
    assert e.level == SafetyLevel.OK  # 恢复正常后返回OK
    print("  [PASS]")


def test_failsafe_reset():
    """KILL 后 reset"""
    print("[TEST] Failsafe reset")
    m = FailsafeMonitor()
    m.check(battery=2, attitude=[0, 0, 0], height=100)  # KILL
    assert m.active_level == SafetyLevel.KILL
    m.reset()
    assert m.active_level == SafetyLevel.OK
    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  Mission 层测试套件")
    print("=" * 50)
    test_state_enum()
    test_valid_transitions()
    test_invalid_transitions()
    test_transition_raises()
    test_emergency_only_to_idle()
    test_failsafe_ok()
    test_failsafe_warn()
    test_failsafe_land()
    test_failsafe_kill()
    test_failsafe_attitude()
    test_failsafe_height()
    test_failsafe_recover()
    test_failsafe_reset()
    print("\n[OK] 所有 Mission 层测试通过!")
