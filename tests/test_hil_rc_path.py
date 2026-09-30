"""HIL 风格真机 RC 路径端到端测试台 (P0-2 验收)。

被测对象: TelloController(mock=False) -> RCManager -> 底层 djitellopy 对象。
本文件不联网、不连真机, 而是把 `djitellopy` 模块替换成一个**记录型假对象**,
从而在离线环境里跑通真机分支的完整控制链:

    connect() -> takeoff() -> set_velocity() -> land() / kill()

并顺带刻画仿真侧 (SimDroneAdapter + Quadrotor3D) 的速度语义, 作为对照。

设计约束: 线程用例一律"短超时 + 轮询等待", 不依赖长墙钟睡眠, 避免 flaky。
"""

import sys
import threading
import time
import types

import numpy as np
import pytest

from backend.drone.rc_manager import RCManager
from backend.drone.tello_basic import FlightState, TelloController
from backend.simulation.drone_adapter import SimDroneAdapter
from backend.simulation.models import Quadrotor3D


class FakeTello:
    """记录型 djitellopy.Tello 替身。

    rc_frames 元素: (时间戳, lr, fb, ud, yaw) —— 即底层真正收到的 send_rc_control。
    """

    def __init__(self):
        self.rc_frames = []
        self.commands = []
        self.emergencies = 0
        self.is_flying = False
        self.height = 100
        self._lock = threading.Lock()

    def _log(self, name):
        with self._lock:
            self.commands.append(name)

    def connect(self):
        self._log("connect")
        return True

    def takeoff(self):
        self.is_flying = True
        self._log("takeoff")
        return True

    def land(self):
        self.is_flying = False
        self.height = 0
        self._log("land")
        return True

    def emergency(self):
        self.emergencies += 1
        self.is_flying = False
        self._log("emergency")
        return True

    def move_down(self, dist):
        self._log(("move_down", dist))
        return True

    def send_rc_control(self, lr, fb, ud, yaw):
        with self._lock:
            self.rc_frames.append((time.time(), int(lr), int(fb), int(ud), int(yaw)))

    def send_keepalive(self):
        self._log("keepalive")

    def get_battery(self):
        return 100

    def get_height(self):
        return self.height

    def frames(self):
        with self._lock:
            return list(self.rc_frames)

    def values(self):
        return [f[1:] for f in self.frames()]


ZERO = (0, 0, 0, 0)


def _wait_until(pred, timeout=2.0, interval=0.01):
    """轮询等待条件成立; 返回是否成立 (不抛异常, 便于给出可读断言信息)。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(interval)
    return pred()


@pytest.fixture
def hil(monkeypatch):
    """真机分支 + 假底层对象; 退出时确保 RC 线程被回收。"""
    fake = FakeTello()
    module = types.ModuleType("djitellopy")
    module.Tello = lambda *args, **kwargs: fake
    monkeypatch.setitem(sys.modules, "djitellopy", module)

    ctl = TelloController(mock=False)
    try:
        yield ctl, fake
    finally:
        ctl.release()


# =============================================================================
# 1) 真机 RC 路径端到端
# =============================================================================

def test_real_connect_starts_rc_thread_and_streams_velocity(hil):
    """connect() -> takeoff() -> set_velocity(): 20Hz 线程持续下发同一速度。"""
    ctl, fake = hil

    assert ctl.connect() is True
    assert isinstance(ctl._rc, RCManager)
    assert ctl.takeoff() is True
    assert ctl.state == FlightState.HOVERING
    assert fake.commands[:2] == ["connect", "takeoff"]
    assert ctl._rc._running is True, "真机 connect() 必须启动 20Hz RC 发送线程"

    t0 = time.time()
    assert ctl.set_velocity(20, -10, 5, 3) is True
    assert ctl.state == FlightState.MOVING

    target = (20, -10, 5, 3)
    ok = _wait_until(lambda: fake.values().count(target) >= 5, timeout=2.0)
    n = fake.values().count(target)
    elapsed = time.time() - t0
    assert ok, "短窗口内应收到多条 send_rc_control, 实际 {}".format(n)
    assert n >= 5
    # 20Hz 发送 -> 每 50ms 一条; 下限放宽到 10Hz 以免 CI 抖动导致 flaky。
    assert n / elapsed >= 10.0, "实际发送频率约 {:.1f}Hz".format(n / elapsed)
    assert ctl._rc.last_cmd == target, "限幅后的意图指令应等于设定值"


def test_land_sends_zero_and_stops_streaming_velocity(hil):
    """land() 之后必须归零, 且不再继续下发旧速度。"""
    ctl, fake = hil
    ctl.connect()
    ctl.takeoff()
    ctl.set_velocity(30, 0, 0)
    assert _wait_until(lambda: (30, 0, 0, 0) in fake.values(), timeout=2.0)

    t_land = time.time()
    assert ctl.land() is True
    assert "land" in fake.commands
    assert ctl._rc.last_cmd == ZERO, "切入 LANDING 必须先把速度归零"

    assert _wait_until(lambda: fake.values()[-3:] == [ZERO] * 3, timeout=1.5), \
        "land() 后线程应持续下发归零, 实际尾部 {}".format(fake.values()[-3:])
    # 归零之后不允许再出现速度指令(留一个发送周期余量给在途帧)
    frames = fake.frames()
    tail = [f[1:] for f in frames if f[0] > t_land + 0.15]
    assert all(v == ZERO for v in tail), "land() 后仍在下发速度: {}".format(tail)


def test_kill_refused_above_safe_height(hil):
    """审计 P0-D 补完: 高空调用 kill() 必须**拒绝**。

    此前 kill()/legacy_kill 沿用 3m 上限 —— 但"高度 <3m"不是通用安全证明,
    而且该高度本身可能来自陈旧/无效遥测(见 tests/test_safety_separation.py)。
    收紧后: 只有确认在 30cm 以内才允许真正停桨; 即便被拒, 也必须先归零速度。
    """
    ctl, fake = hil
    ctl.connect()
    ctl.takeoff()
    fake.height = 100  # > SAFE_CUTOFF_HEIGHT_CM(30cm)
    ctl.set_velocity(30, 0, 0)
    assert _wait_until(lambda: (30, 0, 0, 0) in fake.values(), timeout=2.0)

    assert ctl.kill() is False, "100cm 处不得停桨"
    assert fake.emergencies == 0, "拒绝时不得调用底层 emergency()"
    assert ctl._rc.last_cmd == ZERO, "即便被拒, 也必须先归零速度"
    assert ctl.state != FlightState.EMERGENCY, "没有停桨就不该声称已处于 EMERGENCY"


def test_kill_allowed_below_safe_height(hil):
    """确认在安全高度以内时, 停桨仍要正常工作(且停桨前先归零)。"""
    ctl, fake = hil
    ctl.connect()
    ctl.takeoff()
    fake.height = 20  # <= 30cm
    ctl.set_velocity(30, 0, 0)
    assert _wait_until(lambda: (30, 0, 0, 0) in fake.values(), timeout=2.0)

    assert ctl.kill() is True
    assert ctl._rc.last_cmd == ZERO
    assert fake.emergencies == 1, "安全高度内 kill() 应调用底层 emergency()"
    assert ctl.state == FlightState.EMERGENCY
    assert _wait_until(lambda: fake.values()[-3:] == [ZERO] * 3, timeout=1.5)


def test_rc_auto_zero_after_zero_timeout_without_new_command(hil):
    """超过 ZERO_TIMEOUT 没有新指令 -> 线程自动归零(防飞丢)。"""
    ctl, fake = hil
    ctl.connect()
    ctl.takeoff()
    rc = ctl._rc
    timeout_s = rc.ZERO_TIMEOUT
    assert timeout_s > 0

    t_cmd = time.time()
    ctl.set_velocity(40, 0, 20)
    assert _wait_until(lambda: (40, 0, 20, 0) in fake.values(), timeout=2.0)

    # 不再下发任何新指令, 只等线程自己超时归零
    assert _wait_until(lambda: fake.values()[-3:] == [ZERO] * 3, timeout=2.0), \
        "超时后未自动归零, 尾部 {}".format(fake.values()[-3:])
    assert rc.last_rc == ZERO

    frames = fake.frames()
    vals = [f[1:] for f in frames]
    idx_last_nz = max(i for i, v in enumerate(vals) if v != ZERO)
    idx_zero = next(i for i, v in enumerate(vals)
                    if i > idx_last_nz and v == ZERO)
    gap = frames[idx_zero][0] - t_cmd
    assert gap >= timeout_s * 0.7, \
        "归零过早({:.3f}s), 说明超时窗口没生效".format(gap)
    assert gap <= timeout_s + 1.0, \
        "归零过晚({:.3f}s), 超时保护可能失效".format(gap)


# =============================================================================
# 2) 仿真适配器行为刻画 (set_velocity vs move_to)
# =============================================================================

def _flying_adapter(dt=0.1):
    quad = Quadrotor3D(dt=dt)
    ad = SimDroneAdapter(quad)
    ad.connect()
    ad.takeoff()   # _target_pos = 当前位置, z=1.2m 悬停目标
    return quad, ad


def _hover_control(quad):
    """悬停推力控制量 [thrust(N), roll, pitch, yaw_rate]。"""
    return np.array([quad.mass * quad.g, 0.0, 0.0, 0.0])


def test_adapter_set_velocity_writes_quad_velocity_channel():
    """set_velocity 立即写 Quadrotor3D 速度通道(cm/s -> m/s), 不瞬移也不改位置目标。"""
    quad, ad = _flying_adapter()
    pos_before = quad.get_position().copy()
    target_before = ad.get_target_pos().copy()
    assert target_before[2] == pytest.approx(1.2)

    assert ad.set_velocity(30, -20, 10) is True

    assert np.allclose(quad.get_velocity(), [0.3, -0.2, 0.1]), \
        "实际速度 {}".format(quad.get_velocity())
    assert np.allclose(quad.get_position(), pos_before), "速度指令不应产生即时位移"
    assert np.allclose(ad.get_target_pos(), target_before), "速度指令不改位置目标"


def test_adapter_move_to_only_moves_target_position():
    """move_to 只改位置目标(_target_pos), 速度与位置都不动 —— 与 set_velocity 正交。

    注意: 仿真主循环 SimRuntime.step() 并不读 _target_pos, 它按 MissionController
    的上一帧速度指令 _last_control 做加速度限制的一阶跟踪; 因此 move_to 在仿真里
    只是一个"位置目标"记录, 仿真有自己的一套控制架构。
    """
    quad, ad = _flying_adapter()
    ad.hover()
    assert np.allclose(quad.get_velocity(), np.zeros(3))
    pos_before = quad.get_position().copy()

    assert ad.move_to(100, 0, 50) is True   # 相对位移 cm

    assert np.allclose(quad.get_position(), pos_before), "move_to 不产生即时位移"
    assert np.allclose(quad.get_velocity(), np.zeros(3)), "move_to 不写速度通道"
    assert np.allclose(ad.get_target_pos(), pos_before + [1.0, 0.0, 0.5]), \
        "目标位置应为 当前位置 + 100cm/-0cm/50cm, 实际 {}".format(ad.get_target_pos())


def test_adapter_set_velocity_and_move_to_rejected_before_takeoff():
    quad = Quadrotor3D()
    ad = SimDroneAdapter(quad)
    ad.connect()
    assert ad.set_velocity(30, 0, 0) is False
    assert ad.move_to(100, 0, 0) is False
    assert np.allclose(quad.get_velocity(), np.zeros(3))


# =============================================================================
# 3) 指令 -> 物理闭环 (Quadrotor3D.step)
# =============================================================================

def test_quad_step_displaces_along_velocity_command():
    """恒定速度指令 20 步(2s)后, 位移方向与指令一致且量级合理。

    单位链: set_velocity(cm/s) -> Quadrotor3D 速度(m/s) -> step(dt 秒) -> 位置(m)。
    悬停推力下只有气动阻力衰减速度, 因此位移必须 <= 无阻力上限 v*t。
    """
    quad, ad = _flying_adapter()
    start = quad.get_position().copy()
    assert ad.set_velocity(30, -20, 0) is True    # +0.3 m/s x, -0.2 m/s y

    for _ in range(20):
        quad.step(_hover_control(quad), dt=0.1)   # 2.0 s

    d = quad.get_position() - start
    assert d[0] > 0.15, "x 位移应显著为正, 实际 {:.3f}m".format(d[0])
    assert d[1] < -0.10, "y 位移应显著为负, 实际 {:.3f}m".format(d[1])
    assert abs(d[2]) < 1e-6, "无 z 指令不应升降, 实际 {:.3f}m".format(d[2])
    assert d[0] <= 0.3 * 2.0 + 1e-9, "位移不应超过无阻力上限 v*t"
    assert quad.get_velocity()[0] > 0, "速度应保持指令方向"


def test_sustained_commands_hold_speed_where_single_shot_decays():
    """"持续速度指令"与"一次性位移"的物理差别: 每步重发才维持速度。"""
    def fly(resend_each_step, n=20, dt=0.1):
        quad, ad = _flying_adapter(dt=dt)
        start = quad.get_position().copy()
        ad.set_velocity(30, 0, 0)
        for _ in range(n):
            if resend_each_step:
                ad.set_velocity(30, 0, 0)
            quad.step(_hover_control(quad), dt=dt)
        return (quad.get_position() - start)[0], quad.get_velocity()[0]

    one_shot_dx, one_shot_v = fly(False)
    sustained_dx, sustained_v = fly(True)

    assert 0.15 < one_shot_dx < 0.6, "一次性指令位移 {:.3f}m".format(one_shot_dx)
    assert sustained_dx > one_shot_dx * 1.3, \
        "20Hz 持续重发应比一次性指令走得更远 ({:.3f} vs {:.3f})".format(
            sustained_dx, one_shot_dx)
    assert sustained_v > 0.2, "持续重发应维持接近 0.3m/s 的速度, 实际 {:.3f}".format(
        sustained_v)
    assert one_shot_v < sustained_v


def test_vertical_velocity_command_climbs():
    """z 正方向 = 上升: 指令(cm/s) -> 高度(m) 单调增加。"""
    quad, ad = _flying_adapter()
    z0 = quad.get_position()[2]
    assert ad.set_velocity(0, 0, 20) is True      # +0.2 m/s 上升

    for _ in range(15):
        quad.step(_hover_control(quad), dt=0.1)   # 1.5 s

    dz = quad.get_position()[2] - z0
    assert dz > 0.1, "应爬升, 实际 dz={:.3f}m".format(dz)
    assert dz <= 0.2 * 1.5 + 1e-9
    assert quad.get_velocity()[2] > 0
