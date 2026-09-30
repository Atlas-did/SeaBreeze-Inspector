---
uid: 1f8b3d20
id: seabreeze-inspector.tooling.flash-firmware
parent: seabreeze-inspector.tooling
tags: [tooling, firmware]
name: {zh: "固件编译与烧录", en: "Firmware Build & Flash"}
description:
  zh: >
      arduino-cli 探测与安装引导、板级核心与库准备、编译、上传、失败诊断与烧录后校验（含双平台入口）。
      
  en: >
      arduino-cli detection with install guidance, board core and library preparation, compile, upload, failure diagnosis and post-flash verification (both platform entry points).
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.853Z"
fingerprint: c711a532473ca32520bd242f0c81809c124c997c03b183455f381123a3f06995
source:
  - path: "scripts/flash_firmware.py"
  - path: "scripts/flash_firmware.bat"
  - path: "scripts/flash_firmware.sh"
apis:
  - protocol: rpc
    path: "flash_firmware.detect_port"
    description:
      zh: >
          探测串口。
          
      en: >
          Detects the serial port.
          
  - protocol: rpc
    path: "flash_firmware.compile_firmware"
    description:
      zh: >
          编译固件。
          
      en: >
          Compiles the firmware.
          
  - protocol: rpc
    path: "flash_firmware.upload_firmware"
    description:
      zh: >
          上传固件。
          
      en: >
          Uploads the firmware.
          
  - protocol: rpc
    path: "flash_firmware.verify_upload"
    description:
      zh: >
          烧录后校验。
          
      en: >
          Verifies the upload.
          
---
