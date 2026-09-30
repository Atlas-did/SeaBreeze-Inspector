---
uid: b6f3d219
id: seabreeze-inspector.backend.core.trajectory-rrt
parent: seabreeze-inspector.backend.core
tags: [planning, rrt]
name: {zh: "RRT* 三维路径规划", en: "RRT* 3D Path Planner"}
description:
  zh: >
      随机采样 RRT* 规划器：10% 目标偏置采样、cKDTree 最近邻与半径查询、步长 steering 扩展、球体/圆柱碰撞检测、代价重连（rewire）保证渐进最优、回溯路径并做避障中值平滑；支持超时与最大迭代上限，未精确到达时返回最近节点路径。圆柱碰撞模型对应风机塔筒场景。
      
  en: >
      Sampling-based RRT* planner: 10% goal-biased sampling, cKDTree nearest-neighbour and radius queries, step-size steering, sphere/cylinder collision checks, cost-based rewiring for asymptotic optimality, path backtracking and collision-safe midpoint smoothing. Bounded by max iterations and a timeout; when the goal is not reached exactly it returns the nearest-node path. The cylinder model targets the turbine-tower scenario.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.796Z"
fingerprint: d6bfed691a72678202ab01b85db46a56ed65dbfad3673aec6b287763fb5cf711
source:
  - path: "backend/core/trajectory_planning.py"
    line: 1
    end_line: 260
---
