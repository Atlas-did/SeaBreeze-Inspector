---
uid: e4b7c02a
id: seabreeze-inspector.backend.drone.rc-manager
parent: seabreeze-inspector.backend.drone
tags: [drone, rc, threading]
name: {zh: "RC 速度指令管理器", en: "RC Command Manager"}
description:
  zh: >
      以独立守护线程 20Hz 持续下发 rc_control 的生命周期管理器：set_command 对 lr/fb/ud/yaw 做 ±100 cm/s 限幅；0.5s 无新指令自动归零（防飞丢）；每 3s 发一次 keepalive 维持连接；stop() 先停线程再补发一次归零指令。mock 模式下只更新状态、不触碰硬件。
      
  en: >
      Lifecycle manager that streams rc_control from a daemon thread at 20 Hz: set_command clamps lr/fb/ud/yaw to +/-100 cm/s, the command auto-zeroes after 0.5 s without an update (anti-flyaway), a keepalive is sent every 3 s, and stop() joins the thread then sends one final zero. In mock mode it only tracks state, never touching hardware.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.798Z"
fingerprint: 03cf893cbe70f56d8a013d07908833ba3996f1f2d5d79091a31d04ae60c459bb
source:
  - path: "backend/drone/rc_manager.py"
    line: 19
    end_line: 125
apis:
  - protocol: rpc
    path: "RCManager.start"
    description:
      zh: >
          启动 20Hz RC 发送守护线程（重复调用无副作用）。
          
      en: >
          Starts the 20 Hz RC sender daemon thread (idempotent).
          
  - protocol: rpc
    path: "RCManager.stop"
    description:
      zh: >
          停止发送线程（最多等 1s）并补发一次全零指令。
          
      en: >
          Stops the sender thread (joining up to 1 s) and sends one final all-zero command.
          
  - protocol: rpc
    path: "RCManager.set_command"
    description:
      zh: >
          设置 lr/fb/ud/yaw 速度指令，各轴限幅到 ±100 并刷新超时计时。
          
      en: >
          Sets the lr/fb/ud/yaw velocity command, clamping each axis to +/-100 and refreshing the timeout clock.
          
---
