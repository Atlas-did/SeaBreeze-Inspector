"""§14.4 保真度**接线**的验收测试。

分工说明:
  * `tests/test_transport_model.py` /  `tests/test_transport_fidelity.py` 覆盖传输模型本身；
  * `tests/test_ekf_delayed_measurement.py` 覆盖 EKF 对测量年龄的处理；
  * **本文件测接线**：整包反馈是否真的整体延迟、丢包是否真的表达给控制器、
    以及"遥测陈旧"是否可观测。

背景（审计 §14.4）:
  1. 之前只有 6 维遥测 z 走传输模型, pos/vel/att 仍是瞬时真值 —— 延迟被低估；
  2. 之前没有测量年龄, 延迟包被当成"刚到的新测量";
  3. 之前 `stale_after_s` 没有接任何降级/可观测路径。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402

from backend.main import MissionController  # noqa: E402
from backend.runtime.loop import SimRuntime  # noqa: E402
from backend.simulation.models import (  # noqa: E402
    Quadrotor3D,
    RobotArm3DOF,
    VirtualSensor,
    WindDisturbance,
)

DT = 0.02


def _silence_logger(mc):
    mc.logger.start_session = lambda *a, **k: None
    mc.logger.log_frame = lambda *a, **k: None


def _runtime(**kwargs):
    mc = MissionController(mode="simulation", mock=True)
    _silence_logger(mc)
    wind = WindDisturbance(base_wind=np.zeros(3), freq=0.0, gust_amp=0.0)
    sensor = VirtualSensor(imu_noise=0.0, opt_noise=0.0, bar_noise=0.0,
                           bias_drift_rate=0.0, rw_std=0.0)
    rt = SimRuntime(mc, Quadrotor3D(), wind, RobotArm3DOF(), sensor, **kwargs)
    return mc, rt


def _spy_feedback(mc):
    """记录每次喂给控制器的 (pos_cm, vel_cmps, kwargs)。"""
    seen = []
    real = mc.update_with_external_data

    def spy(sensor_z, position, velocity, attitude, **kw):
        seen.append({
            "pos_cm": np.asarray(position, dtype=float).copy(),
            "vel_cmps": np.asarray(velocity, dtype=float).copy(),
            "kwargs": dict(kw),
        })
        return real(sensor_z, position, velocity, attitude, **kw)

    mc.update_with_external_data = spy
    return seen


def test_default_path_feeds_current_truth_bitwise():
    """默认(全 0)时反馈必须是**本帧采样时刻**的真值 —— 接线不能改变既有数值。

    注意采样时序: `step()` 在**物理步进之前**读位置, 所以喂给 mc 的是步进前的真值;
    与之比较也必须用步进前的值(拿步进后的值比会差一个物理步)。
    """
    mc, rt = _runtime()
    seen = _spy_feedback(mc)
    rt.step(DT, {"Space"})
    for _ in range(10):
        before_cm = rt.quad.get_position() * 100.0
        rt.step(DT, set())
        assert np.array_equal(seen[-1]["pos_cm"], before_cm), \
            "默认路径喂给 mc 的位置应逐位等于本帧采样时刻的真值"


def test_latency_applies_to_whole_feedback_packet_not_only_z():
    """延迟必须作用在**整包反馈**上: 位置/速度反馈也要跟着变旧。"""
    mc, rt = _runtime(sensor_latency_s=0.1)     # 0.1s / dt 0.02 = 5 帧
    seen = _spy_feedback(mc)
    rt.step(DT, {"Space"})
    for _ in range(30):
        rt.step(DT, set())

    quad_cm = rt.quad.get_position() * 100.0
    fed_cm = seen[-1]["pos_cm"]
    assert not np.allclose(fed_cm, quad_cm, atol=1e-6), \
        "延迟没有作用到位置反馈上(仍然喂本帧真值) —— 说明只有 z 过了传输模型"


def test_latency_feedback_matches_the_actual_past_sample():
    """整包延迟的正确性: 喂进去的位置应等于若干帧之前的真值, 而不是随手取一个旧值。"""
    mc, rt = _runtime(sensor_latency_s=0.1)
    seen = _spy_feedback(mc)
    history = []
    rt.step(DT, {"Space"})
    for _ in range(40):
        rt.step(DT, set())
        history.append(rt.quad.get_position() * 100.0)

    fed_cm = seen[-1]["pos_cm"]
    # 延迟 5 帧: 用历史里的某一帧比对(允许 1 帧的边界差)
    deltas = [float(np.linalg.norm(fed_cm - h)) for h in history]
    best = int(np.argmin(deltas))
    age_frames = len(history) - 1 - best
    assert deltas[best] < 5.0, "喂进去的位置不是任何历史帧的真值: 最小差 {}".format(deltas[best])
    assert 3 <= age_frames <= 7, "延迟帧数应在 5 帧附近, 实测 {}".format(age_frames)


def test_dropout_is_reported_as_stale_in_state_dict():
    """丢包必须表达给控制器, 并在状态字典里可观测(不能"看起来一切正常")。"""
    mc, rt = _runtime(sensor_drop_rate=1.0)     # 恒丢
    rt.step(DT, {"Space"})
    for _ in range(20):
        rt.step(DT, set())
    sd = mc.get_state_dict()
    assert sd["telemetry_stale"] is True, "全丢包时必须标记遥测陈旧"
    assert mc._sensor_fresh is False


def test_fresh_path_is_not_marked_stale():
    """正常链路不得误报陈旧(否则会无谓触发 failsafe)。"""
    mc, rt = _runtime()
    rt.step(DT, {"Space"})
    for _ in range(20):
        rt.step(DT, set())
    assert mc.get_state_dict()["telemetry_stale"] is False


# ---------- 上行指令链路 (延迟 / 丢包) ----------

def _hover_velocity_mode(**kwargs):
    mc, rt = _runtime(velocity_command_mode=True, **kwargs)
    rt.step(DT, {"Space"})
    for _ in range(600):
        data = rt.step(DT, set())
        if data["state"] == "HOVERING":
            return mc, rt
    raise AssertionError("未进入 HOVERING")


def test_uplink_total_loss_means_vehicle_never_receives_commands():
    """上行链路**中途死亡**: 控制器一直在发速度, 机体却一动不动。

    这正是真机上最难排查的失效("界面显示在发速度、飞机没反应"), 仿真必须能复现。
    注意: 上线就全丢包的话连起飞指令都到不了机体, 所以这里先健康悬停, 再杀掉链路
    (等价于飞行中 Wi-Fi 断)。
    """
    from backend.simulation.transport_model import CommandTransportModel

    mc, rt = _hover_velocity_mode(uplink_latency_s=0.02)   # 建出上行链路对象
    assert rt._command_transport is not None

    rt._command_transport = CommandTransportModel(drop_rate=1.0)   # 链路死亡
    home = rt.quad.get_position().copy()
    mc.set_target(0.0, 200.0, 120.0)      # 前方 2m
    for _ in range(100):                  # 2s
        rt.step(DT, set())
    moved = float(np.linalg.norm(rt.quad.get_position()[:2] - home[:2]))
    assert moved < 0.05, "上行全丢包时不应产生位移, 实测 {:.3f}m".format(moved)
    assert float(np.linalg.norm(rt.adapter.get_commanded_velocity())) > 0.0, \
        "控制器应仍在发指令(只是到不了机体) —— 这才是要复现的失效模式"


def test_uplink_latency_delays_the_vehicle_response():
    """上行延迟: 指令要过延迟线才生效 —— 早期位移应明显小于无延迟情形。"""
    def run(uplink_latency_s):
        mc, rt = _hover_velocity_mode(uplink_latency_s=uplink_latency_s)
        home = rt.quad.get_position().copy()
        mc.set_target(0.0, 200.0, 120.0)
        for _ in range(25):               # 0.5s
            rt.step(DT, set())
        return float(np.linalg.norm(rt.quad.get_position()[:2] - home[:2]))

    no_delay = run(0.0)
    with_delay = run(0.3)                 # 0.3s 延迟 = 15 帧
    assert with_delay < no_delay, \
        "有上行延迟时早期位移应更小: 无延迟={:.3f}m, 有延迟={:.3f}m".format(no_delay, with_delay)
    assert no_delay > 0.01, "无延迟时必须真的动了(否则该对比无意义): {:.3f}m".format(no_delay)


import pytest  # noqa: E402  (审计 D16: pytestmark 需要它)


# 审计 D16: 逐帧驱动 runtime/mission 的用例不得让**墙钟**参与判定
# (慢 runner 上心跳间隔可能真的超过 timeout_land=1.0s -> 安全层跳闸 -> 断言失真)
pytestmark = pytest.mark.no_wall_clock
