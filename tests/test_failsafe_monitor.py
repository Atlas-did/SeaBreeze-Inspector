#!/usr/bin/env python3
"""
FailsafeMonitor 分层安全监控测试 — 替代被删除的 test_safety_guard.py

覆盖: OK/WARN/LAND/KILL 四级、阈值边界、心跳超时、heartbeat()、
      reset()、can_recover()、实例级 THRESHOLDS 隔离、事件历史上限

注意: 每个测试用例都必须先调 monitor.heartbeat() 或立刻 check(),
      避免真实时间流逝触发通信超时分支干扰断言。
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.mission.safety import FailsafeMonitor, SafetyLevel


def _fresh() -> FailsafeMonitor:
    """新建监控器 (心跳时间 = 现在, 不会误触发超时)"""
    return FailsafeMonitor()


def test_normal_state():
    """正常状态 → OK"""
    print("[TEST] 正常状态")
    m = _fresh()
    e = m.check(battery=80, attitude=[5, 2, 1], height=200)
    assert e.level == SafetyLevel.OK
    assert m.active_level == SafetyLevel.OK
    assert m.can_recover()
    print("  [PASS]")


def test_battery_warn():
    """电量偏低 → WARN (不干预飞行)"""
    print("[TEST] 电量WARN")
    m = _fresh()
    e = m.check(battery=15, attitude=[0, 0, 0], height=100)  # 默认阈值: warn=20
    assert e.level == SafetyLevel.WARN
    assert "电量" in e.reason
    assert m.can_recover(), "WARN 应可恢复"
    print("  原因: {}".format(e.reason))
    print("  [PASS]")


def test_battery_land():
    """低电量 → LAND (自动降落, 可恢复语义)"""
    print("[TEST] 低电量LAND")
    m = _fresh()
    e = m.check(battery=8, attitude=[0, 0, 0], height=100)   # 默认阈值: land=10
    assert e.level == SafetyLevel.LAND
    assert "低电量" in e.reason
    print("  原因: {}".format(e.reason))
    print("  [PASS]")


def test_battery_kill():
    """电量危急 → KILL (需手动 reset)"""
    print("[TEST] 电量KILL")
    m = _fresh()
    e = m.check(battery=3, attitude=[0, 0, 0], height=100)   # 默认阈值: kill=5
    assert e.level == SafetyLevel.KILL
    assert "电量危急" in e.reason
    assert not m.can_recover(), "KILL 不应自动恢复"
    print("  原因: {}".format(e.reason))
    print("  [PASS]")


def test_attitude_land_and_kill():
    """姿态异常 → LAND; 姿态危急 → KILL"""
    print("[TEST] 姿态两级")
    m = _fresh()
    e = m.check(battery=80, attitude=[35, 0, 0], height=100)  # land=30°
    assert e.level == SafetyLevel.LAND
    assert "姿态" in e.reason

    m2 = _fresh()
    e2 = m2.check(battery=80, attitude=[65, 0, 0], height=100)  # kill=60°
    assert e2.level == SafetyLevel.KILL
    print("  [PASS]")


def test_height_land_and_kill():
    """高度超限 → LAND; 高度危急 → KILL"""
    print("[TEST] 高度两级")
    m = _fresh()
    e = m.check(battery=80, attitude=[0, 0, 0], height=350)   # land=300cm
    assert e.level == SafetyLevel.LAND
    assert "高度" in e.reason

    m2 = _fresh()
    e2 = m2.check(battery=80, attitude=[0, 0, 0], height=600)  # kill=500cm
    assert e2.level == SafetyLevel.KILL
    print("  [PASS]")


def test_timeout_land_and_kill():
    """心跳超时: >1s LAND, >3s KILL (默认值)"""
    print("[TEST] 心跳超时两级")
    m = _fresh()
    m._last_heartbeat = time.time() - 1.5   # 模拟 1.5s 无心跳
    e = m.check(battery=80, attitude=[0, 0, 0], height=100)
    assert e.level == SafetyLevel.LAND
    assert "通信" in e.reason

    m2 = _fresh()
    m2._last_heartbeat = time.time() - 3.5  # 模拟 3.5s 无心跳
    e2 = m2.check(battery=80, attitude=[0, 0, 0], height=100)
    assert e2.level == SafetyLevel.KILL
    assert "通信中断" in e2.reason
    print("  [PASS]")


def test_heartbeat_prevents_timeout():
    """heartbeat() 每帧调用则永不触发超时 — 回归 A1 Bug"""
    print("[TEST] heartbeat 防超时 (A1回归)")
    m = _fresh()
    for _ in range(5):
        m.heartbeat()
        e = m.check(battery=80, attitude=[0, 0, 0], height=100)
        assert e.level == SafetyLevel.OK, "有心跳时不应误报超时"
    print("  [PASS]")


def test_reset_recovers_from_kill():
    """KILL 后 reset() 恢复"""
    print("[TEST] reset 恢复")
    m = _fresh()
    m.check(battery=3, attitude=[0, 0, 0], height=100)
    assert m.active_level == SafetyLevel.KILL

    m.reset()
    assert m.active_level == SafetyLevel.OK
    assert m.active_reason == ""
    e = m.check(battery=80, attitude=[0, 0, 0], height=100)
    assert e.level == SafetyLevel.OK
    print("  [PASS]")


def test_thresholds_per_instance():
    """实例级 THRESHOLDS 修改不污染其他实例 (跨测试泄漏回归)"""
    print("[TEST] THRESHOLDS 实例隔离")
    m1 = _fresh()
    m1.THRESHOLDS["battery_kill"] = 50

    m2 = _fresh()
    assert m2.THRESHOLDS["battery_kill"] == 5, "类默认被实例修改污染!"

    e = m2.check(battery=30, attitude=[0, 0, 0], height=100)
    assert e.level != SafetyLevel.KILL, "m1 的阈值修改泄漏到了 m2"
    print("  [PASS]")


def test_event_history_capped():
    """事件历史保留最近20条"""
    print("[TEST] 事件历史上限")
    m = _fresh()
    for _ in range(30):
        m.heartbeat()  # 避免超时分支
        m.check(battery=15, attitude=[0, 0, 0], height=100)  # WARN
    assert len(m._event_history) == 20
    print("  [PASS]")


def test_kill_priority_over_land():
    """多项同时超限时取最高级别 (KILL > LAND > WARN)"""
    print("[TEST] 级别优先级")
    m = _fresh()
    # 同时: 电量3%(KILL) + 姿态35°(LAND) + 电量也<20%(WARN)
    e = m.check(battery=3, attitude=[35, 0, 0], height=100)
    assert e.level == SafetyLevel.KILL, "应取最高级别"
    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  FailsafeMonitor 测试套件")
    print("=" * 50)
    test_normal_state()
    test_battery_warn()
    test_battery_land()
    test_battery_kill()
    test_attitude_land_and_kill()
    test_height_land_and_kill()
    test_timeout_land_and_kill()
    test_heartbeat_prevents_timeout()
    test_reset_recovers_from_kill()
    test_thresholds_per_instance()
    test_event_history_capped()
    test_kill_priority_over_land()
    print("\n[OK] 所有安全监控测试通过!")
