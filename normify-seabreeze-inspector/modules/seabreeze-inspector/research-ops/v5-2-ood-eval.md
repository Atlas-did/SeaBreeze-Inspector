---
uid: 9a4e2f70
id: seabreeze-inspector.research-ops.v5-2-ood-eval
parent: seabreeze-inspector.research-ops
tags: [research, ood]
name: {zh: "v5.2 冻结 OOD 评估", en: "v5.2 Frozen OOD Evaluation"}
description:
  zh: >
      论文里 ID/OOD 双口径数字的产出处：冻结测试集一次性评估、IoU 匹配、分桶统计与锁文件防重跑。
      
  en: >
      Where the paper's ID/OOD dual-protocol numbers come from: one-shot frozen-test evaluation, IoU matching, bucket statistics and a lock file that blocks re-runs.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.838Z"
fingerprint: 23e135e41b196cb7e63359b4b5445aba32ecbe933e12820caba4f41cab5d3d9b
source:
  - path: "research/v5_2/ood_eval.py"
  - path: "research/v5_2/test_ood_eval.py"
apis:
  - protocol: rpc
    path: "ood_eval.match_detections"
    description:
      zh: >
          检测框与真值匹配。
          
      en: >
          Matches detections to ground truth.
          
  - protocol: rpc
    path: "ood_eval.build_report"
    description:
      zh: >
          生成 OOD 报告。
          
      en: >
          Builds the OOD report.
          
  - protocol: rpc
    path: "ood_eval.check_ood_lock"
    description:
      zh: >
          防重跑锁校验。
          
      en: >
          Checks the anti-rerun lock.
          
  - protocol: rpc
    path: "ood_eval.aggregate"
    description:
      zh: >
          聚合指标。
          
      en: >
          Aggregates metrics.
          
---
