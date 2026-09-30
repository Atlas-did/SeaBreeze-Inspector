---
uid: f6a7b8c9
id: seabreeze-inspector.verification.sim-mode-bench
parent: seabreeze-inspector.verification
tags: [verification, benchmark, simulation]
name: {zh: "速度模式专项基准", en: "Velocity-Mode Benchmark"}
description:
  zh: >
      在同一套协议（v1：悬停保持 / 航点 / 返航 × 静风与 2m/s 持续风）下对照两条执行路径：legacy 位置级联与 velocity 速度链路（与真机 RC 同源）。输出 JSON 与对比表，固定 seed/帧数，两次运行逐字节一致。实测 legacy 在持续风下发散（横向数百米）而 velocity 保持个位数厘米。
      
  en: >
      Compares two execution paths under one protocol (v1: hover hold, waypoint, return-home x calm and 2 m/s sustained wind): the legacy position cascade versus the velocity path that shares the real RC link. Emits JSON plus a table; fixed seed and frame counts make two runs byte-identical. Measured: legacy diverges under sustained wind (hundreds of metres) while velocity stays within centimetres.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:32:18.250Z"
fingerprint: 2b12f6948c2591c18b10fbe3250f5387a48d68007c7cb6c175650d9ce78aadd3
source:
  - path: "scripts/bench_sim_modes.py"
    line: 1
    end_line: 210
apis:
  - protocol: rpc
    path: "run_case"
    description:
      zh: >
          跑一种模式 × 一种风况的完整协议并返回指标。
          
      en: >
          Runs the full protocol for one mode and one wind condition, returning metrics.
          
  - protocol: file
    path: "docs/bench/velocity_mode_bench.json"
    description:
      zh: >
          基准结果落盘（协议版本/帧数/seed/各工况指标）。
          
      en: >
          Benchmark result artefact: protocol version, frame counts, seed and per-case metrics.
          
---
