---
uid: 2a9d5c68
id: seabreeze-inspector.backend.core.ekf-disturbance.predict-update
parent: seabreeze-inspector.backend.core.ekf-disturbance
tags: [ekf, estimator]
name: {zh: "预测与更新", en: "Predict & Update"}
description:
  zh: >
      预测步（灌入已知控制加速度，使 IMU 残差可归因于风扰）与更新步（Joseph 形式协方差），以及自适应 Q 调整。
      
  en: >
      The predict step (injecting known control acceleration so the IMU residual is attributed to wind) and the update step (Joseph-form covariance), plus adaptive Q adjustment.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.794Z"
fingerprint: 4c4db63e676670c89291bd53f9b9d10ae1cb91350cd106897ca70756a8807016
source:
  - path: "backend/core/disturbance_observer.py"
    line: 265
    end_line: 440
apis:
  - protocol: rpc
    path: "DisturbanceObserverEKF.predict"
    description:
      zh: >
          预测步。
          
      en: >
          Predict step.
          
  - protocol: rpc
    path: "DisturbanceObserverEKF.update"
    description:
      zh: >
          更新步。
          
      en: >
          Update step.
          
  - protocol: rpc
    path: "DisturbanceObserverEKF._adaptive_Q_adjustment"
    description:
      zh: >
          自适应过程噪声。
          
      en: >
          Adaptive process noise.
          
---
