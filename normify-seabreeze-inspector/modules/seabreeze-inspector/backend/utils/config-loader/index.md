---
uid: c4e81a63
id: seabreeze-inspector.backend.utils.config-loader
parent: seabreeze-inspector.backend.utils
tags: [config, yaml, validation]
name: {zh: "配置加载与校验", en: "Configuration Loader"}
description:
  zh: >
      YAML 配置唯一入口：按 config_dir → 项目 config/ → /etc → ~/.config 顺序查找，支持 UAVARM_<NAME>__<PATH> 环境变量覆盖与类型转换，再按内置 schema（drone/arm/yolo 三套）校验必填字段、类型与非负范围；带进程内缓存、热重载与可读错误信息。
      
  en: >
      The single YAML config entry: searches config_dir then project config/, /etc and ~/.config, applies UAVARM_<NAME>__<PATH> environment overrides with type conversion, and validates required fields, types and non-negative ranges against built-in schemas (drone/arm/yolo); provides in-process caching, hot reload and readable errors.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.812Z"
fingerprint: 31b2297fee9d3736eda3e1c06c4a66df82696dc41b7e2bcfab4826961da4103e
source:
  - path: "backend/utils/config.py"
    line: 28
    end_line: 393
---
