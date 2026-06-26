"""
YOLO训练脚本 — 使用ultralytics API

数据增强(ultralytics自动启用):
  - Mosaic: 4图拼接, 丰富场景上下文
  - MixUp: 图像混合, 提升泛化能力
  - 随机翻转/旋转/缩放
  - HSV色彩扰动

用法:
  python backend/vision/train.py --data data.yaml --epochs 200
"""

import argparse
from pathlib import Path


def train(data_yaml: str, epochs: int = 200, imgsz: int = 640, batch: int = 8,
          device: str = "cpu", resume: bool = False, validate: bool = True):
    """训练YOLO模型 (P1-13: 增强错误处理和恢复)

    参数:
        data_yaml: 数据集配置YAML路径
        epochs: 训练轮数
        imgsz: 输入图像尺寸
        batch: 批大小
        device: 设备 (cpu/cuda/mps)
        resume: 是否从checkpoint恢复
        validate: 训练后是否验证
    """
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERR] 缺少ultralytics库。安装: pip install ultralytics")
        return False

    try:
        model = YOLO("yolov8n.pt")
        print(f"[INFO] 开始训练, epochs={epochs}, device={device}")
        model.train(
            data=data_yaml,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=device,
            resume=resume,
        )

        if validate:
            print("[INFO] 训练完成, 开始验证...")
            metrics = model.val()
            print("[OK] 验证完成: mAP50={:.3f}".format(
                metrics.box.map50 if metrics.box else 0.0
            ))
        else:
            print("[OK] 训练完成 (跳过验证)")

        return True
    except FileNotFoundError as e:
        print(f"[ERR] 文件缺失: {e}")
        print("提示: 检查 data_yaml 路径是否正确, 数据集是否已准备")
        return False
    except MemoryError:
        print("[ERR] 内存不足, 请减小 batch_size 或 imgsz")
        return False
    except Exception as e:
        print(f"[ERR] 训练失败: {e}")
        print("提示: 在Google Colab上训练可免费用GPU加速")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="数据集YAML路径")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    train(args.data, args.epochs, args.imgsz, args.batch, args.device)
