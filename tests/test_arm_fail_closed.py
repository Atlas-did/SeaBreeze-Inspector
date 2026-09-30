#!/usr/bin/env python3
"""
机械臂控制器 fail-closed 测试 — 硬件模式不得"未连接却报告成功" + 角度限位校验

不依赖真实 Arduino: 硬件模式用注入的假串口对象 (FakeSerial) 验证。
"""

import sys
import time
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.arm.arm_controller import ArmController


class FakeSerial:
    """最小串口替身: 只记录写入, 不碰真实硬件"""

    def __init__(self, fail_on_write: bool = False):
        self.written = []
        self.closed = False
        self.in_waiting = 0
        self._fail = fail_on_write

    def write(self, data):
        if self._fail:
            raise OSError("simulated serial write failure")
        self.written.append(data)

    def readline(self):
        return b""

    def close(self):
        self.closed = True


def hardware_arm(**kw):
    """显式硬件模式, 且从不 connect() — 模拟"没插 Arduino"""
    return ArmController(port="COM_NOT_PRESENT", mock=False, **kw)


# ---------------------------------------------------------------- 1. fail-closed
def test_hardware_mode_without_serial_returns_false():
    """核心: 硬件模式 + 无串口 → False, 且状态/原因表明不可用 (不再假成功)"""
    arm = hardware_arm()
    assert arm.is_mock is False
    assert arm.is_connected is False

    ok = arm.set_joint_angles([120, 80, 40], duration=10)

    assert ok is False, "硬件模式下无串口必须返回 False"
    assert arm.status == ArmController.STATUS_ARM_UNAVAILABLE
    assert arm.fault_reason, "必须给出失败原因"
    assert "串口" in arm.fault_reason or "connect" in arm.fault_reason
    # 没有真的动过: 内部角度仍为初始值
    assert np.allclose(arm.get_current_angles(), [90, 90, 90])


def test_hardware_mode_move_to_position_also_fails_closed():
    """move_to_position 走同一条失败关闭路径"""
    arm = hardware_arm()
    from backend.arm.arm_kinematics import FK

    pos = FK(90, 60, 90)
    assert arm.move_to_position(pos[0], pos[1], pos[2]) is False
    assert arm.status == ArmController.STATUS_ARM_UNAVAILABLE


# ---------------------------------------------------------------- 2. 显式 mock
def test_explicit_mock_mode_still_succeeds():
    """显式 mock=True → 与既有语义一致: 返回 True 并更新角度"""
    arm = ArmController(mock=True, blocking_wait=False)
    assert arm.is_mock is True
    assert arm.set_joint_angles([90, 45, 30], duration=500) is True
    assert np.allclose(arm.get_current_angles(), [90, 45, 30], atol=0.1)
    assert arm.status == ArmController.STATUS_MOCK
    assert arm.fault_reason is None


def test_empty_port_default_keeps_legacy_mock_semantics():
    """默认参数(空 port)仍自动判定为 mock — 既有调用方行为不变"""
    arm = ArmController(port="")
    assert arm.is_mock is True
    assert arm.set_joint_angles([90, 90, 90], duration=100) is True
    assert arm.reset() is True


# ---------------------------------------------------------------- 3. 角度限位
def test_out_of_range_base_rejected():
    """base=999 越界 → False + ANGLE_REJECTED, 且不更新角度"""
    arm = ArmController(mock=True, blocking_wait=False)
    assert arm.set_joint_angles([999, 90, 90]) is False
    assert arm.status == ArmController.STATUS_ANGLE_REJECTED
    assert "base" in arm.fault_reason
    assert "999" in arm.fault_reason
    assert np.allclose(arm.get_current_angles(), [90, 90, 90])


@pytest.mark.parametrize("angles,channel", [
    ([-1, 90, 90], "base"),
    ([90, 5, 90], "shoulder"),
    ([90, 170, 90], "shoulder"),
    ([90, 90, 181], "elbow"),
])
def test_each_channel_limit_enforced(angles, channel):
    """三个通道各自的下/上限都被强制"""
    arm = ArmController(mock=True, blocking_wait=False)
    assert arm.set_joint_angles(angles) is False
    assert arm.status == ArmController.STATUS_ANGLE_REJECTED
    assert channel in arm.fault_reason


def test_boundary_angles_accepted():
    """边界值本身合法(闭区间), 不应误杀"""
    arm = ArmController(mock=True, blocking_wait=False)
    for angles in ([0, 15, 0], [180, 165, 180]):
        assert arm.set_joint_angles(angles) is True, angles


def test_out_of_range_blocks_serial_write():
    """越界时硬件模式也不会写串口(既不发危险指令, 也不误报成功)"""
    arm = hardware_arm()
    fake = FakeSerial()
    arm.ser = fake
    assert arm.set_joint_angles([999, 90, 90]) is False
    assert fake.written == []
    assert arm.status == ArmController.STATUS_ANGLE_REJECTED


# ---------------------------------------------------------------- 4. nan / inf
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_angles_rejected(bad):
    """nan/inf(含IK不可达可能返回的inf)→ False + ANGLE_INVALID"""
    arm = ArmController(mock=True, blocking_wait=False)
    assert arm.set_joint_angles([bad, 90, 90]) is False
    assert arm.status == ArmController.STATUS_ANGLE_INVALID
    assert arm.fault_reason
    assert np.allclose(arm.get_current_angles(), [90, 90, 90])


def test_wrong_arity_and_unparsable_rejected():
    """角度个数不对 / 非数值 → 拒绝而不是抛异常"""
    arm = ArmController(mock=True, blocking_wait=False)
    assert arm.set_joint_angles([90, 90]) is False
    assert arm.status == ArmController.STATUS_ANGLE_INVALID
    assert arm.set_joint_angles(["a", "b", "c"]) is False
    assert arm.status == ArmController.STATUS_ANGLE_INVALID


# ---------------------------------------------------------------- 5. disconnect
def test_disconnect_returns_to_unavailable():
    """连接 → 成功; disconnect() 后 ser=None → 回到不可用语义(False)"""
    arm = hardware_arm(blocking_wait=False)
    arm.ser = FakeSerial()
    assert arm.is_connected is True
    assert arm.set_joint_angles([90, 90, 90]) is True
    assert arm.status == ArmController.STATUS_OK

    arm.disconnect()
    assert arm.is_connected is False
    assert arm.status == ArmController.STATUS_ARM_UNAVAILABLE

    ok = arm.set_joint_angles([100, 100, 100])
    assert ok is False, "disconnect 后不得报告成功"
    assert arm.status == ArmController.STATUS_ARM_UNAVAILABLE
    assert arm.fault_reason
    assert np.allclose(arm.get_current_angles(), [90, 90, 90]), "断连后指令不应生效"


def test_serial_write_failure_is_reported():
    """中途断开(写入抛异常)→ False 而不是崩溃/假成功"""
    arm = hardware_arm(blocking_wait=False)
    arm.ser = FakeSerial(fail_on_write=True)
    ok = arm.set_joint_angles([90, 90, 90])
    assert ok is False
    assert arm.status == ArmController.STATUS_ARM_UNAVAILABLE
    assert "写入失败" in arm.fault_reason


# ---------------------------------------------------------------- 硬件路径正常 + 不阻塞
def test_connected_hardware_sends_command():
    """有串口时: 写出的指令格式正确, 状态回到 OK"""
    arm = hardware_arm(blocking_wait=False)
    fake = FakeSerial()
    arm.ser = fake
    assert arm.set_joint_angles([100, 120, 45], duration=500) is True
    assert fake.written == [b"A100,120,45\n"]
    assert arm.status == ArmController.STATUS_OK
    assert arm.fault_reason is None


def test_hardware_mode_does_not_block_for_duration():
    """硬件模式默认不按 duration 阻塞主控制循环(90°差≈1800ms 也立即返回)"""
    arm = hardware_arm()
    arm.ser = FakeSerial()
    arm.set_joint_angles([90, 90, 90])
    t0 = time.perf_counter()
    assert arm.set_joint_angles([90, 90, 180], duration=2000) is True
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 200, f"硬件模式不应阻塞 {elapsed_ms:.0f}ms"


def test_hardware_mode_blocking_wait_is_opt_in():
    """显式 blocking_wait=True 时才按 duration 等待(可选行为, 已注明)"""
    arm = hardware_arm(blocking_wait=True)
    arm.ser = FakeSerial()
    arm.set_joint_angles([90, 90, 90])
    t0 = time.perf_counter()
    arm.set_joint_angles([90, 90, 100], duration=200)
    assert (time.perf_counter() - t0) * 1000 > 100
