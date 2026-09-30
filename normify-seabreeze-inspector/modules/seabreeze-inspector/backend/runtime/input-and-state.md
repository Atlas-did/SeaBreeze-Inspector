---
uid: e6d2b174
id: seabreeze-inspector.backend.runtime.input-and-state
parent: seabreeze-inspector.backend.runtime
tags: [runtime, input]
name: {zh: "键盘输入与状态更新", en: "Input & State Update"}
description:
  zh: >
      headless 模式下的按键扫描与状态汇总（无窗口时接收外部注入的控制输入）。
      
  en: >
      Key scanning and state aggregation in headless mode, where control input is injected externally instead of coming from a window.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.806Z"
fingerprint: 8ef7ce05bb012abe7799f3468ca9c40cf70923a5e62be55163844b49cec89f1e
source:
  - path: "backend/runtime/loop.py"
    line: 201
apis:
  - protocol: rpc
    path: "SimRuntime._process_keys"
    description:
      zh: >
          处理按键输入。
          
      en: >
          Processes key input.
          
  - protocol: rpc
    path: "SimRuntime._update_state"
    description:
      zh: >
          汇总仿真状态。
          
      en: >
          Aggregates simulation state.
          
---
