---
uid: 8c5f2e09
id: seabreeze-inspector.research-ops.kimi-review
parent: seabreeze-inspector.research-ops
tags: [research, llm]
name: {zh: "Kimi 评审与视觉调用", en: "Kimi Review & Vision"}
description:
  zh: >
      调用 Kimi 做代码/文档评审与图片理解：密钥加载、上下文汇总、流式对话与图像转 data URL。
      
  en: >
      Calls Kimi for code/document review and image understanding: key loading, context gathering, streaming chat and image-to-data-URL conversion.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.836Z"
fingerprint: d4b97ca93dbc57ec03ee93449c7c44f838115c495e8e7e6261d47e1522d517a5
source:
  - path: "research/kimi_k3_review.py"
  - path: "research/kimi_vision.py"
apis:
  - protocol: rpc
    path: "kimi_k3_review.stream_chat"
    description:
      zh: >
          流式对话。
          
      en: >
          Streaming chat.
          
  - protocol: rpc
    path: "kimi_k3_review.gather"
    description:
      zh: >
          汇总待评审上下文。
          
      en: >
          Gathers review context.
          
  - protocol: rpc
    path: "kimi_vision.image_to_data_url"
    description:
      zh: >
          图像转 data URL。
          
      en: >
          Image to data URL.
          
---
