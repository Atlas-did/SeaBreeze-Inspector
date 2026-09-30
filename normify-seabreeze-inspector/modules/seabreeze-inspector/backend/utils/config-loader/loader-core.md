---
uid: 4c1b6e95
id: seabreeze-inspector.backend.utils.config-loader.loader-core
parent: seabreeze-inspector.backend.utils.config-loader
tags: [config, loader]
name: {zh: "配置加载器主流程", en: "Config Loader Core"}
description:
  zh: >
      load() 主流程：定位 YAML、解析、环境变量覆盖与缓存，供全系统取参。
      
  en: >
      The load() pipeline: locate the YAML, parse it, apply environment overrides and cache the result for the whole system.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.812Z"
fingerprint: 31b2297fee9d3736eda3e1c06c4a66df82696dc41b7e2bcfab4826961da4103e
source:
  - path: "backend/utils/config.py"
    line: 91
    end_line: 254
apis:
  - protocol: rpc
    path: "ConfigLoader.load"
    description:
      zh: >
          加载配置文件。
          
      en: >
          Loads a config file.
          
  - protocol: rpc
    path: "ConfigLoader.reload"
    description:
      zh: >
          强制重新加载（忽略缓存）。
          
      en: >
          Forces a reload, ignoring the cache.
          
  - protocol: rpc
    path: "ConfigLoader._find_config_file"
    description:
      zh: >
          定位配置文件。
          
      en: >
          Locates the config file.
          
  - protocol: rpc
    path: "ConfigLoader._parse_yaml"
    description:
      zh: >
          解析 YAML。
          
      en: >
          Parses YAML.
          
  - protocol: rpc
    path: "ConfigLoader._apply_env_overrides"
    description:
      zh: >
          环境变量覆盖。
          
      en: >
          Applies env overrides.
          
---
