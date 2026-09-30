---
uid: 9d5a1c83
id: seabreeze-inspector.omnisim-assets.http-entry-and-mesh
parent: seabreeze-inspector.omnisim-assets
tags: [omnisim, http]
name: {zh: "桥的 HTTP 入口与网格资产", en: "Bridge HTTP Entry & Meshes"}
description:
  zh: >
      风场桥对外的 HTTP 入口（GET/POST 处理与启动函数）与随包的 3-DOF 机械臂 OBJ/MTL 网格资产。
      
  en: >
      The bridge's outward HTTP entry (GET/POST handlers and the start function) plus the bundled 3-DOF arm OBJ/MTL mesh assets.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.827Z"
fingerprint: abf9d2db4a947d4c43ca5492439ee01f305a1ee1663c5a0d9483cf486e7da429
source:
  - path: "omnisim_wind_assets/seabreeze_tello_wind_bridge.py"
    line: 901
  - path: "omnisim_models/meshes/base_link.obj"
apis:
  - protocol: rpc
    path: "start_bridge"
    description:
      zh: >
          启动桥服务。
          
      en: >
          Starts the bridge.
          
  - protocol: rpc
    path: "Handler.do_GET"
    description:
      zh: >
          GET 接口。
          
      en: >
          GET handler.
          
  - protocol: rpc
    path: "Handler.do_POST"
    description:
      zh: >
          POST 接口。
          
      en: >
          POST handler.
          
  - protocol: file
    path: "omnisim_models/meshes/base_link.obj"
    description:
      zh: >
          机械臂基座网格。
          
      en: >
          Arm base mesh.
          
---
