---
uid: c92a5d70
id: seabreeze-inspector.backend.simulation.renderer.scene-draw
parent: seabreeze-inspector.backend.simulation.renderer
tags: [render, scene]
name: {zh: "场景绘制", en: "Scene Drawing"}
description:
  zh: >
      地面网格、风机（塔筒/机舱/叶片）、无人机、机械臂、规划路径与风粒子的绘制。
      
  en: >
      Draws the ground grid, the turbine (tower, nacelle, blades), the drone, the arm, the planned path and the wind particles.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.811Z"
fingerprint: 2084031753932317830047bfe33ff3e603803f935c5bb125ae1c263a15eda877
source:
  - path: "backend/simulation/renderer.py"
    line: 142
    end_line: 583
apis:
  - protocol: rpc
    path: "Renderer.draw_ground"
    description:
      zh: >
          画地面网格。
          
      en: >
          Draws the ground grid.
          
  - protocol: rpc
    path: "Renderer.draw_turbine"
    description:
      zh: >
          画风机。
          
      en: >
          Draws the turbine.
          
  - protocol: rpc
    path: "Renderer.draw_drone"
    description:
      zh: >
          画无人机。
          
      en: >
          Draws the drone.
          
  - protocol: rpc
    path: "Renderer.draw_arm"
    description:
      zh: >
          画机械臂。
          
      en: >
          Draws the arm.
          
  - protocol: rpc
    path: "Renderer.draw_path"
    description:
      zh: >
          画规划路径。
          
      en: >
          Draws the planned path.
          
  - protocol: rpc
    path: "Renderer.draw_wind_particles"
    description:
      zh: >
          画风场粒子。
          
      en: >
          Draws wind particles.
          
---
