---
uid: 0b6d4f92
id: seabreeze-inspector.backend.drone.state-parser
parent: seabreeze-inspector.backend.drone
tags: [drone, telemetry]
name: {zh: "Tello 状态解析", en: "Tello State Parser"}
description:
  zh: >
      把 djitellopy 的原始状态字典（pitch/roll/yaw/vgx/vgy/vgz/tof/h/bat/baro）规范化为 EKF 可用的量：vg* 由 dm/s ×10 转 cm/s，输出 height(cm)/battery/temperature 与速度向量；velocity_approx 明确标注为速度差分近似而非真实加速度（N12 说明），避免下游误当加速度使用。
      
  en: >
      Normalizes the raw djitellopy state dict (pitch/roll/yaw/vgx/vgy/vgz/tof/h/bat/baro) into EKF-ready quantities: vg* converted from dm/s to cm/s by a factor of 10, plus height (cm), battery, temperature and a velocity vector. velocity_approx is explicitly flagged as a velocity-difference approximation rather than true acceleration (note N12) so downstream code cannot mistake it for one.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.798Z"
fingerprint: 361fad5be213955d122d16b18eaad1eb71eab20ddfbe2a7c3a240dc4f0cd1dde
source:
  - path: "backend/drone/tello_state.py"
    line: 1
    end_line: 42
apis:
  - protocol: rpc
    path: "parse_tello_state"
    description:
      zh: >
          解析原始状态字典，输出速度/高度/电量/温度的标准化字典；空输入返回空字典。
          
      en: >
          Parses the raw state dict into normalized velocity/height/battery/temperature fields; an empty input yields an empty dict.
          
  - protocol: rpc
    path: "get_state_dict"
    description:
      zh: >
          从 Tello 对象读取 get_current_state 并解析，读取异常时告警并返回空字典。
          
      en: >
          Reads get_current_state from a Tello object and parses it, warning and returning an empty dict on failure.
          
---
