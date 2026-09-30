---
uid: d0e4a875
id: seabreeze-inspector.web3d.hud-and-entry
parent: seabreeze-inspector.web3d
tags: [threejs, hud]
name: {zh: "HUD 与页面入口", en: "HUD & Page Entry"}
description:
  zh: >
      浏览器端 HUD 仪表与页面入口：初始化场景/相机/渲染循环，并把遥测数据映射到显示。
      
  en: >
      Browser-side HUD and page entry: initialises the scene, camera and render loop, and maps telemetry onto the display.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.861Z"
fingerprint: 2a4c215890cc7054a7ec52ae380bc054c9b1fa6b88a59b0c45488fde3406f6b1
source:
  - path: "seabreeze-3d-sim/js/hud.js"
  - path: "seabreeze-3d-sim/js/main.js"
apis:
  - protocol: rpc
    path: "hud.HUD"
    description:
      zh: >
          HUD 实例。
          
      en: >
          HUD instance.
          
  - protocol: rpc
    path: "main.init"
    description:
      zh: >
          页面入口初始化。
          
      en: >
          Page entry init.
          
---
