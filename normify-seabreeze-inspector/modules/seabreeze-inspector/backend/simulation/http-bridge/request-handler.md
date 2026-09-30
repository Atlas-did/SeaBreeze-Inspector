---
uid: 9f6e2a41
id: seabreeze-inspector.backend.simulation.http-bridge.request-handler
parent: seabreeze-inspector.backend.simulation.http-bridge
tags: [http, bridge]
name: {zh: "HTTP 路由处理器", en: "HTTP Request Handler"}
description:
  zh: >
      Web 3D 与后端之间的 HTTP 接口：/api/state 读仿真状态、/api/command 下发指令、/api/log 取日志。
      
  en: >
      The HTTP interface between the Web 3D view and the backend: /api/state reads simulation state, /api/command issues commands, /api/log returns logs.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.808Z"
fingerprint: 7807014269620f47b29774379d286bff01137cd85e7818f687b284d97687422a
source:
  - path: "backend/simulation/http_bridge.py"
    line: 95
    end_line: 201
apis:
  - protocol: http
    method: GET
    path: "/api/state"
    description:
      zh: >
          读仿真状态。
          
      en: >
          Reads simulation state.
          
  - protocol: http
    method: GET
    path: "/api/command"
    description:
      zh: >
          下发控制指令。
          
      en: >
          Issues a control command.
          
  - protocol: http
    method: GET
    path: "/api/log"
    description:
      zh: >
          取飞行日志。
          
      en: >
          Returns the flight log.
          
---
