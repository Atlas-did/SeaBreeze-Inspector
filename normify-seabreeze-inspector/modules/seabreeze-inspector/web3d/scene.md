---
uid: 6f2b9d41
id: seabreeze-inspector.web3d.scene
parent: seabreeze-inspector.web3d
tags: [threejs, scene]
name: {zh: "3D 场景与模型构建", en: "Scene & Model Building"}
description:
  zh: >
      Three.js 场景搭建与模型工厂：风机/无人机/机械臂几何体、环境与风场粒子。
      
  en: >
      Three.js scene setup and model factory: turbine, drone and arm geometry, environment and wind particles.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.863Z"
fingerprint: 82753780194227751274672a164b61c4c91bf1cf8c277ba53dc79b7c69a3cf1f
source:
  - path: "seabreeze-3d-sim/js/scene.js"
  - path: "seabreeze-3d-sim/js/models.js"
apis:
  - protocol: rpc
    path: "scene.SimScene"
    description:
      zh: >
          场景实例。
          
      en: >
          Scene instance.
          
  - protocol: rpc
    path: "models.buildTurbine"
    description:
      zh: >
          构建风机模型。
          
      en: >
          Builds the turbine.
          
  - protocol: rpc
    path: "models.buildDrone"
    description:
      zh: >
          构建无人机模型。
          
      en: >
          Builds the drone.
          
  - protocol: rpc
    path: "models.buildWindParticles"
    description:
      zh: >
          构建风粒子。
          
      en: >
          Builds wind particles.
          
---
