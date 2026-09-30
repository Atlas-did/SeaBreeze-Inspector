---
uid: b73c0d96
id: seabreeze-inspector.backend.simulation.http-bridge.flight-recorder
parent: seabreeze-inspector.backend.simulation.http-bridge
tags: [bridge, logging]
name: {zh: "飞行记录器", en: "Flight Recorder"}
description:
  zh: >
      Web 仿真下的飞行日志：逐帧记录位置/姿态/扰动并落盘 CSV。
      
  en: >
      Flight logging under the web simulation: records position, attitude and disturbance per frame and writes a CSV.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.807Z"
fingerprint: 7807014269620f47b29774379d286bff01137cd85e7818f687b284d97687422a
source:
  - path: "backend/simulation/http_bridge.py"
    line: 53
    end_line: 94
apis:
  - protocol: rpc
    path: "FlightRecorder.record"
    description:
      zh: >
          记录一帧。
          
      en: >
          Records one frame.
          
  - protocol: rpc
    path: "FlightRecorder.close"
    description:
      zh: >
          关闭并落盘。
          
      en: >
          Closes and flushes to disk.
          
---
