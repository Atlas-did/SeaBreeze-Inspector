---
uid: 2c9e5b81
id: seabreeze-inspector.backend.drone.mock-tello
parent: seabreeze-inspector.backend.drone
tags: [drone, mock, test]
name: {zh: "Mock Tello 仿真机", en: "Mock Tello"}
description:
  zh: >
      离线测试用 Tello 替身：在内存中维护飞行标志、电量、高度、位置与姿态，实现连接/起降/紧急与各路位移指令，并提供电量、高度、姿态、位置与标准化状态字典读接口，使 runtime 与任务层无需真机即可跑通全流程。
      
  en: >
      Tello stand-in for offline testing: keeps flight flag, battery, height, position and attitude in memory, implements connect/takeoff/land/emergency and the per-axis move commands, and exposes battery, height, attitude, position and a normalized state-dict readout so runtime and mission code can run end to end without hardware.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.798Z"
fingerprint: 3fab0867f0594a02b33e341537fb2018327b78701a617b4dbd5e86e2096570b9
source:
  - path: "backend/drone/tello_basic.py"
    line: 31
    end_line: 102
apis:
  - protocol: rpc
    path: "MockTello.connect"
    description:
      zh: >
          模拟连接，恒返回 True。
          
      en: >
          Simulated connection, always returns True.
          
  - protocol: rpc
    path: "MockTello.takeoff"
    description:
      zh: >
          模拟起飞：置飞行标志并把高度设为 50cm。
          
      en: >
          Simulated takeoff: sets the flying flag and height to 50 cm.
          
  - protocol: rpc
    path: "MockTello.land"
    description:
      zh: >
          模拟降落：清除飞行标志并把高度归零。
          
      en: >
          Simulated landing: clears the flying flag and zeroes the height.
          
  - protocol: rpc
    path: "MockTello.move_forward"
    description:
      zh: >
          模拟前进，按距离累加位置（另有 back/left/right/up/down 同类接口）。
          
      en: >
          Simulated forward move accumulating position by distance (back/left/right/up/down share this shape).
          
  - protocol: rpc
    path: "MockTello.get_state_dict"
    description:
      zh: >
          返回 battery/height/position/attitude/is_flying 的标准状态字典。
          
      en: >
          Returns the standard state dict with battery/height/position/attitude/is_flying.
          
---
