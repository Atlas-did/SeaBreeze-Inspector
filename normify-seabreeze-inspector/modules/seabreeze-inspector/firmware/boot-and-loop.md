---
uid: e91d4b62
id: seabreeze-inspector.firmware.boot-and-loop
parent: seabreeze-inspector.firmware
tags: [arduino, firmware]
name: {zh: "固件初始化与主循环", en: "Firmware Boot & Loop"}
description:
  zh: >
      全局状态（当前/目标角度、串口缓冲、运动标志）与 setup()/loop() 骨架：舵机与 PCA9685 初始化、主循环轮询。
      
  en: >
      Global state (current/target angles, serial buffer, moving flag) plus the setup()/loop() skeleton: servo and PCA9685 initialisation and main-loop polling.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.821Z"
fingerprint: 8a753e740394f9e799e3c216f19e8ba3b8d0690197a4c45c5e4537792ddd3e88
source:
  - path: "firmware/servo_controller/servo_controller.ino"
    line: 104
    end_line: 185
apis:
  - protocol: rpc
    path: "setup"
    description:
      zh: >
          初始化舵机与串口。
          
      en: >
          Initialises servos and serial.
          
  - protocol: rpc
    path: "loop"
    description:
      zh: >
          主循环。
          
      en: >
          Main loop.
          
---
