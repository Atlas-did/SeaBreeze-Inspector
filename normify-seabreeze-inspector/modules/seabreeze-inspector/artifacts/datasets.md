---
uid: e8b4d206
id: seabreeze-inspector.artifacts.datasets
parent: seabreeze-inspector.artifacts
tags: [dataset, artefacts]
name: {zh: "数据集清单与类别表", en: "Dataset Manifests"}
description:
  zh: >
      数据侧的可提交产物：划分清单 split_manifest.csv 与缺陷类别定义 wind_turbine_defect.yaml。
      
  en: >
      Committable data-side artefacts: the split manifest and the defect class definition.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.789Z"
fingerprint: 1fbd0f46dcfa292db6b9cd9de71d3de22664489ec5ac712a367f98e20054726c
source:
  - path: "data/split_manifest.csv"
  - path: "data/processed/wind_turbine_defect.yaml"
apis:
  - protocol: file
    path: "data/split_manifest.csv"
    description:
      zh: >
          数据集划分清单。
          
      en: >
          Dataset split manifest.
          
  - protocol: file
    path: "data/processed/wind_turbine_defect.yaml"
    description:
      zh: >
          缺陷类别定义。
          
      en: >
          Defect class definition.
          
---
