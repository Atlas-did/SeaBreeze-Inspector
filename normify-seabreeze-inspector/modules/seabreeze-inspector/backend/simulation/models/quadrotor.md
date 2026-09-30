---
uid: 1c9f4a72
id: seabreeze-inspector.backend.simulation.models.quadrotor
parent: seabreeze-inspector.backend.simulation.models
tags: [dynamics, simulation]
name: {zh: "四旋翼质点模型", en: "Quadrotor Point-Mass Model"}
description:
  zh: >
      Tello 的质点动力学：质量/时间步、控制加速度与风扰叠加、位置/速度/姿态积分与状态读写。
      
  en: >
      Tello point-mass dynamics: mass and time step, control acceleration plus wind disturbance, position/velocity/attitude integration and state accessors.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.809Z"
fingerprint: ce32ed8a7bada782ae8d16b707a8b42692c87b33f5e71d299304766a744293ab
source:
  - path: "backend/simulation/models.py"
    line: 29
    end_line: 204
apis:
  - protocol: rpc
    path: "Quadrotor3D.step"
    description:
      zh: >
          推进一个动力学步。
          
      en: >
          Advances one dynamics step.
          
  - protocol: rpc
    path: "Quadrotor3D.get_position"
    description:
      zh: >
          读位置。
          
      en: >
          Reads position.
          
  - protocol: rpc
    path: "Quadrotor3D.get_velocity"
    description:
      zh: >
          读速度。
          
      en: >
          Reads velocity.
          
  - protocol: rpc
    path: "Quadrotor3D.get_attitude"
    description:
      zh: >
          读姿态。
          
      en: >
          Reads attitude.
          
---
