---
uid: 2e8f4a13
id: seabreeze-inspector.research-ops.v5-2-audit
parent: seabreeze-inspector.research-ops
tags: [research, audit]
name: {zh: "v5.2 标注审计", en: "v5.2 Label Audit"}
description:
  zh: >
      扫描 YOLO 标注与划分清单，按场景块归类检测框、统计尺寸与类别分布，输出审计结果。
      
  en: >
      Scans YOLO labels and the split manifest, classifies boxes by scene block and reports size and class distributions.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.837Z"
fingerprint: 66232cfc7fdd10026edb66a127e3bf61ff166ea10943fc0e06e7ed71cc595380
source:
  - path: "research/v5_2/audit_labels.py"
apis:
  - protocol: rpc
    path: "audit_labels.scan_split"
    description:
      zh: >
          扫描划分集。
          
      en: >
          Scans a split.
          
  - protocol: rpc
    path: "audit_labels.classify_box"
    description:
      zh: >
          归类检测框。
          
      en: >
          Classifies a box.
          
  - protocol: rpc
    path: "audit_labels.main"
    description:
      zh: >
          命令行入口。
          
      en: >
          CLI entry.
          
---
