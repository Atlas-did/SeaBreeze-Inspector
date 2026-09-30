---
uid: 7e5b0d92
id: seabreeze-inspector.backend.simulation.altitude-driver
parent: seabreeze-inspector.backend.simulation
tags: [simulation, altitude-hold, experiment]
name: {zh: "仿真高度保持驱动", en: "Sim Altitude Driver"}
description:
  zh: >
      把 SimRuntime 包成 commands.AltitudeHoldDriver 的自家仿真实现：set_target_altitude 经 mc.takeoff 设定绝对高度，settle 按同一有效步长（clamp 20ms）步进并返回末 5 秒稳态高度均值/标准差，calm 开关决定静风还是 0.5m/s 顺风+阵风。
      
  en: >
      Wraps SimRuntime as the in-house commands.AltitudeHoldDriver: set_target_altitude sets an absolute height through mc.takeoff, settle steps with the same effective clamp (20 ms) and returns the last-five-second steady-state mean and standard deviation, and the calm switch selects zero wind or a 0.5 m/s tailwind with gusts.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.807Z"
fingerprint: 88002f9a51ef92f5390bf04d23f8e3d96a1d9d4dc1d50030efacf465ff872c98
source:
  - path: "backend/simulation/altitude_driver.py"
    line: 19
    end_line: 85
apis:
  - protocol: rpc
    path: "SimRuntimeDriver.set_target_altitude"
    description:
      zh: >
          把目标高度（米）转换为 mc.takeoff 的绝对高度指令并返回是否接受。
          
      en: >
          Converts the target height in metres into an absolute mc.takeoff command and reports acceptance.
          
  - protocol: rpc
    path: "SimRuntimeDriver.settle"
    description:
      zh: >
          按 dt 步进仿真 seconds 秒，返回末 5 秒稳态高度均值/标准差/末值与物理步数。
          
      en: >
          Steps the simulation for the requested seconds and returns the last-five-second mean, standard deviation, final value and physics step count.
          
  - protocol: rpc
    path: "SimRuntimeDriver.backend_name"
    description:
      zh: >
          后端标识固定为 sim，用于跨后端结果对比。
          
      en: >
          Reports the backend name sim for cross-backend comparison.
          
  - protocol: rpc
    path: "build_sim_driver"
    description:
      zh: >
          按仓库标准装配方式构建驱动：静风近零噪声或带风工况，用于 OmniSim 对比。
          
      en: >
          Builds the driver the way the repo standard does: calm near-zero-noise or windy, for OmniSim comparison.
          
deps:
  - kind: call
    to: seabreeze-inspector.backend.runtime.loop-core
    from_api: "rpc:SimRuntimeDriver.settle"
    to_api: "rpc:SimRuntime.step"
    label: {zh: "按有效步长步进单控制循环", en: "Steps runtime at effective dt"}
  - kind: call
    to: seabreeze-inspector.backend.main.mission-fsm.state-commands
    from_api: "rpc:SimRuntimeDriver.set_target_altitude"
    to_api: "rpc:MissionController.takeoff"
    label: {zh: "用起飞指令设定绝对目标高度", en: "Takeoff sets target height"}
  - kind: call
    to: seabreeze-inspector.backend.simulation.models.wind
    from_api: "rpc:build_sim_driver"
    to_api: "rpc:WindDisturbance.sample"
    label: {zh: "装配静风或带风工况", en: "Configures calm or windy case"}
---
