---
uid: 3c8a2d05
id: seabreeze-inspector.backend.main.mission-fsm.state-commands
parent: seabreeze-inspector.backend.main.mission-fsm
tags: [mission, commands]
name: {zh: "任务命令与状态转换", en: "Mission Commands & Transitions"}
description:
  zh: >
      对外任务命令：起飞、状态请求（经转换表校验）、目标设定、路径规划与紧急触发。
      
  en: >
      Outward mission commands: takeoff, state request (validated by the transition table), target setting, path planning and emergency trigger.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.802Z"
fingerprint: 9d1343fe24eaed513fb689bc1c42fdc8ab476655d66ed0c72ac05e60699704d7
source:
  - path: "backend/main.py"
    line: 593
    end_line: 647
apis:
  - protocol: rpc
    path: "MissionController.takeoff"
    description:
      zh: >
          从 IDLE 起飞。
          
      en: >
          Takes off from IDLE.
          
  - protocol: rpc
    path: "MissionController.request_state"
    description:
      zh: >
          请求状态转换。
          
      en: >
          Requests a state transition.
          
  - protocol: rpc
    path: "MissionController.set_target"
    description:
      zh: >
          设定目标位置。
          
      en: >
          Sets the target position.
          
  - protocol: rpc
    path: "MissionController.plan_path"
    description:
      zh: >
          规划巡检路径。
          
      en: >
          Plans the inspection path.
          
  - protocol: rpc
    path: "MissionController.trigger_emergency"
    description:
      zh: >
          触发紧急。
          
      en: >
          Triggers emergency.
          
---
