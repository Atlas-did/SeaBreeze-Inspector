#!/usr/bin/env python3
"""无头仿真 ↔ 真机"速度指令链路"对齐测试。

背景: 真机链路是
    MissionController.compute() --(cm/s)--> _send_control() --> drone.set_velocity()
    --> RCManager 20Hz 持续下发 --> 机体速度环
而 SimRuntime 默认走的是另一条路 (位置级联: 读 mc.target_pos → 位置环 → 速度环
→ 推力), 控制器下发的速度指令在无头仿真里没有落点。本文件锁住:

  1. 默认模式必须仍是旧的位置级联 (False), 且完全不下发速度指令;
  2. 旧路径里 set_velocity 为什么**不能**当作可对齐的速度指令 (陷阱证据);
  3. velocity_command_mode=True 时物理真的由 adapter 的速度指令驱动
     (恒定指令 → 位移 ≈ v·dt·N; 零指令 → 悬停不漂);
  4. 方向语义与 backend/drone/tello_basic.py 的 set_velocity 文档一致
     (x 正=左, y 正=前, z 正=上升);
  5. IDLE/未起飞不产生位移。

稳定性: 全部用静风 + 零噪声传感器, 且只步进有限帧数 (无墙钟依赖);
实测同一装配两次运行的轨迹逐位一致 (bitwise)。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from backend.main import MissionController
from backend.runtime.loop import SimRuntime
from backend.simulation.models import (
    Quadrotor3D,
    RobotArm3DOF,
    VirtualSensor,
    WindDisturbance,
)

DT = 0.02  # 50Hz, 与 SimRuntime 的 sim_dt 一致


def _silence_logger(mc):
    """短路 FlightLogger 的落盘 (start_session / log_frame), 让测试不碰磁盘。

    本文件只验证物理与速度指令链路, 不验证日志落盘; 而沙箱/CI 下仓库
    data/logs 与 pytest 的 tmp 目录都可能被拒 —— SimRuntime.__init__ 一定会调
    logger.start_session() 去打开 data/logs/<时间>.csv, 不短路就是 PermissionError。
    """
    mc.logger.start_session = lambda *a, **k: None
    mc.logger.log_frame = lambda *a, **k: None


def _make_runtime(velocity_command_mode=False):
    """按仓库标准装配构建 SimRuntime (静风 + 零噪声 → 确定性)。"""
    mc = MissionController(mode="simulation", mock=True)
    _silence_logger(mc)
    wind = WindDisturbance(base_wind=np.zeros(3), freq=0.0, gust_amp=0.0)
    sensor = VirtualSensor(imu_noise=0.0, opt_noise=0.0, bar_noise=0.0,
                           bias_drift_rate=0.0, rw_std=0.0)
    return SimRuntime(mc, Quadrotor3D(), wind, RobotArm3DOF(), sensor,
                      velocity_command_mode=velocity_command_mode)


def _hover(runtime, limit=400):
    """起飞并步进到 HOVERING, 返回所用帧数。"""
    runtime.step(DT, {"Space"})
    for i in range(limit):
        data = runtime.step(DT, set())
        if data["state"] == "HOVERING":
            return i
    raise AssertionError("未进入 HOVERING (state=%s)" % data["state"])


def _issue(runtime, vx, vy, vz, frames):
    """像真机 RCManager 那样, 每个控制周期持续下发同一速度指令 (cm/s)。"""
    for _ in range(frames):
        runtime.adapter.set_velocity(vx, vy, vz)
        runtime.step(DT, set())


# =============================================================================
# 1) 默认路径: 必须是旧的位置级联, 且不碰速度指令
# =============================================================================

def test_default_mode_is_off_and_never_issues_commands():
    """默认构造 = 旧位置级联路径, 全程不下发速度指令。

    硬要求: 论文已发表的悬停/高度精度是在旧路径上测的, 默认值不能翻转。
    锁两件事: (1) velocity_command_mode 默认 False;
    (2) 默认路径下 get_commanded_velocity() 恒为零 —— 新增链路对旧数值零影响。
    """
    rt = _make_runtime()
    assert rt.velocity_command_mode is False
    _hover(rt)
    for _ in range(30):
        rt.step(DT, set())
        assert np.array_equal(rt.adapter.get_commanded_velocity(), np.zeros(3))
    assert rt.quad.get_position()[2] > 1.0  # 旧级联照常把飞机送到悬停高度


# =============================================================================
# 2) 旧路径的陷阱: set_velocity 不是"可对齐真机"的速度指令通道
# =============================================================================

def test_default_path_velocity_command_is_not_a_command_channel():
    """默认(False)路径下 set_velocity 的行为刻画 —— 为什么不默认开。

    实测(静风, 逐位可复现, 见各断言):
      * 连续下发 0.5 m/s 50 帧: 位移 0.4453m (期望 0.5m), 稳态速度 0.4353 ≠ 0.5;
      * 只下发一次: 位移 0.0941m (期望 0.2m), 速度被速度环反向拉过零 (-0.026)。
    原因: set_velocity 只是把指令写进 Quadrotor3D 的速度通道, 而位置级联每帧
    把同一个通道当"当前速度"读, 立刻用 (v_des - vel)/VEL_TAU 去减速 —— 指令不是
    被保持的命令, 而是与位置级联互相打架的一次性注入。

    注意(实测校正): "命令被每帧覆盖、完全不起作用"的说法不成立 —— 注入会经
    速度通道漏进这一帧的积分 (所以 50 帧能飘出 0.445m)。真正的坑是: 执行结果
    由位置级联决定而非由指令决定, 同一指令的位移永远对不上 v·dt。
    """
    # (a) move_to() 在无头仿真里没有消费者: 只改 _target_pos, 物理逐位不变
    ref = _make_runtime()
    _hover(ref)
    moved = _make_runtime()
    _hover(moved)
    assert moved.adapter.move_to(100, 0, 100) is True
    for _ in range(30):
        assert ref.step(DT, set())["pos"] == moved.step(DT, set())["pos"]

    # (b) 连续下发同一指令: 位移明显短于 v·dt·N, 速度也对不上指令
    rt = _make_runtime()
    _hover(rt)
    x0 = rt.quad.get_position().copy()
    _issue(rt, 50, 0, 0, 50)  # 0.5 m/s
    dx = float(rt.quad.get_position()[0] - x0[0])
    expected = 0.5 * DT * 50
    assert 0.80 * expected < dx < 0.95 * expected, "旧路径 dx=%.4f (期望 %.4f)" % (dx, expected)
    assert rt.quad.get_velocity()[0] < 0.5 - 0.02, "旧路径速度未被速度环压低"

    # (c) 只下发一次: 指令完全不被保持 (真机 RC 缺省会持续重发最后指令)
    rt = _make_runtime()
    _hover(rt)
    x0 = rt.quad.get_position().copy()
    rt.adapter.set_velocity(50, 0, 0)
    for _ in range(20):
        rt.step(DT, set())
    dx1 = float(rt.quad.get_position()[0] - x0[0])
    assert dx1 < 0.6 * (0.5 * DT * 20), "旧路径单次指令 dx=%.4f" % dx1
    assert rt.quad.get_velocity()[0] < 0.1, "单次指令未被衰减"


# =============================================================================
# 3) 速度指令模式: 恒定指令 → 位移与 v·dt 同阶; 零指令 → 悬停
# =============================================================================

def test_velocity_mode_constant_command_is_executed():
    """velocity_command_mode=True 时物理真的由指令驱动 (真机同源链路)。"""
    rt = _make_runtime(velocity_command_mode=True)
    _hover(rt)
    p0 = rt.quad.get_position().copy()
    _issue(rt, 50, 0, 0, 50)  # 0.5 m/s 持续 1s
    d = rt.quad.get_position() - p0
    expected = 0.5 * DT * 50
    assert abs(d[0] - expected) < 0.025, "dx=%.4f 期望≈%.4f" % (d[0], expected)
    assert abs(d[1]) < 1e-9, "y 轴不应被 x 指令牵连: %.2e" % d[1]
    assert abs(d[2]) < 0.01, "z 轴不应被 x 指令牵连: %.4f" % d[2]


def test_velocity_mode_zero_command_holds_position():
    """零指令 = 悬停: 位置几乎不动, 速度归零。"""
    rt = _make_runtime(velocity_command_mode=True)
    _hover(rt)
    p0 = rt.quad.get_position().copy()
    _issue(rt, 0, 0, 0, 30)
    assert np.allclose(rt.quad.get_position(), p0, atol=1e-9), \
        "零指令下发生漂移: %s" % (rt.quad.get_position() - p0)
    assert np.linalg.norm(rt.quad.get_velocity()) < 1e-9


# =============================================================================
# 4) 闭环: 不手工下发任何指令, 控制器输出经 set_velocity 驱动物理
# =============================================================================

def test_velocity_mode_closed_loop_reaches_and_holds_hover():
    """控制器 → adapter.set_velocity → 物理 这条链路本身能把飞机飞到悬停高度。

    这是与真机对齐的实质: 速度模式不读 mc.target_pos 做位置级联, 只消费
    adapter 里的速度指令; 起飞/悬停仍能完成, 说明指令链路是完整的闭环。
    """
    rt = _make_runtime(velocity_command_mode=True)
    frames = _hover(rt)
    assert frames < 300, "进入 HOVERING 用了 %d 帧" % frames
    for _ in range(200):
        rt.step(DT, set())
    z = float(rt.quad.get_position()[2])
    assert rt.mc.state == "HOVERING"
    assert 1.0 < z < 1.25, "稳态高度 z=%.4f m" % z


def test_platform_primitive_takeoff_and_landing():
    """TAKEOFF/LAND/EMERGENCY 是机体自主的平台原语, 速度模式必须补垂直指令。

    mc 只在 HOVERING/NAVIGATE/INSPECT/RETURN 调 controller.compute(), 起飞/降落
    没有速度指令; 没有这段补丁飞机永远离不开地面、也降不下去。触地后进 IDLE
    且指令归零 (不留残余指令)。
    """
    rt = _make_runtime(velocity_command_mode=True)
    _hover(rt)
    rt.step(DT, {"KeyE"})  # 紧急降落
    landed = None
    for i in range(300):
        if rt.step(DT, set())["state"] == "IDLE":
            landed = i
            break
    assert landed is not None, "紧急降落未在 300 帧内触地"
    assert float(rt.quad.get_position()[2]) < 0.06, "未触地"
    assert np.array_equal(rt.adapter.get_commanded_velocity(), np.zeros(3))


# =============================================================================
# 5) 方向语义与真机一致 (tello_basic.set_velocity 文档: x左 / y前 / z上)
# =============================================================================

def test_direction_semantics_match_real_rc():
    """x 正=左, y 正=前, z 正=上升 (z-up); 且轴间不串扰。"""
    for axis in (0, 1, 2):
        rt = _make_runtime(velocity_command_mode=True)
        _hover(rt)
        p0 = rt.quad.get_position().copy()
        cmd = [0.0, 0.0, 0.0]
        cmd[axis] = 30.0  # 30 cm/s
        _issue(rt, cmd[0], cmd[1], cmd[2], 40)
        d = rt.quad.get_position() - p0
        assert d[axis] > 0.05, "轴 %d 未沿正方向移动: %s" % (axis, d)
        for other in range(3):
            if other != axis:
                assert abs(d[other]) < 0.01, "轴间串扰 %s" % (d,)


# =============================================================================
# 6) IDLE / 未起飞: 不产生位移
# =============================================================================

def test_idle_and_pre_takeoff_produce_no_motion():
    """未起飞时 set_velocity/move_to 仍返回 False; IDLE 帧不产生任何位移。"""
    rt = _make_runtime(velocity_command_mode=True)
    assert rt.adapter.set_velocity(30, 0, 0) is False
    assert rt.adapter.move_to(100, 0, 0) is False
    for _ in range(20):
        assert rt.step(DT, set())["state"] == "IDLE"
    assert np.array_equal(rt.quad.get_position(), np.zeros(3)), "IDLE 下发生位移"
    assert np.array_equal(rt.adapter.get_commanded_velocity(), np.zeros(3))


import pytest  # noqa: E402  (审计 D16: pytestmark 需要它)


# 审计 D16: 逐帧驱动 runtime/mission 的用例不得让**墙钟**参与判定
# (慢 runner 上心跳间隔可能真的超过 timeout_land=1.0s -> 安全层跳闸 -> 断言失真)
pytestmark = pytest.mark.no_wall_clock
