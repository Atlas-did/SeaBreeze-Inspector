"""Tello SDK 边界故障注入测试 (审计 Phase 3)。

被测对象: TelloController / RCManager / MissionController 在 **SDK 边界** 上的
故障行为 —— connect / 遥测读取 / 状态包冻结 / 畸形状态行 / RC 发送 / keepalive /
land / emergency 全部抛异常时, 系统必须"不假成功、不崩溃"。

手法与 tests/test_hil_rc_path.py 一致: 把 sys.modules["djitellopy"] 换成一个
记录型假 Tello, 真机分支被完整跑通, 且每个故障点都能单独注入。

三个关键设计:
  * FakeClock: 把 tello_basic 里的 time 换成可手动推进的假时钟, 于是
    "遥测陈旧(>0.5s)"与 controlled_land/emergency_descent 的超时循环都能
    确定性触发, 不需要真等墙钟 (sleep 只推进假时钟)。
  * FakeSdkTello.calls: 假 SDK 在**抛异常之前**先记录方法名, 因此可以严格区分
    "压根没有调用底层 emergency()" 与 "调用了但底层失败" —— 前者才叫拒绝。
  * 以 test_gap_ 开头的用例断言的是**期望但尚未实现**的性质, 统一标 xfail;
    它们 xpass 的那天, 就说明缺口被补上了。

本文件只新增测试, 不修改任何生产代码。
"""

import sys
import threading
import time
import types

import pytest

import backend.drone.tello_basic as tello_basic
from backend.drone.rc_manager import RCManager
from backend.drone.tello_basic import (
    RX_STAMP_FIELD,
    FlightState,
    TelloController,
    _install_state_stamp,
)
from backend.main import MissionController


class FakeClock:
    """可手动推进的单调时钟 —— 让"遥测陈旧"与各种超时循环离线可测。"""

    def __init__(self, t: float = 10_000.0):
        self.t = float(t)

    def monotonic(self) -> float:
        return self.t

    def time(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        # 不睡墙钟: 只把假时钟往前推, 循环的下一次超时判断立刻成立。
        self.t += max(0.0, float(seconds))

    def advance(self, seconds: float) -> None:
        self.t += float(seconds)


@pytest.fixture
def clock(monkeypatch):
    """把 tello_basic 的时间源替换成假时钟(只影响该模块的全局名)。"""
    c = FakeClock()
    monkeypatch.setattr(tello_basic, "time", c)
    return c


class FakeSdkTello:
    """记录型 djitellopy.Tello 替身, 支持逐方法注入故障。

    fail:  {方法名: 异常实例} —— 被调用时**先记录调用**, 再抛出该异常。
    calls: 被调用过的方法名(含抛异常的那些)。

    先记录后抛异常, 是为了能严格区分"拒绝时压根没碰底层"与"碰了但底层失败"。
    """

    def __init__(self, height: int = 100, battery: int = 88):
        self.height = height
        self.battery = battery
        self.is_flying = False
        self.calls = []
        self.rc_frames = []
        self.fail = {}
        self._lock = threading.Lock()

    def _enter(self, name):
        with self._lock:
            self.calls.append(name)
        exc = self.fail.get(name)
        if exc is not None:
            raise exc

    def __call__(self, *args, **kwargs):
        """让替身可以直接当 Tello 类用: Tello() -> 同一个记录型对象。"""
        return self

    def connect(self):
        self._enter("connect")
        return True

    def takeoff(self):
        self._enter("takeoff")
        self.is_flying = True
        return True

    def land(self):
        self._enter("land")
        self.is_flying = False
        return True

    def emergency(self):
        self._enter("emergency")
        self.is_flying = False
        return True

    def send_rc_control(self, lr, fb, ud, yaw):
        with self._lock:
            self.rc_frames.append((int(lr), int(fb), int(ud), int(yaw)))
        self._enter("send_rc_control")

    def send_keepalive(self):
        self._enter("send_keepalive")

    def get_battery(self):
        self._enter("get_battery")
        return self.battery

    def get_height(self):
        self._enter("get_height")
        return self.height

    def frames(self):
        with self._lock:
            return list(self.rc_frames)

    def values(self):
        return self.frames()


class FakeStateTello(FakeSdkTello):
    """带状态包通道的假 SDK: 复刻 djitellopy 的 parse_state / get_current_state。

    get_* 与真库一样读**状态字典**(缺字段就抛), 因此"状态包冻结"能真实复现:
    包不再更新, 但 getter 仍然返回上一次的值、且不抛异常。
    """

    @staticmethod
    def parse_state(state_str):
        # 与 djitellopy 一致: 畸形字段直接跳过, 不抛异常。
        d = {}
        for field in str(state_str).split(";"):
            kv = field.split(":")
            if len(kv) < 2:
                continue
            try:
                d[kv[0].strip()] = int(kv[1].strip())
            except ValueError:
                continue
        return d

    def __init__(self, **kw):
        super().__init__(**kw)
        self._state = {}

    def feed(self, line):
        """投递一个状态包 (真机里由 UDP 接收线程 parse_state 后写入状态字典)。"""
        # self.parse_state 在 _install_state_stamp 之后即被打点的包装函数。
        self._state = self.parse_state(line)
        return self._state

    def get_current_state(self):
        return self._state

    def get_height(self):
        self._enter("get_height")
        if "h" not in self._state:
            raise RuntimeError("Could not get state property: h")
        return int(self._state["h"])

    def get_battery(self):
        self._enter("get_battery")
        if "bat" not in self._state:
            raise RuntimeError("Could not get state property: bat")
        return int(self._state["bat"])


@pytest.fixture
def drone_factory(monkeypatch):
    """构造 (TelloController(mock=False), 假 SDK), 收尾时回收 RC 线程。"""
    created = []

    def _make(cls=FakeSdkTello, **kw):
        fake = cls(**kw)
        module = types.ModuleType("djitellopy")
        module.Tello = fake          # 可调用替身: Tello() 返回同一个记录对象
        monkeypatch.setitem(sys.modules, "djitellopy", module)
        ctl = TelloController(mock=False)
        created.append(ctl)
        return ctl, fake

    yield _make
    for c in created:
        c.release()


def _wait_until(pred, timeout=1.0, interval=0.01):
    """轮询等待 (短超时, 返回是否成立)。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(interval)
    return pred()


# =============================================================================
# 故障 1: connect() 抛异常 -> 如实失败, 任务不得启动
# =============================================================================

def test_connect_exception_returns_false_and_leaves_no_rc_thread(drone_factory):
    """SDK connect() 抛异常: 返回 False, 状态回落 IDLE, RC 线程不得启动。

    若假成功会怎样: 若 connect() 吞掉异常返回 True(或状态停在 CONNECTING),
    主循环会以为"已经连上"而开始任务 —— 飞机根本没连上, 之后每条指令都打进
    空气里, 而界面/日志显示一切正常。
    """
    ctl, fake = drone_factory()
    fake.fail["connect"] = OSError("UDP 8889 不可达")

    assert ctl.connect() is False, "连接失败必须如实返回 False, 不得假成功"
    assert ctl.state is FlightState.IDLE, "失败后应回落 IDLE, 而不是停在 CONNECTING"
    assert ctl._rc._running is False, "连接失败绝不能启动 20Hz RC 发送线程"
    assert ctl.takeoff() is False, "没连上就不允许起飞"
    assert ctl.is_flying is False


def test_start_does_not_run_mission_when_connect_fails(monkeypatch):
    """MissionController.start(): 连接失败 -> 任务不启动, 且绝不静默降级为模拟。

    只留"连接失败"一条路径: video / logger 打桩, 离线且不碰硬件。
    """
    mission = MissionController(mode="simulation", mock=True)
    monkeypatch.setattr(mission.video_stream, "start", lambda: None)
    monkeypatch.setattr(mission.logger, "start_session", lambda: None)
    monkeypatch.setattr(mission.drone, "connect", lambda *a, **k: False)
    mission.mock = False          # 走真机分支

    assert mission.start() is False
    assert mission._running is False, "连接失败后主循环不得处于运行态"
    assert mission.mock is False, "硬件连不上绝不允许偷偷换成模拟模式"
    assert mission.get_state_dict()["hardware_fault"] == "Tello 连接失败"


# =============================================================================
# 故障 2: 遥测 getter 抛异常 -> 不被打点, 也不许把异常抛穿
# =============================================================================

def test_telemetry_getter_exception_is_not_a_fresh_packet(drone_factory):
    """get_battery()/get_height() 抛异常: 不刷新新鲜度, 异常不抛穿。

    若假成功会怎样: 若把"getter 返回了值"当成"链路还活着", 断链后
    height_is_known() 会拿着陈旧高度放行停桨判断; 若异常抛穿, 主循环直接死。
    """
    ctl, fake = drone_factory()
    assert ctl.connect() is True
    fake.fail["get_battery"] = IOError("SDK 读取超时")
    fake.fail["get_height"] = IOError("SDK 读取超时")

    assert ctl.get_battery() == 0, "读不到电量必须诚实返回 0, 不得沿用旧值"
    assert ctl.get_height() == 0, "读不到高度必须诚实返回 0(0 不等于贴地)"
    assert ctl.last_packet_timestamp is None, "读取失败绝不能被当成收到新包"
    assert ctl.has_fresh_telemetry() is False
    assert ctl.height_is_known() is False
    assert ctl.motor_cutoff("collision") is False, "高度未知时任何理由都不得停桨"
    assert "emergency" not in fake.calls, "被拒绝时不得调用底层 emergency()"


# =============================================================================
# 故障 3: 状态包冻结 (parse_state 不再被调用) -> 高度必须判为未知
# =============================================================================

def test_frozen_state_packet_makes_height_unknown_and_refuses_cutoff(drone_factory, clock):
    """冻结: 不再有新包, 但 getter 仍返回旧的 100cm。

    若假成功会怎样: 断链后 djitellopy 的 getter 照旧返回缓存值且不抛异常,
    若据此认为"高度可用", 停桨闸门就会拿一个可能已经过时几秒的高度做生死判断。
    """
    ctl, fake = drone_factory(FakeStateTello)
    assert ctl.connect() is True
    fake.feed("pitch:0;roll:0;yaw:0;h:100;bat:88")     # 唯一一个真包
    assert ctl.get_height() == 100
    # 对照: 刚收到包时闸门放行 —— 证明下面的 False 来自"陈旧", 不是"永远拒绝"
    assert ctl.has_fresh_telemetry() is True
    assert ctl.height_is_known() is True

    clock.advance(1.1)          # 越过 SAFETY_TELEMETRY_MAX_AGE_S(0.5s)
    assert ctl.get_height() == 100, "冻结时 getter 仍返回旧值(这正是陷阱)"
    assert ctl.has_fresh_telemetry() is False
    assert ctl.height_is_known() is False
    assert ctl.motor_cutoff("legacy_kill") is False
    assert "emergency" not in fake.calls, "拒绝停桨时底层 emergency() 必须零调用"


def test_stale_low_altitude_does_not_authorize_cutoff(drone_factory, clock):
    """陈旧高度哪怕显示"已贴地"(10cm)也不得授权停桨; 同一高度一旦新鲜就放行。

    若假成功会怎样: 只比阈值(10 <= 30)而不查新鲜度, 一次链路中断后残留的
    "10cm"就能触发真停桨 —— 而飞机可能其实还在 10m 高空。
    """
    ctl, fake = drone_factory(FakeStateTello)
    assert ctl.connect() is True
    fake.feed("h:10;bat:88")
    assert ctl.get_height() == 10
    assert ctl.height_is_known() is True
    assert ctl.SAFE_CUTOFF_HEIGHT_CM >= 10, "10cm 本身在阈值内: 拒绝只能来自陈旧"

    clock.advance(0.6)
    assert ctl.motor_cutoff("legacy_kill") is False, "陈旧高度严禁停桨"
    assert "emergency" not in fake.calls

    fake.feed("h:10;bat:88")                    # 同一高度, 但是个新包
    assert ctl.motor_cutoff("legacy_kill") is True, "新鲜且够低时必须真的放行"
    assert fake.calls.count("emergency") == 1


# =============================================================================
# 故障 4: 畸形状态行 -> 解析不得抛穿
# =============================================================================

def test_real_djitellopy_parse_state_survives_garbage():
    """真库边界: 畸形状态行(含空串/ok/非数值字段)不得抛异常。

    真 djitellopy 的 parse_state 对畸形字段是"跳过并记日志", 因此这一层是安全的。
    本用例会把打点包装器套到真 Tello 类上, 结束后原样还原(不改库文件)。
    """
    Tello = pytest.importorskip("djitellopy").Tello
    orig = Tello.__dict__["parse_state"]
    had_flag = "_seabreeze_stamped" in Tello.__dict__
    try:
        assert _install_state_stamp(Tello) is True
        for line in ["", "ok", "garbage", "h:notanumber;bat:xx", ";;;", "h:100"]:
            state = Tello.parse_state(line)
            assert isinstance(state, dict), "畸形行 {!r} 解析后应为 dict".format(line)
            assert RX_STAMP_FIELD in state, "打点包装器必须给每个包盖时间戳"
        assert Tello.parse_state("h:100")["h"] == 100
    finally:
        Tello.parse_state = orig
        if not had_flag:
            delattr(Tello, "_seabreeze_stamped")


def test_malformed_state_line_never_fabricates_altitude(drone_factory):
    """畸形状态包(无有效字段): 不得编造高度, 也不得把异常抛穿控制器。

    若假成功会怎样: 若把"收到过一个包"当成"高度有效", 垃圾包会顶掉真实高度,
    让 height_is_known() 为真 —— 安全闸门就建立在一包垃圾上。
    """
    ctl, fake = drone_factory(FakeStateTello)
    assert ctl.connect() is True
    fake.feed("h:100;bat:88")
    assert ctl.get_height() == 100

    fake.feed("garbage")           # 没有任何有效字段
    assert ctl.get_height() == 0, "无有效高度字段时必须诚实返回 0"
    assert ctl.height_is_known() is False
    assert ctl.motor_cutoff("legacy_kill") is False
    assert "emergency" not in fake.calls


def test_gap_parse_state_error_should_not_kill_state_receiver(drone_factory):
    """已实现(原为 xfail 缺口, 已修): 底层解析器抛异常时, 打点包装器不应把异常放出去。

    现状: _install_state_stamp 直接调用 orig(state_str), 异常原样上抛。
    djitellopy 的 udp_state_receiver 对该异常是 `except Exception: break` ——
    接收线程**永久退出**, 此后 get_current_state() 永远返回旧包(故障 3 的成因)。
    """
    ctl, fake = drone_factory(FakeStateTello)
    orig = fake.parse_state

    def flaky(line):
        if line == "BOOM":
            raise ValueError("底层解析器炸了")
        return orig(line)

    fake.parse_state = flaky
    assert ctl.connect() is True          # 打点包装器套在 flaky 外面
    try:
        fake.parse_state("BOOM")
    except ValueError as e:
        pytest.fail("打点包装器把解析异常抛穿了(会永久杀死状态接收线程): {}".format(e))


# =============================================================================
# 故障 5: send_rc_control 抛异常 -> 不得静默死掉发送线程
# =============================================================================

def test_rc_send_exception_keeps_sender_thread_alive(drone_factory):
    """send_rc_control 抛异常: 主流程不崩, 20Hz 发送线程必须继续跑。

    若假成功会怎样: 若异常冲出 _send_rc, 线程会静默死亡 —— 而 last_rc/last_cmd
    仍在被更新(看起来"一直在发"), 飞机却一条指令都收不到。
    """
    ctl, fake = drone_factory()
    assert ctl.connect() is True
    assert ctl.takeoff() is True
    fake.fail["send_rc_control"] = OSError("UDP 发送失败")
    assert ctl.set_velocity(20, 0, 0) is True
    assert ctl.state is FlightState.MOVING

    n1 = len(fake.frames())
    assert n1 > 0, "必须先真的看到发送尝试"
    assert _wait_until(lambda: len(fake.frames()) > n1, timeout=1.0), \
        "异常之后发送线程必须继续尝试, 实际停在 {} 帧".format(n1)
    assert ctl._rc._running is True


def test_gap_rc_send_failure_should_be_observable(drone_factory):
    """已实现(原为 xfail 缺口, 已修): RC 发送失败要留下可见痕迹(失败计数或最后错误)。

    现状: 底层异常被吞掉, rc_log/last_rc 里失败帧与成功帧长得一模一样,
    排查"界面显示在发速度、飞机却没反应"时无据可依。
    """
    ctl, fake = drone_factory()
    assert ctl.connect() is True
    assert ctl.takeoff() is True
    fake.fail["send_rc_control"] = OSError("UDP 发送失败")
    assert ctl.set_velocity(20, 0, 0) is True
    assert _wait_until(lambda: len(fake.frames()) >= 3, timeout=1.0)

    rc = ctl._rc
    observed = getattr(rc, "send_failures", 0) or getattr(rc, "last_error", None)
    assert observed, "底层发送失败后应留下失败计数/最后错误, 实际没有任何痕迹"


# =============================================================================
# 故障 6: send_keepalive 抛异常 -> 不影响主流程
# =============================================================================

def test_keepalive_exception_does_not_disturb_rc_stream(drone_factory, monkeypatch):
    """keepalive 抛异常: 不得影响 RC 主流(线程不能死, 速度继续发)。

    若假成功会怎样: keepalive 异常冲出 _loop 会让整个发送线程死掉, 于是
    0.5s 超时归零保护也一起消失, 飞机带着最后一条速度指令一直飞。
    """
    monkeypatch.setattr(RCManager, "KEEPALIVE_INTERVAL", 0.01)   # 不真等 3s
    ctl, fake = drone_factory()
    assert ctl.connect() is True
    assert ctl.takeoff() is True
    fake.fail["send_keepalive"] = RuntimeError("keepalive 失败")
    assert ctl.set_velocity(20, 0, 0) is True

    assert _wait_until(lambda: "send_keepalive" in fake.calls, timeout=1.0), \
        "keepalive 必须真的被调用过, 否则本用例什么也没测到"
    n = len(fake.frames())
    assert _wait_until(lambda: len(fake.frames()) > n, timeout=1.0), \
        "keepalive 失败后 RC 发送必须继续"
    assert ctl._rc._running is True


# =============================================================================
# 故障 7: land() / emergency() 抛异常 -> 绝不返回 True
# =============================================================================

def test_land_exception_makes_controlled_land_return_false(drone_factory, clock):
    """land() 抛异常: controlled_land() 必须返回 False。

    若假成功会怎样: 返回 True 会让上层以为"已安全落地"并推进后续流程,
    而飞机其实还在空中、停桨也未必发生。
    """
    ctl, fake = drone_factory()
    assert ctl.connect() is True
    assert ctl.takeoff() is True
    fake.fail["land"] = RuntimeError("SDK land 超时")

    assert ctl.controlled_land(timeout_s=0.2, poll_s=0.05) is False
    assert ctl.state is FlightState.EMERGENCY, "降落失败必须如实进入紧急态"
    assert "降落失败" in ctl.get_state_dict()["emergency_reason"]


def test_emergency_exception_makes_motor_cutoff_return_false(drone_factory):
    """底层 emergency() 抛异常: motor_cutoff() 必须返回 False, 且不声称已停桨。

    若假成功会怎样: 历史上这里是 `except: ... return True` —— 上层以为桨停了,
    实际螺旋桨还在转, 而系统已经放弃后续处置。这是最典型的"看起来成功"。
    """
    ctl, fake = drone_factory()
    assert ctl.connect() is True
    assert ctl.takeoff() is True
    fake.height = 10                    # 安全高度内: 闸门本应放行
    assert ctl.get_height() == 10       # 打点 -> 遥测新鲜
    fake.fail["emergency"] = RuntimeError("SDK emergency 无响应")

    assert ctl.motor_cutoff("legacy_kill") is False, "停桨失败绝不能报成功"
    assert fake.calls.count("emergency") == 1, "必须真的尝试过停桨"
    assert ctl.state is not FlightState.EMERGENCY, "没停成就不该声称已停桨"


# =============================================================================
# 故障 8: 故障帧进入 MissionController._update() -> FAULT + 速度归零
# =============================================================================

class ExplodingDrone(TelloController):
    """读取状态即抛异常的控制器: 模拟 SDK 在控制回路里硬失败。"""

    def __init__(self):
        super().__init__(mock=True)
        self.stop_calls = 0

    def get_state_dict(self):
        raise RuntimeError("SDK 状态读取爆炸")

    def stop_velocity(self):
        self.stop_calls += 1
        super().stop_velocity()


def test_update_fault_frame_enters_fault_and_stops_velocity():
    """故障帧交给 _update(): 进 FAULT 终态 + 归零速度 + 异常不抛穿主循环。

    若假成功会怎样: 异常冲出 _update() 会杀死控制线程, 飞机按最后一条速度
    指令继续飞, 外部只看到"循环不再更新", 状态还停在正常态。
    """
    mission = MissionController(mode="simulation", mock=True)
    drone = ExplodingDrone()
    drone._rc.set_command(50, 0, 0, 0)      # 先留一条非零速度, 便于验证归零
    mission.drone = drone
    mission.mock = False                   # 让 _get_sensor_data 走真机分支

    mission._update()                      # 不得抛异常

    assert mission.state == "FAULT", "故障帧后必须进入 FAULT 终态"
    assert mission.state in MissionController.FAILURE_STATES
    assert drone.stop_calls >= 1, "进 FAULT 前必须调用 stop_velocity()"
    assert drone._rc.last_cmd == (0, 0, 0, 0), "必须真的把速度归零"
    reason = mission.get_state_dict()["fault_reason"]
    assert reason and "控制循环异常" in reason, \
        "故障原因必须可观测, 实际 {!r}".format(reason)

    mission._update()                      # 再来一帧也不得二次炸穿
    assert mission.state == "FAULT"


# =============================================================================
# 深层缺口: 冻结遥测仍被当成"本帧取到了传感器数据"
# =============================================================================

def test_gap_stale_telemetry_must_not_refresh_sensor_heartbeat(drone_factory, clock):
    """已实现(原为 xfail 缺口, 已修): 遥测陈旧时不得刷新安全心跳, 也不得把旧高度当新观测。

    现状(backend/main.py:528-533): 真机分支只要 get_state_dict() 不抛异常就把
    _sensor_fresh 置 True —— 而 djitellopy 的 getter 读缓存字段, 链路断了也
    不抛异常、照旧返回值。于是:
      * _check_safety() 每帧 heartbeat(), monitor 的 timeout_land/kill 算不出超时;
      * 陈旧高度被当成新鲜气压计观测喂给 EKF, 位置估计被"冻住"却看起来正常。
    若假成功会怎样: 通信中断保护形同虚设, 而所有外部指标(心跳/状态/高度)都正常。
    """
    ctl, fake = drone_factory(FakeStateTello)
    assert ctl.connect() is True
    fake.feed("h:100;bat:88")
    assert ctl.get_height() == 100
    clock.advance(1.1)                      # 状态包冻结, 链路已死
    assert ctl.has_fresh_telemetry() is False, "前提: 控制器已认定遥测陈旧"

    mission = MissionController(mode="simulation", mock=True)
    mission.drone = ctl
    mission.mock = False                    # 走真机分支
    obs = mission._get_sensor_data()

    assert mission._sensor_fresh is False, \
        "遥测陈旧时不得刷新安全心跳(否则通信超时保护永不触发)"
    assert obs is None, \
        ("遥测陈旧时必须**不注入**观测(而不是把陈旧高度当新观测); "
         "实际返回: {}".format(obs))
