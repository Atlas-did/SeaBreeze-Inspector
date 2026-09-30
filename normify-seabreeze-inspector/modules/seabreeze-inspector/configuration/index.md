---
uid: c2a6f31d
id: seabreeze-inspector.configuration
parent: seabreeze-inspector
tags: [config, yaml]
name: {zh: "YAML 配置", en: "YAML Configuration"}
description:
  zh: >
      系统参数配置：无人机（drone_config.yaml）、机械臂（arm_config.yaml）、检测模型（yolo_config.yaml）。由 backend.utils.config-loader 加载并做类型/范围校验，是仿真与真机共用的唯一参数来源。
      
  en: >
      System parameter configuration: drone (drone_config.yaml), arm (arm_config.yaml) and detection model (yolo_config.yaml). Loaded and type/range-validated by backend.utils.config-loader; the single parameter source shared by simulation and real hardware.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.817Z"
fingerprint: ce3d743eb1975866afd4938a143703fd8f2228c22f39dff1d832a17472db72a7
source:
  - path: "config/arm_config.yaml"
  - path: "config/drone_config.yaml"
  - path: "config/yolo_config.yaml"
---
