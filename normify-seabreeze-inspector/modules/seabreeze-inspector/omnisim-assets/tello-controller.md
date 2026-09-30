---
uid: e4b2f708
id: seabreeze-inspector.omnisim-assets.tello-controller
parent: seabreeze-inspector.omnisim-assets
tags: [omnisim, controller]
name: {zh: "巡检测试控制器", en: "Inspection Test Controller"}
description:
  zh: >
      风场桥里的飞行侧主逻辑：航点推进与偏航对齐、每步飞行推进，以及被 HTTP 桥调用的主循环。
      
  en: >
      The flight-side logic inside the wind bridge: waypoint advance with yaw alignment, the per-step flight advance, and the main loop the HTTP bridge drives.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.828Z"
fingerprint: 32c20e16989a2c109c98650f4a298604d3fcd7afbf43e53828dae1be5c6cf1ab
source:
  - path: "omnisim_wind_assets/seabreeze_tello_wind_bridge.py"
    line: 346
    end_line: 900
apis:
  - protocol: rpc
    path: "TelloController._set_yaw_desired"
    description:
      zh: >
          偏航对齐。
          
      en: >
          Aligns yaw.
          
  - protocol: rpc
    path: "TelloController.flight_step"
    description:
      zh: >
          单步飞行推进。
          
      en: >
          Advances one flight step.
          
  - protocol: rpc
    path: "TelloController.main_loop"
    description:
      zh: >
          主循环。
          
      en: >
          Main loop.
          
---
