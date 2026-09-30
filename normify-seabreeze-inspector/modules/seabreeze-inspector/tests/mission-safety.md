---
uid: 6b3d8e42
id: seabreeze-inspector.tests.mission-safety
parent: seabreeze-inspector.tests
tags: [pytest, mission]
name: {zh: "任务与安全测试", en: "Mission & Safety Tests"}
description:
  zh: >
      任务状态机与三级失效保护的测试（含心跳、可恢复性判定）。
      
  en: >
      Tests for the mission FSM and the tiered failsafe (heartbeat and recoverability checks).
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.848Z"
fingerprint: 49e110bbf34b3edc058d9099476c8d28ed4e3256aa63134ca1e53653757ffbea
source:
  - path: "tests/test_mission.py"
  - path: "tests/test_failsafe_monitor.py"
apis:
  - protocol: rpc
    path: "pytest:tests/test_mission.py"
    description:
      zh: >
          任务状态用例（13 条）。
          
      en: >
          Mission cases (13).
          
  - protocol: rpc
    path: "pytest:tests/test_failsafe_monitor.py"
    description:
      zh: >
          失效保护用例（12 条）。
          
      en: >
          Failsafe cases (12).
          
---
