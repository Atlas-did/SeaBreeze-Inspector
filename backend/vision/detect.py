"""
缺陷检测推理 — 训练线为 YOLO11s (`backend/vision/train.py` 的 DEFAULT_MODEL)。

部署权重以 `config/yolo_config.yaml` 为**权威**（由 scripts/check_deployment_config.py
校验存在性与 SHA256）；其 provenance 尚未登记，见 README 的"模型状态"说明。
"""

from __future__ import annotations

from typing import Dict, List, Optional

import cv2
import numpy as np
import zlib


class DefectDetector:
    """YOLO缺陷检测器 — 参数优先从 yolo_config.yaml 读取"""

    DEFECT_NAMES = {0: "crack", 1: "corrosion", 2: "leading_edge_damage"}
    # Compat: old dataset used "erosion" → normalize to "corrosion"
    _CLASS_ALIASES = {"erosion": "corrosion", "rust": "corrosion"}
    DEFECT_COLORS = {
        "crack": (0, 0, 255),  # 红色
        "corrosion": (0, 140, 255),  # 橙色
        "leading_edge_damage": (0, 255, 255),  # 黄色
    }

    def __init__(
        self,
        model_path: str = None,
        conf_threshold: float = None,
        device: str = None,
        mock: bool = False,
    ):
        # 从 yolo_config.yaml 加载默认参数
        if model_path is None or conf_threshold is None or device is None:
            try:
                from backend.utils.config import ConfigLoader
                ycfg = ConfigLoader.load("yolo_config")
                if model_path is None:
                    model_path = str(ycfg["model"]["weights_path"])
                if conf_threshold is None:
                    conf_threshold = float(ycfg["inference"]["conf_threshold"])
                if device is None:
                    device = str(ycfg["model"]["device"])
            except Exception:
                if model_path is None:
                    # 读配置失败时的最后兜底: 与部署配置里的权重**同名**, 而不是一个
                    # 并不存在的历史路径(yolov8n.pt)。权重缺失时 P1-3 的 fail-closed
                    # 会让检测器进入 VISION_UNAVAILABLE, 不会静默降级。
                    model_path = "data/weights/seabreeze_v3.pt"
                if conf_threshold is None:
                    conf_threshold = 0.45
                if device is None:
                    device = "cpu"
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.device = device
        # P1-3: 显式区分三种状态, 绝不再"加载失败就悄悄变 mock":
        #   OK                  = 模型已加载, 正常推理
        #   MOCK                = 调用方**显式**要求模拟(仅用于 UI/演示)
        #   VISION_UNAVAILABLE  = 模型不可用(加载失败/连续推理异常) —— 必须显式暴露
        self.status = "MOCK" if mock else "OK"
        self.unavailable_reason: Optional[str] = None
        self.inference_errors = 0
        self.max_inference_errors = 5
        self.mock = mock            # 向后兼容: 仅表示"调用方显式要求 mock"
        self.model = None

        if not mock:
            try:
                from ultralytics import YOLO
                self.model = YOLO(model_path)
                print(f"[OK] YOLO模型已加载: {model_path}")
            except Exception as e:
                # P1-3: 不再降级为 mock —— 故障必须可见, 检测结果宁可为空
                self.model = None
                self.status = "VISION_UNAVAILABLE"
                self.unavailable_reason = "模型加载失败: {}".format(e)
                print("[ERROR] VISION_UNAVAILABLE: YOLO模型加载失败: {} "
                      "(不会退化为 mock; 检测结果将为空)".format(e))

    @property
    def is_available(self) -> bool:
        """检测能力是否可用。MOCK 也算可用(它是显式选择的模式);
        只有 VISION_UNAVAILABLE 表示"真的没有检测能力"。"""
        return self.status != "VISION_UNAVAILABLE"

    def detect(self, image: np.ndarray) -> List[Dict]:
        """检测单帧图像, 返回检测框列表

        P1-3: 任何故障都不再"自动退化为 mock"。
        - status == VISION_UNAVAILABLE: 直接返回空列表(原因在 status/unavailable_reason 暴露);
        - 连续推理/解析异常达到 max_inference_errors 次后转为 VISION_UNAVAILABLE;
        - 成功一帧即把连续错误计数清零。
        """
        if image is None or not hasattr(image, "shape") or image.size == 0:
            return []
        if self.status == "VISION_UNAVAILABLE":
            return []
        if self.mock:
            return self._mock_detect(image)

        try:
            results = self.model(image, conf=self.conf_threshold, device=self.device, verbose=False)
        except Exception as e:
            self._on_inference_failure("推理", e)
            return []

        detections = []
        try:
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
        except Exception as e:
            self._on_inference_failure("结果解析", e)
            return []

        self.inference_errors = 0
        return detections

    def _on_inference_failure(self, stage: str, exc: Exception) -> None:
        """P1-3: 记录连续推理失败; 达到阈值即标记 VISION_UNAVAILABLE(不再降级为 mock)。"""
        import traceback
        self.inference_errors += 1
        print("[ERROR] 检测{}失败 (第 {}/{} 次): {}".format(
            stage, self.inference_errors, self.max_inference_errors, exc))
        traceback.print_exc()
        if self.inference_errors >= self.max_inference_errors:
            self.status = "VISION_UNAVAILABLE"
            self.unavailable_reason = "{}连续失败 {} 次: {}".format(
                stage, self.inference_errors, exc)
            print("[ERROR] VISION_UNAVAILABLE: {}".format(self.unavailable_reason))

    def _mock_detect(self, image: np.ndarray) -> List[Dict]:
        """模拟检测: 在图像上随机生成检测框 (P1-F: 用帧hash确保不同帧结果不同)"""
        h, w = image.shape[:2]
        import random
        # 每帧用独立种子, 帧间有变化, 帧内可复现
        # 性能: 下采样4x后 CRC32, 避免完整帧 tobytes() 的高 CPU/内存开销
        thumbnail = image[::4, ::4]
        frame_seed = zlib.crc32(thumbnail.tobytes()) % 100000 + 42
        rng = random.Random(frame_seed)
        n_det = rng.randint(0, 3)
        detections = []
        for i in range(n_det):
            x1 = rng.randint(0, max(10, w - 100))
            y1 = rng.randint(0, max(10, h - 100))
            cls_id = rng.choice([0, 1, 2])
            detections.append({
                "class_id": cls_id,
                "class_name": self.DEFECT_NAMES.get(cls_id, "unknown"),
                "confidence": round(rng.uniform(0.5, 0.95), 3),
                "bbox": [x1, y1, x1 + rng.randint(50, 150), y1 + rng.randint(30, 100)],
                "severity": rng.choice(["light", "moderate", "severe"]),
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
        # P1-3: 与 DefectDetector 保持同一套状态字段。
        # MOCK 是"调用方显式选择的模式", 不等于 VISION_UNAVAILABLE。
        self.status = "MOCK"
        self.unavailable_reason = None
        self.inference_errors = 0
        self.max_inference_errors = 5
        self.model_path = "<mock>"
        self.DEFECT_NAMES = {0: "crack", 1: "corrosion", 2: "leading_edge_damage"}
        self.DEFECT_COLORS = {
            "crack": (0, 0, 255),
            "corrosion": (0, 140, 255),
            "leading_edge_damage": (0, 255, 255),
        }

    def detect(self, image: np.ndarray) -> List[Dict]:
        """模拟检测, 返回标准化格式的检测结果"""
        if image is None or not hasattr(image, "shape") or image.size == 0:
            return []
        h, w = image.shape[:2]
        import random
        # P1-F/5.4: 用固定种子 + frame hash 确保同一帧结果一致, 不同帧结果不同
        # 性能: 下采样4x后 CRC32, 避免完整帧 tobytes() 的高 CPU/内存开销
        thumbnail = image[::4, ::4]
        _rng = random.Random(zlib.crc32(thumbnail.tobytes()) % 10000 + 42)
        n_det = _rng.randint(0, 4)
        detections = []
        for i in range(n_det):
            x1 = random.randint(10, max(20, w - 120))
            y1 = random.randint(10, max(20, h - 120))
            bw = _rng.randint(40, min(120, w - x1))
            bh = _rng.randint(30, min(100, h - y1))
            cls_name = _rng.choice(["crack", "corrosion", "leading_edge_damage"])
            cls_id_map = {"crack": 0, "corrosion": 1, "leading_edge_damage": 2}
            cls_id = cls_id_map.get(cls_name, 0)
            conf = round(_rng.uniform(0.5, 0.98), 2)
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
