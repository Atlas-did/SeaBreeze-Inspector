"""P0-C 加强验收: 用状态包**到达时间戳**判定遥测新鲜度。

背景:
  djitellopy 的 get_battery()/get_height() 读的是**缓存字段**
  (tello.py:374/404 -> get_state_field -> get_own_udp_object()['state']),
  链路断了照样返回旧值且不抛异常 —— 所以"getter 成功"证明不了新鲜。

最强证据是在状态包解析处打点: djitellopy 的状态字典**只有一处被写入**
  udp_state_receiver(): drones[address]['state'] = Tello.parse_state(data)
本文件验证 `_install_state_stamp()` 注入的到达时间戳被正确消费。
"""

import time

from backend.drone.tello_basic import (
    RX_STAMP_FIELD,
    TelloController,
    _install_state_stamp,
)


class _FakeTello:
    """最小底層替身: 只提供 get_height 与 get_current_state。"""

    def __init__(self):
        self.state_dict = {}

    def get_height(self):
        return 100

    def get_current_state(self):
        return self.state_dict


def test_install_state_stamp_injects_arrival_time():
    """包装 parse_state 后, 每个状态包都应带上到达时刻。"""

    class FakeTello:
        @staticmethod
        def parse_state(state_str):
            return {"h": 100}

    assert _install_state_stamp(FakeTello) is True
    out = FakeTello.parse_state("h:100")
    assert RX_STAMP_FIELD in out
    assert isinstance(out[RX_STAMP_FIELD], float)

    # 幂等: 重复安装不应层层嵌套(时间戳仍需可读)
    assert _install_state_stamp(FakeTello) is True
    out2 = FakeTello.parse_state("h:100")
    assert RX_STAMP_FIELD in out2


def test_exact_stamp_marks_fresh_when_fields_are_identical():
    """关键边角: 字段逐一相同(完全静止悬停)时, 时间戳推进仍算收到新包。"""
    c = TelloController(mock=False)
    fake = _FakeTello()
    c._tello = fake

    fake.state_dict = {"h": 100, "bat": 90, RX_STAMP_FIELD: time.monotonic()}
    c.get_height()
    assert c.has_fresh_telemetry(1.0) is True

    # 同一个时间戳重复读取 -> 不应重复计数
    n = c.telemetry_packet_count
    c.get_height()
    assert c.telemetry_packet_count == n, "同一包不得被重复计数"

    # 时间戳推进(新包), 但所有业务字段都不变 -> 必须算新包
    fake.state_dict = {"h": 100, "bat": 90, RX_STAMP_FIELD: time.monotonic()}
    c.get_height()
    assert c.telemetry_packet_count == n + 1, "时间戳推进必须算新包"
    assert c.has_fresh_telemetry(1.0) is True


def test_stale_stamp_is_not_fresh():
    """到达时间戳很旧 -> 即便 getter 仍返回数值, 也必须判为不新鲜。"""
    c = TelloController(mock=False)
    fake = _FakeTello()
    c._tello = fake
    fake.state_dict = {"h": 100, RX_STAMP_FIELD: time.monotonic() - 5.0}

    assert c.get_height() == 100          # getter 照样成功返回旧值
    assert c.has_fresh_telemetry(0.5) is False, "旧包不得被判为新鲜"
