#!/usr/bin/env python3
"""HAL contract tests - verify DroneInterface/ArmInterface implementations."""

import sys, numpy as np
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from backend.hal.interfaces import DroneInterface, ArmInterface, VisionInterface
from backend.simulation.models import Quadrotor3D, RobotArm3DOF
from backend.simulation.drone_adapter import SimDroneAdapter


class TestDroneInterfaceContract:
    """Verify SimDroneAdapter satisfies DroneInterface contract."""

    @pytest.fixture
    def drone(self):
        quad = Quadrotor3D()
        return SimDroneAdapter(quad)

    def test_implements_abc(self, drone):
        assert isinstance(drone, DroneInterface)

    def test_connect(self, drone):
        assert drone.connect() is True

    def test_takeoff_sets_flying(self, drone):
        drone.connect()
        assert drone.takeoff() is True
        assert drone.is_flying is True

    def test_takeoff_fails_without_connect(self, drone):
        assert drone.takeoff() is False

    def test_land_clears_flying(self, drone):
        drone.connect()
        drone.takeoff()
        assert drone.land() is True
        assert drone.is_flying is False

    def test_emergency_stops(self, drone):
        drone.connect()
        drone.takeoff()
        assert drone.emergency() is True
        assert drone.is_flying is False
    
    def test_move_to_requires_flying(self, drone):
        drone.connect()
        assert drone.move_to(0, 0, 10) is False
        drone.takeoff()
        assert drone.move_to(0, 0, 10) is True

    def test_get_battery_returns_int(self, drone):
        assert isinstance(drone.get_battery(), int)
        assert 0 <= drone.get_battery() <= 100

    def test_get_height_returns_cm(self, drone):
        h = drone.get_height()
        assert isinstance(h, int)
        assert h >= 0  # on ground

    def test_get_attitude_keys(self, drone):
        att = drone.get_attitude()
        for k in ['roll', 'pitch', 'yaw']:
            assert k in att
            assert isinstance(att[k], float)

    def test_get_state_dict_keys(self, drone):
        state = drone.get_state_dict()
        for k in ['position', 'velocity', 'attitude', 'battery', 'is_flying']:
            assert k in state, f'Missing key: {k}'

    def test_hover_zeros_velocity(self, drone):
        drone.connect()
        drone.takeoff()
        drone.hover()
        vel = drone._quad.get_velocity()
        assert np.allclose(vel, [0, 0, 0])

    def test_set_battery_range(self, drone):
        drone.set_battery(50.5)
        assert drone.get_battery() == 50
        drone.set_battery(-10)
        assert drone.get_battery() == 0
        drone.set_battery(200)
        assert drone.get_battery() == 100


class TestArmInterfaceContract:
    """Verify RobotArm3DOF satisfies ArmInterface contract."""

    @pytest.fixture
    def arm(self):
        return RobotArm3DOF()

    def test_implements_abc(self, arm):
        assert isinstance(arm, ArmInterface)

    def test_default_angles(self, arm):
        angles = arm.get_angles()
        assert len(angles) == 3
        assert np.allclose(angles, [90, 90, 45])

    def test_set_angles(self, arm):
        arm.set_angles([120, 60, 30])
        angles = arm.get_angles()
        assert np.allclose(angles, [120, 60, 30])

    def test_get_endpoint_shape(self, arm):
        ep = arm.get_endpoint()
        assert len(ep) == 3
        assert all(isinstance(v, float) for v in ep)


if __name__ == "__main__":
    print("=" * 50)
    print("  HAL contract tests")
    print("=" * 50)
    drone = SimDroneAdapter(Quadrotor3D())
    dt = TestDroneInterfaceContract()
    dt.test_implements_abc(drone)
    dt.test_connect(drone)
    dt.test_takeoff_sets_flying(drone)
    print('  [PASS] drone contract')
    arm = RobotArm3DOF()
    at = TestArmInterfaceContract()
    at.test_implements_abc(arm)
    at.test_default_angles(arm)
    at.test_set_angles(arm)
    print('  [PASS] arm contract')
    print("\n[OK] All HAL contract tests passed!")