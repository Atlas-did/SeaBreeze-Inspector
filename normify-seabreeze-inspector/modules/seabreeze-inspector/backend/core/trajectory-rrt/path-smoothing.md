---
uid: 7d4a9e15
id: seabreeze-inspector.backend.core.trajectory-rrt.path-smoothing
parent: seabreeze-inspector.backend.core.trajectory-rrt
tags: [planning, smoothing]
name: {zh: "路径回溯与平滑", en: "Path Backtracking & Smoothing"}
description:
  zh: >
      从目标回溯父节点还原路径，并做拉直式平滑与路径级碰撞复检。
      
  en: >
      Backtracks parent pointers from the goal to recover the path, then straightens it and re-checks the whole path for collisions.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.796Z"
fingerprint: d6bfed691a72678202ab01b85db46a56ed65dbfad3673aec6b287763fb5cf711
source:
  - path: "backend/core/trajectory_planning.py"
    line: 249
apis:
  - protocol: rpc
    path: "RRTStarPlanner._path_collision"
    description:
      zh: >
          整条路径碰撞复检。
          
      en: >
          Whole-path collision re-check.
          
  - protocol: rpc
    path: "RRTStarPlanner._backtrack"
    description:
      zh: >
          回溯父节点还原路径。
          
      en: >
          Backtracks to recover the path.
          
  - protocol: rpc
    path: "RRTStarPlanner._smooth_path"
    description:
      zh: >
          路径平滑。
          
      en: >
          Smooths the path.
          
---
