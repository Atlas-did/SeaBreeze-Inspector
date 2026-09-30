---
uid: a5d9c382
id: seabreeze-inspector.backend.utils.config-loader.config-view
parent: seabreeze-inspector.backend.utils.config-loader
tags: [config]
name: {zh: "配置视图与异常", en: "Config View & Errors"}
description:
  zh: >
      配置对象与专用异常：Config 的字典式读取、包含判定、默认值与导字典。
      
  en: >
      The config object and its dedicated errors: dict-style access, containment, defaults and dict export.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.812Z"
fingerprint: 31b2297fee9d3736eda3e1c06c4a66df82696dc41b7e2bcfab4826961da4103e
source:
  - path: "backend/utils/config.py"
    line: 38
    end_line: 90
apis:
  - protocol: rpc
    path: "Config.__getitem__"
    description:
      zh: >
          按 key 取配置。
          
      en: >
          Reads a config key.
          
  - protocol: rpc
    path: "Config.get"
    description:
      zh: >
          带默认值读取。
          
      en: >
          Reads with a default.
          
  - protocol: rpc
    path: "Config.to_dict"
    description:
      zh: >
          导出为字典。
          
      en: >
          Exports to a dict.
          
---
