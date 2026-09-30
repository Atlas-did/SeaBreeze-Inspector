---
uid: c8a5e031
id: seabreeze-inspector.research-ops.fog-synthesis
parent: seabreeze-inspector.research-ops
tags: [research, augmentation]
name: {zh: "起雾与海雾退化合成", en: "Fog & Salt-Spray Synthesis"}
description:
  zh: >
      用深度图合成不同浓度的雾、盐雾、噪声与运动模糊，生成域偏移数据用于鲁棒性对比。
      
  en: >
      Synthesises fog, salt spray, noise and motion blur at several intensities from depth maps, producing domain-shifted data for robustness comparison.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.830Z"
fingerprint: e44d33ddcc0d03942497611e8a63652c14be303a5449cacc48f3c81140749293
source:
  - path: "research/fog_synth.py"
apis:
  - protocol: rpc
    path: "fog_synth.add_fog"
    description:
      zh: >
          合成雾气。
          
      en: >
          Adds fog.
          
  - protocol: rpc
    path: "fog_synth.degrade_all"
    description:
      zh: >
          批量退化。
          
      en: >
          Degrades a batch.
          
  - protocol: rpc
    path: "fog_synth.make_grid"
    description:
      zh: >
          生成对比网格图。
          
      en: >
          Builds a comparison grid.
          
---
