---
uid: 7a5c9e03
id: seabreeze-inspector.backend.runtime.loop-core
parent: seabreeze-inspector.backend.runtime
tags: [runtime, control-loop]
name: {zh: "运行时主循环", en: "Runtime Loop Core"}
description:
  zh: >
      SimRuntime 本体：单控制循环的装配、日志缓冲与 step() 推进（不依赖 Pygame 的 headless 运行路径）。
      
  en: >
      The SimRuntime class itself: single control-loop assembly, log buffering and the step() advance on the Pygame-free headless path.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.806Z"
fingerprint: 8ef7ce05bb012abe7799f3468ca9c40cf70923a5e62be55163844b49cec89f1e
source:
  - path: "backend/runtime/loop.py"
    line: 44
    end_line: 200
apis:
  - protocol: rpc
    path: "SimRuntime.step"
    description:
      zh: >
          推进一个控制周期。
          
      en: >
          Advances one control cycle.
          
  - protocol: rpc
    path: "SimRuntime._add_log"
    description:
      zh: >
          写入一帧日志。
          
      en: >
          Appends a log frame.
          
---
