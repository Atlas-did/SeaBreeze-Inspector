"""终态 (FAULT / MISSION_FAILED) 与任务期有效性的回归测试。

外部审计第 1/2/4/5 条 (已逐条用代码与实验核实):
  1. FAULT/MISSION_FAILED 曾是 main.py 里的**字符串**, 不在 MissionState 枚举内 ——
     `request_state()` 的 `except KeyError: pass` 会把**整张转换表跳过**, 实测在 FAULT
     状态下 request_state("TAKEOFF") 返回 True 并真的复活起飞。
  2. mark_fault() 原先只 stop_velocity(): 飞机还在空中时那只是停止任务输出, 不等于安全。
  4. 定位/视觉只在"进入状态"时过闸门, 任务中途失效要等下一个转换点才暴露。
  5. 定位新鲜 ≠ 气压高度新鲜, 两者拼成一包喂 EKF 会把 x/y 的真实性和 z 的陈旧混在一起。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from backend.main import MissionController  # noqa: E402
from backend.mission.states import (  # noqa: E402
    TERMINAL_STATES,
    MissionState,
    can_transition,
    is_terminal,
    normalize_state_name,
)


def _mc(mock=True):
    mc = MissionController(mode="simulation", mock=mock)
    mc.logger.start_session = lambda *a, **k: None
    mc.logger.log_frame = lambda *a, **k: None
    return mc


class FakeDrone:
    """记录调用的假机体 (覆盖 mark_fault / 有效性检查用到的接口)。"""

    def __init__(self, flying=True, height_known=True, telemetry_fresh=True):
        self.is_flying = flying
        self._height_known = height_known
        self._telemetry_fresh = telemetry_fresh
        self.calls = []
        self.descent_args = []

    def has_fresh_telemetry(self, max_age_s=1.0):
        """真实 TelloController 的语义: 以**状态包到达**为准, 而不是 getter 是否抛异常。"""
        return self._telemetry_fresh

    def stop_velocity(self):
        self.calls.append("stop_velocity")

    def emergency_descent(self, *a, **kw):
        self.calls.append("emergency_descent")
        self.descent_args.append(kw)

    def land(self):
        self.calls.append("land")

    def motor_cutoff(self, reason=""):
        self.calls.append("motor_cutoff")
        return True

    def height_is_known(self, *a, **kw):
        return self._height_known

    def get_height(self):
        return 100

    def get_battery(self):
        return 80

    def get_state_dict(self):
        return {"battery": 80, "height": 100}

    def get_attitude(self):
        return {}


# =============================================================================
# 1) 枚举与转换表: 终态无出边, 任何状态都可进终态
# =============================================================================

def test_terminal_states_are_in_the_authoritative_enum():
    """FAULT / MISSION_FAILED 必须是 MissionState 的正式成员。"""
    assert MissionState["FAULT"] is not None
    assert MissionState["MISSION_FAILED"] is not None
    assert normalize_state_name("FAULT") == "FAULT"
    assert normalize_state_name("MISSION_FAILED") == "MISSION_FAILED"
    assert {"FAULT", "MISSION_FAILED"} <= {s.name for s in MissionState}


def test_terminal_states_have_no_outgoing_transitions():
    """终态不能回到 TAKEOFF/NAVIGATE/INSPECT —— 只能人工复位。"""
    targets = [s.name for s in MissionState if s not in TERMINAL_STATES]
    for src in ("FAULT", "MISSION_FAILED"):
        assert is_terminal(src)
        for dst in targets:
            assert not can_transition(src, dst), \
                "{} → {} 必须被拒绝(终态无出边)".format(src, dst)


def test_any_state_may_enter_a_terminal_state():
    """故障随时可能发生: 任何非终态都允许进入终态。"""
    for src in (s.name for s in MissionState if s not in TERMINAL_STATES):
        for dst in ("FAULT", "MISSION_FAILED"):
            assert can_transition(src, dst), "{} → {} 应被允许".format(src, dst)


# =============================================================================
# 2) 审计第 1 条的核心回归: 终态不能被 request_state 复活
# =============================================================================

def test_request_state_cannot_revive_from_fault():
    """曾经的真实缺陷: request_state("TAKEOFF") 在 FAULT 下返回 True 并复活。"""
    mc = _mc()
    mc.mark_fault("注入故障")
    assert mc.state == "FAULT"

    assert mc.request_state("TAKEOFF", "外部请求复活") is False
    assert mc.state == "FAULT", "终态被复活了: {}".format(mc.state)
    assert mc.request_state("NAVIGATE", "外部请求导航") is False
    assert mc.state == "FAULT"


def test_request_state_cannot_revive_from_mission_failed():
    mc = _mc()
    mc._set_state("MISSION_FAILED", "闸门拦下", force=True)
    for target in ("TAKEOFF", "NAVIGATE", "INSPECT", "RETURN"):
        assert mc.request_state(target, "外部请求") is False
    assert mc.state == "MISSION_FAILED"


def test_request_state_rejects_unknown_state_names():
    """未知状态名不得被"兼容旧代码"地直接设置(fail-closed)。"""
    mc = _mc()
    assert mc.request_state("NOT_A_STATE", "乱来") is False
    assert mc.state == "IDLE"


# =============================================================================
# 3) 复位: 唯一出口, 且飞行中禁止
# =============================================================================

def test_clear_fault_is_refused_while_flying():
    mc = _mc()
    mc.drone = FakeDrone(flying=True)
    mc.mark_fault("空中故障")
    assert mc.clear_fault("尝试复位") is False
    assert mc.state == "FAULT"


def test_clear_fault_resets_to_idle_on_the_ground():
    mc = _mc()
    mc.drone = FakeDrone(flying=False)
    mc.mark_fault("地面故障")
    assert mc.clear_fault("人工复位") is True
    assert mc.state == "IDLE"
    assert mc._fault_reason is None


# =============================================================================
# 4) 审计第 2 条: mark_fault 在空中必须发起受控下降
# =============================================================================

def test_mark_fault_in_flight_starts_controlled_descent():
    mc = _mc(mock=False)
    drone = FakeDrone(flying=True)
    mc.drone = drone
    mc.mark_fault("控制循环异常")
    assert mc.state == "FAULT"
    assert "stop_velocity" in drone.calls, "必须先停止速度指令"
    assert "emergency_descent" in drone.calls, \
        "空中故障必须发起受控下降, 实际调用: {}".format(drone.calls)
    assert mc._fault_descent_started is True


def test_mark_fault_on_ground_does_not_descend():
    mc = _mc(mock=False)
    drone = FakeDrone(flying=False)
    mc.drone = drone
    mc.mark_fault("地面故障")
    assert "emergency_descent" not in drone.calls
    assert drone.calls == ["stop_velocity"]


def test_fault_state_keeps_descending_every_frame():
    """终态不是"什么都不做": 仍在空中时每帧都要继续受控下降。"""
    mc = _mc(mock=False)
    drone = FakeDrone(flying=True)
    mc.drone = drone
    mc.mark_fault("故障")
    before = drone.calls.count("emergency_descent")
    for _ in range(3):
        mc._handle_state_machine(np.zeros(3))
    after = drone.calls.count("emergency_descent")
    assert after > before, "FAULT 期间未持续下降: {}".format(drone.calls)


# =============================================================================
# 5) 审计第 4 条: 任务期逐帧失效检查
# =============================================================================

def test_localization_lost_midmission_fails_the_mission():
    """导航中途定位失效 -> 停速度 + MISSION_FAILED (不再继续按旧指令飞)。"""
    mc = _mc(mock=False)
    drone = FakeDrone(flying=True, height_known=True)
    mc.drone = drone
    mc.state = "NAVIGATE"
    assert mc.localization_available() is False      # 未接定位源

    assert mc._check_task_validity() is True
    assert mc.state == "MISSION_FAILED"
    assert "stop_velocity" in drone.calls


def test_localization_lost_with_unknown_height_triggers_descent():
    """连高度都不可信 -> 无法保证稳定悬停, 直接受控下降而不是干等。"""
    mc = _mc(mock=False)
    drone = FakeDrone(flying=True, height_known=False)
    mc.drone = drone
    mc.state = "RETURN"
    assert mc._check_task_validity() is True
    assert mc.state == "EMERGENCY"
    assert "stop_velocity" in drone.calls


def test_validity_check_is_inert_in_idle():
    mc = _mc(mock=False)
    mc.drone = FakeDrone(flying=False)
    mc.state = "IDLE"
    assert mc._check_task_validity() is False
    assert mc.state == "IDLE"


# =============================================================================
# 6) 审计第 5 条: 定位新鲜 + 气压陈旧 不得拼成一包观测
# =============================================================================

class _FixedSource:
    """固定返回一条可用观测的定位源。"""

    name = "fixed"

    def __init__(self, position):
        from backend.localization.base import LocalizationObservation
        self._obs = LocalizationObservation(
            np.asarray(position, dtype=float), timestamp=None, quality=1.0)
        self._obs.timestamp = __import__("time").monotonic()

    def read(self):
        return self._obs


def test_stale_barometer_uses_localization_height_instead_of_stale_cache():
    """气压陈旧时: 高度改用**同一观测**的定位高度, 而不是 Tello 缓存值。

    审计第 5 条的要害是"不得把不同时刻的观测拼成一包"。所以拒绝的是**陈旧缓存**,
    不是整包丢弃: ArUco 本身也测 z, 用同源观测的高度才是一致的。
    """
    mc = _mc(mock=False)
    mc.drone = FakeDrone(flying=True, telemetry_fresh=False)   # 链路陈旧
    mc.attach_localization_source(_FixedSource([123.0, -45.0, 80.0]))
    assert mc.localization_available() is True

    obs = mc._get_sensor_data()
    assert obs is not None, "新鲜定位不应被整体丢弃"
    assert obs[3] == pytest.approx(123.0) and obs[4] == pytest.approx(-45.0)
    assert obs[5] == pytest.approx(80.0), \
        "高度必须来自同源定位观测(80), 而不是陈旧的 Tello 缓存(100), 实际 {}".format(obs[5])
    assert mc.get_state_dict()["localization_fresh"] is True
    assert mc.get_state_dict()["barometer_fresh"] is False


def test_stale_barometer_with_no_localization_height_skips_the_update():
    """定位也没有有效高度时, 宁可本帧不注入观测, 也不用陈旧缓存。"""
    mc = _mc(mock=False)
    mc.drone = FakeDrone(flying=True, telemetry_fresh=False)
    src = _FixedSource([123.0, -45.0, 80.0])
    src._obs.position = np.array([123.0, -45.0, float("nan")])
    mc.attach_localization_source(src)
    assert mc._get_sensor_data() is None


def test_fresh_localization_and_fresh_barometer_are_both_used():
    mc = _mc(mock=False)
    mc.drone = FakeDrone(flying=True)
    mc.attach_localization_source(_FixedSource([123.0, -45.0, 80.0]))
    mc._sensor_fresh = True
    obs = mc._get_sensor_data()
    assert obs is not None
    assert obs[3] == pytest.approx(123.0) and obs[4] == pytest.approx(-45.0)
