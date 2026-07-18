"""
任务状态枚举 + 转换表 — 全系统唯一权威状态定义

铁律 #1: 全系统只有这一个任务状态枚举。
任何模块（仿真、HTTP桥、Dashboard）不得自定义任务状态字符串。

历史问题（已修复）:
  http_bridge.py 曾私自定义 TAKING_OFF / RETURNING / LANDING 等别名,
  与 MissionState 命名不一致, 导致前后端状态语义分叉。
  本模块提供 normalize_state_name() 统一收口所有历史别名。
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Dict, Set, Union


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


# =============================================================================
# 状态名规范化 (P1: 收口历史别名, 为 Phase 3 统一命名铺路)
# =============================================================================

# 历史别名 → 权威名。新增模块禁止使用左侧名字。
_STATE_ALIASES: Dict[str, str] = {
    # http_bridge.py 的私有命名
    "TAKING_OFF": "TAKEOFF",
    "RETURNING": "RETURN",
    "LANDING": "LAND",
    # 口语化缩写
    "HOVER": "HOVERING",
    "NAV": "NAVIGATE",
    "EMERG": "EMERGENCY",
}

_VALID_NAMES: Set[str] = {s.name for s in MissionState}


def normalize_state_name(name: str) -> str:
    """把任意历史状态名规范化为 MissionState 的权威名 (大写)。

    非法名字抛 ValueError —— 宁可早炸, 不让脏状态名在系统里流动。
    """
    if not isinstance(name, str):
        raise ValueError("状态名必须是字符串, 收到: {!r}".format(name))
    upper = name.strip().upper()
    upper = _STATE_ALIASES.get(upper, upper)
    if upper not in _VALID_NAMES:
        raise ValueError(
            "未知任务状态: {!r} (合法值: {})".format(
                name, sorted(_VALID_NAMES)))
    return upper


def to_state(state: Union[str, MissionState]) -> MissionState:
    """字符串或枚举 → MissionState 枚举 (别名自动规范化)"""
    if isinstance(state, MissionState):
        return state
    return MissionState[normalize_state_name(state)]


def is_valid_state(state: Union[str, MissionState]) -> bool:
    """是否为合法任务状态 (含别名)"""
    try:
        to_state(state)
        return True
    except (ValueError, KeyError):
        return False


def can_transition(src: Union[MissionState, str],
                   dst: Union[MissionState, str]) -> bool:
    """检查状态转换是否合法 (接受枚举或字符串, 非法名字返回 False)"""
    try:
        s = to_state(src)
        d = to_state(dst)
    except ValueError:
        return False
    return d in TRANSITIONS.get(s, set())


def transition(src: Union[MissionState, str],
               dst: Union[MissionState, str],
               reason: str = "") -> MissionState:
    """执行状态转换, 非法时抛异常"""
    s = to_state(src)
    d = to_state(dst)
    if not can_transition(s, d):
        raise ValueError(
            "非法状态转换: {} → {} ({})".format(
                s.name, d.name, reason or "无理由"))
    return d
