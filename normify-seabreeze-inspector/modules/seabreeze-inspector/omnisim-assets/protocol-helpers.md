---
uid: 8c1d5f37
id: seabreeze-inspector.omnisim-assets.protocol-helpers
parent: seabreeze-inspector.omnisim-assets
tags: [omnisim, util]
name: {zh: "输出重定向与角度工具", en: "Output Tee & Angle Helpers"}
description:
  zh: >
      把仿真输出同时写到控制台与日志的 Tee 包装，以及限幅与角度归一化（wrap_pi）工具。
      
  en: >
      A Tee wrapper that mirrors simulation output to console and log, plus clamping and angle normalisation (wrap_pi) helpers.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.828Z"
fingerprint: 32c20e16989a2c109c98650f4a298604d3fcd7afbf43e53828dae1be5c6cf1ab
source:
  - path: "omnisim_wind_assets/seabreeze_tello_wind_bridge.py"
    line: 58
    end_line: 186
apis:
  - protocol: rpc
    path: "_Tee.write"
    description:
      zh: >
          双路输出。
          
      en: >
          Mirrors output.
          
  - protocol: rpc
    path: "clamp"
    description:
      zh: >
          数值限幅。
          
      en: >
          Clamps a value.
          
  - protocol: rpc
    path: "wrap_pi"
    description:
      zh: >
          角度归一化到 [-π,π]。
          
      en: >
          Normalises an angle to [-pi, pi].
          
---
