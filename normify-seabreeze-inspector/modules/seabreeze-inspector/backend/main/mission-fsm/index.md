---
uid: dd2f7b19
id: seabreeze-inspector.backend.main.mission-fsm
parent: seabreeze-inspector.backend.main
tags: [main, fsm, mission]
name: {zh: "8 状态任务机", en: "Mission FSM"}
description:
  zh: >
      MissionController 的 8 状态处理与状态变更接口：IDLE/TAKEOFF/HOVERING/NAVIGATE/INSPECT/RETURN/LAND/EMERGENCY 各自的期望行为（含受控紧急下降与近地升级硬停桨），以及 set_target/takeoff/plan_path/request_state（走转换表校验）/trigger_emergency。
      
  en: >
      MissionController's eight state handlers and state-change API: the expected behaviour of IDLE/TAKEOFF/HOVERING/NAVIGATE/INSPECT/RETURN/LAND/EMERGENCY, including controlled emergency descent and near-ground escalation to a hard cut, plus set_target/takeoff/plan_path/request_state (validated by the transition table)/trigger_emergency.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.802Z"
fingerprint: 9d1343fe24eaed513fb689bc1c42fdc8ab476655d66ed0c72ac05e60699704d7
source:
  - path: "backend/main.py"
    line: 261
    end_line: 408
  - path: "backend/main.py"
    line: 593
    end_line: 647
deps:
  - kind: reference
    to: seabreeze-inspector.backend.mission.states
    from_api: "rpc:MissionController.request_state"
    to_api: "rpc:can_transition"
    label: {zh: "状态转换表校验", en: "Validates transition table"}
---
