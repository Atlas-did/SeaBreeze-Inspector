#!/usr/bin/env python3
"""pub-sub 消息总线测试"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.utils.bus import (
    MessageBus, Message, Subscription, create_message_bus,
    TOPIC_MISSION_STATUS, TOPIC_DRONE_COMMAND,
)


def test_subscribe_and_read():
    """基本 pub-sub: 订阅→发布→读取"""
    print("[TEST] pub-sub 基本功能")
    bus = MessageBus()
    sub = bus.subscribe("test/topic")
    bus.publish("test/topic", {"value": 42}, source="test")
    msg = sub.read_latest()
    assert msg is not None, "应收到消息"
    assert msg.data["value"] == 42
    assert msg.source == "test"
    print("  [PASS]")


def test_read_latest_skips_old():
    """read_latest() 只返回最新的消息"""
    print("[TEST] read_latest 只取最新")
    bus = MessageBus()
    sub = bus.subscribe("test/topic")
    for i in range(10):
        bus.publish("test/topic", i)
    msg = sub.read_latest()
    assert msg is not None
    assert msg.data == 9  # 最新的一条
    # 再次读取应为 None (已消费)
    assert sub.read_latest() is None
    print("  [PASS]")


def test_multiple_subscribers():
    """多个订阅者各自收到全量"""
    print("[TEST] 多订阅者独立接收")
    bus = MessageBus()
    sub1 = bus.subscribe("test/topic")
    sub2 = bus.subscribe("test/topic")
    bus.publish("test/topic", "hello")
    m1 = sub1.read_latest()
    m2 = sub2.read_latest()
    assert m1 is not None and m1.data == "hello"
    assert m2 is not None and m2.data == "hello"
    print("  [PASS]")


def test_topic_isolation():
    """不同 topic 互不干扰"""
    print("[TEST] topic 隔离")
    bus = MessageBus()
    sub_a = bus.subscribe("a")
    sub_b = bus.subscribe("b")
    bus.publish("a", "data_a")
    bus.publish("b", "data_b")
    assert sub_a.read_latest().data == "data_a"
    assert sub_b.read_latest().data == "data_b"
    print("  [PASS]")


def test_no_competition():
    """dashboard 命令和 status 在不同的 subscription 上不竞争"""
    print("[TEST] 无消费者竞争 (Dashboard 命令+状态)  ")
    bus = MessageBus()
    cmd_sub = bus.subscribe(TOPIC_DRONE_COMMAND)
    status_sub = bus.subscribe(TOPIC_MISSION_STATUS)

    # 大量状态推送
    for i in range(50):
        bus.publish(TOPIC_MISSION_STATUS, {"frame": i})

    # 中间发一条命令
    bus.publish(TOPIC_DRONE_COMMAND, {"command": "takeoff"})

    # 命令订阅者应能读到命令, 不受状态洪水影响
    cmd_msg = cmd_sub.read_latest()
    assert cmd_msg is not None
    assert cmd_msg.data["command"] == "takeoff"

    # 状态订阅者读到最新状态
    status_msg = status_sub.read_latest()
    assert status_msg is not None
    assert status_msg.data["frame"] == 49
    print("  [PASS]")


def test_queue_full_drops_oldest():
    """队列满时丢弃最旧的, 保留最新的"""
    print("[TEST] 队列满丢弃最旧")
    bus = MessageBus()
    sub = bus.subscribe("test/topic", maxsize=3)
    for i in range(10):
        bus.publish("test/topic", i)
    # 应读到最新的数据 (7 or later)
    msg = sub.read_latest()
    assert msg is not None
    assert msg.data >= 7
    print("  [PASS]")


def test_backward_compat():
    """向后兼容: put/get 接口仍可用"""
    print("[TEST] 向后兼容 put/get")
    bus = create_message_bus()
    sub = bus.subscribe("drone/state")
    msg = Message(topic="drone/state", data={"battery": 85}, source="test")
    bus.put(msg)
    received = sub.read_latest()
    assert received is not None
    assert received.data["battery"] == 85
    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  pub-sub 总线测试套件")
    print("=" * 50)
    test_subscribe_and_read()
    test_read_latest_skips_old()
    test_multiple_subscribers()
    test_topic_isolation()
    test_no_competition()
    test_queue_full_drops_oldest()
    test_backward_compat()
    print("\n[OK] 所有总线测试通过!")
