---
uid: 5e1b8f24
id: seabreeze-inspector.backend.core.ekf-disturbance.queries
parent: seabreeze-inspector.backend.core.ekf-disturbance
tags: [ekf, api]
name: {zh: "估计查询与复位", en: "Estimate Queries & Reset"}
description:
  zh: >
      对外读出接口：状态/扰动/位置/速度/协方差与残差马氏距离，以及状态与协方差复位。
      
  en: >
      Read-out interface: state, disturbance, position, velocity, covariance and residual Mahalanobis distance, plus state/covariance reset.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.795Z"
fingerprint: 4c4db63e676670c89291bd53f9b9d10ae1cb91350cd106897ca70756a8807016
source:
  - path: "backend/core/disturbance_observer.py"
    line: 441
apis:
  - protocol: rpc
    path: "DisturbanceObserverEKF.get_state"
    description:
      zh: >
          读完整状态。
          
      en: >
          Reads the full state.
          
  - protocol: rpc
    path: "DisturbanceObserverEKF.get_disturbance"
    description:
      zh: >
          读扰动等效加速度。
          
      en: >
          Reads disturbance acceleration.
          
  - protocol: rpc
    path: "DisturbanceObserverEKF.get_covariance"
    description:
      zh: >
          读协方差 P。
          
      en: >
          Reads covariance P.
          
  - protocol: rpc
    path: "DisturbanceObserverEKF.mahalanobis_distance"
    description:
      zh: >
          残差马氏距离。
          
      en: >
          Residual Mahalanobis distance.
          
  - protocol: rpc
    path: "DisturbanceObserverEKF.reset"
    description:
      zh: >
          复位状态与协方差。
          
      en: >
          Resets state and covariance.
          
---
