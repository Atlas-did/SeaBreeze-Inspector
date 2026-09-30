---
uid: 1a7c3e58
id: seabreeze-inspector.backend.core.ekf-disturbance
parent: seabreeze-inspector.backend.core
tags: [ekf, control, wind]
name: {zh: "EKF 扰动观测器", en: "EKF Disturbance Observer"}
description:
  zh: >
      12 维全状态扩展卡尔曼扰动观测器。状态 X=[x,y,z,vx,vy,vz,ax,ay,az,dx,dy,dz]，观测 Z=[IMU 加速度×3, 光流位置×2, 气压高度]。常加速度模型 + 扰动随机游走，观测线性无需雅可比；predict(u) 把已知控制加速度灌入状态，从而把 IMU 残差归因于风扰；残差 Mahalanobis 距离超阈值时按 α 放大 Q，加快阵风跟踪。
      
  en: >
      12-state EKF disturbance observer. State X=[x,y,z,vx,vy,vz,ax,ay,az,dx,dy,dz], measurement Z=[IMU accel x3, optical-flow position x2, barometric height]. Constant-acceleration model plus disturbance random walk; the measurement model is linear so no Jacobian is needed. predict(u) injects the known control acceleration so the IMU residual is attributed to wind, and an over-threshold Mahalanobis residual inflates Q by alpha to track gusts faster.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.794Z"
fingerprint: 4c4db63e676670c89291bd53f9b9d10ae1cb91350cd106897ca70756a8807016
source:
  - path: "backend/core/disturbance_observer.py"
    line: 1
    end_line: 406
---
