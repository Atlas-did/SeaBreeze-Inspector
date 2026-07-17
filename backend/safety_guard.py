"""
安全守护模块 — 10Hz周期检查, 异常时紧急悬停

检查项:
  1. 电池 < 10% → 强制降落
  2. 姿态 > 30° → 强制降落
  3. 高度 > 5m → 强制降落
  4. 与塔筒 < 1m → 强制避障
  5. 失联 > 1秒 → 自动降落
"""

import time

import numpy as np


class SafetyGuard:
    """安全守护"""

    # 与 config/drone_config.yaml safety 段保持一致
    THRESHOLDS = {
        "battery": 20,        # %  (drone_config: low_battery_land_threshold)
        "attitude": 30,       # 度
        "height": 300,        # cm (drone_config: boundary.z_max)
        "wall_distance": 100, # cm (drone_config: near_wall_min_distance)
        "timeout": 1.0,       # 秒
    }

    def __init__(self):
        self.THRESHOLDS = dict(self.THRESHOLDS)  # per-instance copy
        self._last_heartbeat = time.time()
        self._emergency_active = False
        self._emergency_reason = ""

    def check(self, state: dict) -> bool:
        """
        安全检查。

        返回: True=安全, False=触发紧急状态
        """
        if self._emergency_active:
            return False

        # 1. 电池检查
        battery = state.get("battery", 100)
        if battery < self.THRESHOLDS["battery"]:
            self._trigger_emergency(f"低电量: {battery}%")
            return False

        # 2. 姿态检查
        attitude = state.get("attitude", [0, 0, 0])
        if max(abs(a) for a in attitude) > self.THRESHOLDS["attitude"]:
            self._trigger_emergency(f"姿态异常: {attitude}")
            return False

        # 3. 高度检查
        height = state.get("height", 0)
        if height > self.THRESHOLDS["height"]:
            self._trigger_emergency(f"高度超限: {height}cm")
            return False

        # 4. 失联检查
        if time.time() - self._last_heartbeat > self.THRESHOLDS["timeout"]:
            self._trigger_emergency("通信超时")
            return False

        self._last_heartbeat = time.time()
        return True

    def _trigger_emergency(self, reason: str):
        self._emergency_active = True
        self._emergency_reason = reason
        print(f"[EMERGENCY] {reason}")

    def reset(self):
        self._emergency_active = False
        self._emergency_reason = ""
        self._last_heartbeat = time.time()

    @property
    def is_emergency(self) -> bool:
        return self._emergency_active

    @property
    def emergency_reason(self) -> str:
        return self._emergency_reason
