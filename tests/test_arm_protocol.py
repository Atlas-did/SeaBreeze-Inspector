#!/usr/bin/env python3
"""
机械臂串口 ACK/LIMIT 协议测试 — 不碰真串口, 全部用 FakeSerial 注入

覆盖:
  1) 收到角度一致的 ACK            -> True(status=OK)
  2) 完全不回复                    -> False(status=ACK_TIMEOUT)
  3) 回复 LIMIT:elbow              -> False(status=LIMIT_TRIGGERED) + 记录关节
  4) ACK 角度与请求不符/回包是噪声 -> False(status=ACK_MISMATCH)
  5) capabilities() 如实声明能力边界(无位置/电流/温度反馈, 无堵转检测)
  6) read/write 抛异常             -> 全局不可用, 且返回 False
外加: ACK 默认关闭(既有调用方语义不变)、限位时不得更新内部角度。

说明: 真串口在此测试中**一次都不打开**, FakeSerial 只记录写入并按脚本吐回复。
"""

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.arm.arm_controller import ArmController


class FakeSerial:
    """脚本化串口替身: 写入即"触发固件回复", 回复按行排队"""

    def __init__(self, replies=(), fail_on_write=False, fail_on_read=False):
        self.written = []
        self.closed = False
        self.in_waiting = 0
        self._queue = list(replies)
        self._line = b""
        self._fail_write = fail_on_write
        self._fail_read = fail_on_read

    def _pump(self):
        if self._queue:
            self._line = self._queue.pop(0)
            self.in_waiting = len(self._line)

    def write(self, data):
        if self._fail_write:
            raise OSError("simulated serial write failure")
        self.written.append(data)
        self._pump()

    def readline(self):
        if self._fail_read:
            raise OSError("simulated serial read failure")
        if not self.in_waiting:
            return b""
        self.in_waiting = 0
        return self._line

    def reset_input_buffer(self):
        self.in_waiting = 0
        self._queue = []

    def close(self):
        self.closed = True


def hw_arm(**kw):
    """硬件模式 + 打开 ACK 等待 + 很短的超时(测试不许变慢)"""
    replies = kw.pop("replies", ())
    kw.setdefault("mock", False)
    kw.setdefault("wait_ack", True)
    kw.setdefault("ack_timeout", 0.05)
    arm = ArmController(port="COM_TEST", **kw)
    arm.ser = FakeSerial(replies)
    return arm


# ---------------------------------------------------------------- 1. ACK 一致
def test_ack_matching_angles_returns_true():
    """固件回 ACK 且角度与请求一致 → True, 状态 OK, 回读值被记录"""
    arm = hw_arm(replies=[b"ACK:A120,S80,E40\n"])
    assert arm.set_joint_angles([120, 80, 40]) is True
    assert arm.status == ArmController.STATUS_OK
    assert arm.fault_reason is None
    assert arm.ser.written == [b"A120,80,40\n"]
    assert np.allclose(arm.last_ack_angles, [120, 80, 40])
    assert np.allclose(arm.get_current_angles(), [120, 80, 40])


def test_ack_within_tolerance_is_accepted():
    """±1度量化误差内算一致(SG90 固件按整数步进, 这是写在注释里的容差)"""
    arm = hw_arm(replies=[b"ACK:A120,S81,E40\n"], ack_tolerance=1.0)
    assert arm.set_joint_angles([120, 80, 40]) is True


def test_ack_disabled_by_default_keeps_legacy_semantics():
    """默认不开 ACK: 写完即返回 True(既有调用方/测试语义不变)"""
    arm = ArmController(port="COM_TEST", mock=False)
    assert arm.capabilities()["ack_wait_enabled"] is False
    arm.ser = FakeSerial(replies=[])          # 永不回复
    assert arm.set_joint_angles([100, 90, 90]) is True
    assert arm.status == ArmController.STATUS_OK


def test_mock_mode_ignores_ack_config():
    """模拟模式无串口, ACK 配置不改变既有 mock 语义"""
    arm = ArmController(mock=True, wait_ack=True, ack_timeout=0.01)
    assert arm.set_joint_angles([90, 45, 30]) is True
    assert arm.status == ArmController.STATUS_MOCK


# ---------------------------------------------------------------- 2. 超时
def test_no_reply_times_out_with_ack_timeout_status():
    """固件不回复 → False + ACK_TIMEOUT, 且内部角度不推进(不许假装动过)"""
    arm = hw_arm(replies=[])
    assert arm.set_joint_angles([150, 90, 90]) is False
    assert arm.status == ArmController.STATUS_ACK_TIMEOUT
    assert arm.fault_reason and "ACK" in arm.fault_reason
    assert np.allclose(arm.get_current_angles(), [90, 90, 90]), "未确认的指令不得改状态"


def test_ack_timeout_is_configurable_and_short():
    """超时可配: 30ms 的等待不应拖成秒级"""
    import time

    arm = hw_arm(replies=[], ack_timeout=0.03)
    t0 = time.perf_counter()
    assert arm.set_joint_angles([150, 90, 90]) is False
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.3, f"ACK 等待不该阻塞这么久: {elapsed:.3f}s"


# ---------------------------------------------------------------- 3. LIMIT
def test_limit_reply_returns_false_and_records_joint():
    """固件回 LIMIT:elbow → False + LIMIT_TRIGGERED, 触发关节被记录"""
    arm = hw_arm(replies=[b"LIMIT:elbow\n"])
    assert arm.set_joint_angles([120, 80, 170]) is False
    assert arm.status == ArmController.STATUS_LIMIT_TRIGGERED
    assert arm.last_limit_joint == "elbow"
    assert "elbow" in arm.fault_reason
    assert np.allclose(arm.get_current_angles(), [90, 90, 90])


@pytest.mark.parametrize("joint", ["base", "shoulder", "elbow"])
def test_each_joint_limit_is_parsed(joint):
    """三个关节的 LIMIT 行都能解析出关节名"""
    arm = hw_arm(replies=[("LIMIT:%s\n" % joint).encode()])
    assert arm.set_joint_angles([120, 80, 40]) is False
    assert arm.status == ArmController.STATUS_LIMIT_TRIGGERED
    assert arm.last_limit_joint == joint


# ---------------------------------------------------------------- 4. 内容不符
def test_ack_angle_mismatch_returns_false():
    """约定: ACK 角度超容差 → False + ACK_MISMATCH(宁可判失败也不当成功)"""
    arm = hw_arm(replies=[b"ACK:A10,S10,E10\n"])
    assert arm.set_joint_angles([120, 80, 40]) is False
    assert arm.status == ArmController.STATUS_ACK_MISMATCH
    assert "不符" in arm.fault_reason
    assert np.allclose(arm.get_current_angles(), [90, 90, 90])


@pytest.mark.parametrize("reply", ["[OK] 运动完成\n".encode(), b"garbage\n", b"ACK:oops\n"])
def test_non_ack_reply_is_mismatch(reply):
    """非 ACK/LIMIT 的回复(含固件日志行、残缺 ACK)→ False + ACK_MISMATCH"""
    arm = hw_arm(replies=[reply])
    assert arm.set_joint_angles([120, 80, 40]) is False
    assert arm.status == ArmController.STATUS_ACK_MISMATCH
    assert arm.fault_reason


def test_per_call_wait_ack_override():
    """构造时默认关, 单次调用可以强制打开(反之亦然)"""
    arm = ArmController(port="COM_TEST", mock=False, ack_timeout=0.05)
    arm.ser = FakeSerial(replies=[b"ACK:A120,S80,E40\n"])
    assert arm.set_joint_angles([120, 80, 40], wait_ack=True) is True

    arm2 = hw_arm(replies=[])
    assert arm2.set_joint_angles([120, 80, 40], wait_ack=False) is True


# ---------------------------------------------------------------- 5. 能力自述
def test_capabilities_reflect_hardware_reality():
    """能力自述必须如实: SG90 开环 → 无位置/电流/温度反馈, 堵转不可判"""
    caps = ArmController(port="COM_TEST", mock=False).capabilities()
    assert caps["position_feedback"] is False, "SG90 无位置反馈"
    assert caps["current_sensing"] is False, "无电流采样"
    assert caps["temperature_sensing"] is False
    assert caps["stall_detection"] is False, "无电流无位置 → 堵转物理不可判"
    assert caps["limit_switches"] is True, "固件实现了 GPIO 限位开关"
    assert caps["ack_protocol"] is True
    assert caps["hardware_verified"] is False, "固件改动未经实机验证"
    # 不得出现"把无反馈写成有反馈"的键
    assert not any(v is True for k, v in caps.items()
                   if k in ("position_feedback", "current_sensing", "stall_detection"))


def test_capabilities_expose_ack_config():
    """自述里要能看出 ACK 到底开没开、超时多少"""
    arm = hw_arm(replies=[], ack_timeout=0.05)
    caps = arm.capabilities()
    assert caps["ack_wait_enabled"] is True
    assert caps["ack_timeout_s"] == pytest.approx(0.05)
    assert caps["ack_tolerance_deg"] == pytest.approx(1.0)
    assert caps["mock"] is False


# ---------------------------------------------------------------- 6. I/O 异常
def test_write_exception_marks_unavailable():
    """write 抛异常 → 全局 ARM_UNAVAILABLE, 且返回 False"""
    arm = hw_arm(replies=[])
    arm.ser = FakeSerial(fail_on_write=True)
    assert arm.set_joint_angles([100, 90, 90]) is False
    assert arm.status == ArmController.STATUS_ARM_UNAVAILABLE
    assert "写入失败" in arm.fault_reason
    assert arm.is_connected is False, "I/O 故障后不得继续宣称已连接"


def test_read_exception_marks_unavailable():
    """read 抛异常(USB 掉线) → 同样全局不可用, 不是抛给调用方"""
    arm = hw_arm(replies=[])
    ser = FakeSerial(fail_on_read=True)
    ser.in_waiting = 8          # 声称有数据, 真去读时设备已掉线(USB 拔出)
    arm.ser = ser
    assert arm.set_joint_angles([100, 90, 90]) is False
    assert arm.status == ArmController.STATUS_ARM_UNAVAILABLE
    assert "读取失败" in arm.fault_reason
    # 后续指令继续失败关闭, 不恢复
    assert arm.set_joint_angles([100, 90, 90]) is False
    assert arm.status == ArmController.STATUS_ARM_UNAVAILABLE


def test_unavailable_arm_still_returns_false_without_serial():
    """无串口的硬件模式仍是 False + ARM_UNAVAILABLE(不因新增 ACK 而回退)"""
    arm = ArmController(port="COM_NOT_PRESENT", mock=False, wait_ack=True)
    assert arm.set_joint_angles([100, 90, 90]) is False
    assert arm.status == ArmController.STATUS_ARM_UNAVAILABLE
    assert arm.fault_reason
