---
uid: 7f1d8a36
id: seabreeze-inspector.backend.drone.tello-controller
parent: seabreeze-inspector.backend.drone
tags: [drone, tello, state-machine]
name: {zh: "Tello 状态机控制器", en: "Tello State-Machine Controller"}
description:
  zh: >
      以 FlightState 枚举（IDLE/CONNECTING/CONNECTED/TAKING_OFF/HOVERING/MOVING/LANDING/EMERGENCY/DISCONNECTED）与 TRANSITIONS 表驱动的 Tello 控制器。connect 经 djitellopy 连接；emergency 改为高空受控高速下降、仅当高度 ≤300cm 才硬停桨（P0-1 修复，kill 单独暴露硬停桨）；move_to 用位移指令执行相对移动；mock=True 时全程不触碰硬件。
      
  en: >
      Tello controller driven by the FlightState enum (IDLE/CONNECTING/CONNECTED/TAKING_OFF/HOVERING/MOVING/LANDING/EMERGENCY/DISCONNECTED) and a TRANSITIONS table. connect goes through djitellopy; emergency now performs a controlled high-speed descent and only cuts the motors below 300 cm (P0-1 fix, with kill exposed separately); move_to issues relative displacement commands; mock=True keeps the whole flow off hardware.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.799Z"
fingerprint: 3fab0867f0594a02b33e341537fb2018327b78701a617b4dbd5e86e2096570b9
source:
  - path: "backend/drone/tello_basic.py"
    line: 105
    end_line: 294
apis:
  - protocol: rpc
    path: "TelloController.connect"
    description:
      zh: >
          连接 Tello（mock 时直接成功），失败打印错误并回到 IDLE。
          
      en: >
          Connects to the Tello (immediate success when mocking); on failure it logs the error and returns to IDLE.
          
  - protocol: rpc
    path: "TelloController.takeoff"
    description:
      zh: >
          仅在 CONNECTED 状态允许起飞，成功转入 HOVERING，失败转入 EMERGENCY。
          
      en: >
          Allows takeoff only from CONNECTED, moving to HOVERING on success and EMERGENCY on failure.
          
  - protocol: rpc
    path: "TelloController.land"
    description:
      zh: >
          从 HOVERING/MOVING 降落，失败时触发紧急状态。
          
      en: >
          Lands from HOVERING/MOVING and triggers the emergency path if landing fails.
          
  - protocol: rpc
    path: "TelloController.emergency"
    description:
      zh: >
          受控紧急降落：高空只做最大速度下降，高度 ≤300cm 才调用 SDK emergency 停桨。
          
      en: >
          Controlled emergency descent: at altitude it only descends at maximum speed and calls the SDK emergency stop below 300 cm.
          
  - protocol: rpc
    path: "TelloController.move_to"
    description:
      zh: >
          按相对位移 (x,y,z) cm 移动，各轴超过 20cm 才下发指令，非飞行状态直接拒绝。
          
      en: >
          Moves by relative (x,y,z) in cm, issuing a command per axis only above 20 cm, and refuses outright when not flying.
          
---
