---
uid: 6e4b9c82
id: seabreeze-inspector.backend.main.runtime-loop.start-and-frame
parent: seabreeze-inspector.backend.main.runtime-loop
tags: [runtime, control-loop]
name: {zh: "主循环启动与单帧推进", en: "Loop Start & Frame Step"}
description:
  zh: >
      固定周期主循环的启动（起日志/视频、真机失败降级为 mock）与单帧控制逻辑 _update()。
      
  en: >
      Starting the fixed-period main loop (begins logging/video, falls back to mock if the real link fails) and the single-frame control logic in _update().
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.804Z"
fingerprint: 9d1343fe24eaed513fb689bc1c42fdc8ab476655d66ed0c72ac05e60699704d7
source:
  - path: "backend/main.py"
    line: 177
    end_line: 259
apis:
  - protocol: rpc
    path: "MissionController.start"
    description:
      zh: >
          启动主循环。
          
      en: >
          Starts the main loop.
          
  - protocol: rpc
    path: "MissionController._update"
    description:
      zh: >
          单帧控制循环。
          
      en: >
          Single control frame.
          
---
