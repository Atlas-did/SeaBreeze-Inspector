---
uid: 8c4e2f19
id: seabreeze-inspector.backend.vision.defect-detector
parent: seabreeze-inspector.backend.vision
tags: [vision, yolo, detection]
name: {zh: "YOLO 缺陷检测器", en: "YOLO Defect Detector"}
description:
  zh: >
      叶片缺陷检测推理：类别 0=crack / 1=corrosion / 2=leading_edge_damage，并把旧数据集的 erosion/rust 别名归一为 corrosion；参数缺省时从 yolo_config.yaml 读取权重路径、置信度与设备。detect 对空帧直接返回，推理或结果解析抛异常时打印 traceback 并自动降级到 mock 检测，保证主循环不断。输出含 class_id/class_name/confidence/bbox/severity。
      
  en: >
      Blade defect inference: classes 0=crack, 1=corrosion, 2=leading_edge_damage with legacy erosion/rust aliases normalized to corrosion; weights path, confidence and device default from yolo_config.yaml. detect returns immediately on empty frames, and on inference or parsing errors prints a traceback and degrades to mock detection so the main loop never dies. Outputs class_id/class_name/confidence/bbox/severity.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.814Z"
fingerprint: 863c3b047bd8fd6d147d20192f3d8bb15989ff60ea6e9744d7a778d20d27e051
source:
  - path: "backend/vision/detect.py"
    line: 15
    end_line: 225
apis:
  - protocol: rpc
    path: "DefectDetector.detect"
    description:
      zh: >
          对单帧推理并返回检测框列表（含类别名、置信度、像素 bbox 与严重度），异常自动切换 mock 模式。
          
      en: >
          Runs inference on one frame and returns detection dicts with class name, confidence, pixel bbox and severity, switching to mock mode on error.
          
  - protocol: rpc
    path: "DefectDetector.draw_detections"
    description:
      zh: >
          在图像副本上按类别颜色绘制检测框与 "name conf" 标签并返回。
          
      en: >
          Draws coloured boxes and name/confidence labels on a copy of the image and returns it.
          
  - protocol: rpc
    path: "DefectDetector._mock_detect"
    description:
      zh: >
          模拟检测：以 4× 下采样帧的 CRC32 为帧内种子生成 0–3 个框，帧内可复现、帧间有变化。
          
      en: >
          Mock detection: seeds a per-frame RNG from the CRC32 of a 4x downsampled frame to emit 0-3 boxes, reproducible within a frame and varying across frames.
          
  - protocol: rpc
    path: "DefectDetector._estimate_severity"
    description:
      zh: >
          按置信度分档估计轻/中/重严重度（已在注释中说明其局限）。
          
      en: >
          Buckets confidence into light/moderate/severe severity (its limitations are documented in the source).
          
---
