---
uid: 6b2f8d41
id: seabreeze-inspector.backend.vision.dataset-utils
parent: seabreeze-inspector.backend.vision
tags: [vision, dataset]
name: {zh: "缺陷数据集工具", en: "Defect Dataset Utilities"}
description:
  zh: >
      训练数据准备：把 LabelMe JSON 多边形标注转成 YOLO 归一化中心点格式 txt（类别映射 crack/corrosion/leading_edge_damage → 0/1/2），并保留 convert_labelme_to_yolo 兼容别名；split_dataset 按比例划分训练/验证集，同时成对返回图像与标签路径，并跳过缺少同名 .txt 标签的图像。
      
  en: >
      Training-data preparation: converts LabelMe JSON polygons into YOLO normalized-centre txt (mapping crack/corrosion/leading_edge_damage to 0/1/2) with a convert_labelme_to_yolo compatibility alias; split_dataset divides images and labels into train/val while returning them in pairs and skipping images that lack a matching .txt label.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.814Z"
fingerprint: 510501039bfccd0202649e6b5bfc21caaae0c83341c7fbd448cb6467197f2f6a
source:
  - path: "backend/vision/dataset_utils.py"
    line: 13
    end_line: 90
apis:
  - protocol: rpc
    path: "DefectLabelConverter.labelme_to_yolo"
    description:
      zh: >
          把单个 LabelMe JSON 转成同名 YOLO txt 并返回输出路径。
          
      en: >
          Converts one LabelMe JSON into a same-named YOLO txt and returns the output path.
          
  - protocol: rpc
    path: "DefectLabelConverter.convert_labelme_to_yolo"
    description:
      zh: >
          labelme_to_yolo 的兼容别名，签名一致。
          
      en: >
          Compatibility alias of labelme_to_yolo with an identical signature.
          
  - protocol: rpc
    path: "DefectLabelConverter.split_dataset"
    description:
      zh: >
          按 train_ratio 划分数据集，返回 (训练图, 验证图, 训练标签, 验证标签) 四元组。
          
      en: >
          Splits the dataset by train_ratio, returning the (train images, val images, train labels, val labels) tuple.
          
---
