---
uid: 2b9e4c07
id: seabreeze-inspector.verification.hover-wind
parent: seabreeze-inspector.verification
tags: [verification, hover]
name: {zh: "悬停精度与风扰注入", en: "Hover Accuracy & Wind Injection"}
description:
  zh: >
      3D 悬停精度测量（对应 hover_*_trace.csv）与向仿真桥注入指定风速的风扰注入器。
      
  en: >
      3D hover-accuracy measurement (the hover_*_trace.csv artefacts) and the injector that pushes a given wind speed into the bridge.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.858Z"
fingerprint: d55e82920e0a0b279961b486625cb319ed83f70be808aaf79f71f079fb392dea
source:
  - path: "verify_scripts/measure_hover_3d.py"
  - path: "verify_scripts/wind_gust_injector.py"
apis:
  - protocol: rpc
    path: "measure_hover_3d.main"
    description:
      zh: >
          悬停精度测量。
          
      en: >
          Hover-accuracy measurement.
          
  - protocol: rpc
    path: "wind_gust_injector.force_for_speed"
    description:
      zh: >
          风速→力换算。
          
      en: >
          Speed-to-force conversion.
          
  - protocol: rpc
    path: "wind_gust_injector.main"
    description:
      zh: >
          注入入口。
          
      en: >
          Injection entry.
          
---
