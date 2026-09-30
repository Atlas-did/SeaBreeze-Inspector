---
uid: 8d4e6b05
id: seabreeze-inspector.tests.flight-commands
parent: seabreeze-inspector.tests
tags: [pytest, drone]
name: {zh: "飞控指令测试", en: "Flight Command Tests"}
description:
  zh: >
      飞行指令序列化与 MockTello 行为测试。
      
  en: >
      Flight-command serialisation and MockTello behaviour tests.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.840Z"
fingerprint: fe83cda2854305b5bd2995acfb3bcb7a3574e868bc4921e43377ec2868dddba1
source:
  - path: "tests/test_commands.py"
  - path: "tests/test_tello_mock.py"
apis:
  - protocol: rpc
    path: "pytest:tests/test_commands.py"
    description:
      zh: >
          指令用例（6 条）。
          
      en: >
          Command cases (6).
          
  - protocol: rpc
    path: "pytest:tests/test_tello_mock.py"
    description:
      zh: >
          MockTello 用例（4 条）。
          
      en: >
          MockTello cases (4).
          
---
