---
uid: 0e4a71c3
id: seabreeze-inspector.backend.omnisim.cli
parent: seabreeze-inspector.backend.omnisim
tags: [cli, omnisim, experiment]
name: {zh: "高度保持实验 CLI", en: "Altitude-hold CLI"}
description:
  zh: >
      python -m backend.omnisim 的命令行入口：altitude 子命令解析目标高度/后端(sim|omnisim|mock)/机型/工况/稳态时长/种子/备注，装配对应驱动并调用统一 run_altitude_hold，把结果 JSON 写入 data/processed/omnisim/commands/ 并可 --json 打印。
      
  en: >
      CLI entry for python -m backend.omnisim: the altitude subcommand parses target height, backend (sim, omnisim or mock), model, wind case, settle time, seed and note, builds the matching driver and calls the shared run_altitude_hold, writing the result JSON under data/processed/omnisim/commands/ with an optional --json print.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.805Z"
fingerprint: d60c9767c5094af6d5bb1362c79f4b6bc419c9742b48efb5f4b494d017812e85
source:
  - path: "backend/omnisim/__main__.py"
    line: 23
    end_line: 109
apis:
  - protocol: rpc
    path: "backend.omnisim.__main__.main"
    description:
      zh: >
          执行高度保持实验：装配驱动、跑 run_altitude_hold、写 JSON 并打印摘要，失败退出码 2。
          
      en: >
          Runs the altitude-hold experiment: builds the driver, calls run_altitude_hold, writes JSON and prints a summary, exiting 2 on failure.
          
  - protocol: rpc
    path: "backend.omnisim.__main__._build_parser"
    description:
      zh: >
          构造 argparse：altitude 子命令与目标高度/后端/机型/风况/时长/种子/备注/输出参数。
          
      en: >
          Builds the argparse tree: the altitude subcommand plus target height, backend, model, wind, duration, seed, note and output options.
          
  - protocol: rpc
    path: "backend.omnisim.__main__._build_driver"
    description:
      zh: >
          按 --backend 装配驱动：sim 走自家仿真、omnisim 走 HTTP 驱动，mock 明确拒绝。
          
      en: >
          Builds the driver for the chosen backend: sim for the in-house simulation, omnisim for the HTTP driver, and an explicit refusal for mock.
          
  - protocol: file
    path: "data/processed/omnisim/commands/altitude_hold_1.5m_sim_calm_42.json"
    description:
      zh: >
          实验结果的落盘位置示例（按目标高度/后端/风况/种子命名）。
          
      en: >
          Example result artefact path, named by target height, backend, wind case and seed.
          
deps:
  - kind: call
    to: seabreeze-inspector.backend.omnisim.adapter
    from_api: "rpc:backend.omnisim.__main__._build_driver"
    to_api: "rpc:OmniSimDriver.set_target_altitude"
    label: {zh: "omnisim 后端装配 HTTP 驱动", en: "Builds HTTP bridge driver"}
  - kind: call
    to: seabreeze-inspector.backend.simulation.altitude-driver
    from_api: "rpc:backend.omnisim.__main__._build_driver"
    to_api: "rpc:build_sim_driver"
    label: {zh: "sim 后端装配自家仿真驱动", en: "Builds in-house sim driver"}
---
