---
uid: 5b9c2e03
id: seabreeze-inspector.tooling.diagnostics
parent: seabreeze-inspector.tooling
tags: [tooling, diagnostics]
name: {zh: "依赖体检与仿真冒烟", en: "Dependency Check & Smoke Test"}
description:
  zh: >
      环境依赖/权重/配置目录的体检脚本，以及不依赖 Pygame 窗口的仿真冒烟测试。
      
  en: >
      An environment check covering dependencies, weights and config directories, plus a windowless simulation smoke test.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.852Z"
fingerprint: 00909193d7c40b57bf32cdb078a8a27e581e0f84c4f193aa3457d039daeb15bd
source:
  - path: "scripts/check_deps.py"
  - path: "scripts/smoke_test_sim.py"
apis:
  - protocol: rpc
    path: "check_deps.main"
    description:
      zh: >
          依赖与环境体检。
          
      en: >
          Dependency and environment check.
          
  - protocol: rpc
    path: "smoke_test_sim.main"
    description:
      zh: >
          仿真冒烟测试。
          
      en: >
          Simulation smoke test.
          
---
