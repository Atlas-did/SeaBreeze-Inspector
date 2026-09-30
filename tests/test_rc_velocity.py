"""P0-2 验收测试: 控制链必须走 RC 速度控制, 而不是一次性位移指令。

背景(审计 P0-2):
  主循环每 100ms 输出一次速度指令(cm/s), 但 `TelloController.move_to()` 的实现
  其实是**一次性相对位移**(move_left/forward/...), 还带 >20cm 死区, `speed`
  参数被完全忽略。语义不符 -> 过冲/阻塞/控制频率失真, 且小幅修正被静默丢弃。

本文件锁定"修复后的行为":
  * 主控制链只调用 set_velocity();
  * 真机下速度由 RCManager 以 20Hz 持续下发, 超时自动归零;
  * 任何切入非可控飞行状态的转换都会先把速度归零。
"""

import time

import numpy as np

from backend.drone.rc_manager import RCManager
from backend.drone.tello_basic import FlightState, TelloController
from backend.main import MissionController


def test_set_velocity_records_rc_command():
    """速度指令必须落到 RC 通道(而不是位移指令)。"""
    c = TelloController(mock=True)
    assert c.set_velocity(10, -20, 3) is True
    assert c._rc.last_cmd == (10, -20, 3, 0)


def test_set_velocity_clamps_to_100():
    """RC 通道限幅 ±100 cm/s。"""
    c = TelloController(mock=True)
    c.set_velocity(500, -500, 120)
    assert c._rc.last_cmd == (100, -100, 100, 0)


def test_stop_velocity_zeroes():
    c = TelloController(mock=True)
    c.set_velocity(30, 30, 30)
    c.stop_velocity()
    assert c._rc.last_cmd == (0, 0, 0, 0)


def test_real_mode_rejects_velocity_when_not_flying():
    """真机模式下未进入 HOVERING/MOVING 时不允许下发速度。"""
    c = TelloController(mock=False)
    assert c.state == FlightState.IDLE
    assert c.set_velocity(10, 0, 0) is False


def test_hovering_with_velocity_transitions_to_moving():
    c = TelloController(mock=True)
    c.connect()
    c.takeoff()
    assert c.state == FlightState.HOVERING
    c.set_velocity(20, 0, 0)
    assert c.state == FlightState.MOVING


def test_transition_to_landing_zeroes_velocity():
    """切入非可控飞行状态必须先归零速度。"""
    c = TelloController(mock=True)
    c.connect()
    c.takeoff()
    c.set_velocity(20, 20, 0)
    assert c._rc.last_cmd == (20, 20, 0, 0)
    c.land()
    assert c._rc.last_cmd == (0, 0, 0, 0)


def test_kill_zeroes_velocity_in_mock():
    c = TelloController(mock=True)
    c.connect()
    c.takeoff()
    c.set_velocity(30, 0, 0)
    c.kill()
    assert c._rc.last_cmd == (0, 0, 0, 0)


def test_send_control_uses_velocity_not_move_to():
    """真机控制链必须调用 set_velocity, 且绝不再调用 move_to()。

    注意: 只测**真机分支**。仿真分支(mock=True)有自己的控制器架构,
    主循环仍走位置积分, 不注入速度 —— 这是刻意的。
    """
    mc = MissionController(mode="simulation", mock=False)
    c = TelloController(mock=True)
    c.connect()
    c.takeoff()                      # -> HOVERING
    mc.drone = c
    mc.mock = False

    def _boom(*args, **kwargs):
        raise AssertionError("真机控制链不应再调用 move_to() (一次性位移语义不符)")

    c.move_to = _boom
    mc._send_control(np.array([15.0, 0.0, 0.0]))
    assert c._rc.last_cmd == (15, 0, 0, 0)


def test_send_control_dead_zone_zeroes_immediately():
    """死区(|v|<1)必须**立即归零**, 而不是让上一条指令多活半个周期。

    审计 P1: 死区里直接 return 会让上一条非零 RC 指令一直生效到
    RCManager 的 ZERO_TIMEOUT(0.5s) 才自动归零 —— 等于指令多活半秒。
    修复后死区即归零。
    (本用例原先断言"死区不改动上一条指令", 那是在修复前写的错误预期。)
    """
    mc = MissionController(mode="simulation", mock=False)
    c = TelloController(mock=True)
    c.connect()
    c.takeoff()
    mc.drone = c
    mc.mock = False
    c.set_velocity(7, 0, 0)
    assert c._rc.last_cmd == (7, 0, 0, 0)
    mc._send_control(np.array([0.5, 0.0, 0.0]))
    assert c._rc.last_cmd == (0, 0, 0, 0), "死区必须立即归零"


def test_rc_manager_zero_timeout():
    """0.5s 无新指令应自动归零速度(防飞丢)。"""
    rc = RCManager(mock=True)
    rc.ZERO_TIMEOUT = 0.05
    rc.start()
    try:
        rc.set_command(lr=50)
        time.sleep(0.35)
        assert rc.last_rc == (0, 0, 0, 0), "超时后必须归零, 实际 {}".format(rc.last_rc)
    finally:
        rc.stop()
