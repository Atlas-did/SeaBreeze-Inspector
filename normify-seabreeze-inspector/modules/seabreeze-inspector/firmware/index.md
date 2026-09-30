---
uid: 3f7a2c98
id: seabreeze-inspector.firmware
parent: seabreeze-inspector
tags: [arduino, firmware, servo]
name: {zh: "Arduino 舵机固件", en: "Arduino Servo Firmware"}
description:
  zh: >
      Arduino Nano（CH340）+ PCA9685 舵机驱动固件：解析串口单字符命令，执行 3-DOF 机械臂的角度控制（绝对/相对/归位/停止）并支持状态查询，是机械臂从仿真走向真机的执行端。
      
  en: >
      Arduino Nano (CH340) + PCA9685 servo-driver firmware: parses single-character serial commands to drive the 3-DOF arm (absolute, relative, home, stop) and answer state queries; the actuator end that takes the arm from simulation to real hardware.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.821Z"
fingerprint: 8a753e740394f9e799e3c216f19e8ba3b8d0690197a4c45c5e4537792ddd3e88
source:
  - path: "firmware/servo_controller/servo_controller.ino"
    line: 1
    end_line: 419
---
