#!/usr/bin/env python3
"""
模块间通信测试 — 验证 Queue + Thread 消息总线
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.utils.communication import Message, MessageBus, ModuleConnector


def test_message_bus_basic():
    """测试消息总线基础功能"""
    print("[TEST] 消息总线基础功能")

    bus = MessageBus(maxsize=10)
    bus.start()

    # 发送消息
    msg = Message(topic="test/topic", data={"value": 42}, source="test")
    assert bus.put(msg), "消息发送应成功"

    # 接收消息
    received = bus.get(block=True, timeout=1.0)
    assert received is not None, "应收到消息"
    assert received.topic == "test/topic"
    assert received.data["value"] == 42
    assert received.source == "test"

    bus.stop()
    print("  [PASS]")


def test_callback_dispatch():
    """测试回调分发"""
    print("[TEST] 回调分发")

    bus = MessageBus(maxsize=10)
    received_data = []

    def handler(msg):
        received_data.append(msg.data)

    bus.register_callback("drone/state", handler)
    bus.start()

    # 发送消息
    bus.put(Message("drone/state", {"battery": 85}, source="drone"))

    # 等待分发
    time.sleep(0.2)

    assert len(received_data) == 1, f"应收到1条消息, 实际={len(received_data)}"
    assert received_data[0]["battery"] == 85

    bus.stop()
    print("  [PASS]")


def test_module_connector():
    """测试模块连接器"""
    print("[TEST] 模块连接器")

    bus = MessageBus(maxsize=10)
    drone_connector = ModuleConnector("drone", bus)
    main_connector = ModuleConnector("main", bus)

    received = []

    def on_drone_state(msg):
        received.append(msg.data)

    main_connector.on("drone/state", on_drone_state)
    bus.start()

    # drone 发送状态
    drone_connector.send("drone/state", {"battery": 90, "height": 120})

    time.sleep(0.2)

    assert len(received) == 1
    assert received[0]["battery"] == 90

    bus.stop()
    print("  [PASS]")


def test_thread_safety():
    """测试线程安全性: 多线程并发发送"""
    print("[TEST] 线程安全性")

    import threading

    bus = MessageBus(maxsize=100)
    bus.start()

    count = [0]
    lock = threading.Lock()

    def handler(msg):
        with lock:
            count[0] += 1

    bus.register_callback("test/count", handler)

    # 多线程发送
    threads = []
    for i in range(5):
        def sender(idx=i):
            for j in range(10):
                bus.put(Message("test/count", {"idx": idx, "j": j}))
        t = threading.Thread(target=sender)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    time.sleep(0.5)
    assert count[0] == 50, f"应收到50条消息, 实际={count[0]}"

    bus.stop()
    print("  [PASS]")


def test_queue_overflow():
    """测试队列溢出处理"""
    print("[TEST] 队列溢出处理")

    bus = MessageBus(maxsize=2)

    # 填满队列
    bus.put(Message("test/1", {}), block=False)
    bus.put(Message("test/2", {}), block=False)

    # 第三条应失败 (不阻塞)
    result = bus.put(Message("test/3", {}), block=False)
    assert result is False, "队列满时应返回False"

    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  模块通信测试套件")
    print("=" * 50)
    test_message_bus_basic()
    test_callback_dispatch()
    test_module_connector()
    test_thread_safety()
    test_queue_overflow()
    print("\n[OK] 所有通信测试通过!")
