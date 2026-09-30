---
uid: 1e9b6d27
id: seabreeze-inspector.backend.vision.mock-detector
parent: seabreeze-inspector.backend.vision
tags: [vision, mock]
name: {zh: "Mock 缺陷检测器", en: "Mock Defect Detector"}
description:
  zh: >
      无需模型权重的缺陷检测替身，供 UI 开发与测试：用 4× 下采样帧的 CRC32 作种子，保证同一帧结果一致、不同帧结果不同；每次生成 0–4 个带 center 字段的检测框；draw_results 统一按 class_name 绘制（兼容旧的 class 字段）。继承 DefectDetector 以复用严重度估计与配色。
      
  en: >
      Weight-free defect-detection stand-in for UI development and tests: seeds its RNG from the CRC32 of a 4x downsampled frame so a given frame yields identical results while different frames vary, emits 0-4 boxes carrying a center field, and draw_results always keys on class_name (with a legacy class fallback). It subclasses DefectDetector to reuse severity estimation and colours.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.814Z"
fingerprint: 863c3b047bd8fd6d147d20192f3d8bb15989ff60ea6e9744d7a778d20d27e051
source:
  - path: "backend/vision/detect.py"
    line: 166
    end_line: 225
apis:
  - protocol: rpc
    path: "MockBladeDefectDetector.detect"
    description:
      zh: >
          生成 0–4 个模拟检测框（含 center），空帧返回空列表。
          
      en: >
          Generates 0-4 simulated detections (including center), returning an empty list for empty frames.
          
  - protocol: rpc
    path: "MockBladeDefectDetector.draw_results"
    description:
      zh: >
          按 class_name 在图像副本上绘制框与 "name: conf" 标签并返回。
          
      en: >
          Draws boxes and name: confidence labels keyed on class_name onto an image copy and returns it.
          
---
