---
uid: 83d1b7e5
id: seabreeze-inspector.artifacts
parent: seabreeze-inspector
tags: [data, weights, dataset, artefacts]
name: {zh: "数据与训练产物", en: "Data & Training Artefacts"}
description:
  zh: >
      仓库内的数据与训练产物位置（多为 gitignore 的大体积资产，此处只记录布局与来源，不描述算法）：data/weights 下的 YOLO 权重（seabreeze_v3.pt、best.onnx/torchscript）、datasets/derived/v5_2_adjudicated 已裁决数据集、runs/ 下的训练与验证输出、data/processed/logs 下的飞行 CSV。
      
  en: >
      Where in-repo data and training artefacts live (mostly gitignored large assets; this records layout and provenance only, not algorithm): YOLO weights under data/weights (seabreeze_v3.pt, best.onnx/torchscript), the adjudicated dataset under datasets/derived/v5_2_adjudicated, training and validation outputs under runs/, and flight CSVs under data/processed/logs.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.792Z"
fingerprint: a3fd580804e5bdd9fdabcc9ab3602531fdd87fa8b2b4090b070b9719b788465a
source:
  - path: "data/weights/.ci-placeholder.pt"
  - path: "data/weights/.gitkeep"
  - path: "data/split_manifest.csv"
  - path: "data/processed/wind_turbine_defect.yaml"
  - path: "runs/train/seabreeze/weights/.gitkeep"
---
