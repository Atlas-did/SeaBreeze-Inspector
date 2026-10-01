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
import time
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
    """记录调用的假机体。

    **替身保真度铁律**（第四轮审计 D1 的血的教训）：替身必须复刻真机的**状态机与失败路径**，
    不能把 `is_flying` 写成"永远为真"的普通属性。这里：
      * `land()` 失败时**返回 False 并把 `is_flying` 置 False** —— 与 `TelloController` 一致
        （真机 `land()` 异常 -> 转 EMERGENCY -> `is_flying`(property) 变 False, tello_basic.py:287-289/730-732）；
      * 失败同时让高度变为"不可信"，复刻"降落失败后高度读数不可依赖"的现实。
    """

    def __init__(self, flying=True, height_known=True, telemetry_fresh=True,
                 height=100.0, land_ok=True, descent_ok=True, state=None):
        self.is_flying = flying
        self._height_known = height_known
        self._telemetry_fresh = telemetry_fresh
        self._height = float(height)
        self._land_ok = land_ok
        self._descent_ok = descent_ok
        # 真机 TelloController 有状态机(FlightState), is_flying 是它的派生属性 ——
        # 第五轮审计 D17: 替身必须复刻这一点(EMERGENCY 下 is_flying 同样是 False),
        # 否则又会把「异常态导致的 False」误当成「已落地」。
        self.state = state
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
        if self._descent_ok and self._height > 0:
            self._height = max(0.0, self._height - 20.0)   # 每帧下降 20cm, 便于模拟到低空
        return self._descent_ok

    def land(self):
        self.calls.append("land")
        if not self._land_ok:
            # 真机: land() 抛异常 -> _emergency() -> EMERGENCY, 而 is_flying(property) 变 False;
            # **遥测仍在送包**, 所以高度依然可信(第五轮审计 D17: 旧替身把它改成「不可信」,
            # 于是代码走了下降分支, 掩盖了「EMERGENCY + 新鲜低空」这条真实路径)。
            self.is_flying = False
            self.state = "EMERGENCY"
            return False
        self.is_flying = False
        self.state = "CONNECTED"          # 干净落地态
        self._height = 0.0
        return True

    def reset_from_emergency(self):
        """复刻真机 tello_basic.reset_from_emergency: 仅 EMERGENCY -> IDLE 的纯状态复位。"""
        self.calls.append("reset_from_emergency")
        if self.state == "EMERGENCY":
            self.state = "IDLE"
            return True
        return False

    def motor_cutoff(self, reason=""):
        self.calls.append("motor_cutoff")
        return True

    def height_is_known(self, *a, **kw):
        return self._height_known

    def get_height(self):
        return self._height

    def get_battery(self):
        return 80

    def get_state_dict(self):
        return {"battery": 80, "height": int(self._height)}

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

def test_clear_fault_is_refused_without_grounded_evidence():
    """D2: 没有**正面落地证据**时拒绝复位（仍在飞 且 高度 100cm）。"""
    mc = _mc(mock=False)
    mc.drone = FakeDrone(flying=True, height=100.0)
    mc.mark_fault("空中故障")
    assert mc.clear_fault("尝试复位") is False
    assert mc.state == "FAULT"


def test_clear_fault_resets_to_idle_when_grounded():
    """D2: 高度可信且 <=30cm 且不再飞行才算落地 —— 此时允许复位。"""
    mc = _mc(mock=False)
    mc.drone = FakeDrone(flying=False, height=10.0)
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


# =============================================================================
# 7) 第三轮审计 P0: 终态闩锁 —— 安全检查不得成为第二条出口
# =============================================================================

def test_terminal_latch_survives_safety_escalation():
    """KILL 事件可以把 FAULT 升级为 EMERGENCY(安全动作仍要做), 但**不得解锁终态**。"""
    mc = _mc(mock=False)
    drone = FakeDrone(flying=True)
    mc.drone = drone
    mc.mark_fault("注入故障")
    assert mc._terminal_latched is True

    mc.trigger_emergency("KILL 级安全事件")          # 安全升级: 允许
    assert mc.state == "EMERGENCY"

    # 任何"离开终态"的转换都必须被拒 —— 包括 force=True
    assert mc._set_state("IDLE", "想偷偷复位", force=True) is False
    assert mc.state == "EMERGENCY"
    assert mc.request_state("TAKEOFF", "外部请求") is False
    assert mc.state == "EMERGENCY"


def test_terminal_latch_blocks_emergency_to_idle_recovery():
    """EMERGENCY 降落后的 IDLE 恢复路径也不得绕过 clear_fault()。"""
    mc = _mc(mock=False)
    drone = FakeDrone(flying=True, height_known=True)
    mc.drone = drone
    mc.mark_fault("故障")
    mc.trigger_emergency("安全升级")
    drone.is_flying = False                          # 已落地
    for _ in range(3):
        mc._handle_state_machine(np.zeros(3))        # 状态机尝试收尾
    assert mc.state != "IDLE", "落地后自行回到 IDLE, 绕过了人工复位"
    assert mc._terminal_latched is True

    assert mc.clear_fault("人工复位") is True         # 唯一出口仍然可用
    assert mc.state == "IDLE" and mc._terminal_latched is False


# =============================================================================
# 8) 第三轮审计 P0: FAULT 下降必须是闭环(返回值 + 收尾降落)
# =============================================================================

class _FailingDescentDrone(FakeDrone):
    """emergency_descent 返回 False(表示"没有下降能力")的假机体。"""

    def emergency_descent(self, *a, **kw):
        self.calls.append("emergency_descent")
        return False


class _LowDrone(FakeDrone):
    """已确认低空(<=30cm)的假机体。"""

    def get_height(self):
        return 10


def test_fault_descent_failure_is_escalated_not_ignored():
    """emergency_descent 返回 False 时必须显式升级, 不能假装在下降。"""
    mc = _mc(mock=False)
    drone = _FailingDescentDrone(flying=True, height_known=True)
    mc.drone = drone
    mc.mark_fault("故障")
    assert mc._fault_descent_started is False
    assert mc._fault_descent_failures >= 1, "下降失败必须被计数/告警"

    before = mc._fault_descent_failures
    for _ in range(3):
        mc._handle_state_machine(np.zeros(3))
    assert mc._fault_descent_failures > before, "终态期间应持续察觉下降未推进"


def test_fault_descent_lands_when_low_altitude_confirmed():
    """确认低空后必须调 land() 收尾 —— emergency_descent 自己不会 land。"""
    mc = _mc(mock=False)
    drone = _LowDrone(flying=True, height_known=True)
    mc.drone = drone
    mc.mark_fault("故障")
    drone.calls.clear()
    for _ in range(3):
        mc._handle_state_machine(np.zeros(3))
    assert drone.calls.count("land") == 1, "低空确认后应请求降落收尾一次, 实际 {}".format(drone.calls)


def test_fault_descent_stops_issuing_after_touchdown():
    """彻底落地后不再继续下发下降/降落指令。"""
    mc = _mc(mock=False)
    drone = _LowDrone(flying=False, height_known=True)
    mc.drone = drone
    mc.mark_fault("故障")
    drone.calls.clear()
    for _ in range(5):
        mc._handle_state_machine(np.zeros(3))
    assert drone.calls == [], "未起飞/已落地时不应再下发任何动作, 实际 {}".format(drone.calls)


# =============================================================================
# 9) 第三轮审计 P1: 零视频帧也是"视频不可用"
# =============================================================================

def test_zero_video_frames_eventually_count_as_stalled():
    """从未拿到任何帧时, 冻结检测必须能触发(否则 INSPECT 白等到超时当成功)。"""
    mc = _mc(mock=False)
    mc.drone = FakeDrone(flying=True)
    mc.attach_localization_source(_FixedSource([0.0, 0.0, 100.0]))   # 定位独立可用
    mc.state = "INSPECT"
    mc._video_frame = None

    mc._state_entry_time = time.time()               # 刚进入 -> 不判失效
    assert mc.video_stalled() is False

    mc._state_entry_time = time.time() - (mc.VIDEO_STALL_MAX_AGE_S + 1.0)
    assert mc.video_stalled() is True, "零视频帧超时后必须判为视频不可用"


def test_zero_video_frames_fail_the_inspection_midmission():
    """零视频帧的 INSPECT 必须 MISSION_FAILED(且原因可读)。"""
    mc = _mc(mock=False)
    drone = FakeDrone(flying=True, height_known=True)
    mc.drone = drone
    mc.attach_localization_source(_FixedSource([0.0, 0.0, 100.0]))
    mc.state = "INSPECT"
    mc._video_frame = None
    mc._state_entry_time = time.time() - (mc.VIDEO_STALL_MAX_AGE_S + 1.0)

    assert mc._check_task_validity() is True
    assert mc.state == "MISSION_FAILED"
    assert "VIDEO_STALLED" in (mc.get_state_dict().get("mission_failed_reason") or "")


# =============================================================================
# 10) 第三轮审计 P1: 真机高度能力必须 fail-closed
# =============================================================================

class _NoHeightProbeDrone(FakeDrone):
    """没实现 height_is_known() 的真机适配器(契约不符)。"""

    height_is_known = None


def test_missing_height_probe_is_fail_closed():
    """适配器不提供 height_is_known() 时按"高度不可信"处理, 而不是默认可信。"""
    mc = _mc(mock=False)
    mc.drone = _NoHeightProbeDrone(flying=True)
    assert mc.height_is_known() is False
    assert mc._safe_height_cm() is None


def test_simulation_height_is_trusted():
    """仿真由物理模型给出高度, 恒为可信(此改动不影响仿真路径)。"""
    mc = _mc(mock=True)
    assert mc.height_is_known() is True


# =============================================================================
# 11) 第四轮审计 D1/D2: 降落失败不得记成成功; 复位必须有落地证据
# =============================================================================

def test_fault_land_failure_is_not_recorded_as_success():
    """D1+D17: land() 失败(真机 -> EMERGENCY)不得记为成功, 也不得空转重试 land()。"""
    mc = _mc(mock=False)
    drone = FakeDrone(flying=True, height=10.0, land_ok=False, state="HOVERING")
    mc.drone = drone
    mc.mark_fault("空中故障")

    drone.calls.clear()
    mc._handle_state_machine(np.zeros(3))
    assert "land" in drone.calls, "低空 + 可降落状态时未尝试收尾降落"
    assert mc._fault_land_requested is False, "降落失败被记成了成功"
    assert mc._fault_land_failures >= 1, "降落失败未被计数"

    # 失败后适配器处于 EMERGENCY: 该状态下 land() 不会下发任何命令(真机 tello_basic.py:290)
    # -> 必须改为继续 RC 下降, 而不是反复调用一个空转的 land()。
    drone.calls.clear()
    for _ in range(mc.FAULT_LAND_RETRY_FRAMES + 2):
        mc._handle_state_machine(np.zeros(3))
    assert drone.calls.count("land") == 0, "在 EMERGENCY 下空转重试 land()"
    assert drone.calls.count("emergency_descent") > 0, "EMERGENCY 下停止了安全下降动作"


def test_fault_treats_unknown_height_as_airborne_even_when_not_flying():
    """D1: is_flying 为 False(真机降落失败转 EMERGENCY 的情形)但高度未知时仍需继续下降。"""
    mc = _mc(mock=False)
    drone = FakeDrone(flying=False, height_known=False)
    mc.drone = drone
    mc.state = "FAULT"
    mc._terminal_latched = True

    drone.calls.clear()
    mc._handle_state_machine(np.zeros(3))
    assert "emergency_descent" in drone.calls,         "高度未知时被 is_flying=False 骗过, 停止了安全动作: {}".format(drone.calls)


def test_fault_landing_success_then_grounded_allows_reset():
    """D1+D2 合起来: 收尾降落成功 -> 高度归零 -> 才允许复位。"""
    mc = _mc(mock=False)
    drone = FakeDrone(flying=True, height=10.0, land_ok=True)
    mc.drone = drone
    mc.mark_fault("故障")

    drone.calls.clear()
    for _ in range(3):
        mc._handle_state_machine(np.zeros(3))
    assert mc._fault_land_requested is True
    assert drone.calls.count("land") == 1, "收尾降落应只下发一次, 实际 {}".format(drone.calls)
    assert mc.clear_fault("落地后复位") is True
    assert mc.state == "IDLE"


def test_clear_fault_requires_operator_confirmation_when_height_unknown():
    """D2: 高度不可知时默认拒绝复位; 只有操作员显式确认才放行。"""
    mc = _mc(mock=False)
    mc.drone = FakeDrone(flying=False, height_known=False)
    mc.mark_fault("故障")

    assert mc.clear_fault("无依据复位") is False
    assert mc.state == "FAULT"
    assert mc.clear_fault("操作员确认", operator_confirmed=True) is True
    assert mc.state == "IDLE"


def test_emergency_state_with_fresh_low_height_is_not_treated_as_landed():
    """D17(第五轮审计): EMERGENCY + 遥测新鲜 + 高度 25cm 时, 必须继续下降而不是停手。"""
    mc = _mc(mock=False)
    drone = FakeDrone(flying=False, height_known=True, height=25.0, state="EMERGENCY")
    mc.drone = drone
    mc.state = "FAULT"
    mc._terminal_latched = True

    drone.calls.clear()
    mc._handle_state_machine(np.zeros(3))
    assert drone.calls.count("emergency_descent") > 0, "被 is_flying=False 骗过而停手"
    assert drone.calls.count("land") == 0, "EMERGENCY 下调用 land() 只会空转"


def test_emergency_state_refuses_reset_without_operator_confirmation():
    """D17: EMERGENCY 下即使高度读数 <30cm, 也不能据此复位。"""
    mc = _mc(mock=False)
    mc.drone = FakeDrone(flying=False, height_known=True, height=25.0, state="EMERGENCY")
    mc.mark_fault("故障")

    assert mc.clear_fault("无依据复位") is False
    assert mc.state == "FAULT"
    assert mc.clear_fault("操作员确认", operator_confirmed=True) is True
    assert mc.state == "IDLE"


def test_touchdown_band_stops_actuation_in_emergency():
    """衍生缺口②: EMERGENCY 下高度已到触地带(<=5cm 连续 3 帧)后必须停止继续下压。"""
    mc = _mc(mock=False)
    drone = FakeDrone(flying=False, height_known=True, height=3.0, state="EMERGENCY")
    mc.drone = drone
    mc.mark_fault("降落失败")
    drone.calls.clear()

    for _ in range(3):                       # 连续 3 帧触地确认
        mc._handle_state_machine(np.zeros(3))
    assert "emergency_descent" in drone.calls, "触地确认前应仍在推进下降"
    before = drone.calls.count("emergency_descent")
    for _ in range(4):                       # 确认后不得再下压
        mc._handle_state_machine(np.zeros(3))
    assert drone.calls.count("emergency_descent") == before,         "已进入触地带却仍在持续下压"
    assert mc.clear_fault("落地后复位") is True   # 触地带 + 连续确认 => 可复位
    assert mc.state == "IDLE"


def test_operator_confirmed_reset_uses_adapter_reset_hook():
    """衍生缺口①: 操作员确认后应把适配器从 EMERGENCY 拉回干净态(reset 边可达)。"""
    mc = _mc(mock=False)
    drone = FakeDrone(flying=False, height_known=True, height=25.0, state="EMERGENCY")
    mc.drone = drone
    mc.mark_fault("降落失败")
    drone.calls.clear()

    assert mc.clear_fault("操作员确认", operator_confirmed=True) is True
    assert "reset_from_emergency" in drone.calls, "未触发适配器的 reset 边"
    assert drone.state == "IDLE"
    assert mc.state == "IDLE"


# 审计 D16: 逐帧驱动 runtime/mission 的用例不得让**墙钟**参与判定
# (慢 runner 上心跳间隔可能真的超过 timeout_land=1.0s -> 安全层跳闸 -> 断言失真)
pytestmark = pytest.mark.no_wall_clock
