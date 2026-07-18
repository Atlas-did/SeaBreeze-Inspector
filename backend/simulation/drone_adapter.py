"""SimDroneAdapter - Wraps Quadrotor3D as a DroneInterface implementation.

Phase 4: Enables MissionController to control simulated and real drones
through the same DroneInterface. Eliminates if/mock branches in main.py.
"""

from typing import Any, Dict, List
import numpy as np

from backend.hal.interfaces import DroneInterface


class SimDroneAdapter(DroneInterface):
    """Adapts Quadrotor3D physics model to DroneInterface.

    Usage:
        quad = Quadrotor3D()
        drone = SimDroneAdapter(quad)
        drone.connect()
        drone.takeoff()
        drone.move_to(0, 0, 50)  # move up 50cm
    """

    def __init__(self, quad):
        """Args: quad: Quadrotor3D physics model instance."""
        self._quad = quad
        self._flying = False
        self._battery = 100
        self._connected = False
        self._target_pos = np.zeros(3)

    # ---- DroneInterface implementation ----

    def connect(self) -> bool:
        self._connected = True
        return True

    def takeoff(self) -> bool:
        if not self._connected:
            return False
        self._flying = True
        self._target_pos = self._quad.get_position().copy()
        self._target_pos[2] = 1.2  # hover height (z-up meters)
        return True

    def land(self) -> bool:
        self._flying = False
        self._target_pos = self._quad.get_position().copy()
        self._target_pos[2] = 0.0
        self._quad.set_velocity(np.zeros(3))
        return True

    def emergency(self) -> bool:
        self._flying = False
        self._quad.set_velocity(np.zeros(3))
        self._quad.state[2] = 0.0
        return True

    def move_to(self, x: float, y: float, z: float, speed: int = 30) -> bool:
        """Move by relative offset (cm).

        In simulation this sets the target position relative to current pos.
        """
        if not self._flying:
            return False
        offset_m = np.array([x, y, z], dtype=float) / 100.0  # cm -> m
        self._target_pos = self._quad.get_position() + offset_m
        return True

    def hover(self) -> None:
        self._quad.set_velocity(np.zeros(3))

    def get_battery(self) -> int:
        return int(self._battery)

    def get_height(self) -> int:
        """Height in cm (z-up)."""
        return int(self._quad.get_position()[2] * 100)

    def get_attitude(self) -> Dict[str, float]:
        att = self._quad.get_attitude()
        return {"roll": float(np.degrees(att[0])),
                "pitch": float(np.degrees(att[1])),
                "yaw": float(np.degrees(att[2]))}

    def get_state_dict(self) -> Dict[str, Any]:
        pos = self._quad.get_position()
        vel = self._quad.get_velocity()
        return {
            "position": pos.tolist(),
            "velocity": vel.tolist(),
            "attitude": self.get_attitude(),
            "battery": self.get_battery(),
            "height_cm": self.get_height(),
            "is_flying": self._flying,
        }

    @property
    def is_flying(self) -> bool:
        return self._flying

    # ---- Sim-specific helpers ----

    def set_battery(self, pct: float) -> None:
        """Set battery percentage (for simulation battery drain)."""
        self._battery = max(0.0, min(100.0, pct))

    def get_target_pos(self) -> np.ndarray:
        """Get target position for PID control (meters, z-up)."""
        return self._target_pos.copy()