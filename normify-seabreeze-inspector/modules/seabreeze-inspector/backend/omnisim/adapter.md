---
uid: b67d20af
id: seabreeze-inspector.backend.omnisim.adapter
parent: seabreeze-inspector.backend.omnisim
tags: [omnisim, http, driver]
name: {zh: "OmniSim 高度驱动", en: "OmniSim Altitude Driver"}
description:
  zh: >
      OmniSim Mavic bridge 的 HTTP 驱动：POST /action 下发 takeoff（wait=true）并区分 409 忙碌与 fault，GET /state 轮询 z 与 mode；settle 按最后 5 秒均值统计稳态高度，并显式声明 n_steps 是轮询次数而非物理步数；z 缺失时跳过而不静默当 0 参与均值。
      
  en: >
      HTTP driver for the OmniSim Mavic bridge: POST /action issues takeoff with wait=true and distinguishes 409 busy from a fault, GET /state polls z and mode; settle averages the last five seconds and states that n_steps counts polls, not physics steps; missing z is skipped rather than silently averaged as zero.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.805Z"
fingerprint: fb12e48110ca9ff5e733f7fccadb31daa387acc3aed0c2cfc440ae11d7cf4d02
source:
  - path: "backend/omnisim/adapter.py"
    line: 25
    end_line: 186
apis:
  - protocol: rpc
    path: "OmniSimDriver.set_target_altitude"
    description:
      zh: >
          下发 takeoff 到目标高度并等待到达；409 返回 False，fault/超时/不可达抛桥接错误。
          
      en: >
          Issues takeoff to the target altitude and waits; 409 returns False while fault, timeout or unreachable raises a bridge error.
          
  - protocol: rpc
    path: "OmniSimDriver.settle"
    description:
      zh: >
          按 dt 轮询 bridge 遥测 seconds 秒，返回末 5 秒稳态高度统计与机型标注。
          
      en: >
          Polls bridge telemetry for the requested seconds and returns last-five-second steady-state altitude stats with the model label.
          
  - protocol: rpc
    path: "OmniSimDriver.backend_name"
    description:
      zh: >
          后端标识固定为 omnisim，用于跨后端结果对比。
          
      en: >
          Reports the backend name omnisim for cross-backend comparison.
          
  - protocol: http
    method: POST
    path: "/action"
    description:
      zh: >
          向 bridge 下发动作（takeoff + altitude + wait + timeout_s）。
          
      en: >
          Posts an action to the bridge (takeoff with altitude, wait and timeout_s).
          
  - protocol: http
    method: GET
    path: "/state"
    description:
      zh: >
          读取 bridge 实测遥测（z 高度与 mode 模式）。
          
      en: >
          Reads measured bridge telemetry (z altitude and mode).
          
---
