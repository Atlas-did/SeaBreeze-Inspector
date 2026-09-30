---
uid: e5f6a7b8
id: seabreeze-inspector.backend.simulation.transport-model
parent: seabreeze-inspector.backend.simulation
tags: [simulation, fidelity, transport]
name: {zh: "传输层保真度模型", en: "Transport Fidelity Model"}
description:
  zh: >
      把"理想链路"补成现实链路：传感器离散延迟线（样本带采样时刻，可查测量年龄）/ 可复现丢包（i.i.d. 伯努利或 Gilbert-Elliott 突发，两状态马尔可夫）/ 上行指令链路（延迟+丢包+冷启动语义）/ 执行器一阶惯性（PT1 解析解，非欧拉）。默认全 0 时严格直通、逐位不变。丢包序列同 seed 可复现，且只在"真有包到期"时掷骰。
      
  en: >
      Turns an ideal link into a realistic one: a discrete sensor delay line carrying sample timestamps (so measurement age is queryable), reproducible loss (i.i.d. Bernoulli or Gilbert-Elliott burst), an uplink command path (delay + loss + cold-start semantics) and first-order actuator lag (analytic PT1, not Euler). All defaults are strict pass-through, bit-identical. Loss sequences are seed-reproducible and only consume randomness when a packet is actually due.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:32:18.250Z"
fingerprint: e413fc62faa90cc5ead7e68e58ff4fd9bdf317c2a00cbc9d09b14e9d124070cf
source:
  - path: "backend/simulation/transport_model.py"
    line: 1
    end_line: 335
apis:
  - protocol: rpc
    path: "SensorTransportModel.push"
    description:
      zh: >
          送一帧样本入延迟线，并记录其采样时刻。
          
      en: >
          Pushes one sample into the delay line and records its sampling instant.
          
  - protocol: rpc
    path: "SensorTransportModel.poll"
    description:
      zh: >
          取出当前应交付的样本；未到期或丢包返回 None。
          
      en: >
          Returns the sample due now, or None when not due or dropped.
          
  - protocol: rpc
    path: "SensorTransportModel.last_age"
    description:
      zh: >
          手上这条测量有多旧（EKF 据此膨胀 R）。
          
      en: >
          Age of the measurement in hand, used by the EKF to inflate R.
          
  - protocol: rpc
    path: "CommandTransportModel.poll"
    description:
      zh: >
          返回已到达机体的最新指令；丢包不覆盖上一条。
          
      en: >
          Returns the latest command that reached the vehicle; drops never overwrite the previous one.
          
  - protocol: rpc
    path: "ActuatorLag.update"
    description:
      zh: >
          一阶惯性推进一步（tau<=0 时严格直通）。
          
      en: >
          Advances first-order lag by one step (strict pass-through when tau<=0).
          
---
