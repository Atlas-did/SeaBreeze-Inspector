---
uid: 9b1e6f47
id: seabreeze-inspector.backend.main.mission-fsm.state-machine
parent: seabreeze-inspector.backend.main.mission-fsm
tags: [mission, fsm]
name: {zh: "状态机执行", en: "State Machine Execution"}
description:
  zh: >
      八状态任务机的逐帧推进：按当前状态分发行为（起飞/悬停/巡检/导航/返航），并把扰动与检测结果融入转移条件。
      
  en: >
      Per-frame advance of the 8-state mission FSM: behaviour dispatch by current state (takeoff, hover, inspect, navigate, return) with disturbance and detections folded into the transition conditions.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.803Z"
fingerprint: 9d1343fe24eaed513fb689bc1c42fdc8ab476655d66ed0c72ac05e60699704d7
source:
  - path: "backend/main.py"
    line: 261
    end_line: 408
apis:
  - protocol: rpc
    path: "MissionController._handle_state_machine"
    description:
      zh: >
          推进状态机。
          
      en: >
          Advances the state machine.
          
---
