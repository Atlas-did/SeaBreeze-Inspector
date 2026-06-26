"""
数据集工具 — 格式转换、增强、验证
"""

import json
import random
from pathlib import Path

import cv2
import numpy as np


class DefectLabelConverter:
    """缺陷标签格式转换器"""

    # 缺陷名称到ID的映射
    CLASS_MAP = {"crack": 0, "corrosion": 1, "leading_edge_damage": 2}

    @staticmethod
    def convert_labelme_to_yolo(json_path: str, img_path: str, output_dir: str):
        """LabelMe JSON → YOLO txt (完整函数名)"""
        return DefectLabelConverter.labelme_to_yolo(json_path, img_path, output_dir)

    @staticmethod
    def labelme_to_yolo(json_path: str, img_path: str, output_dir: str):
        """LabelMe JSON → YOLO txt"""
        with open(json_path) as f:
            data = json.load(f)

        h, w = cv2.imread(img_path).shape[:2]
        labels = []

        for shape in data.get("shapes", []):
            cls_name = shape["label"]
            cls_id = DefectLabelConverter.CLASS_MAP.get(cls_name, 0)

            pts = np.array(shape["points"])
            x_min, y_min = pts.min(axis=0)
            x_max, y_max = pts.max(axis=0)

            cx = (x_min + x_max) / 2 / w
            cy = (y_min + y_max) / 2 / h
            bw = (x_max - x_min) / w
            bh = (y_max - y_min) / h

            labels.append(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

        out_path = Path(output_dir) / (Path(json_path).stem + ".txt")
        out_path.write_text("\\n".join(labels))
        return out_path

    @staticmethod
    def split_dataset(image_dir: str, label_dir: str = None, train_ratio: float = 0.8):
        """划分训练集/验证集 (P1-5: 同时处理标签文件)

        参数:
            image_dir: 图像目录
            label_dir: 标签目录 (默认与image_dir相同, YOLO格式.txt文件)
            train_ratio: 训练集比例

        返回:
            (train_images, val_images, train_labels, val_labels)
        """
        if label_dir is None:
            label_dir = image_dir

        image_dir = Path(image_dir)
        label_dir = Path(label_dir)

        images = list(image_dir.glob("*.jpg")) + list(image_dir.glob("*.png"))
        random.shuffle(images)

        # P1-5: 过滤掉没有对应标签的图像
        valid_images = []
        valid_labels = []
        for img in images:
            label_path = label_dir / (img.stem + ".txt")
            if label_path.exists():
                valid_images.append(img)
                valid_labels.append(label_path)
            else:
                print(f"[WARN] 图像 {img.name} 缺少标签文件, 已跳过")

        n_train = int(len(valid_images) * train_ratio)
        return (
            valid_images[:n_train],
            valid_images[n_train:],
            valid_labels[:n_train],
            valid_labels[n_train:],
        )