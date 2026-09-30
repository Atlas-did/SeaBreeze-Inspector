#!/usr/bin/env python3
"""传输层模型测试: 传感器延迟/丢包 + 执行器一阶滞后 (审计 Phase 3)。

全部确定性: 用**仿真时钟**步进 (now = k*dt), 不 sleep、不依赖墙钟。
装配沿用 tests/test_sim_real_alignment.py 的标准做法 (静风 + 零噪声 + 短路
日志落盘), 实测同一装配两次运行逐位一致。

步数约定 (第 1 条延迟测试依赖它):
    第 k 个 poll 的时刻 = k*dt (k 从 1 开始); 在 t=0 push 的样本, 延迟 L 后
    在首个满足 k*dt >= L 的步交付, 即 k = ceil(L/dt)。L=0.1, dt=0.02 -> k=5。
"""

import math
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from backend.main import MissionController
from backend.mission.safety import SafetyLevel
from backend.runtime.loop import SimRuntime
from backend.simulation.models import (
    Quadrotor3D,
    RobotArm3DOF,
    VirtualSensor,
    WindDisturbance,
)
from backend.simulation.transport_model import ActuatorLag, SensorTransportModel

DT = 0.02  # 50Hz, 与 SimRuntime 的 sim_dt 一致


def _make_runtime(velocity_command_mode=False, **transport_kw):
    """标准确定性装配 (静风 + 零噪声 + 短路日志落盘)。"""
    mc = MissionController(mode="simulation", mock=True)
    mc.logger.start_session = lambda *a, **k: None
    mc.logger.log_frame = lambda *a, **k: None
    wind = WindDisturbance(base_wind=np.zeros(3), freq=0.0, gust_amp=0.0)
    sensor = VirtualSensor(imu_noise=0.0, opt_noise=0.0, bar_noise=0.0,
                           bias_drift_rate=0.0, rw_std=0.0)
    return SimRuntime(mc, Quadrotor3D(), wind, RobotArm3DOF(), sensor,
                      velocity_command_mode=velocity_command_mode, **transport_kw)


def _trace(rt, n=200):
    """逐帧 (pos, vel, state) 序列 (首帧按 Space 起飞)。"""
    out = []
    for i in range(n):
        d = rt.step(DT, {"Space"} if i == 0 else set())
        out.append((list(d["pos"]), list(d["vel"]), d["state"]))
    return out


# 改动前 (HEAD) 的 loop.py 在本机跑同一场景 200 帧得到的快照。
# 用容差 (而非逐位) 断言: CI 矩阵包含 ubuntu/windows x py3.11/3.12, 不同 libm
# 的算术可能在反馈回路里累积出 ~1e-13 的差异; 任何**真实的接线回归** (误开
# 延迟线 / 无条件加滞后) 都会让位置偏移 >= 1e-3 m, 所以 1e-5 的容差
# (10 微米) 既有分辨力又不脆弱。同机逐位一致性由下一条测试 (list ==) 保证。
GOLDEN_FRAMES = {
    0: ([0.0, 0.0, 0.0], [0.0, 0.0, 0.06000000000000004], "TAKEOFF"),
    49: ([0.0, 0.0, 0.6612583392110745], [0.0, 0.0, 0.8462688936485365], "TAKEOFF"),
    99: ([0.0, 0.0, 1.1709413937938933], [0.0, 0.0, 0.13564344580943263], "HOVERING"),
    149: ([0.0, 0.0, 1.203711432399911], [0.0, 0.0, -0.005168031131819431], "HOVERING"),
    199: ([0.0, 0.0, 1.200237089758196], [0.0, 0.0, -0.0010218354482052837], "HOVERING"),
}


# =============================================================================
# A. SensorTransportModel — 延迟 (离散延迟线)
# =============================================================================

def test_latency_delivers_at_ceil_latency_over_dt():
    """latency=0.1, dt=0.02: t=0 push 的样本在第 5 步 (t=0.10s) 交付。"""
    m = SensorTransportModel(latency_s=0.1)
    s = np.array([1.0, 2.0, 3.0])
    m.push(s, 0.0)
    got = [m.poll(k * DT) for k in range(1, 11)]
    assert [k for k, g in enumerate(got, start=1) if g is not None] == [5]
    assert got[4] is s                       # 交付的是原样本
    assert m.delivery_count == 1
    assert m.last_delivery_time() == 5 * DT
    assert m.is_stale(5 * DT) is False       # stale_after_s=None -> 不判过期


def test_zero_latency_is_immediate_passthrough():
    """latency=0: 同一时刻 push 的样本在同一时刻 poll 立刻返回。"""
    m = SensorTransportModel()
    s = np.array([4.0])
    m.push(s, 0.0)
    assert m.poll(0.0) is s
    assert m.poll(0.0) is None               # 没有新样本了


def test_latency_queue_delivers_newest_and_supersedes_older():
    """多个包同时到期时交付最新的一条, 旧包被取代 (不计入 delivery/drop)。"""
    m = SensorTransportModel(latency_s=0.04)  # 2 帧
    m.push(np.array([1.0]), 0.0)              # 预定 t=0.04 交付
    m.push(np.array([2.0]), DT)               # 预定 t=0.06 交付
    assert float(m.poll(3 * DT)[0]) == 2.0
    assert m.delivery_count == 1


# =============================================================================
# B. SensorTransportModel — 丢包
# =============================================================================

def test_drop_rate_extremes():
    """drop_rate=1.0 恒不交付; drop_rate=0.0 恒交付。"""
    never = SensorTransportModel(drop_rate=1.0)
    always = SensorTransportModel(drop_rate=0.0)
    for k in range(1, 51):
        v = np.array([float(k)])
        never.push(v, k * DT)
        always.push(v, k * DT)
        assert never.poll(k * DT) is None
        assert always.poll(k * DT) is v
    assert (never.delivery_count, never.drop_count) == (0, 50)
    assert (always.delivery_count, always.drop_count) == (50, 0)


def _delivery_sequence(seed, n=200, drop_rate=0.3):
    """同一调用节奏下的交付/丢包序列 (True=交付)。"""
    m = SensorTransportModel(drop_rate=drop_rate, seed=seed)
    out = []
    for k in range(1, n + 1):
        m.push(np.array([float(k)]), k * DT)
        out.append(m.poll(k * DT) is not None)
    return out


def test_dropout_sequence_is_reproducible_for_a_seed():
    """同一 seed 两次运行序列完全一致; 不同 seed 序列不同 (宽松判定)。"""
    a = _delivery_sequence(0)
    b = _delivery_sequence(0)
    assert a == b
    assert 0 < sum(a) < len(a)               # 200 帧里交付与丢弃都发生过
    assert a != _delivery_sequence(1)


# =============================================================================
# C. SensorTransportModel — 过期判定
# =============================================================================

def test_is_stale_tracks_last_successful_delivery():
    m = SensorTransportModel(stale_after_s=0.5)
    assert m.is_stale(10.0) is False         # 还没 push 过 -> 不判断
    m.push(np.array([1.0]), 0.0)
    assert m.poll(0.0) is not None
    assert m.is_stale(0.4) is False
    assert m.is_stale(0.6) is True
    # 从未交付过 (全丢) 时以首个 push 为基准, 避免刚构造就被判过期
    d = SensorTransportModel(drop_rate=1.0, stale_after_s=0.5)
    d.push(np.array([1.0]), 0.0)
    assert d.poll(0.0) is None
    assert d.is_stale(0.4) is False
    assert d.is_stale(0.6) is True


# =============================================================================
# D. ActuatorLag — 一阶滞后
# =============================================================================

def test_actuator_lag_tau_zero_is_exact_passthrough():
    """tau=0 严格直通: 返回的就是 cmd, 与内部历史状态无关。"""
    lag = ActuatorLag(tau_s=0.0)
    cmd = np.array([1.0, -2.5, 3.0])
    assert np.array_equal(lag.update(cmd, DT), cmd)
    lag.update(np.array([9.0, 9.0, 9.0]), DT)      # 先制造一个不同的内部状态
    assert np.array_equal(lag.update(cmd, DT), cmd)
    assert np.array_equal(ActuatorLag().update(cmd, DT), cmd)   # 默认参数同样直通
    assert ActuatorLag(tau_s=0.0).tau_s == 0.0


def test_actuator_lag_step_response_is_63_percent_at_one_tau():
    """1τ -> 1-1/e ≈ 63.2%; 单调无过冲; 5τ -> >99%。

    取 dt=0.005, 100 步正好 0.5s = 1τ (步数与 tau 对齐)。容差 0.005:
    v_new = v + (cmd-v)*(1-exp(-dt/tau)) 是该 ODE 的闭式解, 误差只来自浮点
    舍入 (实测 ~2e-15), 容差留出的是量纲无关的余量而不是离散误差。
    """
    tau, dt = 0.5, 0.005
    lag = ActuatorLag(tau_s=tau)
    cmd = np.array([1.0, 0.0, 0.0])
    steps = int(round(tau / dt))
    hist = [float(lag.update(cmd, dt)[0]) for _ in range(steps)]
    assert abs(hist[0] - (1.0 - math.exp(-dt / tau))) < 1e-12   # 首步逐点核对公式
    assert hist == sorted(hist)                                # 单调上升, 无过冲
    assert abs(hist[-1] - (1.0 - math.exp(-1.0))) < 0.005      # 1τ ≈ 63.2%
    v = hist[-1]
    for _ in range(steps * 4):                                 # 累计到 5τ
        v = float(lag.update(cmd, dt)[0])
    assert v > 0.99


# =============================================================================
# E. 默认值行为不变 (硬要求: 已发表的高度/悬停数字来自默认路径)
# =============================================================================

def _velocity_trace(rt, n=120):
    """速度指令模式的逐帧快照 (每帧像真机 RCManager 一样持续重发同一指令)。"""
    out = []
    rt.step(DT, {"Space"})
    for _ in range(n):
        rt.adapter.set_velocity(40.0, 0.0, 10.0)   # 0.4 m/s 前 + 0.1 m/s 升
        d = rt.step(DT, set())
        out.append((list(d["pos"]), list(d["vel"]), d["state"]))
    return out


def test_default_path_matches_pre_change_golden():
    """不传新参数 == 改动前版本 (快照取自未改动的 loop.py)。"""
    trace = _trace(_make_runtime(), 200)
    for i, (gpos, gvel, gstate) in GOLDEN_FRAMES.items():
        pos, vel, state = trace[i]
        assert state == gstate, (i, state, gstate)
        assert np.allclose(pos, gpos, rtol=0, atol=1e-5), (i, pos, gpos)
        assert np.allclose(vel, gvel, rtol=0, atol=1e-5), (i, vel, gvel)


def test_explicit_zero_params_are_bitwise_identical_to_default():
    """显式传 0 == 不传: 逐帧位置/速度/状态完全相等 (列表 == 逐位比较)。"""
    a = _make_runtime()
    b = _make_runtime(sensor_latency_s=0.0, sensor_drop_rate=0.0,
                      actuator_tau_s=0.0, transport_seed=7)
    for fa, fb in zip(_trace(a, 200), _trace(b, 200)):
        assert fa == fb, (fa, fb)
    # 关闭时两个模型对象都不创建 -> 结构上不可能影响数值
    assert a._sensor_transport is None
    assert a._actuator is None


def test_velocity_mode_zero_tau_is_identical_to_no_param():
    """速度指令模式 + tau=0 == 不传该参数 (逐帧逐位)。"""
    a = _velocity_trace(_make_runtime(velocity_command_mode=True))
    b = _velocity_trace(_make_runtime(velocity_command_mode=True, actuator_tau_s=0.0))
    assert a == b


# =============================================================================
# F. 接线: 丢包 -> "本帧没有新遥测" -> 看门狗
# =============================================================================

def test_dropout_frame_clears_sensor_fresh_and_freezes_heartbeat():
    """drop_rate=1.0: 每帧都被显式表达为"没有新遥测", 心跳一次都不再刷新。

    本用例只验证**不变量**: 每帧都没有新遥测、心跳不前进、位置级联照常推进。

    注意(脆弱点及其处理): FailsafeMonitor 用的是**墙钟** `time.time()`。机器负载高时
    这几十帧真的可能花掉 >1.0s, 安全层于是按设计跳闸 LAND —— 那是**正确行为**, 但会让
    本用例的不变量结论失真(实测全量跑时为 LAND、单独跑时为 TAKEOFF)。所以这里把看门狗
    的"上次心跳"推到未来, 把墙钟因素显式排除; 超时跳闸本身由
    test_frozen_heartbeat_reaches_timeout_land_and_kill_tiers 用回拨时间戳做确定性验证。

    (更深一层的修法: 让仿真路径的 failsafe 走**仿真时间**而不是墙钟 —— 见
    docs/HIL_PROTOCOL.md 的后续项。这里先保证用例确定。)
    """
    rt = _make_runtime(sensor_drop_rate=1.0)
    guard = rt.mc.safety_guard
    # **必须在任何步进之前**把上次心跳推到未来: 否则满载下光是前 60 帧预热就可能
    # 花掉 >1.0s 墙钟, 安全层会提前跳闸 LAND, 机体掉头下降(实测高度 0.39 < 0.5)。
    guard._last_heartbeat = time.time() + 3600.0
    rt.step(DT, {"Space"})
    for _ in range(60):                     # 让位置级联把机体抬起来
        rt.step(DT, set())
    hb = guard._last_heartbeat
    for _ in range(20):
        rt.step(DT, set())
        assert rt.mc._sensor_fresh is False       # 本帧没有新遥测
        assert guard._last_heartbeat == hb        # 心跳没有前进
    assert rt._sensor_transport.delivery_count == 0
    # 仿真没有卡死: 位置级联照常爬升 (mc 看不到高度)
    assert rt.quad.get_position()[2] > 0.5
    # 收不到高度 -> 状态机无法完成 TAKEOFF→HOVERING
    assert rt.mc.state == "TAKEOFF", rt.mc.state


def test_frozen_heartbeat_reaches_timeout_land_and_kill_tiers():
    """心跳被冻住后, FailsafeMonitor 在 timeout_land/kill 量级给出 LAND/KILL。

    手法: 不 sleep, 直接把心跳戳回拨到超时线之外 —— 与"真的等了那么久"对
    同一段监控代码等价, 且不引入墙钟依赖。已知边界: mc 的仿真入口
    (backend/main.py 的 update_with_external_data) 每帧无条件置
    _sensor_fresh=True 并在超时判定前消费心跳, 所以丢包帧只能做到"置回 False +
    心跳不前进"; 要让它真的在飞行中自动 LAND/KILL 必须改 main.py (本次禁改)。
    """
    rt = _make_runtime(sensor_drop_rate=1.0)
    rt.step(DT, {"Space"})
    for _ in range(60):
        rt.step(DT, set())
    g = rt.mc.safety_guard
    kwargs = dict(battery=100, attitude=[0.0, 0.0, 0.0], height=0.0)
    g._last_heartbeat = time.time() - (g.THRESHOLDS["timeout_land"] + 0.05)
    assert g.check(**kwargs).level == SafetyLevel.LAND
    g._last_heartbeat = time.time() - (g.THRESHOLDS["timeout_kill"] + 0.05)
    assert g.check(**kwargs).level == SafetyLevel.KILL


# =============================================================================
# G. 接线: 传感器延迟 (交付的就是 5 帧前的真值)
# =============================================================================

def test_delivered_telemetry_is_exactly_five_frames_old():
    """latency=0.1, dt=0.02: 第 k 帧喂给 mc 的遥测 == 第 k-5 帧的真值。"""
    rt = _make_runtime(sensor_latency_s=0.1)
    rt.step(DT, {"Space"})
    hist, delivered = [], []
    for _ in range(40):
        rt.step(DT, set())
        hist.append(float(rt.quad.get_position()[2]) * 100.0)  # cm, 本帧真值
        delivered.append(float(rt._last_delivered_z[5]))       # 喂给 mc 的气压高度
    # 暖机期 (前 5 帧还没交付过) 保持引导样本, 不喂空值
    assert delivered[0] == delivered[4]
    for k in range(5, 40):
        assert abs(delivered[k] - hist[k - 5]) < 1e-9, (k, delivered[k], hist[k - 5])
    assert rt._sensor_transport.delivery_count == 36
    assert rt.quad.get_position()[2] > 0.5      # 有延迟也不会卡死


# =============================================================================
# H. 接线: 速度指令模式 + 执行器一阶滞后
# =============================================================================

def _constant_command_run(actuator_tau_s, n=300):
    """恒定 1.0 m/s 速度指令下跑 n 帧, 返回 (首帧速度, 末帧速度)。"""
    rt = _make_runtime(velocity_command_mode=True, actuator_tau_s=actuator_tau_s)
    rt.adapter.takeoff()
    rt.adapter.set_velocity(100.0, 0.0, 0.0)
    rt.quad.set_velocity(np.zeros(3))   # 清掉 set_velocity 对速度通道的直写
    rt._step_velocity_command(DT, np.zeros(3))
    v0 = float(rt.quad.get_velocity()[0])
    for _ in range(n - 1):
        rt._step_velocity_command(DT, np.zeros(3))
    return v0, float(rt.quad.get_velocity()[0])


def test_actuator_lag_makes_body_speed_approach_the_command():
    """tau>0: 首帧远低于 1.0 m/s 指令, 之后渐近逼近 (而不是瞬时到位)。"""
    v0_lag, v_final = _constant_command_run(0.5, n=300)
    v0_direct, _ = _constant_command_run(0.0, n=1)
    # 首帧 = 指令过 1 个 dt 的一阶滞后 (alpha = 1-exp(-0.02/0.5) = 0.0392)
    assert abs(v0_lag - (1.0 - math.exp(-DT / 0.5))) < 1e-12
    assert v0_lag < 0.2 * 1.0
    assert v0_lag < v0_direct              # 比"仅加速度限幅"(0.06 m/s) 还慢
    assert abs(v_final - 1.0) < 1e-3       # 6s = 12τ 后已跟上指令
