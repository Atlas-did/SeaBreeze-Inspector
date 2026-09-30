---
uid: 3f9a2c71
id: seabreeze-inspector.tests.control-algorithms
parent: seabreeze-inspector.tests
tags: [pytest, control]
name: {zh: "算法与控制测试", en: "Algorithm & Control Tests"}
description:
  zh: >
      EKF 观测器、前馈 PID 控制器、RRT* 轨迹与坐标系变换的单元测试。
      
  en: >
      Unit tests for the EKF observer, the feedforward PID controller, RRT* trajectory planning and frame transforms.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.840Z"
fingerprint: e9f51cfd75288a0e1d35c5186c9a0cf56ac9c51a02cb4b4651ea5882ec6f2ea4
source:
  - path: "tests/test_ekf.py"
  - path: "tests/test_controller.py"
  - path: "tests/test_trajectory.py"
  - path: "tests/test_frames.py"
apis:
  - protocol: rpc
    path: "pytest:tests/test_ekf.py"
    description:
      zh: >
          EKF 用例（5 条）。
          
      en: >
          EKF cases (5).
          
  - protocol: rpc
    path: "pytest:tests/test_controller.py"
    description:
      zh: >
          控制器用例（5 条）。
          
      en: >
          Controller cases (5).
          
  - protocol: rpc
    path: "pytest:tests/test_trajectory.py"
    description:
      zh: >
          轨迹规划用例（4 条）。
          
      en: >
          Trajectory cases (4).
          
  - protocol: rpc
    path: "pytest:tests/test_frames.py"
    description:
      zh: >
          坐标变换用例（8 条）。
          
      en: >
          Frame cases (8).
          
---
