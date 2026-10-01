#!/usr/bin/env python3
"""遥控上行链路的两条真机语义 (外部审计第 6 条)。

真机 backend/drone/rc_manager.py 的 RCManager 有两条语义, 无头仿真此前都没有:

  1. **超时归零**: 超过 ZERO_TIMEOUT = 0.5s 没有**新指令**, 自动下发零速度
     (防失控飞丢)。仿真以前在上行丢包时无限期保持 `_last_arrived_cmd`,
     结果比真机乐观 —— 本文件的 1~3 号用例钉住"0.5s 之后必须归零"。
  2. **死区即归零**: backend/main.py::_send_control 在三轴都 <1cm/s 时调用
     drone.stop_velocity(), 而不是"什么都不做"(老代码注释里写的"与 main.py
     一致"早已不成立)。用例 4 钉住"三轴 <1cm/s -> 下发的指令是零"。

硬要求 (用例 5): 未启用上行模型 (uplink_latency_s=0 且 uplink_drop_rate=0,
`rt._command_transport is None`) 时, 新增的归零逻辑一行都不执行 —— 速度模式与
默认位置级联的既有数值逐位不变。

确定性: 静风 + 零噪声传感器 + 仿真时钟步进 (now = k*dt), 不 sleep、不读墙钟。
装配沿用 tests/test_sim_real_alignment.py / test_transport_model.py 的标准做法
(短路日志落盘, 否则 SimRuntime.__init__ 会去写 data/logs)。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402

from backend.main import MissionController  # noqa: E402
from backend.runtime.loop import RC_ZERO_TIMEOUT, SimRuntime  # noqa: E402
from backend.simulation.models import (  # noqa: E402
    Quadrotor3D,
    RobotArm3DOF,
    VirtualSensor,
    WindDisturbance,
)
from backend.simulation.transport_model import CommandTransportModel  # noqa: E402

DT = 0.02          # 50Hz, 与 SimRuntime 的 sim_dt 一致
UPLINK_LATENCY = 0.02   # 1 帧上行延迟: 用来"建出上行链路对象"


def _make_runtime(velocity_command_mode=True, **transport_kw):
    """标准确定性装配 (静风 + 零噪声 + 短路日志落盘)。"""
    mc = MissionController(mode="simulation", mock=True)
    mc.logger.start_session = lambda *a, **k: None
    mc.logger.log_frame = lambda *a, **k: None
    wind = WindDisturbance(base_wind=np.zeros(3), freq=0.0, gust_amp=0.0)
    sensor = VirtualSensor(imu_noise=0.0, opt_noise=0.0, bar_noise=0.0,
                           bias_drift_rate=0.0, rw_std=0.0)
    return SimRuntime(mc, Quadrotor3D(), wind, RobotArm3DOF(), sensor,
                      velocity_command_mode=velocity_command_mode, **transport_kw)


def _hover_velocity_mode(limit=600):
    """起飞并步进到 HOVERING (速度指令模式 + 上行链路), 返回 SimRuntime。"""
    rt = _make_runtime(velocity_command_mode=True, uplink_latency_s=UPLINK_LATENCY)
    assert rt._command_transport is not None
    rt.step(DT, {"Space"})
    for _ in range(limit):
        if rt.step(DT, set())["state"] == "HOVERING":
            return rt
    raise AssertionError("未进入 HOVERING (state=%s)" % rt.mc.state)


def _issue(rt, vx, vy, vz, frames):
    """像真机 RCManager 那样每个控制周期持续下发同一指令 (cm/s)。

    返回这段步进里的位移 (m)。指令在 step() 之前写入适配器, 因此本帧
    上行链路 push 出去的就是这条指令 —— 控制器自己的输出不参与本用例。
    """
    p0 = rt.quad.get_position().copy()
    for _ in range(frames):
        rt.adapter.set_velocity(vx, vy, vz)
        rt.step(DT, set())
    return rt.quad.get_position() - p0


def _kill_uplink(rt):
    """链路死亡: 上行指令全部丢失 (飞行中 Wi-Fi 断)。"""
    rt._command_transport = CommandTransportModel(drop_rate=1.0)


def _heal_uplink(rt):
    """链路恢复: 同一条延迟线重新开始工作。"""
    rt._command_transport = CommandTransportModel(latency_s=UPLINK_LATENCY)


# =============================================================================
# 1) 持续丢包 > 0.5s: 指令必须归零 (不能无限期保持上一条)
# =============================================================================

def test_uplink_loss_beyond_zero_timeout_stops_the_vehicle():
    """丢包 >0.5s 后本帧用**零**指令: 0~0.5s 段与 0.5s 之后段的位移差一个量级。

    时间线 (dt=0.02, 最后一条指令在断链前一帧到达):
        断链后第 1..25 帧 (0.02s..0.50s): 年龄 <= 0.5s -> 保持 0.5 m/s
        断链后第 26 帧起 (0.52s...):      年龄 > 0.5s  -> v_cmd = 0
    """
    assert RC_ZERO_TIMEOUT == 0.5          # 常量本身钉死 (来源: RCManager)
    rt = _hover_velocity_mode()
    _issue(rt, 50, 0, 0, 40)               # 先建立 0.5 m/s 的稳定指令 (0.8s)
    assert rt.quad.get_velocity()[0] > 0.45

    _kill_uplink(rt)
    d_before = _issue(rt, 50, 0, 0, 25)    # 断链后 0 ~ 0.5s
    d_after = _issue(rt, 50, 0, 0, 25)     # 断链后 0.5 ~ 1.0s

    assert d_before[0] > 0.2, "0.5s 内应保持上一条指令, 实测 %.4f m" % d_before[0]
    assert d_after[0] < 0.3 * d_before[0], \
        ">0.5s 之后应归零 (只剩减速尾巴): %.4f m vs %.4f m" % (d_after[0], d_before[0])

    # 再走 1s: 速度衰减到零后位置必须**逐位**冻住 (静风, 无残余指令)
    _issue(rt, 50, 0, 0, 60)
    assert np.array_equal(rt.quad.get_velocity(), np.zeros(3)), rt.quad.get_velocity()
    d_frozen = _issue(rt, 50, 0, 0, 20)
    assert np.array_equal(d_frozen, np.zeros(3)), d_frozen


# =============================================================================
# 2) 短暂丢包 < 0.5s: 仍使用"最近到达"的指令 (抖动不该立刻停)
# =============================================================================

def test_short_uplink_loss_keeps_the_last_arrived_command():
    """0.4s 的丢包抖动 < ZERO_TIMEOUT: 机体必须继续按上一条指令飞。"""
    rt = _hover_velocity_mode()
    _issue(rt, 50, 0, 0, 40)
    _kill_uplink(rt)
    d = _issue(rt, 50, 0, 0, 20)           # 20 帧 = 0.4s < 0.5s
    expected = 0.5 * DT * 20               # 0.2 m
    assert abs(d[0] - expected) < 1e-6, \
        "0.4s 丢包应完整保持指令: 实测 %.6f m, 期望 %.6f m" % (d[0], expected)
    assert np.linalg.norm(d[1:]) < 1e-9


# =============================================================================
# 3) 新指令到达 -> 归零计时器重置; 之后再次 >0.5s 无新指令 -> 再次归零
# =============================================================================

def test_new_arrival_resets_the_zero_timer():
    """计时基准是"最近一条指令**到达机体**的时刻", 不是断链时刻。"""
    rt = _hover_velocity_mode()
    _issue(rt, 50, 0, 0, 40)

    _kill_uplink(rt)
    _issue(rt, 50, 0, 0, 60)                       # 1.2s 无新指令 -> 已归零
    assert np.array_equal(rt.quad.get_velocity(), np.zeros(3))

    _heal_uplink(rt)                               # 链路恢复
    d_new = _issue(rt, 50, 0, 0, 15)               # 新指令到达, 机体重新动起来
    assert d_new[0] > 0.03, "链路恢复后应重新听指令: %.4f m" % d_new[0]
    assert rt.quad.get_velocity()[0] > 0.45

    _kill_uplink(rt)                               # 再次断链
    d_hold = _issue(rt, 50, 0, 0, 20)              # 0.4s: 计时器已重置 -> 仍保持
    assert abs(d_hold[0] - 0.5 * DT * 20) < 1e-6, \
        "新指令到达必须重置计时器 (否则 0.4s 就会立刻停): %.6f m" % d_hold[0]

    _issue(rt, 50, 0, 0, 46)                       # 越过 0.5s -> 再次归零并停住
    assert np.array_equal(rt.quad.get_velocity(), np.zeros(3))
    assert np.array_equal(_issue(rt, 50, 0, 0, 20), np.zeros(3))


# =============================================================================
# 4) 死区对齐真机: 三轴都 <1cm/s -> 下发**零** (stop_velocity 语义)
# =============================================================================

class _RecordingAdapter:
    """记录型假 adapter: 委托给真适配器, 同时留痕"下发了什么"。"""

    def __init__(self, inner):
        self._inner = inner
        self.set_velocity_calls = []
        self.clear_calls = 0

    def set_velocity(self, vx, vy, vz, yaw=0.0):
        self.set_velocity_calls.append((vx, vy, vz, yaw))
        return self._inner.set_velocity(vx, vy, vz, yaw)

    def clear_velocity_command(self):
        self.clear_calls += 1
        self._inner.clear_velocity_command()

    def get_commanded_velocity(self):
        return self._inner.get_commanded_velocity()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_dead_zone_issues_zero_instead_of_holding_the_previous_command():
    """死区 (三轴 |v|<1 cm/s) 必须把指令变成零, 不是保持上一条。"""
    rt = _hover_velocity_mode()
    rt.adapter = _RecordingAdapter(rt.adapter)
    rec = rt.adapter
    pos = rt.quad.get_position()

    rt._issue_velocity_command(np.array([5.0, 0.0, 0.0]), pos)      # 死区之外
    assert rec.set_velocity_calls[-1] == (5.0, 0.0, 0.0, 0.0)       # 适配器收 cm/s
    assert np.allclose(rt.adapter.get_commanded_velocity(), [0.05, 0.0, 0.0])

    before = len(rec.set_velocity_calls)
    rt._issue_velocity_command(np.array([0.5, -0.5, 0.0]), pos)     # 死区之内
    cmd = rt.adapter.get_commanded_velocity()
    assert np.array_equal(cmd, np.zeros(3)), "死区必须归零, 实际保留 %s" % cmd
    assert all(max(abs(c) for c in call[:3]) < 1e-12
               for call in rec.set_velocity_calls[before:]), "死区不得下发非零指令"


def test_dead_zone_stops_the_body_end_to_end():
    """死区的物理后果: 指令归零 -> 机体按 MAX_ACCEL 减速停下。

    旧行为 (保持上一条 0.5 m/s) 会给 0.5*0.02*20 = 0.2m 位移; 归零后只剩
    "1 帧在途指令 + 减速尾巴"。
    """
    rt = _hover_velocity_mode()
    rt.adapter.set_velocity(50, 0, 0)
    for _ in range(30):
        rt._step_velocity_command(DT, np.zeros(3))
    assert rt.quad.get_velocity()[0] > 0.45            # 机体已稳定在 0.5 m/s

    rt._issue_velocity_command(np.array([0.5, 0.0, 0.0]), rt.quad.get_position())
    assert np.array_equal(rt.adapter.get_commanded_velocity(), np.zeros(3))

    p0 = rt.quad.get_position().copy()
    for _ in range(20):
        rt._step_velocity_command(DT, np.zeros(3))
    d = float(rt.quad.get_position()[0] - p0[0])
    assert np.linalg.norm(rt.quad.get_velocity()) < 1e-12, rt.quad.get_velocity()
    assert d < 0.1, "死区应让机体减速停下, 实测位移 %.4f m (旧行为 0.2m)" % d


# =============================================================================
# 5) 硬要求: 未启用上行模型 (uplink_*=0) 时逐帧逐位不变
# =============================================================================

def _velocity_trace(rt, n=120):
    """速度模式的逐帧快照 (每帧像真机 RCManager 一样持续重发同一指令)。"""
    out = []
    rt.step(DT, {"Space"})
    for _ in range(n):
        rt.adapter.set_velocity(40.0, 0.0, 10.0)
        d = rt.step(DT, set())
        out.append((list(d["pos"]), list(d["vel"]), d["state"]))
    return out


def test_disabled_uplink_is_bitwise_identical_to_default():
    """uplink_*=0 == 不传这些参数: 逐帧 (pos, vel, state) 逐位相等。

    并且结构上证明新增代码没被执行: 没有传输对象, 上行时钟为 0, 没有"到达"记录。
    """
    a = _make_runtime(velocity_command_mode=True)
    b = _make_runtime(velocity_command_mode=True,
                      uplink_latency_s=0.0, uplink_drop_rate=0.0)
    assert a._command_transport is None and b._command_transport is None

    ta, tb = _velocity_trace(a, 120), _velocity_trace(b, 120)
    for i, (fa, fb) in enumerate(zip(ta, tb)):
        assert fa == fb, (i, fa, fb)

    assert a._cmd_time == 0.0                      # 上行时钟一步都没走
    assert a._last_cmd_arrival_t is None           # 从没有"指令到达"
    assert a._last_arrived_cmd is None

    # 已发表数字所在的位置级联路径 (velocity_command_mode=False) 同样没被碰过
    c = _make_runtime(velocity_command_mode=False)
    c.step(DT, {"Space"})
    for _ in range(60):
        c.step(DT, set())
    assert c._cmd_time == 0.0 and c._last_cmd_arrival_t is None


import pytest  # noqa: E402  (审计 D16: pytestmark 需要它)


# 审计 D16: 逐帧驱动 runtime/mission 的用例不得让**墙钟**参与判定
# (慢 runner 上心跳间隔可能真的超过 timeout_land=1.0s -> 安全层跳闸 -> 断言失真)
pytestmark = pytest.mark.no_wall_clock
