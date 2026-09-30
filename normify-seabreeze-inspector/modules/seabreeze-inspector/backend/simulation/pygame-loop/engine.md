---
uid: 4b1e7a20
id: seabreeze-inspector.backend.simulation.pygame-loop.engine
parent: seabreeze-inspector.backend.simulation.pygame-loop
tags: [pygame, simulation]
name: {zh: "仿真引擎与主循环", en: "Simulation Engine & Main Loop"}
description:
  zh: >
      Pygame 仿真类本体：装配无人机/风场/机械臂模型与渲染器，维护仿真时钟，提供 step() 推进与 run() 主循环。
      
  en: >
      The Pygame Simulation class itself: assembles the drone/wind/arm models and renderer, owns the simulation clock, and exposes step() plus the run() main loop.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.810Z"
fingerprint: 05f41f8c8f9b77d05d50bf89aca61a6d3af3b8f91d26f28a9cb1ce258614a526
source:
  - path: "backend/simulation/simulation.py"
    line: 56
    end_line: 376
apis:
  - protocol: rpc
    path: "Simulation.step"
    description:
      zh: >
          推进一个仿真步。
          
      en: >
          Advances one simulation step.
          
  - protocol: rpc
    path: "Simulation.run"
    description:
      zh: >
          主循环。
          
      en: >
          Main loop.
          
---
