---
uid: d0c47e35
id: seabreeze-inspector.backend.simulation.pygame-loop
parent: seabreeze-inspector.backend.simulation
tags: [pygame, simulation, ui]
name: {zh: "Pygame 仿真主循环", en: "Pygame Sim Loop"}
description:
  zh: >
      Pygame 三栏仿真主循环：窗口/headless 两种初始化、配置回退装配仿真对象、键盘事件→目标与手臂、加速度限幅的一阶速度跟踪 + 风扰积分、调用 MissionController 完整流水线、电池消耗，以及中栏 3D 场景/左栏遥测/右栏摄像头与检测日志渲染。
      
  en: >
      Pygame three-column simulation loop: windowed and headless initialisation, object assembly from config with fallbacks, keyboard events to targets and arm, acceleration-limited first-order velocity tracking plus wind integration, MissionController pipeline invocation, battery drain, and rendering of the 3D scene, telemetry panel and camera/detection column.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.810Z"
fingerprint: 05f41f8c8f9b77d05d50bf89aca61a6d3af3b8f91d26f28a9cb1ce258614a526
source:
  - path: "backend/simulation/simulation.py"
    line: 56
    end_line: 836
deps:
  - kind: call
    to: seabreeze-inspector.backend.simulation.models
    from_api: "rpc:Simulation.step"
    to_api: "rpc:VirtualSensor.read_all"
    label: {zh: "取虚拟传感器读数送 mc", en: "Feeds sensor readings to mc"}
  - kind: call
    to: seabreeze-inspector.backend.simulation.renderer
    from_api: "rpc:Simulation._render"
    to_api: "rpc:draw_drone"
    label: {zh: "绘制场景与面板", en: "Draws scene and panels"}
  - kind: call
    to: seabreeze-inspector.backend.main.runtime-loop
    from_api: "rpc:Simulation.step"
    to_api: "rpc:MissionController.update_with_external_data"
    label: {zh: "跑完整的 EKF→安全→状态机流水线", en: "Runs EKF/safety/FSM pipeline"}
  - kind: call
    to: seabreeze-inspector.backend.main.mission-fsm
    from_api: "rpc:Simulation._handle_events"
    to_api: "rpc:MissionController.takeoff"
    label: {zh: "空格键触发起飞/降落状态", en: "Space triggers takeoff/land"}
  - kind: call
    to: seabreeze-inspector.backend.utils.units
    from_api: "rpc:Simulation.step"
    to_api: "rpc:m_to_cm"
    label: {zh: "仿真米制 → mc 厘米制", en: "Sim metres to mc cm"}
  - kind: call
    to: seabreeze-inspector.backend.utils.config-loader
    from_api: "rpc:Simulation.__init__"
    to_api: "rpc:ConfigLoader.load"
    label: {zh: "读取风/风机/电池/IMU 噪声参数", en: "Reads wind/turbine/IMU config"}
---
