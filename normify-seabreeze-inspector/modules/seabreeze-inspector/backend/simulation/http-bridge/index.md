---
uid: 4f8a2b60
id: seabreeze-inspector.backend.simulation.http-bridge
parent: seabreeze-inspector.backend.simulation
tags: [http, bridge, dashboard]
name: {zh: "HTTP 仿真桥", en: "HTTP Sim Bridge"}
description:
  zh: >
      把 SimRuntime 包成 Web 服务的瘦 HTTP 桥：8811 端口静态站 + GET /api/state、/api/command（按键与手臂角度，0.6s TTL 自动释放）、/api/log；后台线程按 ~50Hz 步进仿真并统计 FPS；黑盒 FlightRecorder 每 100ms 落一行 CSV，退出时 atexit 关闭文件。
      
  en: >
      A thin HTTP bridge wrapping SimRuntime: port 8811 static site plus GET /api/state, /api/command (keys and arm angles with a 0.6 s TTL auto-release) and /api/log; a background thread steps the simulation at about 50 Hz with FPS accounting; FlightRecorder appends a black-box CSV row every 100 ms and atexit closes the file.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.807Z"
fingerprint: 7807014269620f47b29774379d286bff01137cd85e7818f687b284d97687422a
source:
  - path: "backend/simulation/http_bridge.py"
    line: 53
    end_line: 310
deps:
  - kind: call
    to: seabreeze-inspector.backend.simulation.models
    from_api: "rpc:backend.simulation.http_bridge.main"
    to_api: "rpc:VirtualSensor.read_all"
    label: {zh: "装配四旋翼/风/手臂/传感器", en: "Assembles sim objects"}
  - kind: call
    to: seabreeze-inspector.backend.runtime
    from_api: "rpc:backend.simulation.http_bridge.main"
    to_api: "rpc:SimRuntime.step"
    label: {zh: "在后台线程中步进单控制循环", en: "Steps runtime in background"}
  - kind: call
    to: seabreeze-inspector.backend.main.mission-controller
    from_api: "rpc:backend.simulation.http_bridge.main"
    to_api: "rpc:MissionController.__init__"
    label: {zh: "创建仿真模式的 MissionController", en: "Creates sim-mode controller"}
---
