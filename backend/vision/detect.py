"""
缺陷检测推理 — 基于YOLOv8-Nano
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np


class DefectDetector:
    """YOLO缺陷检测器"""

    DEFECT_NAMES = {0: "crack", 1: "corrosion", 2: "leading_edge_damage"}
    DEFECT_COLORS = {
        "crack": (0, 0, 255),  # 红色
        "corrosion": (0, 140, 255),  # 橙色
        "leading_edge_damage": (0, 255, 255),  # 黄色
    }

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        conf_threshold: float = 0.45,
        device: str = "cpu",
        mock: bool = False,
    ):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.device = device
        self.mock = mock
        self.model = None

        if not mock:
            try:
                from ultralytics import YOLO
                self.model = YOLO(model_path)
                print(f"[OK] YOLO模型已加载: {model_path}")
            except Exception as e:
                print(f"[WARN] YOLO加载失败, 切换到模拟模式: {e}")
                self.mock = True

    def detect(self, image: np.ndarray) -> List[Dict]:
        """检测单帧图像, 返回检测框列表"""
        if self.mock:
            return self._mock_detect(image)

        results = self.model(image, conf=self.conf_threshold, device=self.device, verbose=False)
        detections = []

        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(float, box.xyxy[0])

                detections.append({
                    "class_id": cls_id,
                    "class_name": self.DEFECT_NAMES.get(cls_id, "unknown"),
                    "confidence": round(conf, 3),
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    "severity": self._estimate_severity(conf),
                })

        return detections

    def _mock_detect(self, image: np.ndarray) -> List[Dict]:
        """模拟检测: 在图像上随机生成检测框"""
        h, w = image.shape[:2]
        import random
        random.seed(42)
        n_det = random.randint(0, 3)
        detections = []
        for i in range(n_det):
            x1 = random.randint(0, w - 100)
            y1 = random.randint(0, h - 100)
            cls_id = random.choice([0, 1, 2])
            detections.append({
                "class_id": cls_id,
                "class_name": self.DEFECT_NAMES[cls_id],
                "confidence": round(random.uniform(0.5, 0.95), 3),
                "bbox": [x1, y1, x1 + random.randint(50, 150), y1 + random.randint(30, 100)],
                "severity": random.choice(["light", "moderate", "severe"]),
            })
        return detections

    def draw_detections(self, image: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """在图像上绘制检测框"""
        img = image.copy()
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            name = det["class_name"]
            color = self.DEFECT_COLORS.get(name, (255, 255, 255))

            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            label = f"{name} {det['confidence']:.2f}"
            cv2.putText(img, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        return img

    def _estimate_severity(self, confidence: float) -> str:
        """基于检测置信度和bbox面积的严重程度估计 (P1-4: 注明局限性)

        NOTE: 当前仅用confidence做启发式估计, 实际严重程度应基于:
        1. 缺陷bbox面积相对于叶片尺寸
        2. 缺陷在叶片上的位置 (前缘/后缘/根部)
        3. 缺陷类型本身的严重性权重
        建议在训练数据集时标注实际严重程度, 用独立分类器替代此方法。
        """
        if confidence < 0.5:
            return "light"
        elif confidence < 0.75:
            return "moderate"
        return "severe"


class MockBladeDefectDetector(DefectDetector):
    """Mock缺陷检测器 — 无需模型, 生成模拟检测结果, 用于UI开发和测试"""

    def __init__(self, conf: float = 0.5, device: str = "cpu"):
        # 直接设置mock, 跳过模型加载
        self.conf_threshold = conf
        self.device = device
        self.model = None
        self.mock = True
        self.DEFECT_NAMES = {0: "crack", 1: "corrosion", 2: "stain"}
        self.DEFECT_COLORS = {
            "crack": (0, 0, 255),
            "corrosion": (0, 140, 255),
            "stain": (0, 255, 255),
        }

    def detect(self, image: np.ndarray) -> List[Dict]:
        """模拟检测, 返回标准化格式的检测结果"""
        h, w = image.shape[:2]
        import random
        random.seed(hash(image.tobytes()) % 10000)
        n_det = random.randint(0, 4)
        detections = []
        for i in range(n_det):
            x1 = random.randint(10, max(20, w - 120))
            y1 = random.randint(10, max(20, h - 120))
            bw = random.randint(40, min(120, w - x1))
            bh = random.randint(30, min(100, h - y1))
            cls_name = random.choice(["crack", "corrosion", "stain"])
            cls_id_map = {"crack": 0, "corrosion": 1, "stain": 2}
            cls_id = cls_id_map.get(cls_name, 0)
            conf = round(random.uniform(0.5, 0.98), 2)
            detections.append({
                "class_id": cls_id,
                "class_name": cls_name,
                "confidence": conf,
                "bbox": [x1, y1, x1 + bw, y1 + bh],
                "center": (x1 + bw // 2, y1 + bh // 2),
                "severity": self._estimate_severity(conf),
            })
        return detections

    def draw_results(self, image: np.ndarray, results: List[Dict]) -> np.ndarray:
        """在图像上绘制检测框和标签 (统一使用 class_name 字段)"""
        import cv2
        img = image.copy()
        for r in results:
            x1, y1, x2, y2 = r["bbox"]
            cls_name = r.get("class_name", r.get("class", "unknown"))  # 兼容两种格式
            conf = r["confidence"]
            color = self.DEFECT_COLORS.get(cls_name, (255, 255, 255))
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            label = "{}: {:.2f}".format(cls_name, conf)
            cv2.putText(img, label, (x1, max(y1 - 5, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        return img
