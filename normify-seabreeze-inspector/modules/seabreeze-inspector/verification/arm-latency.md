---
uid: 7f1a3d68
id: seabreeze-inspector.verification.arm-latency
parent: seabreeze-inspector.verification
tags: [verification, arm]
name: {zh: "机械臂 TCP 与控制延迟测量", en: "Arm TCP & Latency Measurement"}
description:
  zh: >
      通过 HTTP 桥驱动机械臂并测量末端定位误差，以及控制回路逐级延迟测量。
      
  en: >
      Drives the arm through the HTTP bridge to measure end-effector positioning error, and measures control-loop latency stage by stage.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.857Z"
fingerprint: 3358b3f3940a3c34f0ac96ba0953197d8dd726370833ee6f16440ae7bf6dda53
source:
  - path: "verify_scripts/measure_arm_tcp.py"
  - path: "verify_scripts/measure_latency.py"
apis:
  - protocol: rpc
    path: "measure_arm_tcp.extract_tcp"
    description:
      zh: >
          提取 TCP 坐标。
          
      en: >
          Extracts TCP coordinates.
          
  - protocol: rpc
    path: "measure_arm_tcp.main"
    description:
      zh: >
          TCP 精度测量。
          
      en: >
          TCP accuracy measurement.
          
  - protocol: rpc
    path: "measure_latency.main"
    description:
      zh: >
          延迟测量。
          
      en: >
          Latency measurement.
          
---
