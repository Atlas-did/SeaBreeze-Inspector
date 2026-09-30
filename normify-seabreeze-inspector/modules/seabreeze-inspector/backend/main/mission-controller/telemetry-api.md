---
uid: a7d5e903
id: seabreeze-inspector.backend.main.mission-controller.telemetry-api
parent: seabreeze-inspector.backend.main.mission-controller
tags: [mission, telemetry]
name: {zh: "状态查询与复位接口", en: "Telemetry & Reset API"}
description:
  zh: >
      对外查询面：完整状态字典（含 EKF 马氏距离）、电量读写、检测计数与紧急原因，以及任务复位。
      
  en: >
      The outward query surface: the full state dict (including EKF Mahalanobis distance), battery access, detection count and emergency reason, plus mission reset.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.802Z"
fingerprint: 9d1343fe24eaed513fb689bc1c42fdc8ab476655d66ed0c72ac05e60699704d7
source:
  - path: "backend/main.py"
    line: 706
apis:
  - protocol: rpc
    path: "MissionController.get_state_dict"
    description:
      zh: >
          返回完整状态字典。
          
      en: >
          Returns the full state dict.
          
  - protocol: rpc
    path: "MissionController.get_battery"
    description:
      zh: >
          读电量。
          
      en: >
          Reads the battery.
          
  - protocol: rpc
    path: "MissionController.set_battery"
    description:
      zh: >
          设置电量（0-100 限幅）。
          
      en: >
          Sets the battery with 0-100 clamping.
          
  - protocol: rpc
    path: "MissionController.reset_mission"
    description:
      zh: >
          安全复位任务。
          
      en: >
          Resets the mission safely.
          
  - protocol: rpc
    path: "MissionController.get_emergency_reason"
    description:
      zh: >
          读紧急原因。
          
      en: >
          Reads the emergency reason.
          
---
