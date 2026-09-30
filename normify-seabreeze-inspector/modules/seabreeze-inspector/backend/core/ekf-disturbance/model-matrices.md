---
uid: 8c2f7b03
id: seabreeze-inspector.backend.core.ekf-disturbance.model-matrices
parent: seabreeze-inspector.backend.core.ekf-disturbance
tags: [ekf, math]
name: {zh: "状态转移与观测矩阵", en: "State & Observation Matrices"}
description:
  zh: >
      12 状态常加速度模型的 F 矩阵与 6 维线性观测的 H 矩阵构建（观测线性、无需雅可比）。
      
  en: >
      Builds the F matrix of the 12-state constant-acceleration model and the H matrix of the linear 6-D measurement (no Jacobian needed).
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.794Z"
fingerprint: 4c4db63e676670c89291bd53f9b9d10ae1cb91350cd106897ca70756a8807016
source:
  - path: "backend/core/disturbance_observer.py"
    line: 51
    end_line: 264
apis:
  - protocol: rpc
    path: "DisturbanceObserverEKF._build_state_transition_matrix"
    description:
      zh: >
          构建 F 矩阵。
          
      en: >
          Builds the F matrix.
          
  - protocol: rpc
    path: "DisturbanceObserverEKF._build_observation_matrix"
    description:
      zh: >
          构建 H 矩阵。
          
      en: >
          Builds the H matrix.
          
---
