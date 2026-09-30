---
uid: f0b8a247
id: seabreeze-inspector.backend.utils.config-loader.type-coercion
parent: seabreeze-inspector.backend.utils.config-loader
tags: [config, validation]
name: {zh: "类型强转与校验", en: "Type Coercion & Validation"}
description:
  zh: >
      嵌套键写入、字符串→目标类型转换、嵌套读取与类型/范围校验，以及缓存清理。
      
  en: >
      Nested-key writes, string-to-target-type conversion, nested reads, type/range validation and cache clearing.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.812Z"
fingerprint: 31b2297fee9d3736eda3e1c06c4a66df82696dc41b7e2bcfab4826961da4103e
source:
  - path: "backend/utils/config.py"
    line: 255
apis:
  - protocol: rpc
    path: "ConfigLoader._set_nested_value"
    description:
      zh: >
          写嵌套键。
          
      en: >
          Sets a nested key.
          
  - protocol: rpc
    path: "ConfigLoader._convert_type"
    description:
      zh: >
          类型强转。
          
      en: >
          Coerces a type.
          
  - protocol: rpc
    path: "ConfigLoader._validate_types"
    description:
      zh: >
          类型与范围校验。
          
      en: >
          Type and range validation.
          
  - protocol: rpc
    path: "ConfigLoader.clear_cache"
    description:
      zh: >
          清缓存（测试用）。
          
      en: >
          Clears the cache (for tests).
          
---
