#!/usr/bin/env python3
"""End-to-end runtime test - full state sequence through SimRuntime."""

import sys, time, numpy as np
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
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


class TestSimRuntime:
    def test_initial_state_is_idle(self):
        rt = _make_runtime()
        data = rt.step(0.02, set())
        assert data['state'] == 'IDLE'
        assert data['pos'] == [0.0, 0.0, 0.0]

    def test_takeoff_transition(self):
        rt = _make_runtime()
        rt.step(0.02, {'Space'})
        assert rt._sim_state == 'TAKING_OFF'

    def test_takeoff_reaches_hover(self):
        rt = _make_runtime()
        rt.step(0.02, {'Space'})
        for _ in range(200):
            data = rt.step(0.02, set())
            if data['state'] == 'HOVERING':
                break
        assert data['state'] == 'HOVERING'
        assert data['pos'][2] >= 1.0  # z-up: height at pos[2]

    def test_emergency_descent(self):
        rt = _make_runtime()
        rt.step(0.02, {'Space'})
        for _ in range(200):
            rt.step(0.02, set())
        rt.step(0.02, {'KeyE'})
        assert rt._sim_state == 'EMERGENCY'
        for _ in range(200):
            data = rt.step(0.02, set())
            if data['state'] == 'IDLE':
                break
        assert data['state'] == 'IDLE'
        assert data['pos'][2] < 0.02  # near-zero (float precision)

    def test_reset_from_flight(self):
        rt = _make_runtime()
        rt.step(0.02, {'Space'})
        for _ in range(200):
            rt.step(0.02, set())
        rt.step(0.02, {'KeyR'})
        assert rt._sim_state == 'IDLE'
        data = rt.step(0.02, set())
        assert data['pos'] == [0.0, 0.0, 0.0]

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
        assert rt._sim_state == 'NAVIGATE'
        for _ in range(400):
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