---
uid: 8f2d5c17
id: seabreeze-inspector.backend.core
parent: seabreeze-inspector.backend
tags: [python, algorithm, control]
name: {zh: "算法核心", en: "Algorithm Core"}
description:
  zh: >
      飞行控制与规划算法核心：12 维 EKF 扰动观测器（自适应 Q）、前馈+PID 位置控制器、PT1 低通与积分分离数字滤波器、RRT* 三维避障路径规划。全部为纯 NumPy/SciPy 实现，需在 10Hz 控制周期内完成单次递推。
  en: >
      Flight-control and planning algorithm core: a 12-state EKF disturbance observer with adaptive Q, a feedforward+PID position controller, PT1 low-pass and integral-separation filters, and RRT* 3D obstacle-avoiding path planning. Pure NumPy/SciPy, sized for one recursion per 10 Hz control cycle.
revision: 87c9ca9d3bdad6782b1b05816e2dab9be91c40d9
updated_at: "2026-09-30T04:50:00Z"
fingerprint: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
source: []
---
