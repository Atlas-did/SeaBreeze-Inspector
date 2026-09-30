---
uid: a4d7f168
id: seabreeze-inspector.tooling.dataset-ops
parent: seabreeze-inspector.tooling
tags: [tooling, dataset]
name: {zh: "数据集运维", en: "Dataset Ops"}
description:
  zh: >
      标注格式转换（LabelMe→YOLO）、数据集完整校验与公开数据集检索。
      
  en: >
      Annotation format conversion (LabelMe to YOLO), dataset integrity validation and public-dataset search.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.851Z"
fingerprint: 34daa6db5c60e3b4632f81a1de97f424bd93af13cf39c2c2105dcd78381a4212
source:
  - path: "scripts/labelme2yolo.py"
  - path: "scripts/verify_dataset.py"
  - path: "scripts/search_datasets.py"
apis:
  - protocol: rpc
    path: "labelme2yolo.convert_directory"
    description:
      zh: >
          批量转换标注。
          
      en: >
          Batch-converts annotations.
          
  - protocol: rpc
    path: "verify_dataset.verify_dataset"
    description:
      zh: >
          校验数据集。
          
      en: >
          Validates the dataset.
          
  - protocol: rpc
    path: "search_datasets.search_modelscope"
    description:
      zh: >
          检索 ModelScope 数据集。
          
      en: >
          Searches ModelScope datasets.
          
  - protocol: rpc
    path: "search_datasets.search_opendatalab"
    description:
      zh: >
          检索 OpenDataLab 数据集。
          
      en: >
          Searches OpenDataLab datasets.
          
---
