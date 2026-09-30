---
uid: f2a7b490
id: seabreeze-inspector.backend.arm.controller
parent: seabreeze-inspector.backend.arm
tags: [arm, serial]
name: {zh: "机械臂串口控制器", en: "Arm Serial Controller"}
description:
  zh: >
      经 pyserial 与 Arduino Nano 通信的机械臂控制器：默认串口与波特率取自 arm_config.yaml 的 hardware.serial；set_joint_angles 发送 A<base>,<shoulder>,<elbow> 指令，并按固件 50°/s 的平滑速度估算等待时间；move_to_position 先 IK 再下发角度；get_current_angles 发 Q 并解析 A:90,S:45,E:30；reset 归位到 (90,90,90)。pyserial 缺失或未连接时降级为模拟模式。
      
  en: >
      Arm controller talking to an Arduino Nano over pyserial: the port and baud rate default to hardware.serial in arm_config.yaml; set_joint_angles sends A<base>,<shoulder>,<elbow> and waits based on the firmware's fixed 50 deg/s smoothing; move_to_position solves IK before commanding angles; get_current_angles sends Q and parses A:90,S:45,E:30; reset homes to (90,90,90). Missing pyserial or an unopened port degrades to simulated mode.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.793Z"
fingerprint: 393dee82392e0bddafaf2ac203694a5a4ef38e749924ef262b40a6822ad12fe2
source:
  - path: "backend/arm/arm_controller.py"
    line: 28
    end_line: 114
apis:
  - protocol: rpc
    path: "ArmController.connect"
    description:
      zh: >
          打开串口并等待 2s 让 Arduino 复位；缺库或异常时打印原因并返回 False。
          
      en: >
          Opens the serial port and waits 2 s for the Arduino to reset; missing library or errors are logged and return False.
          
  - protocol: rpc
    path: "ArmController.set_joint_angles"
    description:
      zh: >
          发送三关节角度指令，并按最大角度差 × 20ms/度 估算等待时间后更新当前角度缓存。
          
      en: >
          Sends the three joint angles, waiting max-angle-delta x 20 ms/deg before updating the cached current angles.
          
  - protocol: rpc
    path: "ArmController.move_to_position"
    description:
      zh: >
          先 IK 求解 (x,y,z) 得到关节角，再调用 set_joint_angles 下发。
          
      en: >
          Solves IK for (x,y,z) and then dispatches the resulting angles via set_joint_angles.
          
  - protocol: rpc
    path: "ArmController.get_current_angles"
    description:
      zh: >
          发送 Q 查询并解析 A:90,S:45,E:30 回复，失败时返回缓存的当前角度。
          
      en: >
          Sends Q and parses the A:90,S:45,E:30 reply, returning the cached angles on failure.
          
  - protocol: rpc
    path: "ArmController.reset"
    description:
      zh: >
          归位到 (90,90,90)。
          
      en: >
          Homes the arm to (90,90,90).
          
---
