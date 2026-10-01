"""真 TelloController 状态机 + 会抛错的假 SDK: land() 失败后主循环仍须继续安全动作。

第五轮审计建议路径: 真适配器 land() 失败 -> EMERGENCY, 而**遥测仍然新鲜**、
高度 **25cm(<30cm)**。此前两个替身分别掩盖了这条路径的两半:
  1) 假机体把 is_flying 写成恒真 -> 掩盖了 EMERGENCY 下 is_flying=False;
  2) 把"land 失败"写成"高度不可信" -> 掩盖了"遥测新鲜且 25cm"这条真实路径。
所以本文件的假对象**只在 SDK 边界**(抛异常 / 投递状态包)工作: 状态机、遥测新鲜度、
高度判据、FAULT 收尾与复位闸门全部走真实实现。

不变式: 真机 land() 失败转 EMERGENCY 后, 主循环必须
  * 不把 land() 的 False 记成"已收尾"(mc._fault_land_requested is False);
  * 不空转重试 land()(EMERGENCY 下它只会 return False 且不下发命令);
  * 继续用 RC 下降(emergency_descent -> send_rc_control, ud<0)推进安全动作;
  * 拒绝把"EMERGENCY + 25cm"当成已落地 => clear_fault() 必须 False,
    只有操作员显式确认才允许复位。

本文件只新增测试, 不修改任何生产代码。
"""

import sys
import threading
import time
import types

import numpy as np
import pytest

from backend.drone.tello_basic import (
    RX_STAMP_FIELD,
    FlightState,
    TelloController,
)
from backend.main import MissionController


class FakeSdkTello:
    """djitellopy.Tello 的边界替身 —— 只复刻 SDK 行为, **不**模拟机体语义。

    与 tests/test_sdk_fault_injection.py 同手法:
      * 实例可调用 -> `Tello()` 返回同一个记录对象;
      * 调用**先记录再抛异常** -> 能严格区分"压根没调用 land()"与"调用了但底层失败";
      * get_height()/get_battery() 与真库一样读**状态包字典**, 且每次读取都投递一个
        带**新的到达时间戳**的包 -> 真适配器的 has_fresh_telemetry() 为真, 是
        "链路真的在送新包", 而不是替身谎报新鲜。
    """

    def __init__(self, height: int = 25, battery: int = 88):
        self.height = height
        self.battery = battery
        self.calls = []
        self.rc_frames = []
        self.fail = {}
        self._lock = threading.Lock()
        self._last_stamp = None

    def __call__(self, *args, **kwargs):
        return self

    def _enter(self, name):
        with self._lock:
            self.calls.append(name)
        exc = self.fail.get(name)
        if exc is not None:
            raise exc

    def _next_stamp(self):
        """严格递增的到达时刻: 真机每个状态包都带一个新的 monotonic 时间戳。"""
        now = time.monotonic()
        if self._last_stamp is not None and now <= self._last_stamp:
            now = self._last_stamp + 1e-6
        self._last_stamp = now
        return now

    def get_current_state(self):
        """状态包快照: 每次访问都是一个**新包**(真机由 UDP 接收线程写入)。"""
        return {
            "h": int(self.height),
            "bat": int(self.battery),
            RX_STAMP_FIELD: self._next_stamp(),
        }

    def get_height(self):
        self._enter("get_height")
        return int(self.height)

    def get_battery(self):
        self._enter("get_battery")
        return int(self.battery)

    def connect(self):
        self._enter("connect")
        return True

    def takeoff(self):
        self._enter("takeoff")
        return True

    def land(self):
        self._enter("land")          # 先记录后抛: 见 fail
        return True

    def emergency(self):
        self._enter("emergency")
        return True

    def send_rc_control(self, lr, fb, ud, yaw):
        with self._lock:
            self.rc_frames.append((int(lr), int(fb), int(ud), int(yaw)))
        self._enter("send_rc_control")

    def send_keepalive(self):
        self._enter("send_keepalive")

    def frames(self):
        with self._lock:
            return list(self.rc_frames)


@pytest.fixture
def real_adapter(monkeypatch):
    """真 TelloController(mock=False) + 假 djitellopy 边界; 收尾回收 RC 线程。"""
    fake = FakeSdkTello()
    module = types.ModuleType("djitellopy")
    module.Tello = fake
    monkeypatch.setitem(sys.modules, "djitellopy", module)
    ctl = TelloController(mock=False)
    try:
        yield ctl, fake
    finally:
        ctl.release()


def _wait_until(pred, timeout=1.5, interval=0.01):
    """轮询等待 RC 发送线程真的发出帧(短超时, 返回是否成立)。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(interval)
    return pred()


def _hovering_real_adapter(real_adapter, height: int = 25):
    """真适配器连上并起飞到 HOVERING, 且遥测新鲜、高度 height(<30cm)。"""
    ctl, fake = real_adapter
    assert ctl.connect() is True
    assert ctl.state is FlightState.CONNECTED
    assert ctl.takeoff() is True
    assert ctl.state is FlightState.HOVERING, "前置: 真状态机必须真的走到 HOVERING"
    assert ctl.is_flying is True

    fake.height = height
    assert ctl.get_height() == height
    assert ctl.has_fresh_telemetry() is True, "前置: 遥测必须新鲜(真实路径, 不是替身谎报)"
    assert ctl.height_is_known() is True
    return ctl, fake


def _armed_mission(ctl):
    """把真适配器挂到 MissionController(mock=False), 已 mark_fault。"""
    mc = MissionController(mode="simulation", mock=True)
    mc.drone = ctl
    mc.mock = False                      # 真机分支: 高度/状态全部取自真适配器
    mc.mark_fault("控制循环异常")
    assert mc.state == "FAULT"
    return mc


# =============================================================================
# 真适配器边界: land() 抛异常 -> False + EMERGENCY, 且遥测仍新鲜、高度 25cm
# =============================================================================

def test_real_adapter_land_failure_enters_emergency_and_returns_false(real_adapter):
    """真状态机 + 会抛错的假 SDK: land() 必须返回 False 并转入 EMERGENCY。

    若假成功会怎样: 返回 True 会让上层以为"已安全落地"并推进收尾流程, 而飞机还在空中。
    同时这一步**不是**"高度不可信": 遥测依旧新鲜、高度依旧 25cm —— 第二轮 bug 正是靠
    "把 land 失败改写成高度不可信"把这条真实路径掩盖掉的。
    """
    ctl, fake = _hovering_real_adapter(real_adapter)
    fake.fail["land"] = RuntimeError("SDK land 超时")

    assert ctl.land() is False, "land() 底层失败绝不能报成功"
    assert ctl.state is FlightState.EMERGENCY, "降落失败必须转入 EMERGENCY"
    assert ctl.is_flying is False, "EMERGENCY 下 is_flying 为 False(不是恒真替身)"
    assert "降落失败" in ctl.get_state_dict()["emergency_reason"]
    assert fake.calls.count("land") == 1

    # land() 失败 ≠ 高度不可信: 这条路径上遥测仍然新鲜且是 25cm
    assert ctl.has_fresh_telemetry() is True
    assert ctl.height_is_known() is True
    assert ctl.get_height() == 25


# =============================================================================
# 第五轮审计主路径: 真 land() 失败后, 主循环必须继续安全动作 (5 条断言)
# =============================================================================

def test_fault_after_real_land_failure_keeps_descending_and_refuses_reset(real_adapter):
    """真机 land() 失败 -> EMERGENCY + 遥测新鲜 + 25cm: 主循环必须继续 RC 下降。

    全程真实现: TelloController 状态机、遥测新鲜度、FAULT 收尾、复位闸门。
    """
    ctl, fake = _hovering_real_adapter(real_adapter)
    fake.fail["land"] = RuntimeError("SDK land 超时")
    mc = _armed_mission(ctl)

    # --- 第 1 帧: 低空(25cm) 且适配器 HOVERING(可降落) -> 真的下发 land() -> 它失败 ---
    mc._handle_state_machine(np.zeros(3))

    assert ctl.state is FlightState.EMERGENCY, "land() 失败必须让真适配器转入 EMERGENCY"
    assert ctl.is_flying is False
    assert fake.calls.count("land") == 1, "land() 必须真的被尝试过一次"
    assert mc._fault_land_failures == 1, "失败必须被记为失败(而不是成功)"
    # 断言 2: 不把 land() 的 False 记成"已收尾"
    assert mc._fault_land_requested is False, "land() 返回 False 绝不能被记成成功"

    # --- 继续驱动 >2 个重试周期(FAULT_LAND_RETRY_FRAMES == 25) ---
    for _ in range(3 * mc.FAULT_LAND_RETRY_FRAMES):
        mc._handle_state_machine(np.zeros(3))

    # 断言 3: EMERGENCY 下 land() 不得被反复调用(真机只会 return False 且不下发命令)
    assert fake.calls.count("land") == 1, \
        "EMERGENCY 下重试 land() 是空转, 实际调用 {} 次".format(fake.calls.count("land"))
    assert ctl.state is FlightState.EMERGENCY

    # 断言 1: 仍在推进 RC 下降 —— emergency_descent 的 ud<0 路径
    assert "send_rc_control" in fake.calls, "RC 通道必须真的在下发指令"
    speed = ctl.EMERGENCY_DESCEND_SPEED
    assert _wait_until(lambda: any(f[2] == -speed for f in fake.frames())), \
        "假 SDK 必须收到过 ud={} 的下降指令, 实际帧: {}".format(speed, fake.frames()[-5:])
    down = [f for f in fake.frames() if f[2] < 0]
    assert down and all(f[2] == -speed for f in down), \
        "下降帧必须都是 emergency_descent 的速度, 实际 {}".format(sorted({f[2] for f in down}))

    # 前提复查(正是被掩盖的那半): 遥测**仍然新鲜**, 高度**仍然 25cm**
    assert ctl.has_fresh_telemetry() is True, "这条路径上遥测是新鲜的(不是链路断了)"
    assert ctl.height_is_known() is True
    assert ctl.get_height() == 25
    assert mc._safe_height_cm() == 25.0

    # 断言 4: EMERGENCY + 25cm **不能**证明触地 -> 拒绝复位
    assert mc.clear_fault() is False, "EMERGENCY + 25cm 不能证明触地, 必须拒绝复位"
    assert mc.state == "FAULT", "拒绝复位后必须仍停在终态"
    assert ctl.state is FlightState.EMERGENCY

    # 断言 5: 只有操作员显式确认才允许复位
    assert mc.clear_fault(operator_confirmed=True) is True
    assert mc.state == "IDLE"
    assert mc._fault_land_requested is False


# =============================================================================
# 第五轮审计 D17: 已失败过一次后, 高度仍 >30cm 时的"限频重试"不得空转
# =============================================================================

def test_emergency_never_retries_land_even_above_landing_height(real_adapter, monkeypatch):
    """记录过 land() 失败后抬高到 50cm: 重试周期到了也**不得**再调 land()。

    真机 EMERGENCY 下 land() 只 return False 且**不下发任何命令**
    (tello_basic.land 只在 HOVERING/MOVING 下有边)。若不判 `_adapter_accepts_land()`,
    每 25 帧就会空转一次, 且会把"重试过"记成"已尝试收尾"。
    """
    monkeypatch.setattr(MissionController, "FAULT_LAND_RETRY_FRAMES", 3)  # 不真等 25 帧
    ctl, fake = _hovering_real_adapter(real_adapter)
    fake.fail["land"] = RuntimeError("SDK land 超时")
    mc = _armed_mission(ctl)

    mc._handle_state_machine(np.zeros(3))            # 低空收尾: land() 失败一次
    assert ctl.state is FlightState.EMERGENCY
    assert mc._fault_land_failures == 1
    assert fake.calls.count("land") == 1

    fake.height = 50                                 # 仍在上空 -> 走"继续下降 + 限频重试"
    assert ctl.get_height() == 50
    for _ in range(3 * mc.FAULT_LAND_RETRY_FRAMES + 1):
        mc._handle_state_machine(np.zeros(3))

    assert mc._safe_height_cm() == 50.0
    assert fake.calls.count("land") == 1, \
        "EMERGENCY 下 land() 重试是空转, 实际调用 {} 次".format(fake.calls.count("land"))
    assert mc._fault_land_requested is False
    assert _wait_until(lambda: any(f[2] < 0 for f in fake.frames())), \
        "重试被拒绝后必须仍在推进 RC 下降(而不是停手)"
