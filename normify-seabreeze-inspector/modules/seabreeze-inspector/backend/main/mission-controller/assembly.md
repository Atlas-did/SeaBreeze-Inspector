---
uid: 4f2c8b19
id: seabreeze-inspector.backend.main.mission-controller.assembly
parent: seabreeze-inspector.backend.main.mission-controller
tags: [mission, assembly]
name: {zh: "控制器装配与配置回退", en: "Controller Assembly"}
description:
  zh: >
      MissionController 构造：配置读取与安全回退、EKF/控制器/安全监控/日志/总线等子模块的构建与订阅。
      
  en: >
      MissionController construction: config read with safe fallback, plus construction and subscription of the EKF, controller, safety monitor, logger and bus.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.801Z"
fingerprint: 9d1343fe24eaed513fb689bc1c42fdc8ab476655d66ed0c72ac05e60699704d7
source:
  - path: "backend/main.py"
    line: 31
    end_line: 175
apis:
  - protocol: rpc
    path: "MissionController.__init__"
    description:
      zh: >
          装配控制器。
          
      en: >
          Assembles the controller.
          
  - protocol: rpc
    path: "MissionController._build_controller"
    description:
      zh: >
          构建控制器。
          
      en: >
          Builds the controller.
          
  - protocol: rpc
    path: "MissionController._build_safety_guard"
    description:
      zh: >
          构建安全监控。
          
      en: >
          Builds the safety guard.
          
---
