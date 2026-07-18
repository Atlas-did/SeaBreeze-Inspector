"""HAL interfaces - Abstract Base Classes for hardware abstraction.

Phase 4: Define ABCs so simulation and real hardware share the same
control code. MissionController uses only these interfaces,
never importing TelloController or Quadrotor3D directly.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import numpy as np


class DroneInterface(ABC):
    """Abstract drone (quadrotor) interface.

    Implementations:
      - TelloController (real Tello via WiFi)
      - SimDroneAdapter (virtual drone via Quadrotor3D)
    """

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to drone. Returns True on success."""
        ...

    @abstractmethod
    def takeoff(self) -> bool:
        """Initiate takeoff sequence. Returns True if command accepted."""
        ...

    @abstractmethod
    def land(self) -> bool:
        """Initiate landing sequence. Returns True if command accepted."""
        ...

    @abstractmethod
    def emergency(self) -> bool:
        """Immediate motor stop. Returns True if command accepted."""
        ...

    @abstractmethod
    def move_to(self, x: float, y: float, z: float, speed: int = 30) -> bool:
        """Move to relative position (cm). Returns True if command accepted."""
        ...

    @abstractmethod
    def hover(self) -> None:
        """Send hover command (zero velocity)."""
        ...

    @abstractmethod
    def get_battery(self) -> int:
        """Get battery percentage (0-100)."""
        ...

    @abstractmethod
    def get_height(self) -> int:
        """Get current height (cm)."""
        ...

    @abstractmethod
    def get_attitude(self) -> Dict[str, float]:
        """Get roll/pitch/yaw (degrees). Returns {"roll":0,"pitch":0,"yaw":0}."""
        ...

    @abstractmethod
    def get_state_dict(self) -> Dict[str, Any]:
        """Get full drone state as dict for serialization."""
        ...

    @property
    @abstractmethod
    def is_flying(self) -> bool:
        """True if drone is currently airborne."""
        ...


class ArmInterface(ABC):
    """Abstract robotic arm interface.

    Implementations:
      - ArmController (Arduino Nano via serial)
      - RobotArm3DOF (virtual arm, FK only)
    """

    @abstractmethod
    def set_angles(self, angles_deg: List[float]) -> None:
        """Set joint angles [base, shoulder, elbow] in degrees."""
        ...

    @abstractmethod
    def get_endpoint(self) -> np.ndarray:
        """Get end-effector position [x, y, z] in mm."""
        ...

    @abstractmethod
    def get_angles(self) -> np.ndarray:
        """Get current joint angles [base, shoulder, elbow] in degrees."""
        ...


class VisionInterface(ABC):
    """Abstract vision/detection interface.

    Implementations:
      - DefectDetector (YOLO model, real camera)
      - VirtualSensor (mock detections, simulation)
    """

    @abstractmethod
    def detect(self, frame: Optional[np.ndarray] = None) -> List[Dict]:
        """Run object detection on frame.

        Returns:
            List of dicts with keys: class_name, confidence, bbox
        """
        ...