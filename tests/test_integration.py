#!/usr/bin/env python3
"""
集成测试 — 验证各模块间接口

测试内容:
  1. EKF + 控制器: 扰动估计 → 前馈补偿闭环
  2. 机械臂FK/IK: 正逆运动学一致性
  3. 路径规划: RRT*能成功规划路径
  4. 安全守护: 异常状态检测
"""

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.disturbance_observer import DisturbanceObserverEKF
from backend.core.feedforward_controller import FeedforwardController
from backend.arm.arm_kinematics import FK, IK
from backend.core.trajectory_planning import RRTStarPlanner
from backend.mission.safety import FailsafeMonitor, SafetyLevel


def test_ekf_controller_loop():
    """测试EKF+控制器闭环"""
    print("[TEST] EKF+控制器闭环测试")

    dt = 0.1
    n_steps = 100
    ekf = DisturbanceObserverEKF(dt=dt)
    ctrl = FeedforwardController(Kp=1.0, Ki=0.05, Kd=0.5, Kff=1.0, dt=dt)

    target = np.array([50.0, 0.0, 100.0])
    pos = np.zeros(3)

    for k in range(n_steps):
        disturbance = np.array([5.0, 0.0, 0.0])

        # 模拟观测
        z = np.array([disturbance[0], 0, 0, pos[0], pos[1], pos[2]])
        z[:3] += disturbance  # IMU = a + d

        # EKF
        ekf.predict(u=np.zeros(3))
        ekf.update(z)
        d_est = ekf.get_disturbance()

        # 控制器
        output, info = ctrl.compute(target, pos, disturbance_est=d_est)
        pos += output * dt

    err = np.linalg.norm(target - pos)
    print(f"  最终误差: {err:.1f}cm")
    assert err < 20, f"闭环误差{err}过大"
    print("  [PASS]")


def test_arm_fk_ik():
    """测试机械臂正逆运动学一致性"""
    print("[TEST] 机械臂FK/IK一致性测试")

    for t1 in [45, 90, 135]:
        for t2 in [60, 90, 120]:
            for t3 in [30, 60, 90]:
                pos = FK(t1, t2, t3)
                angles = IK(pos[0], pos[1], pos[2])
                pos2 = FK(angles[0], angles[1], angles[2])
                err = np.linalg.norm(pos - pos2)
                assert err < 5.0, f"FK/IK不一致: {err:.1f}mm"

    print("  [PASS] 所有角度组合FK/IK一致")


def test_rrt_star():
    """测试RRT*路径规划"""
    print("[TEST] RRT*路径规划测试")

    planner = RRTStarPlanner(max_iter=200)
    start = np.array([0.0, 0.0, 100.0])
    goal = np.array([200.0, 100.0, 100.0])
    obstacles = [(np.array([100.0, 50.0, 100.0]), 40.0)]

    path = planner.plan(start, goal, obstacles)
    assert path is not None, "RRT*规划失败"
    assert len(path) > 1, "路径太短"

    # 验证起点和终点
    assert np.linalg.norm(path[0] - start) < 50, "起点不匹配"
    assert np.linalg.norm(path[-1] - goal) < 50, "终点不匹配"

    print(f"  路径点数: {len(path)}, 长度: {np.sum(np.linalg.norm(np.diff(path, axis=0), axis=1)):.1f}cm")
    print("  [PASS]")


def test_safety_guard():
    """测试安全守护"""
    print("[TEST] 安全守护测试")

    guard = FailsafeMonitor()

    # 正常状态
    e = guard.check(battery=50, attitude=[0, 0, 0], height=100)
    assert e.level == SafetyLevel.OK

    # 低电量 (默认阈值 land=10, kill=5 → battery=3 触发 KILL)
    guard.heartbeat()
    e = guard.check(battery=3, attitude=[0, 0, 0], height=100)
    assert e.level == SafetyLevel.KILL
    assert "电量" in e.reason

    guard.reset()

    # 姿态异常
    guard.heartbeat()
    e = guard.check(battery=50, attitude=[40, 0, 0], height=100)
    assert e.level == SafetyLevel.LAND  # 默认 attitude_land=30°, kill=60°

    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  集成测试套件")
    print("=" * 50)
    test_ekf_controller_loop()
    test_arm_fk_ik()
    test_rrt_star()
    test_safety_guard()
    print("\\n[OK] 所有集成测试通过!")
