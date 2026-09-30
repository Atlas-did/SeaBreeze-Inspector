---
uid: 1b9d4e27
id: seabreeze-inspector.backend.utils.message-bus
parent: seabreeze-inspector.backend.utils
tags: [bus, pubsub, threading]
name: {zh: "发布订阅消息总线", en: "Pub-Sub Message Bus"}
description:
  zh: >
      全系统唯一的进程内消息总线。每个 topic 维护独立订阅队列（满时丢弃最旧），publish 一次性扇出到全部订阅者并返回投递数；订阅者用 read_latest 非阻塞取最新一帧，无 dispatch 线程。同时登记 drone/arm/ekf/vision/safety/mission/log 全部 topic 常量。
      
  en: >
      The only in-process message bus in the system. Each topic keeps its own subscriber queue (oldest dropped when full); publish fans out once to every subscriber and returns the delivered count; subscribers poll non-blockingly with read_latest and there is no dispatch thread. Also holds every drone/arm/ekf/vision/safety/mission/log topic constant.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.813Z"
fingerprint: 4de04605d38570c358109fd6b20202f0a1028d83553981c7fe8eb078d3d348bb
source:
  - path: "backend/utils/bus.py"
    line: 28
    end_line: 158
apis:
  - protocol: rpc
    path: "MessageBus.publish"
    description:
      zh: >
          向 topic 扇出发布消息，返回接收者数量。
          
      en: >
          Publishes to a topic, fanning out to all subscribers and returning the delivered count.
          
  - protocol: rpc
    path: "MessageBus.subscribe"
    description:
      zh: >
          订阅 topic，返回独立 Subscription 句柄（每订阅者独立队列）。
          
      en: >
          Subscribes to a topic and returns an independent Subscription handle.
          
  - protocol: rpc
    path: "MessageBus.unsubscribe"
    description:
      zh: >
          取消订阅，从该 topic 的订阅者列表移除句柄。
          
      en: >
          Unsubscribes, removing the handle from that topic's subscriber list.
          
  - protocol: rpc
    path: "create_message_bus"
    description:
      zh: >
          消息总线工厂函数（全系统唯一总线入口）。
          
      en: >
          Factory function returning the single bus instance.
          
  - protocol: rpc
    path: "Subscription.read_latest"
    description:
      zh: >
          非阻塞读取最新消息，丢弃中间积压。
          
      en: >
          Non-blocking read of the newest message, discarding intermediate backlog.
          
---
