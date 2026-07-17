"""
任务状态枚举 + 转换表 — 全系统唯一权威状态定义

P1-C 修复: 所有状态变更必须通过 can_transition() 校验,
禁止 simulation.py 等外部模块直接赋值 mc.state = "IDLE"
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Dict, Set


class MissionState(Enum):
    """任务状态枚举 — 全系统唯一权威"""
    IDLE = auto()
    TAKEOFF = auto()
    HOVERING = auto()
    NAVIGATE = auto()
    INSPECT = auto()
    RETURN = auto()
    LAND = auto()
    EMERGENCY = auto()


# 合法状态转换表: {from_state: {to_state, ...}}
TRANSITIONS: Dict[MissionState, Set[MissionState]] = {
    MissionState.IDLE:      {MissionState.TAKEOFF, MissionState.HOVERING, MissionState.NAVIGATE},
    MissionState.TAKEOFF:   {MissionState.HOVERING, MissionState.LAND, MissionState.EMERGENCY},
    MissionState.HOVERING:  {MissionState.NAVIGATE, MissionState.LAND,
                              MissionState.EMERGENCY, MissionState.IDLE},
    MissionState.NAVIGATE:  {MissionState.INSPECT, MissionState.HOVERING,
                              MissionState.EMERGENCY},
    MissionState.INSPECT:   {MissionState.RETURN, MissionState.EMERGENCY},
    MissionState.RETURN:    {MissionState.LAND, MissionState.EMERGENCY},
    MissionState.LAND:      {MissionState.IDLE, MissionState.EMERGENCY},
    MissionState.EMERGENCY: {MissionState.IDLE, MissionState.LAND},  # 重置或强制降落
}


def can_transition(from_state: MissionState, to_state: MissionState) -> bool:
    """检查状态转换是否合法"""
    return to_state in TRANSITIONS.get(from_state, set())


def transition(from_state: MissionState, to_state: MissionState,
               reason: str = "") -> MissionState:
    """执行状态转换, 非法时抛异常"""
    if not can_transition(from_state, to_state):
        raise ValueError(
            "非法状态转换: {} → {} ({})".format(
                from_state.name, to_state.name, reason or "无理由"))
    return to_state
