---
uid: 9e2c4b71
id: seabreeze-inspector.tests.integration-and-vision
parent: seabreeze-inspector.tests
tags: [pytest, integration]
name: {zh: "集成与视觉测试", en: "Integration & Vision Tests"}
description:
  zh: >
      跨模块集成：OmniSim 适配器、主控制器入口与缺陷检测的测试。
      
  en: >
      Cross-module integration: the OmniSim adapter, the main controller entry and defect detection.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.848Z"
fingerprint: 40bf4d40798c818a263237291fa0da7006fded182de1f574e97642f7f39de1ab
source:
  - path: "tests/test_omnisim_adapter.py"
  - path: "tests/test_integration.py"
  - path: "tests/test_main.py"
  - path: "tests/test_vision.py"
apis:
  - protocol: rpc
    path: "pytest:tests/test_main.py"
    description:
      zh: >
          主控制器用例（12 条）。
          
      en: >
          Main controller cases (12).
          
  - protocol: rpc
    path: "pytest:tests/test_omnisim_adapter.py"
    description:
      zh: >
          OmniSim 适配用例（9 条）。
          
      en: >
          OmniSim adapter cases (9).
          
  - protocol: rpc
    path: "pytest:tests/test_vision.py"
    description:
      zh: >
          视觉用例（4 条）。
          
      en: >
          Vision cases (4).
          
---
