---
uid: d4e5f6a7
id: seabreeze-inspector.backend.localization.ground-truth
parent: seabreeze-inspector.backend.localization
tags: [localization, simulation, test-double]
name: {zh: "注入式真值定位源", en: "Injected Ground-Truth Source"}
description:
  zh: >
      给仿真/HIL 用的真值定位源：由外部（仿真器或测试）注入位置，自己只负责包装成符合契约的观测（带时间戳与质量）。它把"定位可用"这件事从具体算法解耦，使状态闸门与 EKF 接线能在没有相机的情况下被确定性地测试。
      
  en: >
      A ground-truth source for simulation/HIL: position is injected externally (simulator or test) and merely wrapped into a contract-conforming observation with timestamp and quality. It decouples "localization available" from any specific algorithm, making the gates and EKF wiring testable without a camera.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:32:18.249Z"
fingerprint: 4ccaf4bd161b16ac0a094792a186aaa6ed449b1a7e82589846ef5949e8c1e5b4
source:
  - path: "backend/localization/ground_truth_source.py"
    line: 1
    end_line: 62
apis:
  - protocol: rpc
    path: "GroundTruthLocalizationSource.read"
    description:
      zh: >
          返回最新注入位置包装成的观测（无注入则 None）。
          
      en: >
          Returns the latest injected position as an observation (None when nothing injected).
          
---
