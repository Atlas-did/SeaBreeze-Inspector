---
uid: a13c95e8
id: seabreeze-inspector.backend.simulation.drone-adapter
parent: seabreeze-inspector.backend.simulation
tags: [hal, adapter, simulation]
name: {zh: "仿真无人机适配器", en: "Sim Drone Adapter"}
description:
  zh: >
      把 Quadrotor3D 适配成 DroneInterface：起降/紧急为延迟语义（保持 is_flying 直到 SimRuntime 探到触地再 mark_landed），move_to 按 cm 偏移设置目标，hover 清零速度，姿态从弧度转度；另提供电量设置与目标位姿查询。
      
  en: >
      Adapts Quadrotor3D to DroneInterface: land/emergency use deferred semantics (is_flying stays true until SimRuntime sees touchdown and calls mark_landed), move_to sets the target from a cm offset, hover zeroes velocity and attitude converts radians to degrees; also exposes battery set and target queries.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.807Z"
fingerprint: 4ec499d6d839de295b55be7a74d505e049ed0baf5488d6595e1fe33ffd271252
source:
  - path: "backend/simulation/drone_adapter.py"
    line: 13
    end_line: 130
apis:
  - protocol: rpc
    path: "SimDroneAdapter.takeoff"
    description:
      zh: >
          起飞：置 is_flying 并把目标高度设为 1.2m。
          
      en: >
          Takes off: sets is_flying and targets a 1.2 m hover height.
          
  - protocol: rpc
    path: "SimDroneAdapter.land"
    description:
      zh: >
          请求降落（延迟语义：等 SimRuntime 判定触地后才置 is_flying=False）。
          
      en: >
          Requests landing with deferred semantics: is_flying clears only after SimRuntime detects touchdown.
          
  - protocol: rpc
    path: "SimDroneAdapter.emergency"
    description:
      zh: >
          请求受控紧急下降（不清零速度，交给级联控制驱动物理下降）。
          
      en: >
          Requests a controlled emergency descent, leaving velocity to the cascaded controller.
          
  - protocol: rpc
    path: "SimDroneAdapter.mark_landed"
    description:
      zh: >
          物理触地回调：清 flying/landing/emergency 标志，让 mc 能回到 IDLE。
          
      en: >
          Touchdown callback: clears the flying, landing and emergency flags so mc can return to IDLE.
          
  - protocol: rpc
    path: "SimDroneAdapter.move_to"
    description:
      zh: >
          按 cm 相对偏移设置仿真目标位置。
          
      en: >
          Sets the simulated target position from a centimetre relative offset.
          
deps:
  - kind: reference
    to: seabreeze-inspector.backend.hal
    from_api: "rpc:SimDroneAdapter.emergency"
    to_api: "rpc:DroneInterface.emergency"
    label: {zh: "实现 HAL 无人机契约（紧急语义一致）", en: "Implements HAL drone contract"}
---
