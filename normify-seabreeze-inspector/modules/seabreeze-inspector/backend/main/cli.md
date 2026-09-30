---
uid: f8e1247b
id: seabreeze-inspector.backend.main.cli
parent: seabreeze-inspector.backend.main
tags: [cli, main, entrypoint]
name: {zh: "命令行入口", en: "CLI Entry"}
description:
  zh: >
      python backend/main.py 的命令行入口：解析 --mode(simulation|hardware)/--target x,y,z(cm)/--mock，构造 MissionController 并设目标，捕获 Ctrl+C 与异常后走紧急降落，最后在 finally 中调用 stop() 保证优雅关闭。另导出 MainController 兼容别名。
      
  en: >
      CLI entry for python backend/main.py: parses --mode (simulation or hardware), --target x,y,z in cm and --mock, builds MissionController and sets the target, turns Ctrl+C and exceptions into an emergency descent, and always calls stop() in finally for a graceful shutdown. Also exports the MainController compatibility alias.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.800Z"
fingerprint: 9d1343fe24eaed513fb689bc1c42fdc8ab476655d66ed0c72ac05e60699704d7
source:
  - path: "backend/main.py"
    line: 763
    end_line: 812
apis:
  - protocol: rpc
    path: "backend.main.main"
    description:
      zh: >
          命令行入口：解析参数、构造控制器、设目标并启动，异常路径触发紧急降落。
          
      en: >
          CLI entry: parses arguments, builds the controller, sets the target and starts, triggering an emergency descent on the exception path.
          
  - protocol: rpc
    path: "backend.main.MainController"
    description:
      zh: >
          MissionController 的兼容别名（角色文档使用的旧名）。
          
      en: >
          Compatibility alias for MissionController used by older role documents.
          
deps:
  - kind: call
    to: seabreeze-inspector.backend.main.mission-controller.assembly
    from_api: "rpc:backend.main.main"
    to_api: "rpc:MissionController.__init__"
    label: {zh: "按命令行参数构造控制器", en: "Builds controller from CLI"}
---
