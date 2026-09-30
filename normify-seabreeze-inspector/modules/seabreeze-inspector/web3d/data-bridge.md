---
uid: 3a7c1e05
id: seabreeze-inspector.web3d.data-bridge
parent: seabreeze-inspector.web3d
tags: [threejs, api]
name: {zh: "前端数据桥与配置", en: "Data Bridge & Config"}
description:
  zh: >
      浏览器端与后端仿真桥的 HTTP 对接，以及前端可调参数（相机/颜色/刷新率）。
      
  en: >
      HTTP wiring from the browser to the backend simulation bridge, plus the front-end tunables (camera, colours, refresh rate).
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.861Z"
fingerprint: 706106edeb2c7fca62f0afba2980c5bff1bded8e4f06d7645a1167c10d33d572
source:
  - path: "seabreeze-3d-sim/js/api.js"
  - path: "seabreeze-3d-sim/js/config.js"
apis:
  - protocol: rpc
    path: "api.backend"
    description:
      zh: >
          调用后端桥接口。
          
      en: >
          Calls the backend bridge.
          
  - protocol: file
    path: "seabreeze-3d-sim/js/config.js"
    description:
      zh: >
          前端配置项。
          
      en: >
          Front-end config.
          
---
