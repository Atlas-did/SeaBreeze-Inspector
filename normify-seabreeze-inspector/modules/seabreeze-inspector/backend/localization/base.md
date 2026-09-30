---
uid: b2c3d4e5
id: seabreeze-inspector.backend.localization.base
parent: seabreeze-inspector.backend.localization
tags: [localization, contract]
name: {zh: "观测契约与可用性判定", en: "Observation Contract & Usability"}
description:
  zh: >
      外部定位的统一契约与判定：LocalizationObservation（位置/时间戳/质量/来源，只规范化不抛异常）与 LocalizationSource 抽象基类；is_finite/is_usable/age 三个判定把维度错误、nan/inf、质量不足与过期统一收口为"不可用"，让"坏观测"与"没有观测"在类型上可区分。阈值 MAX_AGE_S=0.3、MIN_QUALITY=0.3 依据实测残差给出。
      
  en: >
      The localization contract: LocalizationObservation (position/timestamp/quality/source, normalising rather than raising) and the LocalizationSource ABC; is_finite/is_usable/age collapse bad dimensions, nan/inf, low quality and staleness into "unusable", keeping "bad observation" distinct from "no observation". Thresholds MAX_AGE_S=0.3 and MIN_QUALITY=0.3 come from measured residuals.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:32:18.248Z"
fingerprint: e157d48976342e08c3dbb1e1969fa8d0ab494443fc9aed6fa2ace26e077ca855
source:
  - path: "backend/localization/base.py"
    line: 1
    end_line: 103
apis:
  - protocol: rpc
    path: "LocalizationObservation.is_usable"
    description:
      zh: >
          维度/有限性 + 质量分 + 有效期三者全过才算可用。
          
      en: >
          Usable only when dimensions/finiteness, quality and age all pass.
          
  - protocol: rpc
    path: "LocalizationObservation.age"
    description:
      zh: >
          观测年龄（秒），未来时间戳会给出负值从而被判不可用。
          
      en: >
          Observation age in seconds; future timestamps go negative and are rejected.
          
  - protocol: rpc
    path: "LocalizationSource.read"
    description:
      zh: >
          读一次观测；无可用观测返回 None（禁止占位坐标）。
          
      en: >
          Reads one observation, returning None when unusable (no placeholder positions).
          
---
