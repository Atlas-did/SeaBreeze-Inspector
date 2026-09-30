---
uid: 6c0f3a92
id: seabreeze-inspector.backend.runtime
parent: seabreeze-inspector.backend
tags: [runtime, control-loop, simulation]
name: {zh: "单仿真控制循环", en: "Sim Runtime Loop"}
description:
  zh: >
      全仿真共用的单控制循环：按键→mc 状态转换、位置/速度/加速度级联控制驱动物理、风扰采样、传感器注入 MissionController 完整流水线（EKF→安全→状态机→控制器→日志→总线）、电池消耗与触地判定。任务状态只读 mc.state，绝不自行维护第二套。
      
  en: >
      The single control loop all simulations share: keys to mc state transitions, cascaded position/velocity/acceleration control driving physics, wind sampling, sensor injection into MissionController's full pipeline (EKF, safety, state machine, controller, log, bus), battery drain and touchdown detection. Task state is read-only from mc.state, never a second copy.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.806Z"
fingerprint: 8ef7ce05bb012abe7799f3468ca9c40cf70923a5e62be55163844b49cec89f1e
source:
  - path: "backend/runtime/loop.py"
    line: 25
    end_line: 309
deps:
  - kind: call
    to: seabreeze-inspector.backend.simulation.drone-adapter
    from_api: "rpc:SimRuntime.__init__"
    label: {zh: "用适配器替换 mc 的 MockTello", en: "Replaces mc's mock drone"}
  - kind: call
    to: seabreeze-inspector.backend.main.runtime-loop
    from_api: "rpc:SimRuntime.step"
    to_api: "rpc:MissionController.update_with_external_data"
    label: {zh: "注入传感器并跑完整控制流水线", en: "Injects sensors, runs pipeline"}
  - kind: call
    to: seabreeze-inspector.backend.main.mission-fsm
    from_api: "rpc:SimRuntime._process_keys"
    to_api: "rpc:MissionController.request_state"
    label: {zh: "按键触发状态转换（经转换表校验）", en: "Keys trigger state transitions"}
  - kind: call
    to: seabreeze-inspector.backend.utils.units
    from_api: "rpc:SimRuntime.step"
    to_api: "rpc:m_to_cm"
    label: {zh: "仿真米制 ↔ 后端厘米制", en: "Sim metres to backend cm"}
---
