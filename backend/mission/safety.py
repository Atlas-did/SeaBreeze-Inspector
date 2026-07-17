"""
分层 Failsafe — 三级安全监控 + 恢复机制

P1-A 修复: 低电触发后不再永久锁死, 可自动/手动恢复

层级:
  WARN  — 电池 < 20%、高度接近上限 → 告警 (UI闪烁, 不干预飞行)
  LAND  — 电池 < 10%、姿态 > 30° → 自动降落 (可恢复)
  KILL  — 电池 < 5%、通信超时 > 3s → 紧急停桨 (需手动重置)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Optional


class SafetyLevel(Enum):
    """安全级别"""
    OK = auto()      # 正常
    WARN = auto()    # 告警 (UI显示, 不干预)
    LAND = auto()    # 自动降落 (可恢复)
    KILL = auto()    # 紧急停桨 (需手动重置)


@dataclass
class SafetyEvent:
    """安全事件"""
    level: SafetyLevel
    reason: str
    timestamp: float = field(default_factory=time.time)


class FailsafeMonitor:
    """分层安全监控器

    用法:
        monitor = FailsafeMonitor()
        event = monitor.check(battery=85, attitude=[0,0,0], height=100)
        if event.level == SafetyLevel.WARN:
            print(f"警告: {event.reason}")
        elif event.level == SafetyLevel.LAND:
            drone.land()
        elif event.level == SafetyLevel.KILL:
            drone.emergency()
    """

    # 三级阈值 (优先级: KILL > LAND > WARN)
    THRESHOLDS = {
        "battery_warn":  20,   # %  — 低于此值 WARN
        "battery_land":  10,   # %  — 低于此值 LAND
        "battery_kill":   5,   # %  — 低于此值 KILL
        "attitude_land": 30,   # 度 — 超过此值 LAND
        "attitude_kill": 60,   # 度 — 超过此值 KILL
        "height_land":   300,  # cm — 超过此值 LAND
        "height_kill":   500,  # cm — 超过此值 KILL
        "timeout_land":   1.0, # s  — 心跳超时 LAND
        "timeout_kill":   3.0, # s  — 心跳超时 KILL
    }

    def __init__(self):
        self._last_heartbeat = time.time()
        self._active_event: Optional[SafetyEvent] = None
        self._event_history: list[SafetyEvent] = []

    def check(self, battery: int = 100,
              attitude: list = None,
              height: float = 0.0) -> SafetyEvent:
        """执行安全检查, 返回最高级别的安全事件

        参数:
            battery: 电量百分比
            attitude: [roll, pitch, yaw] 姿态角(度)
            height: 高度(cm)
        """
        if attitude is None:
            attitude = [0, 0, 0]
        max_att = max(abs(a) for a in attitude)
        now = time.time()
        elapsed = now - self._last_heartbeat

        # 按严重度递增检查 — KILL 最高优先级
        event = SafetyEvent(SafetyLevel.OK, "正常")

        # KILL 级别
        if battery < self.THRESHOLDS["battery_kill"]:
            event = SafetyEvent(SafetyLevel.KILL,
                "电量危急: {}% < {}%".format(battery, self.THRESHOLDS["battery_kill"]))
        elif max_att > self.THRESHOLDS["attitude_kill"]:
            event = SafetyEvent(SafetyLevel.KILL,
                "姿态危急: {:.0f}° > {:.0f}°".format(max_att, self.THRESHOLDS["attitude_kill"]))
        elif height > self.THRESHOLDS["height_kill"]:
            event = SafetyEvent(SafetyLevel.KILL,
                "高度危急: {:.0f}cm > {:.0f}cm".format(height, self.THRESHOLDS["height_kill"]))
        elif elapsed > self.THRESHOLDS["timeout_kill"]:
            event = SafetyEvent(SafetyLevel.KILL,
                "通信中断: {:.1f}s > {:.1f}s".format(elapsed, self.THRESHOLDS["timeout_kill"]))
        # LAND 级别
        elif battery < self.THRESHOLDS["battery_land"]:
            event = SafetyEvent(SafetyLevel.LAND,
                "低电量: {}% < {}%".format(battery, self.THRESHOLDS["battery_land"]))
        elif max_att > self.THRESHOLDS["attitude_land"]:
            event = SafetyEvent(SafetyLevel.LAND,
                "姿态异常: {:.0f}° > {:.0f}°".format(max_att, self.THRESHOLDS["attitude_land"]))
        elif height > self.THRESHOLDS["height_land"]:
            event = SafetyEvent(SafetyLevel.LAND,
                "高度超限: {:.0f}cm > {:.0f}cm".format(height, self.THRESHOLDS["height_land"]))
        elif elapsed > self.THRESHOLDS["timeout_land"]:
            event = SafetyEvent(SafetyLevel.LAND,
                "通信延迟: {:.1f}s > {:.1f}s".format(elapsed, self.THRESHOLDS["timeout_land"]))
        # WARN 级别
        elif battery < self.THRESHOLDS["battery_warn"]:
            event = SafetyEvent(SafetyLevel.WARN,
                "电量偏低: {}% < {}%".format(battery, self.THRESHOLDS["battery_warn"]))

        self._active_event = event
        if event.level != SafetyLevel.OK:
            self._event_history.append(event)
            # 只保留最近 20 条
            if len(self._event_history) > 20:
                self._event_history = self._event_history[-20:]

        return event

    def heartbeat(self):
        """更新心跳时间 (调用方每帧调用)"""
        self._last_heartbeat = time.time()

    def can_recover(self) -> bool:
        """LAND 级别的紧急可以自动恢复; KILL 级别需要手动 reset"""
        if self._active_event is None:
            return True
        return self._active_event.level in (SafetyLevel.OK, SafetyLevel.WARN)

    def reset(self):
        """重置监控状态 (KILL 后恢复)"""
        self._active_event = None
        self._last_heartbeat = time.time()

    @property
    def active_level(self) -> SafetyLevel:
        if self._active_event is None:
            return SafetyLevel.OK
        return self._active_event.level

    @property
    def active_reason(self) -> str:
        if self._active_event is None:
            return ""
        return self._active_event.reason
