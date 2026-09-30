---
uid: d1f7a538
id: seabreeze-inspector.backend.main.runtime-loop.sensor-and-control
parent: seabreeze-inspector.backend.main.runtime-loop
tags: [runtime, control]
name: {zh: "传感器注入与控制输出", en: "Sensor Injection & Control Output"}
description:
  zh: >
      仿真注入入口与每帧管线：总线命令、传感器取值、安全检查，并回传控制输出与状态。
      
  en: >
      The simulation injection entry and the per-frame pipeline: bus commands, sensor read, safety check, returning control output and state.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.804Z"
fingerprint: 9d1343fe24eaed513fb689bc1c42fdc8ab476655d66ed0c72ac05e60699704d7
source:
  - path: "backend/main.py"
    line: 410
    end_line: 587
apis:
  - protocol: rpc
    path: "MissionController.update_with_external_data"
    description:
      zh: >
          外部数据注入入口。
          
      en: >
          External-data injection entry.
          
  - protocol: rpc
    path: "MissionController._process_bus_commands"
    description:
      zh: >
          处理总线命令。
          
      en: >
          Processes bus commands.
          
  - protocol: rpc
    path: "MissionController._get_sensor_data"
    description:
      zh: >
          取传感器值。
          
      en: >
          Reads sensors.
          
  - protocol: rpc
    path: "MissionController._check_safety"
    description:
      zh: >
          分层安全检查。
          
      en: >
          Tiered safety check.
          
---
