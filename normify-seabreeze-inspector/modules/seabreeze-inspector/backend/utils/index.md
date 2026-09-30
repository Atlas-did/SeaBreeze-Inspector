---
uid: a7f3c910
id: seabreeze-inspector.backend.utils
parent: seabreeze-inspector.backend
tags: [backend, utils, config, bus, logging]
name: {zh: "后端基础设施", en: "Backend Infrastructure"}
description:
  zh: >
      后端基础设施四条互不依赖的地基：YAML 配置加载与 schema 类型校验、单位与坐标系唯一转换点、进程内发布订阅消息总线、CSV 飞行日志记录。任务层、仿真、Web 桥与主调度共用这一层，禁止各自再造第二套。
  en: >
      Four independent foundations for the backend: YAML config loading with schema type checks, the single unit/frame conversion point, the in-process pub-sub message bus, and CSV flight logging. The mission layer, simulation, web bridge and main dispatcher all reuse this layer instead of building a second one.
revision: 87c9ca9d3bdad6782b1b05816e2dab9be91c40d9
updated_at: "2026-09-30T04:50:00Z"
fingerprint: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
source: []
---
