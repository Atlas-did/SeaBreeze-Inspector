---
uid: 2f8b4d16
id: seabreeze-inspector.backend.simulation.pygame-loop.frame-render
parent: seabreeze-inspector.backend.simulation.pygame-loop
tags: [pygame, render]
name: {zh: "逐帧渲染桥接", en: "Per-Frame Render Bridge"}
description:
  zh: >
      把仿真状态交给渲染器画一帧（地面/风机/无人机/机械臂/路径/HUD）。
      
  en: >
      Hands the simulation state to the renderer to draw one frame (ground, turbine, drone, arm, path, HUD).
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.810Z"
fingerprint: 05f41f8c8f9b77d05d50bf89aca61a6d3af3b8f91d26f28a9cb1ce258614a526
source:
  - path: "backend/simulation/simulation.py"
    line: 602
apis:
  - protocol: rpc
    path: "Simulation._render"
    description:
      zh: >
          渲染单帧。
          
      en: >
          Renders one frame.
          
---
