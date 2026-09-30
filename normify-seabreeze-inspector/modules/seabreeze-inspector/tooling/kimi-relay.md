---
uid: e3a6b895
id: seabreeze-inspector.tooling.kimi-relay
parent: seabreeze-inspector.tooling
tags: [tooling, relay]
name: {zh: "Kimi 协议中继", en: "Kimi Relay Proxy"}
description:
  zh: >
      把本地 Ollama 接口转换为 OpenAI 兼容接口的中继服务（供外部评审工具调用）。
      
  en: >
      A relay service that converts the local Ollama API into an OpenAI-compatible one for external review tooling.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.857Z"
fingerprint: 9f28e280dfa98e02589b2e0dbc060b5cdae431f4f8fd9fe6a8ce8b5e16a94d33
source:
  - path: "scripts/kimi_relay_proxy.py"
apis:
  - protocol: http
    method: POST
    path: "/v1/chat/completions"
    description:
      zh: >
          OpenAI 兼容对话接口。
          
      en: >
          OpenAI-compatible chat endpoint.
          
  - protocol: rpc
    path: "kimi_relay_proxy.main"
    description:
      zh: >
          启动中继服务。
          
      en: >
          Starts the relay.
          
---
