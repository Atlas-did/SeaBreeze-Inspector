---
uid: 5d2b8f47
id: seabreeze-inspector.web3d.asset-pipeline
parent: seabreeze-inspector.web3d
tags: [blender, assets]
name: {zh: "Blender 资产流水线", en: "Blender Asset Pipeline"}
description:
  zh: >
      用 Blender bpy 脚本程序化生成无人机/机械臂/风机模型与旋转动画，导出 glb 供网页加载（含页面与样式）。
      
  en: >
      Procedurally builds the drone, arm and turbine models and their spin animation with a Blender bpy script, exporting glb for the page (page and stylesheet included).
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.860Z"
fingerprint: 5dd8c15e3102dc549c328b9ce929138aba62a785edd372a611ce6ddb56a4dae4
source:
  - path: "seabreeze-3d-sim/seabreeze_models_bpy.py"
  - path: "seabreeze-3d-sim/index.html"
  - path: "seabreeze-3d-sim/css/style.css"
apis:
  - protocol: rpc
    path: "build_tello"
    description:
      zh: >
          生成无人机模型。
          
      en: >
          Builds the drone model.
          
  - protocol: rpc
    path: "build_turbine"
    description:
      zh: >
          生成风机模型。
          
      en: >
          Builds the turbine model.
          
  - protocol: rpc
    path: "add_spin_anim"
    description:
      zh: >
          加旋转动画。
          
      en: >
          Adds the spin animation.
          
---
