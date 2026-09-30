---
uid: 6a3c8d15
id: seabreeze-inspector.omnisim-assets.tello-dynamics
parent: seabreeze-inspector.omnisim-assets
tags: [omnisim, dynamics]
name: {zh: "Tello 四旋翼动力学", en: "Tello Dynamics"}
description:
  zh: >
      在 OmniSim 侧用四个电机推力推进 Tello 位姿的简化动力学（含风扰作用）。
      
  en: >
      Simplified dynamics that advance the Tello pose from four motor thrusts on the OmniSim side, including wind-disturbance effect.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.829Z"
fingerprint: 32c20e16989a2c109c98650f4a298604d3fcd7afbf43e53828dae1be5c6cf1ab
source:
  - path: "omnisim_wind_assets/seabreeze_tello_wind_bridge.py"
    line: 311
    end_line: 345
apis:
  - protocol: rpc
    path: "TelloDynamics.step"
    description:
      zh: >
          推进一步动力学。
          
      en: >
          Advances one dynamics step.
          
---
