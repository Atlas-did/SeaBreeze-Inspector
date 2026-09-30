---
uid: 6d1c7b95
id: seabreeze-inspector.research-ops.v5-2-split
parent: seabreeze-inspector.research-ops
tags: [research, dataset]
name: {zh: "v5.2 数据仲裁与划分", en: "v5.2 Split Builder"}
description:
  zh: >
      以感知哈希（pHash）识别同一场景块，重建训练/验证划分，并把标签仲裁结果落成平衡清单。
      
  en: >
      Identifies scene blocks via perceptual hashing, rebuilds the train/val split and writes the adjudicated labels into a balanced manifest.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.839Z"
fingerprint: 5bd39e6e9bc561f31f361db60d8e1d1f5d3e6ccfa7ad4c191e9927d5b590d013
source:
  - path: "research/v5_2/make_v5_2_split.py"
apis:
  - protocol: rpc
    path: "make_v5_2_split.phash"
    description:
      zh: >
          感知哈希去重。
          
      en: >
          Perceptual-hash dedup.
          
  - protocol: rpc
    path: "make_v5_2_split.collect_items"
    description:
      zh: >
          收集候选样本。
          
      en: >
          Collects candidate items.
          
  - protocol: rpc
    path: "make_v5_2_split.main"
    description:
      zh: >
          命令行入口。
          
      en: >
          CLI entry.
          
---
