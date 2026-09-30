---
uid: f2d8a417
id: seabreeze-inspector.research-ops.figure-generation
parent: seabreeze-inspector.research-ops
tags: [research, figures]
name: {zh: "论文与报告配图生成", en: "Figure Generation"}
description:
  zh: >
      用 Matplotlib 画论文图（架构图/控制回路/状态机/机械臂）与报告图，输出到论文配图目录。
      
  en: >
      Draws the thesis figures (architecture, control loop, state machine, arm) and report figures with Matplotlib into the paper's figure directory.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.830Z"
fingerprint: 7e707768266229d76a5bddc8c87d9c0f3e2fdf5b07166606ad01ae8b4573fb8e
source:
  - path: "research/gen_latex_figures.py"
  - path: "research/gen_report_figures.py"
apis:
  - protocol: rpc
    path: "gen_report_figures.fig_architecture"
    description:
      zh: >
          画系统架构图。
          
      en: >
          Draws the architecture figure.
          
  - protocol: rpc
    path: "gen_report_figures.fig_control_loop"
    description:
      zh: >
          画控制回路图。
          
      en: >
          Draws the control-loop figure.
          
  - protocol: rpc
    path: "gen_report_figures.fig_state_machine"
    description:
      zh: >
          画状态机图。
          
      en: >
          Draws the state-machine figure.
          
---
