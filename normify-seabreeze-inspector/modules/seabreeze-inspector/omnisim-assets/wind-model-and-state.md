---
uid: 2f7b9e40
id: seabreeze-inspector.omnisim-assets.wind-model-and-state
parent: seabreeze-inspector.omnisim-assets
tags: [omnisim, wind]
name: {zh: "风场模型与状态快照", en: "Wind Model & State Snapshot"}
description:
  zh: >
      可配置的风场模型（基准风/阵风/方向）及其逐步演化与快照，以及被控对象状态结构。
      
  en: >
      The configurable wind model (base wind, gusts, direction) with its step evolution and snapshot, plus the controlled-object state structure.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.829Z"
fingerprint: 32c20e16989a2c109c98650f4a298604d3fcd7afbf43e53828dae1be5c6cf1ab
source:
  - path: "omnisim_wind_assets/seabreeze_tello_wind_bridge.py"
    line: 187
    end_line: 310
apis:
  - protocol: rpc
    path: "WindModel.configure"
    description:
      zh: >
          配置风场。
          
      en: >
          Configures the wind.
          
  - protocol: rpc
    path: "WindModel.step"
    description:
      zh: >
          推进风场。
          
      en: >
          Steps the wind.
          
  - protocol: rpc
    path: "WindModel.snapshot"
    description:
      zh: >
          导出风场快照。
          
      en: >
          Exports a wind snapshot.
          
  - protocol: rpc
    path: "State.snapshot"
    description:
      zh: >
          导出状态快照。
          
      en: >
          Exports state.
          
---
