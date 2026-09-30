---
uid: 2a7e0c41
id: seabreeze-inspector.backend.simulation.models
parent: seabreeze-inspector.backend.simulation
tags: [physics, simulation, sensors]
name: {zh: "物理模型与虚拟传感器", en: "Physics Models & Sensors"}
description:
  zh: >
      仿真物理与传感器模型（z-up，米制）：Quadrotor3D 点质量动力学（姿态环一阶跟踪、气动阻力、触地钳位）、WindDisturbance 正弦+阵风、RobotArm3DOF 手臂（末端由 arm_kinematics 正解）、WindTurbine 塔筒几何、VirtualSensor 高斯噪声+零偏漂移+随机游走的 IMU/光流/气压计。
      
  en: >
      Simulation physics and sensor models (z-up, metres): Quadrotor3D point-mass dynamics (first-order attitude loop, aerodynamic drag, ground clamp), WindDisturbance sine plus gust, RobotArm3DOF (endpoint from arm_kinematics FK), WindTurbine cylinder geometry, and VirtualSensor IMU/optical-flow/barometer with Gaussian noise, bias drift and random walk.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.809Z"
fingerprint: ce32ed8a7bada782ae8d16b707a8b42692c87b33f5e71d299304766a744293ab
source:
  - path: "backend/simulation/models.py"
    line: 29
    end_line: 481
deps:
  - kind: reference
    to: seabreeze-inspector.backend.hal
    from_api: "rpc:RobotArm3DOF.set_angles"
    to_api: "rpc:ArmInterface.set_angles"
    label: {zh: "仿真手臂实现 HAL 手臂接口", en: "Implements HAL arm contract"}
  - kind: call
    to: seabreeze-inspector.backend.utils.units
    from_api: "rpc:VirtualSensor.read_all"
    to_api: "rpc:m_to_cm"
    label: {zh: "米制物理量转后端厘米制", en: "Physics metres to backend cm"}
---
