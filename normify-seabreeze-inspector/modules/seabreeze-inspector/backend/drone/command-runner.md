---
uid: d8c2e741
id: seabreeze-inspector.backend.drone.command-runner
parent: seabreeze-inspector.backend.drone
tags: [drone, runner]
name: {zh: "单指令执行器", en: "Command Runner"}
description:
  zh: >
      面向任意 DroneInterface 的指令调度：execute_instant 用反射调用 connect/takeoff/land/emergency/kill/hover/move_to 并回读后端状态（不做动力学 settle，因为真机指令异步）；run_altitude_hold 在 AltitudeHoldDriver 上设定目标高度并步进 settle_s 秒，取稳态均值算误差，并在指令被拒（如 bridge 409 busy）时直接返回 accepted=False，不产出误导性的 settled=True 证据。
      
  en: >
      Command dispatch over any DroneInterface: execute_instant reflectively calls connect/takeoff/land/emergency/kill/hover/move_to and reads back the backend state (no settling, since real commands are asynchronous); run_altitude_hold sets an absolute altitude on an AltitudeHoldDriver, steps settle_s seconds and derives the error from the steady-state mean, returning accepted=False outright when the command is rejected (e.g. bridge 409 busy) instead of emitting misleading settled=True evidence.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.797Z"
fingerprint: 5e3c7c5afd57aac0f007017b0a1a2e78de2213a7a8fa0f503a746a267685c02b
source:
  - path: "backend/drone/commands.py"
    line: 118
    end_line: 227
apis:
  - protocol: rpc
    path: "execute_instant"
    description:
      zh: >
          执行一次性指令并返回 CommandResult；不支持的 op 抛 ValueError，缺少方法抛 AttributeError。
          
      en: >
          Executes a one-shot command and returns a CommandResult; unknown ops raise ValueError and missing methods raise AttributeError.
          
  - protocol: rpc
    path: "run_altitude_hold"
    description:
      zh: >
          通用高度保持运行器：设定目标高度、按 dt 步进 settle_s 秒、输出统一稳态误差结果，并按 seed 固定随机性以便复现。
          
      en: >
          Generic altitude-hold runner: sets the target, steps settle_s seconds at dt, and reports the unified steady-state result, seeding the RNG for reproducibility.
          
---
