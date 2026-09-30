---
uid: 8e2b6d41
id: seabreeze-inspector.backend.simulation.models.wind
parent: seabreeze-inspector.backend.simulation.models
tags: [wind, simulation]
name: {zh: "风扰模型", en: "Wind Disturbance Model"}
description:
  zh: >
      基础风向量 + 随机扰动的风场模型，每步采样得到作用于飞行器的扰动力。
      
  en: >
      Wind model with a base wind vector plus stochastic disturbance, sampled each step to yield the force acting on the vehicle.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.809Z"
fingerprint: ce32ed8a7bada782ae8d16b707a8b42692c87b33f5e71d299304766a744293ab
source:
  - path: "backend/simulation/models.py"
    line: 205
    end_line: 236
apis:
  - protocol: rpc
    path: "WindDisturbance.sample"
    description:
      zh: >
          采样一步风扰。
          
      en: >
          Samples one step of wind disturbance.
          
---
