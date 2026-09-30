---
uid: 6a2f8c03
id: seabreeze-inspector.firmware.serial-protocol
parent: seabreeze-inspector.firmware
tags: [arduino, protocol]
name: {zh: "串口协议解析", en: "Serial Protocol Parsing"}
description:
  zh: >
      单字符命令协议的接收、解析与分发：A 绝对角度、R 相对增量、H 归位、Q 查询、S 停止、? 帮助。
      
  en: >
      Reception, parsing and dispatch of the single-character command protocol: A absolute, R relative, H home, Q query, S stop, ? help.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.822Z"
fingerprint: 8a753e740394f9e799e3c216f19e8ba3b8d0690197a4c45c5e4537792ddd3e88
source:
  - path: "firmware/servo_controller/servo_controller.ino"
    line: 186
    end_line: 352
apis:
  - protocol: rpc
    path: "processSerialInput"
    description:
      zh: >
          读串口并组帧。
          
      en: >
          Reads and frames serial input.
          
  - protocol: rpc
    path: "parseAndExecute"
    description:
      zh: >
          解析并分发命令。
          
      en: >
          Parses and dispatches a command.
          
  - protocol: rpc
    path: "handleAbsoluteMode"
    description:
      zh: >
          绝对角度模式。
          
      en: >
          Absolute-angle mode.
          
  - protocol: rpc
    path: "handleRelativeMode"
    description:
      zh: >
          相对增量模式。
          
      en: >
          Relative-increment mode.
          
---
