---
uid: 2d7e9a35
id: seabreeze-inspector.configuration.flight-vehicle
parent: seabreeze-inspector.configuration
tags: [config, yaml]
name: {zh: "飞行器与机械臂配置", en: "Flight Vehicle & Arm Config"}
description:
  zh: >
      无人机控制参数（高度/速度/限幅/EKF 噪声）与机械臂几何和舵机参数的 YAML 配置。
      
  en: >
      YAML configuration for drone control parameters (altitude, speed, limits, EKF noise) and for arm geometry and servo parameters.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.816Z"
fingerprint: f489997f12392e1470c82d09ea2d1f74f8034bdda3bc85a1c2c17871eefc5cbd
source:
  - path: "config/drone_config.yaml"
  - path: "config/arm_config.yaml"
apis:
  - protocol: file
    path: "config/drone_config.yaml"
    description:
      zh: >
          无人机控制配置。
          
      en: >
          Drone control config.
          
  - protocol: file
    path: "config/arm_config.yaml"
    description:
      zh: >
          机械臂配置。
          
      en: >
          Arm config.
          
---
