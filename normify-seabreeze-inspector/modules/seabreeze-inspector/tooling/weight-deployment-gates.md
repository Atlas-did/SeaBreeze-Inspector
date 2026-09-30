---
uid: c9d0e1f2
id: seabreeze-inspector.tooling.weight-deployment-gates
parent: seabreeze-inspector.tooling
tags: [release, weights, gate]
name: {zh: "权重拉取与部署闸门", en: "Weight Fetch & Deployment Gates"}
description:
  zh: >
      发布侧的两道门：按清单登记的 SHA256 从受控仓库拉取权重（未配置仓库/缺 sha256/下载失败/哈希不匹配一律非 0 退出，绝不用占位文件冒充），以及部署配置闸门 —— config/yolo_config.yaml 指向的权重必须存在且已登记、哈希一致，否则拒绝发布。
      
  en: >
      Two release gates: fetching weights from the controlled registry pinned by the manifest SHA256 (no registry, missing hash, failed download or mismatch all exit non-zero; placeholders can never masquerade), and the deployment gate requiring the weight in config/yolo_config.yaml to exist, be registered and hash-match.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:32:18.253Z"
fingerprint: d17deffbe0c56cda4a3d56bdc7bb335ae17a90c25b86c2b72a3a65691fac89a3
source:
  - path: "scripts/fetch_weights.py"
  - path: "scripts/check_deployment_config.py"
apis:
  - protocol: rpc
    path: "fetch_weights.main"
    description:
      zh: >
          按 SHA256 拉取并逐文件校验（支持 http(s) 与 file://）。
          
      en: >
          Fetches and verifies each weight by SHA256, supporting http(s) and file://.
          
  - protocol: rpc
    path: "check_deployment_config.main"
    description:
      zh: >
          部署配置指向的权重必须存在、已登记且哈希一致。
          
      en: >
          The deployment target must exist, be registered and hash-match.
          
---
