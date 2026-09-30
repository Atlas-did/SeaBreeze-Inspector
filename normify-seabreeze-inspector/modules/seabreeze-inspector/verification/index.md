---
uid: b4e9d076
id: seabreeze-inspector.verification
parent: seabreeze-inspector
tags: [verification, benchmark]
name: {zh: "验证与测量脚本", en: "Verification & Measurement"}
description:
  zh: >
      产出论文与报告里可复现实测数字的验证脚本：阵风+EKF 前馈演示、3D 悬停精度、机械臂 TCP 精度、控制回路延迟、检测 FPS 基准、风扰注入。
      
  en: >
      Scripts producing the reproducible measured numbers cited in the thesis and reports: gust + EKF feedforward demo, 3D hover accuracy, arm TCP accuracy, control-loop latency, detection FPS benchmark and wind-gust injection.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.860Z"
fingerprint: e59c7533efb978b8018743d9c3815de7e9d36d415b6d831544b703cf6d5719c1
source:
  - path: "verify_scripts/gust_ekf_demo.py"
  - path: "verify_scripts/measure_hover_3d.py"
  - path: "verify_scripts/measure_arm_tcp.py"
  - path: "verify_scripts/measure_latency.py"
  - path: "verify_scripts/bench_detection_fps.py"
  - path: "verify_scripts/wind_gust_injector.py"
---
