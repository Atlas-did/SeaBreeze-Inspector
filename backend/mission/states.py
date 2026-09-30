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
    """任务状态枚举 — 全系统唯一权威

    终态 (TERMINAL_STATES):
      * FAULT          — 控制循环/硬件异常, 任务终止
      * MISSION_FAILED — 任务无法继续(闸门拦下、任务期失效), 不算完成
    两者**没有出边**: 只能通过 MissionController.clear_fault() 显式人工复位,
    或在落地后重建任务。此前它们是字符串常量、不在本枚举内, 导致
    request_state() 的转换表校验在 KeyError 兜底里被整体跳过 —— 实测可以在
    FAULT 状态下 request_state("TAKEOFF") 成功复活(见 tests/test_terminal_states.py)。
    """
    IDLE = auto()
    TAKEOFF = auto()
    HOVERING = auto()
    NAVIGATE = auto()
    INSPECT = auto()
    RETURN = auto()
    LAND = auto()
    EMERGENCY = auto()
    FAULT = auto()
    MISSION_FAILED = auto()


#: 终态: 无出边, 只能人工复位
TERMINAL_STATES = frozenset({MissionState.FAULT, MissionState.MISSION_FAILED})


# 合法状态转换表: {from_state: {to_state, ...}}
# Q1=A: 手动降落是合理操作, 允许从任意飞行状态 (NAVIGATE/INSPECT) 直接转 LAND
TRANSITIONS: Dict[MissionState, Set[MissionState]] = {
    MissionState.IDLE: {MissionState.TAKEOFF, MissionState.HOVERING, MissionState.NAVIGATE},
    MissionState.TAKEOFF: {MissionState.HOVERING, MissionState.LAND, MissionState.EMERGENCY},
    MissionState.HOVERING: {MissionState.NAVIGATE, MissionState.LAND,
                            MissionState.EMERGENCY, MissionState.IDLE},
    MissionState.NAVIGATE: {MissionState.INSPECT, MissionState.HOVERING,
                            MissionState.LAND, MissionState.EMERGENCY},
    MissionState.INSPECT: {MissionState.RETURN, MissionState.LAND,
                           MissionState.EMERGENCY},
    MissionState.RETURN: {MissionState.LAND, MissionState.EMERGENCY},
    MissionState.LAND: {MissionState.IDLE, MissionState.EMERGENCY},
    MissionState.EMERGENCY: {MissionState.IDLE, MissionState.LAND},  # 重置或强制降落
    # 终态: 出边为空 (进入它们由 can_transition 统一放行, 见下)
    MissionState.FAULT: set(),
    MissionState.MISSION_FAILED: set(),
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


def is_terminal(state: Union[str, MissionState]) -> bool:
    """是否为终态 (FAULT / MISSION_FAILED)。非法名字返回 False。"""
    try:
        return to_state(state) in TERMINAL_STATES
    except (ValueError, KeyError):
        return False


def can_transition(src: Union[MissionState, str],
                   dst: Union[MissionState, str]) -> bool:
    """检查状态转换是否合法 (接受枚举或字符串, 非法名字返回 False)

    终态规则 (审计第 1 条):
      * 终点是终态 -> **任何状态都允许**(故障随时可能发生);
      * 起点是终态 -> **一律不允许**(必须 clear_fault() 人工复位), 这就是
        "不能从 FAULT 直接回 TAKEOFF/NAVIGATE/INSPECT" 的落点。
    """
    try:
        s = to_state(src)
        d = to_state(dst)
    except ValueError:
        return False
    if s in TERMINAL_STATES:
        return False
    if d in TERMINAL_STATES:
        return True
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
