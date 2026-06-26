#!/usr/bin/env python3
"""
主调度器状态机测试 — mock 模式下验证 8 状态转换覆盖
"""

import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import MissionController


def test_initial_state():
    """初始状态应为 IDLE"""
    print("[TEST] 初始状态")
    mc = MissionController(mode="simulation", mock=True)
    assert mc.state == "IDLE", "初始状态应为IDLE, 实际={}".format(mc.state)
    print("  state={}".format(mc.state))
    print("  [PASS]")


def test_idle_to_takeoff():
    """IDLE → TAKEOFF 转换"""
    print("[TEST] IDLE → TAKEOFF")
    mc = MissionController(mode="simulation", mock=True)
    result = mc.takeoff(height=100)
    assert result is True
    assert mc.state == "TAKEOFF", "应为TAKEOFF, 实际={}".format(mc.state)
    print("  [PASS]")


def test_takeoff_to_hovering():
    """TAKEOFF → HOVERING (模拟起飞完成)"""
    print("[TEST] TAKEOFF → HOVERING")
    mc = MissionController(mode="simulation", mock=True)
    mc.takeoff(height=100)

    # 模拟无人机已连接并起飞
    mc.drone.connect()
    mc.drone.takeoff()  # IDLE → CONNECTING → CONNECTED → TAKEOFF → HOVERING
    mc.drone._height = 100
    mc.current_pos[2] = 100  # 达到目标高度

    # 手动触发一帧状态机 — TelloController已处于飞行状态
    disturbance = np.zeros(3)
    mc._handle_state_machine(disturbance)

    assert mc.state == "HOVERING", "应为HOVERING, 实际={}".format(mc.state)
    print("  [PASS]")


def test_hovering_to_navigate():
    """HOVERING → NAVIGATE (有路径时)"""
    print("[TEST] HOVERING → NAVIGATE")
    mc = MissionController(mode="simulation", mock=True)
    mc.state = "HOVERING"
    mc.path = np.array([[0, 0, 100], [10, 10, 100], [20, 20, 100]])
    mc.path_idx = 0

    disturbance = np.zeros(3)
    mc._handle_state_machine(disturbance)
    assert mc.state == "NAVIGATE", "应为NAVIGATE, 实际={}".format(mc.state)
    print("  [PASS]")


def test_navigate_to_inspect():
    """NAVIGATE → INSPECT (路径走完)"""
    print("[TEST] NAVIGATE → INSPECT")
    mc = MissionController(mode="simulation", mock=True)
    mc.state = "NAVIGATE"
    mc.path = np.array([[0, 0, 100], [10, 10, 100]])
    mc.path_idx = 2  # 已过最后一点

    disturbance = np.zeros(3)
    mc._handle_state_machine(disturbance)
    assert mc.state == "INSPECT", "应为INSPECT, 实际={}".format(mc.state)
    print("  [PASS]")


def test_inspect_to_return():
    """INSPECT → RETURN (超时)"""
    print("[TEST] INSPECT → RETURN (超时)")
    mc = MissionController(mode="simulation", mock=True)
    mc.state = "INSPECT"
    mc._state_entry_time = time.time() - 31  # 31秒前

    disturbance = np.zeros(3)
    mc._handle_state_machine(disturbance)
    assert mc.state == "RETURN", "应为RETURN, 实际={}".format(mc.state)
    print("  [PASS]")


def test_return_to_land():
    """RETURN → LAND (到达返航点)"""
    print("[TEST] RETURN → LAND")
    mc = MissionController(mode="simulation", mock=True)
    mc.state = "RETURN"
    mc.current_pos = np.array([0, 0, 100])  # 已在返航点

    disturbance = np.zeros(3)
    mc._handle_state_machine(disturbance)
    assert mc.state == "LAND", "应为LAND, 实际={}".format(mc.state)
    print("  [PASS]")


def test_land_to_idle():
    """LAND → IDLE (降落完成)"""
    print("[TEST] LAND → IDLE")
    mc = MissionController(mode="simulation", mock=True)
    mc.state = "LAND"

    from backend.drone.tello_basic import FlightState
    # 模拟已经降落: drone不再是飞行状态, 高度为0
    mc.drone.state = FlightState.IDLE  # flight state reset
    mc.current_pos[2] = 0

    disturbance = np.zeros(3)
    mc._handle_state_machine(disturbance)
    assert mc.state == "IDLE", "应为IDLE, 实际={}".format(mc.state)
    print("  [PASS]")


def test_trigger_emergency():
    """任意状态 → EMERGENCY"""
    print("[TEST] 触发 EMERGENCY")
    mc = MissionController(mode="simulation", mock=True)
    mc.state = "NAVIGATE"

    mc.trigger_emergency("测试紧急停止")
    assert mc.state == "EMERGENCY", "应为EMERGENCY, 实际={}".format(mc.state)
    assert mc._emergency_reason == "测试紧急停止"
    print("  [PASS]")


def test_safety_guard_integrated():
    """SafetyGuard 已集成并在低电量时触发"""
    print("[TEST] SafetyGuard 集成验证")
    mc = MissionController(mode="simulation", mock=True)
    mc.state = "HOVERING"
    mc._battery = 5  # 低电量

    # _check_safety 应触发
    triggered = mc._check_safety()
    assert triggered is True, "低电量应触发紧急"
    assert mc.state == "EMERGENCY"
    print("  [PASS]")


def test_logger_integrated():
    """FlightLogger 已集成"""
    print("[TEST] FlightLogger 集成验证")
    mc = MissionController(mode="simulation", mock=True)
    assert mc.logger is not None, "应存在 logger 实例"
    assert not mc.logger.is_recording, "初始不应在录制中"
    print("  [PASS]")


def test_video_stream_integrated():
    """VideoStream 已集成"""
    print("[TEST] VideoStream 集成验证")
    mc = MissionController(mode="simulation", mock=True)
    assert mc.video_stream is not None, "应存在 video_stream 实例"
    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  主调度器状态机测试套件")
    print("=" * 50)
    test_initial_state()
    test_idle_to_takeoff()
    test_takeoff_to_hovering()
    test_hovering_to_navigate()
    test_navigate_to_inspect()
    test_inspect_to_return()
    test_return_to_land()
    test_land_to_idle()
    test_trigger_emergency()
    test_safety_guard_integrated()
    test_logger_integrated()
    test_video_stream_integrated()
    print("\n[OK] 所有状态机测试通过!")
