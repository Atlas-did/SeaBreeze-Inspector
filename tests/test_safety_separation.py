#!/usr/bin/env python3
"""P0 安全缺口验收: 降落 / 紧急下降 / 停桨 三概念分离 + 遥测新鲜度基于真收包。

缺口(A): kill() 把"高度未知"当"低空"(get_height() 返回 0 或抛异常都会砍桨),
         而且 except 后照样 return True; 一次性 move_down 也不是闭环下降。
缺口(B): 真机 _get_sensor_data 用 get_state_dict() 成功当"遥测新鲜", 但
         djitellopy 的 getter 读的是缓存字段 —— 链路断了它照样返回旧值。

本文件只用**假底层对象 + 短超时轮询**, 不联网、不连真机、不依赖长墙钟。
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.drone.tello_basic import FlightState, TelloController


class FakeTello:
    """记录型 djitellopy 替身: 可模拟"新包到达"与"链路冻结(只有旧值)"。"""

    def __init__(self):
        self.commands = []
        self.emergencies = 0
        self.height = 100
        self.get_height_error = None
        self.packet_frozen = False
        self._tick = 0
        self._state = {"h": 100, "bat": 100, "yaw": 0.0}

    def _log(self, name):
        self.commands.append(name)

    def get_current_state(self):
        """真机 djitellopy 的整包快照; 冻结时不再变化(= 没有新包到达)。"""
        self._log("get_current_state")
        if not self.packet_frozen:
            self._tick += 1
            self._state = {"h": self.height, "bat": 100, "yaw": self._tick * 0.5}
        return dict(self._state)

    def get_height(self):
        self._log("get_height")
        if self.get_height_error is not None:
            raise self.get_height_error
        return self.height

    def get_battery(self):
        self._log("get_battery")
        return 100

    def emergency(self):
        self.emergencies += 1
        self._log("emergency")
        return True

    def land(self):
        self._log("land")
        self.height = 0
        return True

    def move_down(self, dist):
        self._log(("move_down", dist))
        return True


def _make():
    """真机分支 + 假底层; 直接注入以避开 RC 发送线程(确定性、无并发)。"""
    fake = FakeTello()
    ctl = TelloController(mock=False)
    ctl._tello = fake
    return ctl, fake


def _spy_rc(ctl):
    """记录所有下发的 RC 速度指令(证明下降真的走的是速度通道)。"""
    sent = []
    orig = ctl._rc.set_command

    def spy(lr=0, fb=0, ud=0, yaw=0):
        sent.append((int(lr), int(fb), int(ud), int(yaw)))
        return orig(lr, fb, ud, yaw)

    ctl._rc.set_command = spy
    return sent


# =============================================================================
# 1) 停桨安全闸门: 高度未知/陈旧时拒绝, 且绝不碰底层 emergency()
# =============================================================================

def test_motor_cutoff_refuses_when_height_read_fails():
    """get_height() 抛异常 -> 高度未知 -> 拒绝停桨(返回 False, 不调底层 emergency)。"""
    ctl, fake = _make()
    fake.get_height_error = RuntimeError("link down")
    assert ctl.motor_cutoff("legacy_kill") is False
    assert fake.emergencies == 0
    assert "emergency" not in fake.commands
    assert ctl.state is not FlightState.EMERGENCY, "没停桨就不该对外声称已急停"


def test_motor_cutoff_refuses_on_invalid_height():
    """nan / inf / 负高度都判为未知 -> 一律拒绝。"""
    ctl, fake = _make()
    for bad in (float("nan"), float("inf"), -1.0):
        fake.height = bad
        assert ctl.height_is_known() is False, bad
        assert ctl.motor_cutoff() is False, bad
    assert fake.emergencies == 0
    assert "emergency" not in fake.commands


def test_motor_cutoff_refuses_on_stale_telemetry_at_zero_height():
    """最危险的旧行为: 读数是 0 且遥测陈旧 -> 旧代码直接砍桨, 现在必须拒绝。"""
    ctl, fake = _make()
    ctl.SAFETY_TELEMETRY_MAX_AGE_S = 0.2   # 缩短守卫时限, 避免长墙钟等待
    assert ctl.get_height() == 100        # 建立第一个遥测包
    fake.packet_frozen = True             # 链路冻结: 不再有新包到达
    time.sleep(0.25)
    fake.height = 0                       # 陈旧缓存里的 0 —— 并不代表"贴地"
    assert ctl.get_height() == 0          # getter 照旧返回旧值, 不抛异常
    assert ctl.has_fresh_telemetry(max_age_s=0.2) is False
    assert ctl.height_is_known(max_age_s=0.2) is False
    assert ctl.motor_cutoff("legacy_kill") is False
    assert fake.emergencies == 0
    assert "emergency" not in fake.commands


# =============================================================================
# 2) 高度阈值与白名单
# =============================================================================

def test_motor_cutoff_height_gate_and_whitelist():
    """500cm 拒绝; 20cm 且高度已知才允许; 白名单理由走自己的高度上限。"""
    ctl, fake = _make()
    fake.height = 500
    assert ctl.get_height() == 500
    assert ctl.motor_cutoff() is False               # 默认理由: >30cm 拒绝
    assert ctl.motor_cutoff("legacy_kill") is False  # legacy 阈值 300cm, 仍拒绝
    assert fake.emergencies == 0

    fake.height = 100
    assert ctl.motor_cutoff() is False               # 100cm > 30cm
    assert fake.emergencies == 0
    assert ctl.motor_cutoff("collision") is True     # 白名单: 机械已失效, 允许
    assert fake.emergencies == 1

    ctl2, fake2 = _make()
    fake2.height = 20
    assert ctl2.height_is_known() is True
    assert ctl2.motor_cutoff() is True               # 20cm <= 30cm -> 允许
    assert fake2.emergencies == 1
    assert ctl2.state is FlightState.EMERGENCY


# =============================================================================
# 3) 受控降落 / 紧急下降: 全程不砍桨
# =============================================================================

def test_controlled_land_never_cuts_motors():
    """已在低空 -> 直接用 land() 收尾, 调用序列里没有 emergency。"""
    ctl, fake = _make()
    fake.height = 10
    sent = _spy_rc(ctl)
    assert ctl.controlled_land(timeout_s=0.5, poll_s=0.02) is True
    assert "land" in fake.commands
    assert fake.emergencies == 0
    assert "emergency" not in fake.commands
    assert any(ud < 0 for _, _, ud, _ in sent), "下降必须走 RC 速度(ud<0)"


def test_controlled_land_timeout_still_only_lands():
    """高度一直不降 -> 超时后仍只用 land() 兜底, 绝不砍桨。"""
    ctl, fake = _make()
    fake.height = 200
    sent = _spy_rc(ctl)
    assert ctl.controlled_land(timeout_s=0.3, poll_s=0.02) is True
    assert "land" in fake.commands
    assert fake.emergencies == 0
    assert "emergency" not in fake.commands
    assert len([s for s in sent if s[2] < 0]) >= 2, "超时前应持续重发下降速度"


def test_emergency_descent_never_cuts_motors():
    ctl, fake = _make()
    fake.height = 10
    sent = _spy_rc(ctl)
    assert ctl.emergency_descent(timeout_s=0.5, poll_s=0.02) is True
    assert fake.emergencies == 0
    assert "emergency" not in fake.commands
    assert "land" not in fake.commands, "紧急下降不管 land, 由调用方决定"
    assert any(ud < 0 for _, _, ud, _ in sent)


def test_emergency_descent_with_unknown_height_never_cuts():
    """高度未知时紧急下降只做到超时为止, 绝不退化成砍桨。"""
    ctl, fake = _make()
    fake.get_height_error = RuntimeError("link down")
    assert ctl.emergency_descent(timeout_s=0.2, poll_s=0.02) is True
    assert fake.emergencies == 0
    assert "emergency" not in fake.commands


def test_emergency_entry_point_is_not_a_motor_cut():
    """emergency() = 进入紧急状态 + 下降脉冲, 不再是停桨。"""
    ctl, fake = _make()
    fake.height = 10
    _spy_rc(ctl)
    assert ctl.emergency() is True
    assert fake.emergencies == 0
    assert "emergency" not in fake.commands
    assert ctl.state is FlightState.EMERGENCY


# =============================================================================
# 4) 遥测新鲜度: 以"真收到新包"为准
# =============================================================================

def test_telemetry_freshness_tracks_real_packets():
    ctl, fake = _make()
    assert ctl.last_packet_timestamp is None
    assert ctl.telemetry_packet_count == 0
    assert ctl.has_fresh_telemetry(max_age_s=0.2) is False    # 从未收过包
    assert ctl.get_height() == 100                            # 第一个包
    assert ctl.telemetry_packet_count == 1
    assert ctl.telemetry_packet_timestamp() is not None
    assert ctl.has_fresh_telemetry(max_age_s=0.2) is True

    fake.packet_frozen = True                                 # 冻结: 只剩旧值
    time.sleep(0.25)
    assert ctl.get_height() == 100                            # getter 不抛异常
    assert ctl.has_fresh_telemetry(max_age_s=0.2) is False    # 但没有新包
    frozen_count = ctl.telemetry_packet_count

    fake.packet_frozen = False                                # 链路恢复
    assert ctl.get_height() == 100
    assert ctl.telemetry_packet_count == frozen_count + 1
    assert ctl.has_fresh_telemetry(max_age_s=0.2) is True


def test_failed_read_does_not_count_as_packet():
    ctl, fake = _make()
    assert ctl.get_battery() == 100
    count = ctl.telemetry_packet_count
    fake.get_height_error = RuntimeError("link down")
    assert ctl.get_height() == 0
    assert ctl.telemetry_packet_count == count, "读取失败不能算收到新包"
    assert ctl.motor_cutoff() is False


# =============================================================================
# 5) kill() 仍是 motor_cutoff("legacy_kill") 的薄封装
# =============================================================================

def test_kill_is_thin_wrapper_of_motor_cutoff():
    seen = []
    ctl, _ = _make()
    ctl.motor_cutoff = lambda reason="unspecified": (seen.append(reason), True)[1]
    assert ctl.kill() is True
    assert seen == ["legacy_kill"], "kill() 必须原样转成 legacy_kill"

    # 允许路径: 行为一致
    c1, f1 = _make()
    c2, f2 = _make()
    f1.height = f2.height = 20
    c1.get_height()
    c2.get_height()
    assert c1.kill() is True and c2.motor_cutoff("legacy_kill") is True
    assert f1.emergencies == f2.emergencies == 1

    # 拒绝路径: 行为一致(高空)
    c3, f3 = _make()
    c4, f4 = _make()
    f3.height = f4.height = 500
    c3.get_height()
    c4.get_height()
    assert c3.kill() is False and c4.motor_cutoff("legacy_kill") is False
    assert f3.emergencies == f4.emergencies == 0


def test_mock_mode_counts_every_read_and_still_gates_cutoff():
    """mock 链路视为正常(每次读取都是新包), 但高度闸门同样生效。"""
    ctl = TelloController(mock=True)
    ctl.connect()
    ctl.takeoff()                                             # _height = 100
    assert ctl.has_fresh_telemetry(max_age_s=0.2) is False    # 还没读过
    assert ctl.get_height() == 100
    assert ctl.has_fresh_telemetry(max_age_s=0.2) is True
    ctl._height = 500
    assert ctl.motor_cutoff("legacy_kill") is False           # 高空一样被拦
    ctl._height = 20
    assert ctl.kill() is True
