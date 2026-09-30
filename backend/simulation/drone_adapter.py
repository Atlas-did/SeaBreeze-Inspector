"""SimDroneAdapter - Wraps Quadrotor3D as a DroneInterface implementation.

Phase 4: Enables MissionController to control simulated and real drones
through the same DroneInterface. Eliminates if/mock branches in main.py.
"""

from typing import Any, Dict
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

    def __init__(self, quad, write_velocity_channel: bool = True):
        """Args: quad: Quadrotor3D physics model instance.

        write_velocity_channel:
            True (默认) —— set_velocity() 除记录指令外, 还直接写机体速度通道
            (历史行为, 有测试断言该通道被写)。
            False —— set_velocity() **只记录指令**, 不碰机体速度。速度指令模式下
            必须这样: 由 SimRuntime 的上行传输模型(延迟/丢包)决定指令何时真正到达
            机体; 若适配器仍直写通道, 控制器指令会绕过上行链路 —— "界面在发速度"
            就直接变成机体运动, 与真机不符(实测: 上行全丢包时机体仍移动 0.49m)。
        """
        self._quad = quad
        self._flying = False
        self._battery = 100
        self._connected = False
        self._target_pos = np.zeros(3)
        # 最近一次速度指令 (m/s, z-up)。仅由"速度指令模式"(SimRuntime
        # velocity_command_mode=True) 消费; 默认路径读不到它, 因此不影响旧数值。
        self._cmd_velocity_ms = np.zeros(3)
        self._write_velocity_channel = bool(write_velocity_channel)
        self._landing = False    # land() requested, waiting for physics touch-down
        self._emergency = False  # emergency() requested, waiting for physics touch-down

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
        # Deferred: keep _flying=True so mc's LAND handler waits for physics
        # touch-down. SimRuntime calls mark_landed() when pos[2] < threshold.
        self._landing = True
        self._target_pos = self._quad.get_position().copy()
        self._target_pos[2] = 0.0
        return True

    def emergency(self) -> bool:
        # Deferred: keep _flying=True so mc's EMERGENCY handler waits for physics
        # touch-down. Do NOT zero velocity — SimRuntime's cascaded control handles
        # the descent, and zeroing velocity every frame would freeze the quad in air.
        self._emergency = True
        return True

    def kill(self) -> bool:
        # Hard motor cut in simulation: physics model has no free-fall, so force
        # an immediate drop to ground via the same deferred-touchdown path.
        self._emergency = True
        return True

    def mark_landed(self) -> None:
        """SimRuntime calls this when physics reaches ground (pos[2] ≈ 0).

        This transitions _flying to False, allowing mc's LAND/EMERGENCY
        handler to proceed to IDLE.
        """
        self._flying = False
        self._landing = False
        self._emergency = False

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
        self.clear_velocity_command()  # 悬停 = 速度指令归零 (与真机 stop_velocity 同义)

    def set_velocity(self, vx: float, vy: float, vz: float, yaw: float = 0.0) -> bool:
        """P0-2: 速度控制入口 (cm/s, 与 TelloController.set_velocity 同语义)。

        与 move_to() 的"一次性相对位移"不同, 这是**持续速度指令**, 与主循环
        100ms 控制周期一致。仿真里直接写 Quadrotor3D 的速度通道 (m/s)。

        对齐补充: 指令同时以 m/s 记入 self._cmd_velocity_ms, 供
        SimRuntime(velocity_command_mode=True) 的物理驱动读取, 使无头仿真
        走"控制器→set_velocity→机体速度环"这条与真机相同的链路。
        """
        if not self._flying:
            return False
        v_ms = np.array([vx, vy, vz], dtype=float) / 100.0  # cm/s -> m/s
        self._cmd_velocity_ms = v_ms.copy()
        if self._write_velocity_channel:
            # 保持原有行为(RCS/旧测试断言此通道被写); 速度指令模式下由 SimRuntime
            # 的上行传输模型接管, 见 __init__ 说明。
            self._quad.set_velocity(v_ms)
        return True

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

    def get_commanded_velocity(self) -> np.ndarray:
        """最近一次 set_velocity 下发的速度指令 (m/s, z-up, x左/y前/z上)。

        返回副本, 调用方修改不会污染适配器内部状态。未下发过指令时为零向量。
        """
        return self._cmd_velocity_ms.copy()

    def clear_velocity_command(self) -> None:
        """速度指令归零 (悬停/落地/复位时调用), 避免旧指令被继续执行。"""
        self._cmd_velocity_ms = np.zeros(3)
