---
uid: d0e1f2a3
id: seabreeze-inspector.tooling.hil-smoke
parent: seabreeze-inspector.tooling
tags: [hil, smoke, preflight]
name: {zh: "HIL 冒烟检查", en: "HIL Smoke Check"}
description:
  zh: >
      上机前不接真机也能跑的链路自检：以假 Tello 替换底层，验证速度指令确实走到 send_rc_control、停桨闸门在高度未知时拒绝、以及关键状态字段可读。它是拆桨桌面测试的离线前置，不代替真机验证。
      
  en: >
      A pre-flight link check that runs without hardware: a fake Tello substitutes the SDK to prove velocity commands really reach send_rc_control, that the cutoff gate refuses when height is unknown, and that key state fields are readable. An offline prelude to the props-off bench test, not a substitute for it.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:32:36.118Z"
fingerprint: 5a3c42e4c571ebac0c1e338447cfd9e8bb65dc52b9ced78dcf0c19c597758fe7
source:
  - path: "scripts/hil_smoke.py"
apis:
  - protocol: rpc
    path: "hil_smoke.main"
    description:
      zh: >
          离线跑一遍关键链路并给出通过/失败。
          
      en: >
          Runs the critical path offline and reports pass/fail.
          
---
