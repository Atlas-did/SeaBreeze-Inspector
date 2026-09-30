---
uid: 3a6c9b27
id: seabreeze-inspector.backend.core.trajectory-rrt.planner-core
parent: seabreeze-inspector.backend.core.trajectory-rrt
tags: [rrt-star, planning]
name: {zh: "RRT* 规划主循环", en: "RRT* Planner Core"}
description:
  zh: >
      RRT* 本体与对外 plan() 入口：迭代上限、步长、重连开关与障碍物列表的装配。
      
  en: >
      The RRT* planner itself and its public plan() entry: iteration budget, step size, rewire switch and obstacle list assembly.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.796Z"
fingerprint: d6bfed691a72678202ab01b85db46a56ed65dbfad3673aec6b287763fb5cf711
source:
  - path: "backend/core/trajectory_planning.py"
    line: 25
    end_line: 159
apis:
  - protocol: rpc
    path: "RRTStarPlanner.plan"
    description:
      zh: >
          规划起点到目标的可行路径。
          
      en: >
          Plans a feasible path from start to goal.
          
---
