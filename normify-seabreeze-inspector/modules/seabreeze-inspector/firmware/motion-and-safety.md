---
uid: f4b7d195
id: seabreeze-inspector.firmware.motion-and-safety
parent: seabreeze-inspector.firmware
tags: [arduino, safety]
name: {zh: "平滑运动与安全看门狗", en: "Smooth Motion & Watchdog"}
description:
  zh: >
      逐步逼近目标的平滑运动、命令超时看门狗（失联自停）与单通道舵机角度写入。
      
  en: >
      Step-wise smooth motion toward the target, a command-timeout watchdog that stops on link loss, and per-channel servo angle output.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.821Z"
fingerprint: 8a753e740394f9e799e3c216f19e8ba3b8d0690197a4c45c5e4537792ddd3e88
source:
  - path: "firmware/servo_controller/servo_controller.ino"
    line: 353
apis:
  - protocol: rpc
    path: "processSmoothMotion"
    description:
      zh: >
          平滑推进到目标角度。
          
      en: >
          Advances smoothly to the target angle.
          
  - protocol: rpc
    path: "checkWatchdog"
    description:
      zh: >
          命令超时保护。
          
      en: >
          Command-timeout protection.
          
  - protocol: rpc
    path: "setServoAngle"
    description:
      zh: >
          写单通道舵机角度。
          
      en: >
          Writes one servo channel angle.
          
---
