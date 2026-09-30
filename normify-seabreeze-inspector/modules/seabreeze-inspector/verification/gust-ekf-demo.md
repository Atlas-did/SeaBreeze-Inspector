---
uid: f1a6c920
id: seabreeze-inspector.verification.gust-ekf-demo
parent: seabreeze-inspector.verification
tags: [verification, wind]
name: {zh: "阵风+EKF 前馈演示", en: "Gust + EKF Feedforward Demo"}
description:
  zh: >
      在 OmniSim 风桥上跑两段对照：纯 PID 与前馈-PID，采轨迹并输出演示报告（对应 gust_ekf_demo_*.csv/json）。
      
  en: >
      Runs two legs on the OmniSim wind bridge, pure PID versus feedforward PID, records both traces and writes the demo report (the gust_ekf_demo_*.csv/json artefacts).
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.858Z"
fingerprint: 3d90f788cf78d3e42240cb27152f2c4d5dd3c4fedae960f77adc3c1fee60f2ec
source:
  - path: "verify_scripts/gust_ekf_demo.py"
apis:
  - protocol: rpc
    path: "gust_ekf_demo.run_leg"
    description:
      zh: >
          跑一段对照。
          
      en: >
          Runs one comparison leg.
          
  - protocol: rpc
    path: "gust_ekf_demo.main"
    description:
      zh: >
          命令行入口。
          
      en: >
          CLI entry.
          
---
