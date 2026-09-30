"""审计 P0-A / P0-B / P0-C 验收测试: 安全状态闸门与故障终态。

外部审计指出的问题:
  * 自动导航完成时**直接赋值** `self.state = "INSPECT"`, 绕过 `request_state()`
    里的视觉闸门 → 模型加载失败也能走到"巡检完成";
  * 真机位置观测是"上一帧估计的自我循环", 却没有任何机制阻止真机进入
    NAVIGATE / INSPECT / RETURN;
  * 系统没有 MISSION_FAILED / FAULT 终态;
  * `_update()` 没有故障保护层: 传感器/控制器异常会冲穿主循环, 控制线程
    静默死掉而无人机还在空中。

本文件锁定修复后的行为: 所有状态转换收口到 `_set_state()`, 闸门对**自动**
路径同样生效, 被拦下的自动转换进入 MISSION_FAILED 而不是假装正常。
"""

import numpy as np

from backend.main import MissionController


def _mc(mock=True):
    return MissionController(mode="simulation", mock=mock)


# ---------- P0-A: 自动导航的视觉闸门 ----------

def test_auto_navigate_to_inspect_fails_when_vision_unavailable():
    """核心验收: 自动导航到达巡检点且视觉不可用 -> 必须 MISSION_FAILED。"""
    mc = _mc()
    mc.state = "NAVIGATE"
    mc.path = np.array([[0.0, 0.0, 100.0]])
    mc.path_idx = 1                      # 路径已走完 -> 触发"进入巡检"
    mc.detector.status = "VISION_UNAVAILABLE"
    mc.detector.unavailable_reason = "unit test"

    mc._update_inner()

    assert mc.state == "MISSION_FAILED", "实际状态: {}".format(mc.state)
    reason = mc.get_state_dict()["mission_failed_reason"]
    assert reason and "VISION" in reason, reason


def test_auto_navigate_to_inspect_succeeds_when_vision_ok():
    """视觉可用时原路径不受影响。"""
    mc = _mc()
    mc.state = "NAVIGATE"
    mc.path = np.array([[0.0, 0.0, 100.0]])
    mc.path_idx = 1
    mc.detector.status = "OK"

    mc._update_inner()
    assert mc.state == "INSPECT"


def test_manual_inspect_request_refused_and_state_unchanged():
    mc = _mc()
    mc.state = "NAVIGATE"
    mc.detector.status = "VISION_UNAVAILABLE"
    assert mc.request_state("INSPECT") is False
    assert mc.state == "NAVIGATE", "手工请求被拒时不得改变状态"


# ---------- P0-B: 真机缺少外部定位 ----------

def test_real_mode_without_localization_refuses_position_states():
    mc = _mc(mock=False)
    assert mc.localization_available() is False
    for st in ("NAVIGATE", "INSPECT", "RETURN"):
        mc.state = "HOVERING"
        assert mc.request_state(st) is False, st
        assert mc.state == "HOVERING", st


def test_real_mode_with_external_localization_allows():
    """接上**真实可读**的外部定位源后, 依赖位置的状态恢复可用。

    注意: 只给一个名字是不够的 —— 旧接口 `enable_external_localization("xxx")`
    只要一个字符串就宣称"有定位了", 闸门形同虚设。现在必须真的接一个能
    `read()` 出可用观测的源(见 backend/localization/)。
    前置状态必须是转换表允许的前驱(NAVIGATE→INSPECT);
    HOVERING→INSPECT 本就不合法, 会被转换表拦下(与本闸门无关)。
    """
    from backend.localization import GroundTruthLocalizationSource

    mc = _mc(mock=False)
    assert mc.localization_available() is False, "未接定位源时必须不可用"
    mc.attach_localization_source(GroundTruthLocalizationSource([0.0, 0.0, 100.0]))
    assert mc.localization_available() is True
    mc.state = "NAVIGATE"
    mc.detector.status = "OK"
    assert mc.request_state("INSPECT") is True


class _FixedSource:
    """返回一条固定观测的定位源(用于构造过期/低质量场景)。"""

    name = "fixed-test-source"

    def __init__(self, obs):
        self._obs = obs

    def read(self):
        return self._obs


def _obs(position, age_s=0.0, quality=1.0):
    import time as _time

    from backend.localization import LocalizationObservation

    return LocalizationObservation(
        position=np.asarray(position, dtype=float),
        timestamp=_time.monotonic() - age_s,
        quality=quality,
        source="fixed-test-source",
    )


def test_stale_localization_blocks_position_states():
    """过期的定位观测必须让闸门重新关闭(不能拿旧坐标继续导航)。"""
    from backend.localization import MAX_AGE_S

    mc = _mc(mock=False)
    mc.attach_localization_source(_FixedSource(_obs([0.0, 0.0, 100.0], age_s=MAX_AGE_S + 1.0)))
    assert mc.localization_available() is False
    mc.state = "HOVERING"
    assert mc.request_state("NAVIGATE") is False


def test_low_quality_localization_blocks_position_states():
    """质量低于阈值的观测同样不可用。"""
    from backend.localization import MIN_QUALITY

    mc = _mc(mock=False)
    mc.attach_localization_source(
        _FixedSource(_obs([0.0, 0.0, 100.0], quality=MIN_QUALITY / 2.0)))
    assert mc.localization_available() is False


def test_fresh_localization_is_used_as_position_observation():
    """接入健康定位后, 真机传感器观测里的位置应来自**外部定位**而非自我循环。"""
    mc = _mc(mock=False)
    mc.attach_localization_source(_FixedSource(_obs([123.0, -45.0, 80.0])))
    z = mc._get_sensor_data()
    assert z is not None
    assert z[3] == 123.0 and z[4] == -45.0, "光流通道必须来自外部定位: {}".format(z)
    sd = mc.get_state_dict()
    assert sd["localization_quality"] is not None
    assert sd["localization_age_s"] is not None


def test_mock_mode_has_localization_truth():
    """仿真里位置来自物理模型, 视为可信。"""
    mc = _mc()
    assert mc.localization_available() is True


# ---------- P0-C: 控制循环故障保护层 ----------

def test_control_loop_exception_enters_fault_and_stops_velocity():
    mc = _mc()
    calls = []
    mc.drone.stop_velocity = lambda: calls.append("stop")

    def boom():
        raise RuntimeError("sensor read failed")

    mc._update_inner = boom
    mc._update()                          # 不得向外抛出

    assert mc.state == "FAULT"
    assert "sensor read failed" in (mc.get_state_dict()["fault_reason"] or "")
    assert calls == ["stop"], "进入 FAULT 之前必须停止速度指令"


# ---------- 状态字典可观测性 ----------

def test_state_dict_exposes_new_safety_fields():
    mc = _mc()
    sd = mc.get_state_dict()
    for key in ("fault_reason", "mission_failed_reason",
                "localization_available", "localization_source"):
        assert key in sd, key
    assert sd["localization_available"] is True
