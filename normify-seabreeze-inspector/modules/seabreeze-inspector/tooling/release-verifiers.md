---
uid: b8c9d0e1
id: seabreeze-inspector.tooling.release-verifiers
parent: seabreeze-inspector.tooling
tags: [release, verification, ci]
name: {zh: "发布校验器（模型/数据集/环境）", en: "Release Verifiers"}
description:
  zh: >
      把"什么算发布一致"拆成三个职责单一的校验器加一个总入口：模型（权重存在 + SHA256 + 字节数；release_candidate=true 必须有完整 training/eval provenance）、数据集（内容摘要与派生版本）、环境（只校声明的 Python 协议范围与 requirements 指纹）。权威=内容指纹；mtime/绝对路径/平台/补丁号被显式忽略并打印，这修掉了干净克隆必然失败的根因。
      
  en: >
      Three single-purpose verifiers behind one entry: models (presence, SHA256, byte count; release candidates must carry full provenance), datasets (content digest and derived version) and environment (declared Python range plus requirements fingerprint). Authority is the content fingerprint; mtime, paths, platform and patch versions are ignored and printed - the root cause of clean-clone failure.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:32:18.253Z"
fingerprint: 171dcd84c6a53ebde12bd2eb60e31c4e2487422a4b051c9e31c651778ded94a3
source:
  - path: "scripts/verify_manifest.py"
  - path: "scripts/verify_model_manifest.py"
  - path: "scripts/verify_dataset_manifest.py"
  - path: "scripts/verify_environment.py"
apis:
  - protocol: rpc
    path: "verify_manifest.main"
    description:
      zh: >
          总入口：依次编排三个校验器并汇总退出码。
          
      en: >
          Entry point orchestrating the three verifiers and summarising exit codes.
          
  - protocol: rpc
    path: "verify_model_manifest.main"
    description:
      zh: >
          权重内容指纹 + release_candidate 的 provenance 强制。
          
      en: >
          Weight content fingerprints plus enforced provenance for release candidates.
          
  - protocol: rpc
    path: "verify_environment.main"
    description:
      zh: >
          仅校声明协议（Python 范围 + requirements 指纹），无 lock 也能过。
          
      en: >
          Checks the declared protocol only, passing even without a lock file.
          
---
