#!/usr/bin/env python3
"""
端到端仿真集成测试 — Mock 模式下跑通完整巡检任务流程

流程: IDLE → TAKEOFF → HOVERING → NAVIGATE(RRT*) → INSPECT → RETURN → LAND
"""

import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import MissionController


def run_state_step(mc, n_steps=5):
    """直接驱动状态机 (跳过EKF更新, 用于状态转移测试)"""
    disturbance = np.zeros(3)
    for _ in range(n_steps):
        mc._handle_state_machine(disturbance)


def test_full_mission_flow():
    """完整任务流程: IDLE → TAKEOFF → HOVERING → NAVIGATE → INSPECT → RETURN → LAND → IDLE"""
    print("[TEST] 完整任务流程 (E2E)")
    mc = MissionController(mode="simulation", mock=True)

    # ---- 1. IDLE ----
    assert mc.state == "IDLE"
    print("  [1/8] IDLE OK")

    # ---- 2. TAKEOFF: 起飞到100cm ----
    mc.takeoff(height=100)
    assert mc.state == "TAKEOFF"
    # 连接并起飞 TelloController
    mc.drone.connect()
    mc.drone.takeoff()
    # 模拟高度达到100cm
    mc.current_pos[2] = 100
    run_state_step(mc, n_steps=3)
    assert mc.state == "HOVERING", "起飞后应进入HOVERING, 实际={}".format(mc.state)
    print("  [2/8] TAKEOFF → HOVERING OK")

    # ---- 3. HOVERING: 规划路径后自动进入NAVIGATE ----
    mc.plan_path(
        start=[0, 0, 100],
        goal=[50, 30, 150],
        obstacles=[],
    )
    run_state_step(mc, n_steps=1)
    assert mc.state == "NAVIGATE", "有路径后应进入NAVIGATE, 实际={}".format(mc.state)
    print("  [3/8] HOVERING → NAVIGATE OK (路径点数={})".format(len(mc.path)))

    # ---- 4. NAVIGATE: 快速走完路径 ----
    for _ in range(len(mc.path) + 2):
        # 模拟到达每个路径点
        if mc.path_idx < len(mc.path):
            mc.current_pos = mc.path[mc.path_idx].copy()
        run_state_step(mc, n_steps=1)
    assert mc.state == "INSPECT", "路径走完后应进入INSPECT, 实际={}".format(mc.state)
    print("  [4/8] NAVIGATE → INSPECT OK")

    # ---- 5. INSPECT: 模拟巡检30秒超时 ----
    run_state_step(mc, n_steps=2)
    # 手动快进
    mc._state_entry_time = time.time() - 31
    run_state_step(mc, n_steps=1)
    assert mc.state == "RETURN", "巡检超时后应进入RETURN, 实际={}".format(mc.state)
    print("  [5/8] INSPECT → RETURN OK (超时触发)")

    # ---- 6. RETURN: 模拟到达返航点 ----
    mc.current_pos = np.array([0, 0, 100])  # 返航点
    run_state_step(mc, n_steps=1)
    assert mc.state == "LAND", "到达返航点后应进入LAND, 实际={}".format(mc.state)
    print("  [6/8] RETURN → LAND OK")

    # ---- 7. LAND: 模拟降落完成 (LAND处理器一次调用即完成降落) ----
    from backend.drone.tello_basic import FlightState
    mc.current_pos[2] = 0
    mc.drone.state = FlightState.IDLE  # drone 已不在飞行状态
    run_state_step(mc, n_steps=1)
    assert mc.state == "IDLE", "降落后应进入IDLE, 实际={}".format(mc.state)
    print("  [7/8] LAND → IDLE OK")

    # ---- 8. 验证全程无EMERGENCY ----
    assert mc.state == "IDLE"
    print("  [8/8] 全流程完成, 状态={}".format(mc.state))
    print("  [PASS]")


def test_emergency_interrupt():
    """任务中任意阶段触发 EMERGENCY 应打断正常流程"""
    print("[TEST] EMERGENCY 中断测试")
    mc = MissionController(mode="simulation", mock=True)

    # 进入 NAVIGATE
    mc.state = "NAVIGATE"
    mc.drone.connect()
    mc.drone.takeoff()

    # 触发电量紧急
    mc._battery = 5
    triggered = mc._check_safety()
    assert triggered is True
    assert mc.state == "EMERGENCY"
    assert "电量" in mc._emergency_reason
    print("  触发原因: {}".format(mc._emergency_reason))

    # EMERGENCY 处理
    from backend.drone.tello_basic import FlightState
    mc.drone.state = FlightState.IDLE  # 模拟已停止
    run_state_step(mc, n_steps=2)
    assert mc.state == "IDLE", "EMERGENCY降落后应回到IDLE"
    print("  [PASS]")


def test_logger_records_data():
    """FlightLogger 在任务中正确记录数据"""
    print("[TEST] FlightLogger 数据记录")
    mc = MissionController(mode="simulation", mock=True)

    mc.logger.start_session()
    assert mc.logger.is_recording

    # 记录几帧
    for _ in range(5):
        mc._log_frame(
            disturbance=np.array([1.0, 0.5, 0.0]),
            detections=[
                {"class_name": "crack", "confidence": 0.85, "bbox": [10, 10, 50, 50]}
            ],
        )

    log_path = mc.logger.save()
    assert log_path.exists(), "日志文件应存在"
    assert mc.logger.total_frames == 5
    print("  记录 {} 帧到 {}".format(mc.logger.total_frames, log_path.name))
    print("  [PASS]")


def test_graceful_shutdown():
    """优雅关闭: stop() 不抛异常"""
    print("[TEST] 优雅关闭")
    mc = MissionController(mode="simulation", mock=True)
    mc.logger.start_session()

    # 模拟飞行中停止
    mc.state = "HOVERING"
    mc.drone.connect()
    mc.drone.takeoff()

    try:
        mc.stop()
        assert not mc._running
        assert not mc.logger.is_recording  # 日志已保存
    except Exception as e:
        assert False, "stop() 失败: {}".format(e)

    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 60)
    print("  端到端仿真集成测试套件")
    print("=" * 60)
    test_full_mission_flow()
    test_emergency_interrupt()
    test_logger_records_data()
    test_graceful_shutdown()
    print("\n[OK] 所有端到端测试通过!")
