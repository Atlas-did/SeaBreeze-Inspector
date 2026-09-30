---
uid: 51c8e0a4
id: seabreeze-inspector.backend.main.mission-controller
parent: seabreeze-inspector.backend.main
tags: [main, controller, config]
name: {zh: "任务控制器装配", en: "Mission Controller Setup"}
description:
  zh: >
      MissionController 的装配与公共访问器：按模式加载配置（硬件模式配置失败即 fail-fast）、按 config 构建前馈 PID 与三级安全阈值、组合 EKF/规划器/检测器/Tello/RC/视频/日志/消息总线，并暴露电量、检测数、紧急原因、状态字典与安全重置。
      
  en: >
      MissionController assembly and public accessors: loads config per mode (hardware fails fast on config errors), builds the feedforward PID and three-tier safety thresholds from config, composes EKF, planner, detector, Tello, RC, video, logger and message bus, and exposes battery, detection count, emergency reason, state dict and safe reset.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.801Z"
fingerprint: 9d1343fe24eaed513fb689bc1c42fdc8ab476655d66ed0c72ac05e60699704d7
source:
  - path: "backend/main.py"
    line: 31
    end_line: 175
  - path: "backend/main.py"
    line: 706
    end_line: 760
deps:
  - kind: call
    to: seabreeze-inspector.backend.utils.config-loader
    from_api: "rpc:MissionController.__init__"
    to_api: "rpc:ConfigLoader.load"
    label: {zh: "加载 drone_config（硬件模式失败即抛）", en: "Loads drone_config"}
  - kind: reference
    to: seabreeze-inspector.backend.utils.flight-logger
    from_api: "rpc:MissionController.__init__"
    to_api: "rpc:FlightLogger.start_session"
    label: {zh: "组合飞行日志记录器", en: "Composes the flight logger"}
  - kind: reference
    to: seabreeze-inspector.backend.mission.safety
    from_api: "rpc:MissionController.__init__"
    to_api: "rpc:FailsafeMonitor.check"
    label: {zh: "构建三级安全监控并按 config 覆盖阈值", en: "Builds failsafe thresholds"}
  - kind: event
    to: seabreeze-inspector.backend.utils.message-bus
    from_api: "rpc:MissionController.__init__"
    to_api: "rpc:MessageBus.subscribe"
    label: {zh: "订阅命令与状态 topic", en: "Subscribes to command topics"}
---
