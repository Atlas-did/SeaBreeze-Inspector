---
uid: 1d5c7e83
id: seabreeze-inspector.research-ops
parent: seabreeze-inspector
tags: [research, evaluation, paper]
name: {zh: "实验与报告流水线", en: "Research & Reporting Pipeline"}
description:
  zh: >
      数据集与模型实验的支撑代码：v5.2 标签裁决与划分、ID/OOD 双口径评估、发布前预检、标签审计与复核页；以及起雾数据合成、图表生成、Markdown→DOCX、Kimi 评审与视觉调用。
      
  en: >
      Support code for dataset and model experiments: v5.2 label adjudication and splitting, ID/OOD dual-protocol evaluation, preflight checks, label audit and review sheets; plus fog synthesis, figure generation, Markdown-to-DOCX and Kimi review/vision calls.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.835Z"
fingerprint: f0de35ab343ecc71b109d97ec8680e9ffc71f067ebdf83893d72dc649b900c41
source:
  - path: "research/dsh_setup.ps1"
  - path: "research/fog_synth.py"
  - path: "research/gen_latex_figures.py"
  - path: "research/gen_report_figures.py"
  - path: "research/install_anchored_preset.ps1"
  - path: "research/install_vision_plugin.ps1"
  - path: "research/kimi_k3_review.py"
  - path: "research/kimi_vision.py"
  - path: "research/md_to_docx.py"
  - path: "research/v5_2/_inspect_val.py"
  - path: "research/v5_2/audit_labels.py"
  - path: "research/v5_2/make_review_sheet.py"
  - path: "research/v5_2/make_v5_2_split.py"
  - path: "research/v5_2/ood_eval.py"
  - path: "research/v5_2/preflight_check.py"
  - path: "research/v5_2/test_ood_eval.py"
---
