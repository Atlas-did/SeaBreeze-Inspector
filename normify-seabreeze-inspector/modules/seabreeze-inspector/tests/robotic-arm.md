---
uid: 2c7f1a93
id: seabreeze-inspector.tests.robotic-arm
parent: seabreeze-inspector.tests
tags: [pytest, arm]
name: {zh: "机械臂测试", en: "Robotic Arm Tests"}
description:
  zh: >
      3-DOF 机械臂正逆运动学与串口控制器测试。
      
  en: >
      Forward/inverse kinematics and serial-controller tests for the 3-DOF arm.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.850Z"
fingerprint: d8607aaf3ae618e83b478ac87ba4dc1c9047ec6f63e51b242e4eea0390d48bb1
source:
  - path: "tests/test_arm.py"
  - path: "tests/test_arm_controller.py"
apis:
  - protocol: rpc
    path: "pytest:tests/test_arm.py"
    description:
      zh: >
          运动学用例（4 条）。
          
      en: >
          Kinematics cases (4).
          
  - protocol: rpc
    path: "pytest:tests/test_arm_controller.py"
    description:
      zh: >
          控制器用例（5 条）。
          
      en: >
          Controller cases (5).
          
---
