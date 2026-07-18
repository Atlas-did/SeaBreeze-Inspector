"""
pub-sub 消息总线 — 每 topic 独立分发, 消灭消费者竞争

铁律 #2: 全系统只有这一个消息总线。
禁止新建 Queue / dispatch 线程 / 第二套 Message 类。

用法:
    bus = MessageBus()
    sub = bus.subscribe("drone/state")
    bus.publish("drone/state", {"battery": 85})
    msg = sub.read_latest()  # 非阻塞, 返回最新一条

变更记录 (2026-07 重构 Phase 1):
  - 删除旧的 get() 兼容桩 (原实现永远返回 None, 属于坏的兼容接口)
  - put() 兼容接口保留 (main.py 仿真回路仍在用), Phase 3 统一为 publish() 后移除
"""

from __future__ import annotations

import queue
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Message:
    """模块间消息"""
    topic: str
    data: Any
    timestamp: float = field(default_factory=time.time)
    source: str = ""


class Subscription:
    """订阅者句柄 — 每个 subscriber 独立队列, 不存在竞争"""

    def __init__(self, maxsize: int = 20):
        self._queue: queue.Queue[Message] = queue.Queue(maxsize=maxsize)

    def _put(self, msg: Message) -> bool:
        """内部: 放入队列 (满时丢弃最旧的)"""
        try:
            self._queue.put_nowait(msg)
            return True
        except queue.Full:
            try:
                self._queue.get_nowait()  # 丢弃最旧
                self._queue.put_nowait(msg)
                return True
            except queue.Empty:
                return False

    def read_latest(self) -> Optional[Message]:
        """非阻塞读取最新消息 (丢弃中间积压)"""
        msg = None
        while True:
            try:
                msg = self._queue.get_nowait()
            except queue.Empty:
                break
        return msg

    def drain(self) -> List[Message]:
        """清空队列, 返回所有积压消息"""
        msgs = []
        while True:
            try:
                msgs.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return msgs


class MessageBus:
    """pub-sub 消息总线

    每个 topic 维护一组 subscriber, publish 时 fan-out 到所有订阅者。
    无 dispatch 线程 — 消费者自行 poll。
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Subscription]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, topic: str, maxsize: int = 20) -> Subscription:
        """订阅一个 topic, 返回独立 Subscription"""
        sub = Subscription(maxsize=maxsize)
        with self._lock:
            self._subscribers[topic].append(sub)
        return sub

    def unsubscribe(self, topic: str, sub: Subscription) -> None:
        """取消订阅"""
        with self._lock:
            if sub in self._subscribers[topic]:
                self._subscribers[topic].remove(sub)

    def subscriber_count(self, topic: str) -> int:
        """某 topic 的订阅者数量 (调试用)"""
        with self._lock:
            return len(self._subscribers[topic])

    def publish(self, topic: str, data: Any, source: str = "") -> int:
        """发布消息到 topic, fan-out 到所有订阅者。返回接收者数量"""
        msg = Message(topic=topic, data=data, source=source)
        delivered = 0
        with self._lock:
            subs = list(self._subscribers[topic])
        for sub in subs:
            if sub._put(msg):
                delivered += 1
        return delivered

    # ---- 向后兼容接口 (Phase 3 移除) ----

    def put(self, msg: Message, block: bool = True, timeout: float = 1.0) -> bool:
        """兼容旧接口: publish 到 msg.topic。新代码请直接用 publish()"""
        return self.publish(msg.topic, msg.data, msg.source) > 0

    def get(self, block: bool = True, timeout: float = 1.0) -> Optional[Message]:
        """已移除: pub-sub 模型下不存在全局队列可取。

        旧代码迁移方式:
            sub = bus.subscribe("你的/topic")   # 初始化时一次
            msg = sub.read_latest()             # 消费时
        """
        raise NotImplementedError(
            "MessageBus.get() 已在 Phase 1 移除 (原实现是永远返回 None 的坏桩)。"
            "请改用 bus.subscribe(topic) + sub.read_latest()。")

    def start(self) -> None:
        """兼容旧接口 (pub-sub 模式下无需显式启动)"""
        pass

    def stop(self) -> None:
        """停止总线 (pub-sub 模式下无需显式停止)"""
        pass


def create_message_bus() -> MessageBus:
    """工厂函数"""
    return MessageBus()


# 预定义 topic 常量 — 全系统唯一命名空间, 新增 topic 必须先在这里登记
TOPIC_DRONE_STATE = "drone/state"
TOPIC_DRONE_COMMAND = "drone/command"
TOPIC_ARM_STATE = "arm/state"
TOPIC_ARM_COMMAND = "arm/command"
TOPIC_EKF_OUTPUT = "ekf/output"
TOPIC_VISION_DETECTION = "vision/detection"
TOPIC_VISION_FRAME = "vision/frame"
TOPIC_SAFETY_ALERT = "safety/alert"
TOPIC_MISSION_STATUS = "mission/status"
TOPIC_LOG = "log/message"
