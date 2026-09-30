---
uid: e5a9c260
id: seabreeze-inspector.tests.infrastructure
parent: seabreeze-inspector.tests
tags: [pytest, infrastructure]
name: {zh: "基础设施测试", en: "Infrastructure Tests"}
description:
  zh: >
      消息总线（发布订阅）、配置加载、运行时循环与 HAL 契约的测试——HAL 契约用例最多（17 条）。
      
  en: >
      Tests for the message bus (pub-sub), config loading, the runtime loop and the HAL contract; the HAL contract is the largest set at 17 cases.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.847Z"
fingerprint: d5f03440d18bf545237db11343dc5f51ede0fbef37f8358424f9e755669f8ac5
source:
  - path: "tests/test_bus.py"
  - path: "tests/test_bus_pubsub.py"
  - path: "tests/test_config.py"
  - path: "tests/test_runtime.py"
  - path: "tests/test_hal_contract.py"
apis:
  - protocol: rpc
    path: "pytest:tests/test_hal_contract.py"
    description:
      zh: >
          HAL 契约用例（17 条）。
          
      en: >
          HAL contract cases (17).
          
  - protocol: rpc
    path: "pytest:tests/test_bus_pubsub.py"
    description:
      zh: >
          总线发布订阅用例（8 条）。
          
      en: >
          Bus pub-sub cases (8).
          
  - protocol: rpc
    path: "pytest:tests/test_runtime.py"
    description:
      zh: >
          运行时用例（8 条）。
          
      en: >
          Runtime cases (8).
          
  - protocol: rpc
    path: "pytest:tests/test_config.py"
    description:
      zh: >
          配置用例（4 条）。
          
      en: >
          Config cases (4).
          
---
