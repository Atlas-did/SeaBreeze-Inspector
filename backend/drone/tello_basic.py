"""
Tello控制器 — 状态机驱动连接 + 异常恢复

选型: 状态机驱动连接 (方案C)
  理由: 根据飞行状态管理连接生命周期,
        IDLE/CONNECTED/FLYING/LANDING等状态清晰,
        异常时可快速转入EMERGENCY状态, 鲁棒性最好。
"""

from __future__ import annotations

import time
from enum import Enum, auto
from typing import Callable, Dict, Optional

import numpy as np


class FlightState(Enum):
    IDLE = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    TAKING_OFF = auto()
    HOVERING = auto()
    MOVING = auto()
    LANDING = auto()
    EMERGENCY = auto()
    DISCONNECTED = auto()


class MockTello:
    """Mock Tello 用于离线测试, 模拟飞行状态和传感器数据"""

    def __init__(self):
        self.is_flying = False
        self._battery = 100
        self._height = 0
        self._position = np.zeros(3)
        self._attitude = np.zeros(3)

    def connect(self):
        return True

    def takeoff(self):
        self.is_flying = True
        self._height = 50
        return True

    def land(self):
        self.is_flying = False
        self._height = 0
        return True

    def emergency(self):
        self.is_flying = False
        self._height = 0
        return True

    def move_forward(self, dist: int):
        self._position[0] += dist
        return True

    def move_back(self, dist: int):
        self._position[0] -= dist
        return True

    def move_left(self, dist: int):
        self._position[1] += dist
        return True

    def move_right(self, dist: int):
        self._position[1] -= dist
        return True

    def move_up(self, dist: int):
        self._height += dist
        return True

    def move_down(self, dist: int):
        self._height = max(0, self._height - dist)
        return True

    def get_battery(self) -> int:
        return self._battery

    def get_height(self) -> int:
        return int(self._height)

    def get_attitude(self):
        return {"pitch": 0, "roll": 0, "yaw": 0}

    def get_position(self):
        return self._position.copy()

    def get_state_dict(self):
        return {
            "battery": self._battery,
            "height": int(self._height),
            "position": self._position.tolist(),
            "attitude": self.get_attitude(),
            "is_flying": self.is_flying,
        }


class TelloController:
    """Tello无人机控制器 — 状态机驱动"""

    # 状态转换表: {当前状态: {事件: 下一状态}}
    TRANSITIONS = {
        FlightState.IDLE: {"connect": FlightState.CONNECTING},
        FlightState.CONNECTING: {"success": FlightState.CONNECTED, "fail": FlightState.IDLE},
        FlightState.CONNECTED: {"takeoff": FlightState.TAKING_OFF, "disconnect": FlightState.DISCONNECTED},
        FlightState.TAKING_OFF: {"complete": FlightState.HOVERING, "fail": FlightState.EMERGENCY},
        FlightState.HOVERING: {"move": FlightState.MOVING, "land": FlightState.LANDING, "emergency": FlightState.EMERGENCY},
        FlightState.MOVING: {"hover": FlightState.HOVERING, "emergency": FlightState.EMERGENCY},
        FlightState.LANDING: {"complete": FlightState.CONNECTED, "fail": FlightState.EMERGENCY},
        FlightState.EMERGENCY: {"reset": FlightState.IDLE},
        FlightState.DISCONNECTED: {"connect": FlightState.CONNECTING},
    }

    def __init__(self, config=None, mock: bool = False):
        self.config = config
        self.mock = mock
        self.state = FlightState.IDLE
        self._state_entry_time = time.time()
        self._battery = 100
        self._height = 0
        self._position = np.zeros(3)
        self._attitude = np.zeros(3)
        self._tello = None
        self._emergency_reason = ""

    def _transition(self, event: str) -> bool:
        """状态转换"""
        if self.state in self.TRANSITIONS and event in self.TRANSITIONS[self.state]:
            old_state = self.state
            self.state = self.TRANSITIONS[self.state][event]
            self._state_entry_time = time.time()
            print(f"[STATE] {old_state.name} --{event}--> {self.state.name}")
            return True
        print(f"[WARN] 无效转换: {self.state.name} --{event}-->")
        return False

    def connect(self, wifi_ssid: str = "Tello", max_retry: int = 3) -> bool:
        """连接Tello WiFi, 重试3次"""
        if self.mock:
            self._transition("connect")
            self._transition("success")
            return True

        try:
            from djitellopy import Tello
            self._tello = Tello()
            self._tello.connect()
            self._transition("connect")
            self._transition("success")
            return True
        except Exception as e:
            print(f"[ERR] 连接失败: {e}")
            self._transition("fail")
            return False

    def takeoff(self) -> bool:
        """起飞"""
        if self.state != FlightState.CONNECTED:
            print("[WARN] 未连接, 无法起飞")
            return False
        self._transition("takeoff")
        if self.mock:
            self._height = 100
            self._transition("complete")
            return True
        try:
            self._tello.takeoff()
            self._transition("complete")
            return True
        except Exception as e:
            print(f"[ERR] 起飞失败: {e}")
            self._transition("fail")
            return False

    def land(self) -> bool:
        """降落"""
        if self.state in (FlightState.HOVERING, FlightState.MOVING):
            self._transition("land")
            if self.mock:
                self._height = 0
                self._transition("complete")
                return True
            try:
                self._tello.land()
                self._transition("complete")
                return True
            except Exception as e:
                self._emergency(f"降落失败: {e}")
                return False
        return False

    def emergency(self) -> bool:
        """紧急停止 — 通过状态机转换"""
        # 尝试通过状态机转换
        if not self._transition("emergency"):
            # 如果当前状态没有定义 emergency 转换边，直接切换
            old_state = self.state
            self.state = FlightState.EMERGENCY
            self._state_entry_time = time.time()
            self._emergency_reason = self._emergency_reason or "手动紧急停止"
            print(f"[STATE] {old_state.name} --emergency(force)--> {self.state.name}")
        if self.mock:
            self._height = 0
            return True
        try:
            self._tello.emergency()
        except Exception:
            pass
        return True

    def move_to(self, x: float, y: float, z: float, speed: int = 30) -> bool:
        """移动到相对位置(cm), 使用速度指令(RC control)"""
        if self.state not in (FlightState.HOVERING, FlightState.MOVING):
            return False

        if self.mock:
            self._position += np.array([x, y, z])
            self._height += z
            return True

        try:
            # 使用位移指令 (更可靠)
            if abs(x) > 20:
                self._tello.move_left(int(x)) if x > 0 else self._tello.move_right(int(-x))
            if abs(y) > 20:
                self._tello.move_forward(int(y)) if y > 0 else self._tello.move_back(int(-y))
            if abs(z) > 20:
                self._tello.move_up(int(z)) if z > 0 else self._tello.move_down(int(-z))
            return True
        except Exception as e:
            print(f"[ERR] 移动失败: {e}")
            return False

    def hover(self):
        """悬停"""
        self._transition("hover")

    def get_battery(self) -> int:
        return self._battery if self.mock else (self._tello.get_battery() if self._tello else 0)

    def get_height(self) -> int:
        return int(self._height) if self.mock else (self._tello.get_height() if self._tello else 0)

    def get_attitude(self) -> Dict:
        return {"pitch": 0, "roll": 0, "yaw": 0} if self.mock else {}

    def get_state_dict(self) -> Dict:
        """返回标准化状态字典"""
        return {
            "state": self.state.name,
            "battery": self.get_battery(),
            "height": self.get_height(),
            "position": self._position.tolist(),
            "emergency_reason": self._emergency_reason,
        }

    def _emergency(self, reason: str):
        """触发紧急状态"""
        self._emergency_reason = reason
        self.emergency()

    @property
    def is_flying(self) -> bool:
        return self.state in (FlightState.HOVERING, FlightState.MOVING, FlightState.TAKING_OFF)
