---
uid: 1a7d3b84
id: seabreeze-inspector.research-ops.setup-scripts
parent: seabreeze-inspector.research-ops
tags: [research, setup]
name: {zh: "研究环境安装脚本", en: "Research Setup Scripts"}
description:
  zh: >
      为研究侧工具链准备环境的 PowerShell 脚本：DSH 安装、锚定预设安装与视觉插件安装。
      
  en: >
      PowerShell scripts preparing the research toolchain: DSH setup, anchored-preset install and vision-plugin install.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.837Z"
fingerprint: 0ef35fbad4119c89f0aabed89a1444c5195010a767c8bab679c1ec2ba00d2952
source:
  - path: "research/dsh_setup.ps1"
  - path: "research/install_anchored_preset.ps1"
  - path: "research/install_vision_plugin.ps1"
apis:
  - protocol: file
    path: "research/dsh_setup.ps1"
    description:
      zh: >
          DSH 环境安装。
          
      en: >
          DSH setup.
          
  - protocol: file
    path: "research/install_anchored_preset.ps1"
    description:
      zh: >
          安装锚定预设。
          
      en: >
          Installs the anchored preset.
          
  - protocol: file
    path: "research/install_vision_plugin.ps1"
    description:
      zh: >
          安装视觉插件。
          
      en: >
          Installs the vision plugin.
          
---
