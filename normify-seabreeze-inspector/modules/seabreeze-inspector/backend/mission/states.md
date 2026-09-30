---
uid: 70a5d9ce
id: seabreeze-inspector.backend.mission.states
parent: seabreeze-inspector.backend.mission
tags: [fsm, states, enum]
name: {zh: "任务状态与转换表", en: "Mission States & Transitions"}
description:
  zh: >
      全系统唯一的任务状态定义：IDLE/TAKEOFF/HOVERING/NAVIGATE/INSPECT/RETURN/LAND/EMERGENCY 枚举、合法转换表，以及把 TAKING_OFF/RETURNING/LANDING/HOVER 等历史别名规范化、拒绝未知状态名的收口函数。非法转换会显式抛错而不静默。
      
  en: >
      The system's only mission-state definition: the IDLE/TAKEOFF/HOVERING/NAVIGATE/INSPECT/RETURN/LAND/EMERGENCY enum, the legal transition table, and normalisers that fold historical aliases (TAKING_OFF/RETURNING/LANDING/HOVER) while rejecting unknown names. Illegal transitions raise instead of passing silently.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.805Z"
fingerprint: 5e2590680112a02bb86bd05acd2704fa37157cf8e23562ca526ecc7411ac2197
source:
  - path: "backend/mission/states.py"
    line: 19
    end_line: 120
apis:
  - protocol: rpc
    path: "normalize_state_name"
    description:
      zh: >
          把任意历史状态名规范化为权威名，非法名抛 ValueError。
          
      en: >
          Normalises any historical state name to the authoritative name, raising ValueError for unknown ones.
          
  - protocol: rpc
    path: "to_state"
    description:
      zh: >
          字符串或枚举 → MissionState 枚举（别名自动规范化）。
          
      en: >
          Converts a string or enum to a MissionState enum, folding aliases.
          
  - protocol: rpc
    path: "can_transition"
    description:
      zh: >
          判断状态转换是否在合法转换表中。
          
      en: >
          Checks whether a transition is legal in the transition table.
          
  - protocol: rpc
    path: "transition"
    description:
      zh: >
          执行状态转换，非法时抛异常并带理由。
          
      en: >
          Performs a transition, raising with the reason when illegal.
          
  - protocol: rpc
    path: "is_valid_state"
    description:
      zh: >
          是否为合法任务状态（含历史别名）。
          
      en: >
          Reports whether a name is a valid mission state, aliases included.
          
---
