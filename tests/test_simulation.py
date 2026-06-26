#!/usr/bin/env python3
"""
仿真引擎测试 — 物理步进正确性、键盘事件、风扰动模拟
"""

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.simulation.models import (
    Quadrotor3D, WindDisturbance, VirtualSensor, WindTurbine, RobotArm3DOF,
)


# =========================================================================
# 测试 1: Quadrotor3D 物理步进
# =========================================================================

def test_quadrotor_physics():
    """验证四旋翼动力学模型的基本正确性"""
    print("[TEST] Quadrotor3D 物理步进")

    quad = Quadrotor3D(mass=0.087, dt=0.1)

    # 悬停推力 = mass * g
    hover_thrust = quad.mass * quad.g  # ~0.853 N
    control = np.array([hover_thrust, 0, 0, 0])

    # 单步推进
    quad.step(control)
    pos = quad.get_position()
    vel = quad.get_velocity()

    # 悬停时, 垂直加速度应接近0 (推力=重力)
    # 位置变化应很小
    assert pos[2] >= 0, "高度不应为负"
    print("  悬停步进: pos=({:.3f},{:.3f},{:.3f}), vel=({:.3f},{:.3f},{:.3f})".format(
        pos[0], pos[1], pos[2], vel[0], vel[1], vel[2]
    ))

    # 重置, 测试零推力 (应该下落)
    quad2 = Quadrotor3D(mass=0.087, dt=0.1)
    quad2.state[2] = 1.0  # 从1m高度
    quad2.step(np.array([0, 0, 0, 0]))
    assert quad2.get_velocity()[2] < 0, "零推力时应下落 (重力加速度)"
    print("  零推力下落: vel_z={:.3f} (期望<0)".format(quad2.get_velocity()[2]))

    print("  [PASS]")


def test_quadrotor_acceleration_stored():
    """验证加速度在 step() 后被正确存储"""
    print("[TEST] 加速度存储")

    quad = Quadrotor3D(mass=0.087, dt=0.1)
    quad.step(np.array([quad.mass * quad.g, 0, 0, 0]))

    acc = quad.get_acceleration()
    assert acc.shape == (3,), "加速度应为3维向量"
    assert np.all(np.isfinite(acc)), "加速度应有限"
    print("  存储的加速度: ({:.3f},{:.3f},{:.3f}) m/s^2".format(acc[0], acc[1], acc[2]))
    print("  [PASS]")


# =========================================================================
# 测试 2: WindDisturbance 风扰动
# =========================================================================

def test_wind_disturbance():
    """验证风扰动模型的周期性和范围"""
    print("[TEST] WindDisturbance 风扰动")

    wind = WindDisturbance(
        base_wind=np.array([0.05, 0.02, 0.0]),
        freq=0.5,
        gust_amp=0.03,
    )

    samples = []
    for _ in range(20):
        samples.append(wind.sample(0.1))

    samples = np.array(samples)

    # 风扰动应在合理范围内
    assert samples.shape == (20, 3), "采样维度错误"
    assert np.all(np.isfinite(samples)), "风扰动应有限"
    # 阵风分量应周期性变化
    assert np.std(samples[:, 0]) > 0, "阵风应有变化"
    print("  20步风扰动: mean=({:.4f},{:.4f},{:.4f}), std=({:.4f},{:.4f},{:.4f})".format(
        samples[:, 0].mean(), samples[:, 1].mean(), samples[:, 2].mean(),
        samples[:, 0].std(), samples[:, 1].std(), samples[:, 2].std(),
    ))
    print("  [PASS]")


# =========================================================================
# 测试 3: VirtualSensor 传感器噪声
# =========================================================================

def test_virtual_sensor():
    """验证虚拟传感器的噪声模型和读数正确性"""
    print("[TEST] VirtualSensor 传感器")

    quad = Quadrotor3D(mass=0.087, dt=0.1)
    quad.state[2] = 1.0  # 1m高度
    quad.step(np.array([quad.mass * quad.g, 0, 0, 0]))

    sensor = VirtualSensor(imu_noise=0.05, opt_noise=2.0, bar_noise=10.0)

    # IMU 读数
    imu = sensor.read_imu(quad)
    assert imu.shape == (3,), "IMU应为3维"
    print("  IMU: ({:.3f},{:.3f},{:.3f}) m/s^2".format(imu[0], imu[1], imu[2]))

    # 光流读数
    opt = sensor.read_optical(quad)
    assert opt.shape == (2,), "光流应为2维"
    # 高度1m = 100cm
    assert abs(opt[1]) < 200, "光流位置应在合理范围"
    print("  光流: ({:.1f},{:.1f}) cm".format(opt[0], opt[1]))

    # 气压计读数
    bar = sensor.read_barometer(quad)
    # 1m = 100cm, 允许噪声偏移
    assert 80 < bar < 120, "气压计高度应接近100cm"
    print("  气压计: {:.1f} cm".format(bar))

    # read_all
    all_data = sensor.read_all(quad)
    assert "ekf_z" in all_data, "应包含 ekf_z"
    assert all_data["ekf_z"].shape == (6,), "ekf_z应为6维"
    print("  read_all: ekf_z shape={}".format(all_data["ekf_z"].shape))

    print("  [PASS]")


# =========================================================================
# 测试 4: WindTurbine 碰撞检测
# =========================================================================

def test_wind_turbine_collision():
    """验证风机塔筒碰撞检测"""
    print("[TEST] WindTurbine 碰撞检测")

    turbine = WindTurbine(center_xy=(0, 0), radius=3.0, height=30.0)

    # 内部点
    inside = np.array([1.0, 1.0, 10.0])
    assert turbine.check_collision(inside), "塔筒内部点应检测到碰撞"

    # 外部点 (水平超出)
    outside_h = np.array([5.0, 5.0, 10.0])
    assert not turbine.check_collision(outside_h), "塔筒水平外应无碰撞"

    # 外部点 (高度超出)
    outside_v = np.array([1.0, 1.0, 35.0])
    assert not turbine.check_collision(outside_v), "塔筒高度外应无碰撞"

    # 表面点
    surface = turbine.get_surface_point(angle_deg=0, height_m=15, offset=1.0)
    assert abs(surface[0] - 4.0) < 0.1, "表面点X={:.1f}应接近4.0m".format(surface[0])

    print("  碰撞检测 PASS")
    print("  [PASS]")


# =========================================================================
# 测试 5: RobotArm3DOF 仿真模型
# =========================================================================

def test_robot_arm_model():
    """验证机械臂仿真模型"""
    print("[TEST] RobotArm3DOF 仿真模型")

    arm = RobotArm3DOF(L1=55, L2=45, L3=35)

    # 默认姿态下末端位置
    endpoint = arm.get_endpoint()
    assert endpoint.shape == (3,), "末端位置应为3维"
    print("  默认姿态末端: ({:.3f},{:.3f},{:.3f}) m".format(
        endpoint[0], endpoint[1], endpoint[2]
    ))

    # 改变角度
    arm.set_angles([90, 60, 90])
    endpoint2 = arm.get_endpoint()
    assert not np.allclose(endpoint, endpoint2), "改变角度后末端应移动"

    # 角度限幅
    arm.set_angles([200, -50, 300])  # 超出范围
    assert 0 <= arm.angles[0] <= 180, "theta1应在[0,180]"
    assert 30 <= arm.angles[1] <= 150, "theta2应在[30,150]"
    assert 0 <= arm.angles[2] <= 135, "theta3应在[0,135]"
    print("  角度限幅: ({},{},{})".format(arm.angles[0], arm.angles[1], arm.angles[2]))

    print("  [PASS]")


# =========================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  仿真引擎测试套件")
    print("=" * 50)
    test_quadrotor_physics()
    test_quadrotor_acceleration_stored()
    test_wind_disturbance()
    test_virtual_sensor()
    test_wind_turbine_collision()
    test_robot_arm_model()
    print("\n[OK] 所有仿真测试通过!")
