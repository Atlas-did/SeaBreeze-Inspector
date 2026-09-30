---
uid: 8b6d1e45
id: seabreeze-inspector.frontend
parent: seabreeze-inspector
tags: [tkinter, ui]
name: {zh: "地面站面板", en: "Ground-Station Dashboard"}
description:
  zh: >
      Tkinter 地面站监控面板：连接消息总线、轮询遥测与视频帧，显示飞行状态与检测结果，并可直接下发指令。按 README 定位为只读监控通道（主演示通道是 Web 3D）。
      
  en: >
      Tkinter ground-station monitor: connects to the message bus, polls telemetry and video frames, shows flight state and detections, and can issue commands. The README positions it as the monitor-only channel; the main demo channel is Web 3D.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.822Z"
fingerprint: b5fdab40d04679955e757068fefc68e43919c277b965297981d0bd66c813a6da
source:
  - path: "frontend/dashboard.py"
    line: 1
    end_line: 195
apis:
  - protocol: rpc
    path: "Dashboard.connect_bus"
    description:
      zh: >
          连接后端消息总线。
          
      en: >
          Connects to the backend message bus.
          
  - protocol: rpc
    path: "Dashboard.register_callback"
    description:
      zh: >
          注册遥测/视频回调。
          
      en: >
          Registers telemetry/video callbacks.
          
  - protocol: rpc
    path: "Dashboard.update"
    description:
      zh: >
          刷新遥测显示。
          
      en: >
          Refreshes the telemetry display.
          
  - protocol: rpc
    path: "Dashboard.update_video"
    description:
      zh: >
          刷新视频画面。
          
      en: >
          Refreshes the video frame.
          
  - protocol: rpc
    path: "Dashboard.run"
    description:
      zh: >
          进入 Tkinter 主循环。
          
      en: >
          Enters the Tkinter main loop.
          
---
