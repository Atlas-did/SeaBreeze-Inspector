---
uid: b8f2d504
id: seabreeze-inspector.backend.core.trajectory-rrt.sampling-collision
parent: seabreeze-inspector.backend.core.trajectory-rrt
tags: [sampling, collision]
name: {zh: "采样、扩展与碰撞检测", en: "Sampling, Steering & Collision"}
description:
  zh: >
      随机采样、最近邻搜索、朝目标扩展，以及球形/圆柱体障碍物与整条路径的碰撞判定。
      
  en: >
      Random sampling, nearest-neighbour search, steering toward the goal, plus sphere/cylinder obstacle and whole-path collision checks.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.797Z"
fingerprint: d6bfed691a72678202ab01b85db46a56ed65dbfad3673aec6b287763fb5cf711
source:
  - path: "backend/core/trajectory_planning.py"
    line: 160
    end_line: 248
apis:
  - protocol: rpc
    path: "RRTStarPlanner._random_sample"
    description:
      zh: >
          随机采样节点。
          
      en: >
          Samples a random node.
          
  - protocol: rpc
    path: "RRTStarPlanner._nearest"
    description:
      zh: >
          最近邻搜索。
          
      en: >
          Nearest-neighbour search.
          
  - protocol: rpc
    path: "RRTStarPlanner._steer"
    description:
      zh: >
          朝采样点扩展。
          
      en: >
          Steers toward the sample.
          
  - protocol: rpc
    path: "RRTStarPlanner._cylinder_collision"
    description:
      zh: >
          风机圆柱体碰撞判定。
          
      en: >
          Turbine-cylinder collision test.
          
  - protocol: rpc
    path: "RRTStarPlanner.rewire"
    description:
      zh: >
          邻域重连（渐近最优性）。
          
      en: >
          Neighbourhood rewiring for asymptotic optimality.
          
---
