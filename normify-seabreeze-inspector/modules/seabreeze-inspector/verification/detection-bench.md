---
uid: c4e8b250
id: seabreeze-inspector.verification.detection-bench
parent: seabreeze-inspector.verification
tags: [verification, benchmark]
name: {zh: "检测 FPS 基准", en: "Detection FPS Benchmark"}
description:
  zh: >
      在 640/1024/1280 三种输入尺寸下测检测吞吐，产出 det_fps_*_summary.json 与逐图明细。
      
  en: >
      Benchmarks detection throughput at 640/1024/1280 input sizes, producing the det_fps_*_summary.json files plus per-image detail.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.857Z"
fingerprint: 36bc9b19f55170c4e0645b86d65fad89881c544629a8da30dbd73acfb1dea45b
source:
  - path: "verify_scripts/bench_detection_fps.py"
apis:
  - protocol: rpc
    path: "bench_detection_fps.main"
    description:
      zh: >
          跑 FPS 基准。
          
      en: >
          Runs the FPS benchmark.
          
---
