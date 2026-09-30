---
uid: 5a3f9d16
id: seabreeze-inspector.backend.drone.command-schema
parent: seabreeze-inspector.backend.drone
tags: [drone, schema]
name: {zh: "飞行指令与结果 schema", en: "Flight Command & Result Schema"}
description:
  zh: >
      把一条飞行指令表达为可复现的 FlightCommand（op/params/note，支持字典互转；move_to 单位 cm、altitude_hold 单位 m）与统一可序列化结果 CommandResult（accepted/target_m/measured_m/error_m/steady_std_m/settled，证据等级 evidence_level 默认 simulation-only，避免仿真数据冒充实测），并定义动态指令驱动协议 AltitudeHoldDriver 供 mock/内置仿真/OmniSim/真机四后端共同实现。
      
  en: >
      Represents one flight command as a reproducible FlightCommand (op/params/note with dict round-trip; move_to in cm, altitude_hold in m) and a serializable CommandResult (accepted/target_m/measured_m/error_m/steady_std_m/settled with evidence_level defaulting to simulation-only so simulated numbers cannot masquerade as measurements), plus the AltitudeHoldDriver protocol shared by the mock, built-in simulation, OmniSim and real-drone backends.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.797Z"
fingerprint: 5e3c7c5afd57aac0f007017b0a1a2e78de2213a7a8fa0f503a746a267685c02b
source:
  - path: "backend/drone/commands.py"
    line: 28
    end_line: 111
apis:
  - protocol: rpc
    path: "FlightCommand.to_dict"
    description:
      zh: >
          把指令序列化为 {op, params, note} 字典。
          
      en: >
          Serializes the command to an {op, params, note} dict.
          
  - protocol: rpc
    path: "FlightCommand.from_dict"
    description:
      zh: >
          从字典重建指令（params/note 缺省为空）。
          
      en: >
          Rebuilds a command from a dict, defaulting params/note to empty.
          
  - protocol: rpc
    path: "CommandResult.to_dict"
    description:
      zh: >
          输出可直接 json.dumps 的结果字典，并附加 source=SeaBreeze-Inspector 标记。
          
      en: >
          Emits a json.dumps-ready result dict tagged with source=SeaBreeze-Inspector.
          
  - protocol: rpc
    path: "AltitudeHoldDriver.set_target_altitude"
    description:
      zh: >
          协议方法：设定绝对目标高度（米），返回是否被后端接受。
          
      en: >
          Protocol method: sets the absolute target altitude in metres and reports whether the backend accepted it.
          
  - protocol: rpc
    path: "AltitudeHoldDriver.settle"
    description:
      zh: >
          协议方法：按给定动力学步长运行 seconds 秒，返回含 altitude_m/std_m/n_steps 的稳态统计。
          
      en: >
          Protocol method: steps the dynamics for the given seconds and returns steady-state stats with altitude_m/std_m/n_steps.
          
---
