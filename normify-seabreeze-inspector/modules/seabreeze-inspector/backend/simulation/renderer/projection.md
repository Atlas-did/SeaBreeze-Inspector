---
uid: 6b3e8f14
id: seabreeze-inspector.backend.simulation.renderer.projection
parent: seabreeze-inspector.backend.simulation.renderer
tags: [render, projection]
name: {zh: "等轴投影与坐标变换", en: "Isometric Projection"}
description:
  zh: >
      世界坐标到屏幕坐标的等轴投影（to_isometric）与 Renderer 的投影/帧准备。
      
  en: >
      Isometric world-to-screen projection (to_isometric) plus the Renderer's projection and per-frame preparation.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.811Z"
fingerprint: 2084031753932317830047bfe33ff3e603803f935c5bb125ae1c263a15eda877
source:
  - path: "backend/simulation/renderer.py"
    line: 78
    end_line: 141
apis:
  - protocol: rpc
    path: "to_isometric"
    description:
      zh: >
          世界坐标→屏幕坐标。
          
      en: >
          World to screen coordinates.
          
  - protocol: rpc
    path: "Renderer.project"
    description:
      zh: >
          投影单个 3D 点。
          
      en: >
          Projects one 3D point.
          
  - protocol: rpc
    path: "Renderer.tick"
    description:
      zh: >
          帧开始准备。
          
      en: >
          Starts a frame.
          
---
