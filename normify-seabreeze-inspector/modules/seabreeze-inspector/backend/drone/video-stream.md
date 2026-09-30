---
uid: a9e5b378
id: seabreeze-inspector.backend.drone.video-stream
parent: seabreeze-inspector.backend.drone
tags: [drone, video]
name: {zh: "Tello 视频流", en: "Tello Video Stream"}
description:
  zh: >
      生产者-消费者解耦的视频采集：守护线程持续抓帧写入 maxsize=2 的队列（满则丢弃最旧帧以保低延迟），同时在线程锁下更新最新帧缓存；get_frame 非阻塞取帧并清空陈旧帧，队列为空时回落到缓存；附带 1s 窗口的 FPS 统计。mock 模式生成 640×480 随机帧供 UI 联调。
      
  en: >
      Producer-consumer video capture: a daemon thread keeps grabbing frames into a maxsize=2 queue (dropping the oldest frame when full to keep latency low) while updating a lock-protected latest-frame cache. get_frame takes a frame without blocking, drains stale frames and falls back to the cache when the queue is empty, with 1 s-window FPS statistics. Mock mode fabricates 640x480 random frames for UI work.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.800Z"
fingerprint: ee4276a8a45d7539dd8f0c90801acfbebec25c90dfcf015fa1ca97b9bc1a6d6d
source:
  - path: "backend/drone/tello_video.py"
    line: 12
    end_line: 106
apis:
  - protocol: rpc
    path: "TelloVideoStream.start"
    description:
      zh: >
          启动抓帧守护线程并返回 True。
          
      en: >
          Starts the frame-grabber daemon thread and returns True.
          
  - protocol: rpc
    path: "TelloVideoStream.get_frame"
    description:
      zh: >
          非阻塞取最新帧（清空陈旧帧），队列空时返回缓存帧或 None。
          
      en: >
          Non-blocking retrieval of the freshest frame (draining stale ones), returning the cached frame or None when empty.
          
  - protocol: rpc
    path: "TelloVideoStream.stop"
    description:
      zh: >
          停止采集并等待线程退出（最多 1s）。
          
      en: >
          Stops capture and joins the thread with a 1 s timeout.
          
  - protocol: rpc
    path: "TelloVideoStream.fps"
    description:
      zh: >
          只读属性：最近 1s 窗口的实测帧率。
          
      en: >
          Read-only property: measured frame rate over the last 1 s window.
          
---
