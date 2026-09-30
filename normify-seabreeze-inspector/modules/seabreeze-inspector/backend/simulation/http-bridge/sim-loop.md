---
uid: 3c8e5a17
id: seabreeze-inspector.backend.simulation.http-bridge.sim-loop
parent: seabreeze-inspector.backend.simulation.http-bridge
tags: [bridge, loop]
name: {zh: "桥主循环与入口", en: "Bridge Loop & Entry"}
description:
  zh: >
      固定频率推进仿真并周期播报状态的后台循环，以及命令行入口（默认端口 8811）。
      
  en: >
      The background loop that advances the simulation at a fixed rate and broadcasts state, plus the CLI entry (default port 8811).
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.808Z"
fingerprint: 7807014269620f47b29774379d286bff01137cd85e7818f687b284d97687422a
source:
  - path: "backend/simulation/http_bridge.py"
    line: 202
apis:
  - protocol: rpc
    path: "sim_loop"
    description:
      zh: >
          仿真推进循环。
          
      en: >
          Simulation advance loop.
          
  - protocol: rpc
    path: "main"
    description:
      zh: >
          启动 HTTP 桥服务。
          
      en: >
          Starts the HTTP bridge server.
          
---
