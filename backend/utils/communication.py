#!/usr/bin/env python3
"""
模块间通信 — Queue + Thread 方案

选型对比:
  回调函数: 简单但耦合高
  **Queue + Thread**: 标准库, 线程安全, 解耦 — 本项目选择
  发布-订阅: 解耦但需自己实现
  ZeroMQ: 专业但引入外部依赖

场景: 单机运行, 大学生团队, 无需跨进程通信
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np


@dataclass
class Message:
    """模块间消息格式"""
    topic: str           # 消息主题: 'drone/state', 'arm/command', 'vision/detection'
    data: Any            # 消息内容
    timestamp: float = field(default_factory=time.time)
    source: str = ""     # 发送方: 'tello', 'arm', 'ekf', 'vision', 'main'


class MessageBus:
    """
    线程安全的模块间消息总线

    使用 Queue 实现生产-消费模型:
      - 发送者: put(msg) -> Queue
      - 接收者: get() / register_callback(topic, callback)

    示例:
        bus = MessageBus()
        bus.register_callback('drone/state', handle_state)
        bus.put(Message('drone/state', {'battery': 85}, source='tello'))
    """

    def __init__(self, maxsize: int = 100) -> None:
        self._queue: queue.Queue[Message] = queue.Queue(maxsize=maxsize)
        self._callbacks: Dict[str, List[Callable]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def put(self, msg: Message, block: bool = True, timeout: float = 1.0) -> bool:
        """发送消息到总线"""
        try:
            self._queue.put(msg, block=block, timeout=timeout)
            return True
        except queue.Full:
            return False

    def get(self, block: bool = True, timeout: float = 1.0) -> Optional[Message]:
        """从总线获取消息"""
        try:
            return self._queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def register_callback(self, topic: str, callback: Callable[[Message], None]) -> None:
        """注册 topic 回调函数"""
        with self._lock:
            if topic not in self._callbacks:
                self._callbacks[topic] = []
            self._callbacks[topic].append(callback)

    def unregister_callback(self, topic: str, callback: Callable[[Message], None]) -> None:
        """注销回调函数"""
        with self._lock:
            if topic in self._callbacks and callback in self._callbacks[topic]:
                self._callbacks[topic].remove(callback)

    def start(self) -> None:
        """启动分发线程"""
        self._running = True
        self._thread = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止分发线程"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _dispatch_loop(self) -> None:
        """消息分发循环: 从Queue取出消息, 分发给对应topic的回调"""
        while self._running:
            msg = self.get(block=True, timeout=0.5)
            if msg is None:
                continue

            with self._lock:
                callbacks = self._callbacks.get(msg.topic, [])

            for cb in callbacks:
                try:
                    cb(msg)
                except Exception as e:
                    print(f"[MessageBus] 回调错误: {e}")

    def get_stats(self) -> Dict[str, int]:
        """获取消息统计"""
        return {
            "queue_size": self._queue.qsize(),
            "registered_topics": len(self._callbacks),
            "topic_list": list(self._callbacks.keys()),
        }


class ModuleConnector:
    """
    模块连接器: 为每个模块提供标准化的收发接口

    已注册模块:
      - drone:     Tello 无人机控制与状态
      - arm:       机械臂控制
      - ekf:       EKF 扰动观测
      - vision:    视觉检测
      - main:      主调度
      - dashboard: 监控面板
      - safety:    安全守护
    """

    def __init__(self, module_name: str, bus: MessageBus) -> None:
        self.name = module_name
        self.bus = bus

    def send(self, topic: str, data: Any) -> bool:
        """发送消息到指定 topic"""
        msg = Message(topic=topic, data=data, source=self.name)
        return self.bus.put(msg)

    def on(self, topic: str, callback: Callable[[Message], None]) -> None:
        """订阅指定 topic"""
        self.bus.register_callback(topic, callback)

    def get_state(self, timeout: float = 1.0) -> Optional[Message]:
        """获取本模块的最新状态消息 — 非消费式查询

        注意: 此方法从bus队列消费消息, 如果也有callback注册到同topic,
        callback和get_state可能竞争消费。推荐使用 register_callback 替代。
        """
        # 直接消费队列中的本模块消息 (向后兼容)
        topic = f"{self.name}/state"
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self.bus.get(block=True, timeout=min(0.1, timeout))
            if msg is None:
                continue
            if msg.topic == topic:
                return msg
            # 非本模块的消息放回队列 (P1-8: 避免消费其他topic的消息)
            self.bus.put(msg)
        return None


# 预定义 topic 常量
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


def create_message_bus() -> MessageBus:
    """工厂函数: 创建并启动消息总线"""
    bus = MessageBus(maxsize=200)
    bus.start()
    return bus
