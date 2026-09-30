---
uid: 6a03c5fe
id: seabreeze-inspector.backend.main.runtime-loop
parent: seabreeze-inspector.backend.main
tags: [main, control-loop, safety]
name: {zh: "单帧调度与安全", en: "Frame Loop & Safety"}
description:
  zh: >
      主调度循环与安全/遥测接线：start() 固定周期主循环、_update() 单帧（总线命令→传感器/EKF→安全→状态机→日志→发布状态）、仿真注入入口 update_with_external_data、分层 Failsafe 判定、视频帧注入与优雅关闭（轮询触地、超时兜底硬停桨）。
      
  en: >
      The dispatcher loop and safety/telemetry wiring: the fixed-period start() loop, the single-frame _update() (bus commands, sensors and EKF, safety, state machine, log, publish state), the simulation injection entry update_with_external_data, tiered failsafe judgement, video-frame injection and graceful shutdown with touchdown polling and hard-cut fallback.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.803Z"
fingerprint: 9d1343fe24eaed513fb689bc1c42fdc8ab476655d66ed0c72ac05e60699704d7
source:
  - path: "backend/main.py"
    line: 177
    end_line: 259
  - path: "backend/main.py"
    line: 410
    end_line: 587
  - path: "backend/main.py"
    line: 648
    end_line: 704
deps:
  - kind: call
    to: seabreeze-inspector.backend.mission.safety
    from_api: "rpc:MissionController._update"
    to_api: "rpc:FailsafeMonitor.check"
    label: {zh: "每帧分层安全检查（WARN/LAND/KILL）", en: "Tiered safety check per frame"}
  - kind: event
    to: seabreeze-inspector.backend.utils.message-bus
    from_api: "rpc:MissionController._update"
    to_api: "rpc:MessageBus.publish"
    label: {zh: "发布任务状态到总线", en: "Publishes state to the bus"}
  - kind: call
    to: seabreeze-inspector.backend.utils.flight-logger
    from_api: "rpc:MissionController._update"
    to_api: "rpc:FlightLogger.log_frame"
    label: {zh: "每帧记录位置/扰动/检测框", en: "Logs each frame to CSV"}
---
