---
uid: d4a1e850
id: seabreeze-inspector.backend.simulation.models.virtual-sensor
parent: seabreeze-inspector.backend.simulation.models
tags: [sensor, simulation]
name: {zh: "虚拟传感器", en: "Virtual Sensor"}
description:
  zh: >
      带零偏随机游走的 IMU/光流/气压计仿真：产生与真实 Tello 同量级的噪声观测，供 EKF 与注入接口使用。
      
  en: >
      IMU/optical-flow/barometer simulation with bias random walk, producing noise at the same order as the real Tello for the EKF and the injection interface.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.809Z"
fingerprint: ce32ed8a7bada782ae8d16b707a8b42692c87b33f5e71d299304766a744293ab
source:
  - path: "backend/simulation/models.py"
    line: 356
apis:
  - protocol: rpc
    path: "VirtualSensor.read_imu"
    description:
      zh: >
          输出带噪 IMU 加速度。
          
      en: >
          Emits noisy IMU acceleration.
          
  - protocol: rpc
    path: "VirtualSensor.read_optical"
    description:
      zh: >
          输出带噪光流位置。
          
      en: >
          Emits noisy optical-flow position.
          
  - protocol: rpc
    path: "VirtualSensor.read_barometer"
    description:
      zh: >
          输出带噪气压高度。
          
      en: >
          Emits noisy barometric height.
          
  - protocol: rpc
    path: "VirtualSensor.read_all"
    description:
      zh: >
          一次读出 6 维观测向量。
          
      en: >
          Returns the 6-D measurement vector.
          
---
