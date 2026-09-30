---
uid: 9d2b6f04
id: seabreeze-inspector.backend.core.feedforward-pid
parent: seabreeze-inspector.backend.core
tags: [control, pid]
name: {zh: "前馈 PID 位置控制器", en: "Feedforward PID Controller"}
description:
  zh: >
      位置环控制律 v_cmd = Kp·e + Ki·∫e + Kd·ė + Kff·d_est。含死区、积分限幅与饱和暂停（anti-windup）、D 项 PT1 低通、积分分离；输出按 max_speed 限幅且保持方向，并回传各项分解供诊断。from_config() 从 drone_config.yaml 的 controller/flight 段读取增益、控制频率与最大速度。
      
  en: >
      Position-loop law v_cmd = Kp*e + Ki*int(e) + Kd*e_dot + Kff*d_est. Includes a dead zone, integral clamping with saturation hold (anti-windup), optional PT1 low-pass on the D term, integral separation, direction-preserving clamping to max_speed, and a per-term breakdown for diagnostics. from_config() reads gains, control rate and max speed from drone_config.yaml.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.795Z"
fingerprint: 0850d3167ba4215442f0326bce6bc1eca0727718ad2c01bb8f0c1c3fa10bb5ff
source:
  - path: "backend/core/feedforward_controller.py"
    line: 1
    end_line: 215
apis:
  - protocol: rpc
    path: "compute"
    description:
      zh: >
          输入目标位置、当前位置、可选扰动估计与当前速度，返回 (3 维速度指令, 含 P/I/D/ff/saturated 的 info 字典)。
          
      en: >
          Takes target position, current position, optional disturbance estimate and current velocity; returns the 3-D velocity command plus an info dict with P/I/D/ff terms and the saturation flag.
          
  - protocol: rpc
    path: "reset"
    description:
      zh: >
          清零积分、误差历史与饱和标志，并复位 D 项滤波器与积分分离器。
          
      en: >
          Clears the integral, error history and saturation flag, and resets the D-term filter and integral separator.
          
  - protocol: rpc
    path: "from_config"
    description:
      zh: >
          类方法：从 ConfigLoader 加载 drone_config，构造按 YAML 增益配置的控制器（配置不可用时回落默认值）。
          
      en: >
          Classmethod: loads drone_config through ConfigLoader and builds a controller from the YAML gains, falling back to defaults when the config is unavailable.
          
---
