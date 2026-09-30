---
uid: 8a3c6e14
id: seabreeze-inspector.backend.main.runtime-loop.shutdown-and-log
parent: seabreeze-inspector.backend.main.runtime-loop
tags: [runtime, shutdown]
name: {zh: "优雅关闭与帧日志", en: "Graceful Shutdown & Frame Logging"}
description:
  zh: >
      优雅关闭（降落并轮询触地、超时硬停桨、停线程、存日志、停总线）、逐帧日志记录与外部视频帧注入。
      
  en: >
      Graceful shutdown (land and poll for touchdown, hard cut on timeout, stop threads, save logs, stop the bus), per-frame logging and external video-frame injection.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.804Z"
fingerprint: 9d1343fe24eaed513fb689bc1c42fdc8ab476655d66ed0c72ac05e60699704d7
source:
  - path: "backend/main.py"
    line: 648
apis:
  - protocol: rpc
    path: "MissionController.stop"
    description:
      zh: >
          优雅关闭。
          
      en: >
          Graceful shutdown.
          
  - protocol: rpc
    path: "MissionController._log_frame"
    description:
      zh: >
          记录一帧。
          
      en: >
          Logs one frame.
          
  - protocol: rpc
    path: "MissionController.update_video_frame"
    description:
      zh: >
          注入视频帧。
          
      en: >
          Injects a video frame.
          
---
