#!/usr/bin/env python3
"""
消息总线 pub-sub 测试 — 替代被删除的 test_communication.py

覆盖: 发布/订阅、多订阅者 fan-out、read_latest 丢弃积压、
      队列满丢最旧、drain、unsubscribe、put() 兼容接口、get() 已移除
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from backend.utils.bus import (
    Message, MessageBus, create_message_bus,
    TOPIC_MISSION_STATUS, TOPIC_DRONE_COMMAND,
)


def test_publish_subscribe_basic():
    """基础发布订阅"""
    print("[TEST] 基础发布订阅")
    bus = create_message_bus()
    sub = bus.subscribe("test/topic")

    n = bus.publish("test/topic", {"value": 42}, source="test")
    assert n == 1, "应有1个接收者"

    msg = sub.read_latest()
    assert msg is not None
    assert msg.topic == "test/topic"
    assert msg.data["value"] == 42
    assert msg.source == "test"
    assert msg.timestamp > 0
    print("  [PASS]")


def test_fanout_independent_queues():
    """多订阅者各自独立收全量消息 (pub-sub 核心: 无消费者竞争)"""
    print("[TEST] fan-out 独立队列")
    bus = create_message_bus()
    sub_a = bus.subscribe(TOPIC_MISSION_STATUS)
    sub_b = bus.subscribe(TOPIC_MISSION_STATUS)

    bus.publish(TOPIC_MISSION_STATUS, {"state": "HOVERING"}, source="main")

    # A 读走后, B 必须还能读到 (旧 Queue 模型做不到这一点)
    assert sub_a.read_latest().data["state"] == "HOVERING"
    assert sub_b.read_latest().data["state"] == "HOVERING"
    print("  [PASS]")


def test_topic_isolation():
    """不同 topic 互不串扰"""
    print("[TEST] topic 隔离")
    bus = create_message_bus()
    sub = bus.subscribe(TOPIC_MISSION_STATUS)

    bus.publish(TOPIC_DRONE_COMMAND, {"command": "takeoff"}, source="dashboard")
    assert sub.read_latest() is None, "未订阅的 topic 不应收到"
    print("  [PASS]")


def test_read_latest_drops_backlog():
    """read_latest 只取最新, 丢弃中间积压"""
    print("[TEST] read_latest 丢弃积压")
    bus = create_message_bus()
    sub = bus.subscribe("t")

    for i in range(5):
        bus.publish("t", {"seq": i})

    msg = sub.read_latest()
    assert msg.data["seq"] == 4, "应只读到最新一条"
    assert sub.read_latest() is None, "积压应已被清空"
    print("  [PASS]")


def test_queue_full_drops_oldest():
    """订阅队列满时丢弃最旧消息, 不阻塞发布者"""
    print("[TEST] 队满丢最旧")
    bus = create_message_bus()
    sub = bus.subscribe("t", maxsize=3)

    for i in range(10):
        n = bus.publish("t", {"seq": i})
        assert n == 1, "发布永远不应被阻塞"

    msgs = sub.drain()
    seqs = [m.data["seq"] for m in msgs]
    assert seqs == [7, 8, 9], "应只保留最新3条, 实际={}".format(seqs)
    print("  [PASS]")


def test_unsubscribe():
    """取消订阅后不再接收"""
    print("[TEST] unsubscribe")
    bus = create_message_bus()
    sub = bus.subscribe("t")
    bus.unsubscribe("t", sub)

    n = bus.publish("t", {"x": 1})
    assert n == 0
    assert sub.read_latest() is None
    print("  [PASS]")


def test_put_compat():
    """put() 兼容接口 (main.py 仿真回路在用, Phase 3 移除)"""
    print("[TEST] put() 兼容")
    bus = create_message_bus()
    sub = bus.subscribe("legacy/topic")

    ok = bus.put(Message(topic="legacy/topic", data={"v": 1}, source="old"))
    assert ok is True
    assert sub.read_latest().data["v"] == 1
    print("  [PASS]")


def test_get_removed():
    """get() 已移除 — 必须显式报错而不是悄悄返回 None"""
    print("[TEST] get() 已移除")
    bus = create_message_bus()
    with pytest.raises(NotImplementedError):
        bus.get()
    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  消息总线 pub-sub 测试套件")
    print("=" * 50)
    test_publish_subscribe_basic()
    test_fanout_independent_queues()
    test_topic_isolation()
    test_read_latest_drops_backlog()
    test_queue_full_drops_oldest()
    test_unsubscribe()
    test_put_compat()
    test_get_removed()
    print("\n[OK] 所有总线测试通过!")
