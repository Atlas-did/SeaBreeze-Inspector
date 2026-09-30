---
uid: 4e8a1c73
id: seabreeze-inspector.backend.core.filters
parent: seabreeze-inspector.backend.core
tags: [filter, control]
name: {zh: "数字滤波器与积分分离", en: "Digital Filters & Integral Separation"}
description:
  zh: >
      对标 Betaflight 的信号处理原语：PT1 一阶低通 y[n]=y[n-1]+α(x[n]-y[n-1])，α 由截止频率与采样周期推出，用于抑制 D 项高频噪声；积分分离器在误差超阈值时冻结积分，防积分饱和；另提供对 3 维误差向量的积分分离批处理函数。
      
  en: >
      Betaflight-aligned signal primitives: a PT1 first-order low-pass y[n]=y[n-1]+alpha*(x[n]-y[n-1]) whose alpha derives from cutoff and sample period, used to suppress D-term noise; an integral separator that freezes the I term once the error exceeds a threshold to prevent windup; plus a batch helper applying integral separation to a 3-D error vector.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.795Z"
fingerprint: 350d4823500fdcb0b06bb8f48cdda7de230a327afd7dfef70459f5072af4534c
source:
  - path: "backend/core/filters.py"
    line: 1
    end_line: 71
apis:
  - protocol: rpc
    path: "PT1Filter.update"
    description:
      zh: >
          输入新采样值，返回指数平滑后的输出。
          
      en: >
          Feeds a new sample and returns the exponentially smoothed output.
          
  - protocol: rpc
    path: "PT1Filter.set_cutoff"
    description:
      zh: >
          动态修改截止频率并按 rc=1/(2πfc) 重算滤波系数 α。
          
      en: >
          Changes the cutoff frequency at runtime and recomputes alpha from rc=1/(2*pi*fc).
          
  - protocol: rpc
    path: "PT1Filter.reset"
    description:
      zh: >
          把滤波器内部状态置为给定值（默认 0）。
          
      en: >
          Sets the internal filter state to the given value (0 by default).
          
  - protocol: rpc
    path: "IntegralSeparator.should_integrate"
    description:
      zh: >
          按误差模长判断是否允许积分，并记录冻结标志。
          
      en: >
          Decides from the error magnitude whether integration is allowed and latches the frozen flag.
          
  - protocol: rpc
    path: "apply_integral_separation"
    description:
      zh: >
          对 3 维误差/积分向量做积分分离，超阈值分量置零后返回。
          
      en: >
          Applies integral separation to 3-D error/integral vectors and zeroes the over-threshold components.
          
---
