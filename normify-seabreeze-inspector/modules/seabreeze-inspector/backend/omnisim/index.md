---
uid: 3c9f8152
id: seabreeze-inspector.backend.omnisim
parent: seabreeze-inspector.backend
tags: [omnisim, bridge, experiment]
name: {zh: "OmniSim 桥接适配", en: "OmniSim Bridge Adapter"}
description:
  zh: >
      接入外部 OmniSim 的 Mavic bridge（HTTP）与统一口径高度保持 CLI：真实遥测轮询、显式机型标注（mavic-2-pro，避免把 Mavic 数据误读成 Tello）、未配置 OMNISIM_BASE_URL 或 bridge fault 一律显式报错，绝不拿目标值冒充测量。
  en: >
      Integration with the external OmniSim Mavic bridge over HTTP plus the unified altitude-hold CLI: real telemetry polling, explicit model labelling (mavic-2-pro, so Mavic data is never read as Tello), and hard errors when OMNISIM_BASE_URL is missing or the bridge reports a fault, never substituting the target for a measurement.
revision: 87c9ca9d3bdad6782b1b05816e2dab9be91c40d9
updated_at: "2026-09-30T04:50:00Z"
fingerprint: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
source: []
---
