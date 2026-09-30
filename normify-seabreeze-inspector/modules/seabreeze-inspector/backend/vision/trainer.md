---
uid: c7a3e580
id: seabreeze-inspector.backend.vision.trainer
parent: seabreeze-inspector.backend.vision
tags: [vision, training]
name: {zh: "YOLO 训练入口", en: "YOLO Trainer"}
description:
  zh: >
      基于 ultralytics API 的 YOLOv8n 训练入口（python backend/vision/train.py --data data.yaml --epochs 200）：支持 epochs/imgsz/batch/device/resume 参数，训练后可选 model.val() 并打印 mAP50；对缺库、文件缺失、内存不足分别给出可操作提示并返回布尔成功标志，不向上抛异常中断调用方。
      
  en: >
      YOLOv8n training entry point over the ultralytics API (python backend/vision/train.py --data data.yaml --epochs 200): accepts epochs/imgsz/batch/device/resume, optionally runs model.val() and prints mAP50, and turns missing libraries, missing files and out-of-memory into actionable messages plus a boolean success flag instead of raising into the caller.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.815Z"
fingerprint: f8c4c397eb7658ec89161884a62aa5ad276b3d29e145047aaa19aec5e8622282
source:
  - path: "backend/vision/train.py"
    line: 18
    end_line: 80
apis:
  - protocol: rpc
    path: "train"
    description:
      zh: >
          训练 YOLO 模型并按需验证：返回 True/False 表示是否完成，异常分支打印原因与建议。
          
      en: >
          Trains the YOLO model and optionally validates it, returning True/False and printing the cause and advice on each failure branch.
          
---
