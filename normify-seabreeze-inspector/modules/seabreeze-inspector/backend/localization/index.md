---
uid: a1b2c3d4
id: seabreeze-inspector.backend.localization
parent: seabreeze-inspector.backend
tags: [localization, aruco, safety]
name: {zh: "外部定位源 / External Localization", en: "External Localization Sources"}
description:
  zh: >
      接在 EKF 之前的可信位置来源：统一观测契约（位置 cm/z-up + 单调时钟时间戳 + 0..1 质量分 + 有效期/质量阈值），以及真实 ArUco 解算与注入式真值两种实现。没有可用观测时一律返回 None —— 绝不返回占位坐标。真机上它是导航/巡检/返航闸门的唯一依据。
      
  en: >
      Trusted position sources feeding the EKF: one observation contract (cm/z-up position, monotonic timestamp, 0..1 quality, max-age/quality thresholds) plus real ArUco solving and an injected ground-truth implementation. No usable observation means None — never a placeholder position. On hardware it is the only basis for navigate/inspect/return gates.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:32:18.247Z"
fingerprint: pending
source: []
---
