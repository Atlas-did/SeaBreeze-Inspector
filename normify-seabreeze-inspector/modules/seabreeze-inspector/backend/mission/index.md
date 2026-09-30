---
uid: b82f4601
id: seabreeze-inspector.backend.mission
parent: seabreeze-inspector.backend
tags: [mission, safety, fsm]
name: {zh: "任务与安全层", en: "Mission & Safety"}
description:
  zh: >
      任务语义与安全约束的单源权威：8 个任务状态枚举 + 合法转换表 + 历史别名收口，以及 WARN/LAND/KILL 三级失效保护监视器。仿真、主调度与 HTTP 桥都从这里取状态名与安全级别，不得自造状态字符串。
  en: >
      Single source of truth for mission semantics and safety limits: the eight mission states with their legal transition table and alias normalisation, plus the three-tier WARN/LAND/KILL failsafe monitor. Simulation, the main dispatcher and the HTTP bridge take state names and safety levels from here only.
revision: 87c9ca9d3bdad6782b1b05816e2dab9be91c40d9
updated_at: "2026-09-30T04:50:00Z"
fingerprint: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
source: []
---
