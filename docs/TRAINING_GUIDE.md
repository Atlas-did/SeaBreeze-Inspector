# 风机叶片缺陷检测 — 训练指南

## 一、模型选型

| 模型 | 大小 | CPU延迟 | 预训练 | 微调难度 | 小样本适应 | 推荐 |
|------|------|---------|--------|---------|-----------|------|
| YOLOv5-Nano | 1.9MB | ~30ms | 有 | 低 | ★★★ | ★★★ |
| **YOLOv8-Nano** | **3.2MB** | **~50ms** | **有** | **低** | **★★★** | **★★★★** |
| RT-DETR-R18 | 40MB | ~200ms | 有 | 中 | ★★ | ★★ |
| 传统CV | - | ~20ms | 无 | 高 | ★ | ★ |

**选择 YOLOv8-Nano**：新架构、文档完善、ultralytics官方支持、COCO预训练权重可用。

## 二、数据集准备

### 2.1 数据采集

```
目标: 风机叶片表面缺陷 (裂纹、腐蚀、污渍)
数量: 每类至少 30 张 (共90张以上)
分辨率: 640x480 或更高
角度: 正面、侧面、不同光照
背景: 尽量多样化
```

### 2.2 标注规范 (LabelMe)

```bash
pip install labelme
labelme  # 启动标注工具
```

标注要求:
- 矩形框紧密包围缺陷区域
- 类别名称统一: `crack`(裂纹), `corrosion`(腐蚀), `stain`(污渍)
- 每张图像标注所有可见缺陷

### 2.3 格式转换

```bash
python backend/vision/dataset_utils.py convert \
    --input_dir data/raw/annotations \
    --output_dir data/processed/labels
```

## 三、训练 (Google Colab)

### 3.1 Colab 笔记本模板

```python
# 1. 安装依赖
!pip install ultralytics

# 2. 上传数据集 (压缩为 zip)
from google.colab import files
uploaded = files.upload()  # 上传 dataset.zip
!unzip dataset.zip -d /content/dataset

# 3. 训练
from ultralytics import YOLO

model = YOLO('yolov8n.pt')  # 加载预训练权重
model.train(
    data='/content/dataset/data.yaml',
    epochs=100,
    imgsz=640,
    batch=8,
    patience=20,        # 早停
    device=0,           # GPU
    project='wind_turbine_defect',
    name='exp1',
)
```

### 3.2 数据增强配置

```yaml
# data.yaml
path: /content/dataset
train: train/images
val: val/images
test: test/images

nc: 3
names: ['crack', 'corrosion', 'stain']
```

Ultralytics 自动启用:
- Mosaic (4图拼接)
- 随机翻转 (水平)
- HSV 扰动
- 随机缩放/平移

### 3.3 小样本策略 (<100张)

1. **迁移学习**: 使用 COCO 预训练权重，冻结 backbone 前 10 epoch
2. **增强强度**: 增大 mosaic 比例到 0.8
3. **早停**: patience=20，避免过拟合
4. **验证集**: 至少 10% 数据用于验证

## 四、训练监控

```python
# 训练日志自动保存到 runs/wind_turbine_defect/exp1/
# 包含:
#   results.csv      - mAP, precision, recall
#   confusion_matrix.png
#   F1_curve.png
#   PR_curve.png
```

目标指标:
- mAP@50 > 0.7 (可用)
- mAP@50 > 0.85 (良好)
- mAP@50 > 0.9 (优秀)

## 五、导出与部署

```python
# 导出为 ONNX (跨平台)
model.export(format='onnx')

# 导出为 TorchScript
model.export(format='torchscript')
```

部署文件:
```
data/weights/
  best.pt          # PyTorch 格式 (推荐)
  best.onnx        # ONNX 格式
```

## 六、常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| mAP 一直很低 | 数据标注错误/类别不平衡 | 检查标注质量，增加样本 |
| 过拟合 (val mAP << train) | 数据太少 | 增强数据，降低学习率 |
| 推理慢 | 图像太大 | resize 到 640x480 |
| 小目标检测差 | 特征图分辨率低 | 使用更大的输入尺寸 |
