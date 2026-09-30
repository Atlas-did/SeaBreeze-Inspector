---
uid: 3d6a0c88
id: seabreeze-inspector.backend.utils.units
parent: seabreeze-inspector.backend.utils
tags: [units, coordinates, convert]
name: {zh: "单位与坐标转换", en: "Units & Frames"}
description:
  zh: >
      全项目唯一的单位与坐标系转换点：cm↔m↔mm、m/s↔cm/s、m/s²↔cm/s²，以及后端 z-up(cm) 与 Web three.js y-up(m) 的边界映射。约定跨模块转换必须走这里，禁止手工乘除 100（发现即 code review 打回）。
      
  en: >
      The project's only unit and coordinate-frame conversion point: cm↔m↔mm, m/s↔cm/s, m/s²↔cm/s², plus the boundary mapping between backend z-up (cm) and web three.js y-up (m). Cross-module conversion must go through here; hand-rolled x100 is rejected in review.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.813Z"
fingerprint: 8d72d85414130ba5e5b385ba776cc3d40ccf38416d4c19183a5141df03f4b40c
source:
  - path: "backend/utils/units.py"
    line: 27
    end_line: 119
apis:
  - protocol: rpc
    path: "m_to_cm"
    description:
      zh: >
          米 → 厘米（仿真物理到后端的长度转换）。
          
      en: >
          Metres to centimetres, converting simulation physics to backend units.
          
  - protocol: rpc
    path: "cm_to_m"
    description:
      zh: >
          厘米 → 米。
          
      en: >
          Centimetres to metres.
          
  - protocol: rpc
    path: "mps2_to_cmps2"
    description:
      zh: >
          m/s² → cm/s²（IMU 加速度与扰动估计单位）。
          
      en: >
          m/s² to cm/s² for IMU acceleration and disturbance estimates.
          
  - protocol: rpc
    path: "zup_cm_to_yup_m"
    description:
      zh: >
          后端位置 (cm, z-up) → Web 位置 (m, y-up)，api 层唯一序列化转换点。
          
      en: >
          Backend position (cm, z-up) to web position (m, y-up); the single serialisation conversion in the api layer.
          
  - protocol: rpc
    path: "yup_m_to_zup_cm"
    description:
      zh: >
          Web 位置 (m, y-up) → 后端位置 (cm, z-up)。
          
      en: >
          Web position (m, y-up) to backend position (cm, z-up).
          
---
