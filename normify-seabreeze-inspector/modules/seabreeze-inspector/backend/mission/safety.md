---
uid: e24b8f17
id: seabreeze-inspector.backend.mission.safety
parent: seabreeze-inspector.backend.mission
tags: [safety, failsafe, battery]
name: {zh: "分层失效保护", en: "Failsafe Monitor"}
description:
  zh: >
      三级安全监控：按电池、姿态角、高度与心跳超时判定 OK/WARN/LAND/KILL（优先级 KILL > LAND > WARN），阈值可被配置覆盖。提供心跳、可恢复判定与手动重置——低电触发后不再永久锁死。
      
  en: >
      Three-tier safety monitoring: judges OK/WARN/LAND/KILL from battery, attitude, height and heartbeat timeout (priority KILL > LAND > WARN) with configurable thresholds. Provides heartbeat, recoverability check and manual reset, so a low-battery trip no longer locks the vehicle permanently.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.805Z"
fingerprint: 98816be132acc9ccd16829d6d74f5ef166be2f4771395a79036e45235a1195a4
source:
  - path: "backend/mission/safety.py"
    line: 20
    end_line: 161
apis:
  - protocol: rpc
    path: "FailsafeMonitor.check"
    description:
      zh: >
          按电池/姿态/高度/心跳返回最高级别的安全事件。
          
      en: >
          Returns the highest-severity safety event for battery, attitude, height and heartbeat.
          
  - protocol: rpc
    path: "FailsafeMonitor.heartbeat"
    description:
      zh: >
          更新心跳时间，调用方每帧调用以避免误报通信中断。
          
      en: >
          Refreshes the heartbeat timestamp; callers invoke it every frame to avoid false link-loss alarms.
          
  - protocol: rpc
    path: "FailsafeMonitor.can_recover"
    description:
      zh: >
          判断当前级别能否自动恢复（OK/WARN 可，KILL 需手动 reset）。
          
      en: >
          Reports whether the current level can auto-recover; KILL needs a manual reset.
          
  - protocol: rpc
    path: "FailsafeMonitor.reset"
    description:
      zh: >
          重置监控状态（KILL 后恢复）。
          
      en: >
          Resets monitor state, recovering from a KILL trip.
          
  - protocol: rpc
    path: "SafetyLevel"
    description:
      zh: >
          安全级别枚举 OK/WARN/LAND/KILL。
          
      en: >
          The OK/WARN/LAND/KILL safety-level enum.
          
---
