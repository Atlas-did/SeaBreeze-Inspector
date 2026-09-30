---
uid: 5a9c3e71
id: seabreeze-inspector.artifacts.weights
parent: seabreeze-inspector.artifacts
tags: [weights, artefacts]
name: {zh: "模型权重", en: "Model Weights"}
description:
  zh: >
      检测权重的位置约定（data/weights 与训练输出 runs/train/**/weights），仓库内仅保留占位文件。
      
  en: >
      Where detection weights live (data/weights and runs/train/**/weights); only placeholder files are kept in the repository.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.793Z"
fingerprint: 3811ec6007d60dd8113459f045e85c7a5700111ef78cac842a116ba02f2aaca4
source:
  - path: "data/weights/.ci-placeholder.pt"
  - path: "data/weights/.gitkeep"
  - path: "runs/train/seabreeze/weights/.gitkeep"
apis:
  - protocol: file
    path: "data/weights/.ci-placeholder.pt"
    description:
      zh: >
          检测权重占位。
          
      en: >
          Detection-weight placeholder.
          
  - protocol: file
    path: "runs/train/seabreeze/weights/.gitkeep"
    description:
      zh: >
          训练权重输出目录。
          
      en: >
          Training-weight output directory.
          
---
