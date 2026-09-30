---
uid: 3b7d9c26
id: seabreeze-inspector.research-ops.v5-2-preflight
parent: seabreeze-inspector.research-ops
tags: [research, preflight]
name: {zh: "v5.2 发布前预检与复核页", en: "v5.2 Preflight & Review Sheet"}
description:
  zh: >
      发布前一键体检（哈希、场景块、划分一致性、尺寸分布）与人工复核页生成，另含验证集抽查脚本。
      
  en: >
      One-shot pre-release checks (hashes, scene blocks, split consistency, size distribution) plus review-sheet generation and a val-set spot-check script.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.839Z"
fingerprint: 777ea3a05700806cab38189a9dea50155d56f1f53ec20479be4ad58b48314314
source:
  - path: "research/v5_2/preflight_check.py"
  - path: "research/v5_2/make_review_sheet.py"
  - path: "research/v5_2/_inspect_val.py"
apis:
  - protocol: rpc
    path: "preflight_check.main"
    description:
      zh: >
          发布前预检。
          
      en: >
          Pre-release preflight.
          
  - protocol: rpc
    path: "make_review_sheet.main"
    description:
      zh: >
          生成复核页。
          
      en: >
          Builds the review sheet.
          
---
