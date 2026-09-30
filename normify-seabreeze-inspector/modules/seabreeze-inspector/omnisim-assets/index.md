---
uid: 4c8e6a21
id: seabreeze-inspector.omnisim-assets
parent: seabreeze-inspector
tags: [omnisim, wind, integration]
name: {zh: "OmniSim 风场桥与资产", en: "OmniSim Wind Bridge & Assets"}
description:
  zh: >
      与外部 OmniSim 安装对接的风场桥接控制器（827 行）：风模型（WindModel）、Tello 动力学（TelloDynamics）与状态快照，把仿真侧风扰动注入控制回路，用于阵风—EKF 前馈联合验证；并随包 3-DOF 机械臂 OBJ 网格资产。
      
  en: >
      Wind-bridge controller (827 lines) connecting to the external OmniSim installation: wind model, Tello dynamics and state snapshots, injecting simulation-side wind disturbance into the control loop for joint gust/EKF feedforward verification; ships 3-DOF arm OBJ mesh assets.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.828Z"
fingerprint: abf9d2db4a947d4c43ca5492439ee01f305a1ee1663c5a0d9483cf486e7da429
source:
  - path: "omnisim_wind_assets/seabreeze_tello_wind_bridge.py"
    line: 1
    end_line: 827
  - path: "omnisim_models/meshes/base_link.obj"
---
