---
uid: 7c2e9a45
id: seabreeze-inspector.tooling.environment-setup
parent: seabreeze-inspector.tooling
tags: [tooling, env]
name: {zh: "环境搭建与测试入口", en: "Env Setup & Test Entry"}
description:
  zh: >
      依赖安装与虚拟环境搭建脚本，以及跨平台的测试运行入口。
      
  en: >
      Dependency and virtualenv setup scripts plus the cross-platform test-run entry points.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.853Z"
fingerprint: 2ff4be09e0ca192db345e29a2c4cfab14c7680a9793ab865c8b89bc53a8e43dd
source:
  - path: "scripts/setup_env.bat"
  - path: "scripts/setup_env.sh"
  - path: "scripts/run_tests.bat"
  - path: "scripts/run_tests.sh"
apis:
  - protocol: file
    path: "scripts/setup_env.bat"
    description:
      zh: >
          Windows 环境搭建。
          
      en: >
          Windows env setup.
          
  - protocol: file
    path: "scripts/setup_env.sh"
    description:
      zh: >
          Unix 环境搭建。
          
      en: >
          Unix env setup.
          
  - protocol: file
    path: "scripts/run_tests.bat"
    description:
      zh: >
          Windows 测试入口。
          
      en: >
          Windows test entry.
          
  - protocol: file
    path: "scripts/run_tests.sh"
    description:
      zh: >
          Unix 测试入口。
          
      en: >
          Unix test entry.
          
---
