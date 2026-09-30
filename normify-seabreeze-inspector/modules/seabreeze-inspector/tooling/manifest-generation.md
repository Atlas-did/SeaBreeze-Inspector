---
uid: a7b8c9d0
id: seabreeze-inspector.tooling.manifest-generation
parent: seabreeze-inspector.tooling
tags: [release, manifest, provenance]
name: {zh: "清单与环境锁生成", en: "Manifest & Environment Lock Generation"}
description:
  zh: >
      生成发布用的两份清单与环境锁：数据集清单（条目 path/size/digest + 由条目派生的 dataset_version，运行期产物被排除以避免版本号漂移）与模型清单（权重 SHA256 + 字节数；mtime 只进 informational，因为它是非权威字段）。关键规则：重新生成时按 sha256 继承人工登记的 training/eval provenance，内容变了则显式清空防伪造。
      
  en: >
      Generates the two release manifests and the environment lock: dataset manifest (per-entry path/size/digest plus digest-derived version, runtime artefacts excluded so it cannot drift) and model manifest (SHA256 plus bytes; mtime only in informational). Regeneration inherits hand-registered training/eval provenance only when SHA256 is unchanged, clearing it otherwise so provenance cannot be forged.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:32:18.250Z"
fingerprint: 053cd58706d53c866fcbadff25b1bcaa71535f81a0e0700ccbfa4cd5ca6d6faf
source:
  - path: "scripts/make_manifest.py"
    line: 1
    end_line: 360
apis:
  - protocol: file
    path: "data/dataset_manifest.json"
    description:
      zh: >
          数据集清单（含派生 dataset_version）。
          
      en: >
          Dataset manifest including the derived dataset_version.
          
  - protocol: file
    path: "data/model_manifest.json"
    description:
      zh: >
          模型清单（SHA256 钉扎 + provenance 唯一持久记录）。
          
      en: >
          Model manifest: SHA256 pinning and the only persistent provenance record.
          
  - protocol: file
    path: "environment.lock"
    description:
      zh: >
          环境锁（解释器与依赖快照，路径/平台仅作信息）。
          
      en: >
          Environment lock: interpreter and dependency snapshot, paths/platform informational only.
          
---
