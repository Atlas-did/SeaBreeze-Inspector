#!/usr/bin/env python3
"""End-to-end runtime test - full state sequence through SimRuntime."""

import sys
import numpy as np
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.simulation.models import Quadrotor3D, WindDisturbance, RobotArm3DOF, VirtualSensor
from backend.main import MissionController
from backend.runtime.loop import SimRuntime


def _make_runtime():
    quad = Quadrotor3D()
    wind = WindDisturbance(base_wind=np.array([0.05, 0.02, 0.0]), freq=0.3, gust_amp=0.03)
    arm = RobotArm3DOF()
    sensor = VirtualSensor()
    mc = MissionController(mode='simulation', mock=True)
    return SimRuntime(mc, quad, wind, arm, sensor)


def _hover_wind_xy_err(cascade_ff, n=900, seed=11):
    """起飞后在侧风下悬停，返回稳态 XY 误差均值（最后 300 步）。"""
    np.random.seed(seed)
    quad = Quadrotor3D()
    wind = WindDisturbance(base_wind=np.array([0.05, 0.04, 0.0]), freq=0.3, gust_amp=0.02)
    arm = RobotArm3DOF()
    sensor = VirtualSensor()
    mc = MissionController(mode='simulation', mock=True)
    rt = SimRuntime(mc, quad, wind, arm, sensor, cascade_feedforward=cascade_ff)
    mc.video_stream.stop()
    mc.video_stream._running = False
    for i in range(n):
        rt.step(0.02, {'Space'} if i == 50 else set())
    errs = []
    tgt = np.array(mc.target_pos) / 100.0
    for _ in range(300):
        rt.step(0.02, set())
        errs.append(float(np.linalg.norm(quad.get_position()[:2] - tgt[:2])))
    return float(np.mean(errs))


def test_feedforward_actually_reduces_wind_error():
    """P0-1 回归：级联前馈必须真正作用于物理，并显著降低抗风稳态误差。

    修复前：mc 的 PID+前馈输出被 update_with_external_data 每帧覆盖，
    级联环不知道 d̂ 存在，开/关前馈轨迹逐位相同（评审实测 A==C）。
    修复后：cascade_feedforward=True 时级联环吃掉 d̂ 做前馈抵消。

    注：默认 cascade_feedforward=False 是刻意的 —— 本仓库硬要求"默认路径
    逐位不变"（已发表数字来自默认路径），见 test_transport_model 的 golden 测试。
    另注：风加速度若超过 MAX_ACCEL 会饱和，此时前馈收益甚微（物理边界），
    故本测试选用不饱和的侧风。
    """
    err_off = _hover_wind_xy_err(False)
    err_on = _hover_wind_xy_err(True)
    assert err_on < err_off, (
        "前馈接通后抗风误差应下降：off={:.4f} on={:.4f}".format(err_off, err_on))
    reduction = (err_off - err_on) / max(err_off, 1e-9)
    assert reduction > 0.20, (
        "前馈应把抗风稳态误差降低 >20%，实测 {:.1f}%".format(reduction * 100))


class TestSimRuntime:
    def test_initial_state_is_idle(self):
        rt = _make_runtime()
        data = rt.step(0.02, set())
        assert data['state'] == 'IDLE'
        assert data['pos'] == [0.0, 0.0, 0.0]

    def test_takeoff_transition(self):
        rt = _make_runtime()
        rt.step(0.02, {'Space'})
        assert rt.mc.state == 'TAKEOFF'  # 规范名 (非 TAKING_OFF)

    def test_takeoff_reaches_hover(self):
        rt = _make_runtime()
        rt.step(0.02, {'Space'})
        for _ in range(200):
            data = rt.step(0.02, set())
            if data['state'] == 'HOVERING':
                break
        assert data['state'] == 'HOVERING'
        assert data['pos'][2] >= 0.9  # z-up: near hover height (EKF may lead physics by ~10cm)

    def test_emergency_descent(self):
        rt = _make_runtime()
        rt.step(0.02, {'Space'})
        for _ in range(200):
            rt.step(0.02, set())
        rt.step(0.02, {'KeyE'})
        assert rt.mc.state == 'EMERGENCY'
        for _ in range(200):
            data = rt.step(0.02, set())
            if data['state'] == 'IDLE':
                break
        assert data['state'] == 'IDLE'
        assert data['pos'][2] < 0.05  # near ground (TOUCHDOWN_HEIGHT threshold)

    def test_reset_from_flight(self):
        rt = _make_runtime()
        rt.step(0.02, {'Space'})
        for _ in range(200):
            rt.step(0.02, set())
        rt.step(0.02, {'KeyR'})
        # reset_mission triggers emergency → next frame EMERGENCY→IDLE
        assert rt.mc.state in ('EMERGENCY', 'IDLE')
        data = rt.step(0.02, set())
        assert data['state'] == 'IDLE'
        assert np.allclose(data['pos'], [0.0, 0.0, 0.0], atol=1e-3)

    def test_arm_control(self):
        rt = _make_runtime()
        rt.step(0.02, {'ArrowLeft'})
        data = rt.step(0.02, set())
        angles = data['arm_angles']
        assert angles[0] != 90.0  # base should have moved

    def test_flight_log_grows(self):
        rt = _make_runtime()
        rt.step(0.02, {'Space'})
        data = rt.step(0.02, set())
        assert len(data['flight_log']) >= 2  # SIM_INIT + TAKEOFF

    def test_mission_full_sequence(self):
        rt = _make_runtime()
        rt.step(0.02, {'Space'})
        for _ in range(200):
            data = rt.step(0.02, set())
            if data['state'] == 'HOVERING':
                break
        assert data['state'] == 'HOVERING'
        rt.step(0.02, {'KeyM'})
        assert rt.mc.state == 'NAVIGATE'
        # P0-5 后 KeyM 走 RRT*（多点路径，含绕障采样），航程比原来的两点直线长，
        # 因此步数预算需相应放宽。
        assert rt.mc.path is not None and len(rt.mc.path) > 2, \
            'KeyM 应经 RRT* 规划出多点路径，实际 {} 点'.format(
                0 if rt.mc.path is None else len(rt.mc.path))
        for _ in range(1500):
            data = rt.step(0.02, set())
            if data['state'] in ('INSPECT', 'RETURNING', 'LANDING', 'IDLE'):
                break
        assert data['state'] != 'NAVIGATE'


if __name__ == "__main__":
    print("=" * 50)
    print("  SimRuntime end-to-end tests")
    print("=" * 50)
    t = TestSimRuntime()
    t.test_initial_state_is_idle()
    print('  [PASS] initial state')
    t.test_takeoff_transition()
    print('  [PASS] takeoff transition')
    t.test_takeoff_reaches_hover()
    print('  [PASS] takeoff reaches hover')
    t.test_emergency_descent()
    print('  [PASS] emergency descent')
    t.test_reset_from_flight()
    print('  [PASS] reset from flight')
    t.test_arm_control()
    print('  [PASS] arm control')
    t.test_flight_log_grows()
    print('  [PASS] flight log')
    t.test_mission_full_sequence()
    print('  [PASS] mission full sequence')
    print("\n[OK] All runtime tests passed!")


import pytest  # noqa: E402  (审计 D16: pytestmark 需要它)


# 审计 D16: 逐帧驱动 runtime/mission 的用例不得让**墙钟**参与判定
# (慢 runner 上心跳间隔可能真的超过 timeout_land=1.0s -> 安全层跳闸 -> 断言失真)
pytestmark = pytest.mark.no_wall_clock
