---
uid: 2e7f4b06
id: seabreeze-inspector.backend.simulation.renderer.panels
parent: seabreeze-inspector.backend.simulation.renderer
tags: [render, hud]
name: {zh: "HUD 与遥测面板", en: "HUD & Telemetry Panels"}
description:
  zh: >
      屏幕叠层：HUD 状态栏、遥测面板与机械臂角度面板的绘制。
      
  en: >
      Screen overlays: the HUD status bar, the telemetry panel and the arm-angle panel.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.811Z"
fingerprint: 2084031753932317830047bfe33ff3e603803f935c5bb125ae1c263a15eda877
source:
  - path: "backend/simulation/renderer.py"
    line: 584
apis:
  - protocol: rpc
    path: "Renderer.draw_hud"
    description:
      zh: >
          画 HUD。
          
      en: >
          Draws the HUD.
          
  - protocol: rpc
    path: "Renderer.draw_telemetry_panel"
    description:
      zh: >
          画遥测面板。
          
      en: >
          Draws the telemetry panel.
          
  - protocol: rpc
    path: "Renderer.draw_arm_panel"
    description:
      zh: >
          画机械臂角度面板。
          
      en: >
          Draws the arm-angle panel.
          
---
