---
uid: 9c3d5f81
id: seabreeze-inspector.backend.simulation.pygame-loop.input-actions
parent: seabreeze-inspector.backend.simulation.pygame-loop
tags: [pygame, input]
name: {zh: "键盘输入与任务动作", en: "Keyboard Input & Mission Actions"}
description:
  zh: >
      事件与按键处理：起飞/降落/复位、机械臂按键控制、目标位置微调与按键保持判定。
      
  en: >
      Event and key handling: takeoff/land/reset, arm key control, target nudging and key-held detection.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.810Z"
fingerprint: 05f41f8c8f9b77d05d50bf89aca61a6d3af3b8f91d26f28a9cb1ce258614a526
source:
  - path: "backend/simulation/simulation.py"
    line: 377
    end_line: 601
apis:
  - protocol: rpc
    path: "Simulation._handle_events"
    description:
      zh: >
          分发 Pygame 事件。
          
      en: >
          Dispatches Pygame events.
          
  - protocol: rpc
    path: "Simulation._on_key_down"
    description:
      zh: >
          处理按键按下。
          
      en: >
          Handles key-down.
          
  - protocol: rpc
    path: "Simulation._do_takeoff"
    description:
      zh: >
          触发起飞。
          
      en: >
          Triggers takeoff.
          
  - protocol: rpc
    path: "Simulation._do_land"
    description:
      zh: >
          触发降落。
          
      en: >
          Triggers landing.
          
  - protocol: rpc
    path: "Simulation._do_reset"
    description:
      zh: >
          复位仿真。
          
      en: >
          Resets the simulation.
          
---
