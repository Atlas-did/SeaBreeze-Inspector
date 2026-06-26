# 常见问题排查 (Troubleshooting)

## 一、软件问题

### 1. 导入错误 (ModuleNotFoundError)

```bash
# 确认在项目根目录运行
cd offshore-wind-uav-arm
export PYTHONPATH="${PWD}:${PYTHONPATH}"

# 或安装为可编辑包
pip install -e .
```

### 2. 测试失败

```bash
# 先运行单个测试定位问题
python tests/test_ekf.py

# 检查 scipy 是否安装
pip install scipy numpy matplotlib pygame

# 检查 Python 版本 (需 >=3.8)
python --version
```

### 3. 仿真窗口不显示

```bash
# Linux: 需要图形界面
export DISPLAY=:0

# 或测试无GUI模式
python backend/main.py --mode simulation --no-gui

# Windows: 确保 pygame 安装正确
pip install pygame --force-reinstall
```

### 4. EKF 发散 (估计值越来越大)

- 检查 dt 设置是否与实际循环周期一致
- 增大 Q_scale (更信任观测)
- 检查传感器数据是否在合理范围

## 二、硬件问题

### 1. Tello 无法连接

| 现象 | 解决 |
|------|------|
| 找不到 Tello WiFi | 长按电源键5秒重启，LED快闪后连"TELLO-XXX" |
| 连接后无响应 | 确认IP 192.168.10.1，关闭防火墙 |
| 频繁掉线 | 靠近Tello(<3m)，关闭其他WiFi设备 |

### 2. Arduino 无法烧入

| 现象 | 解决 |
|------|------|
| 找不到COM口 | 换USB线(需数据线)，换USB口 |
| 上传失败 | 确认板子选"Arduino Nano"，处理器选"ATmega328P" |
| 波特率错误 | 检查代码和串口监视器都使用115200 |

### 3. 舵机不转

- 确认PCA9685外接5V电源
- 检查I2C地址 (默认0x40): `i2cdetect -y 1` (Linux)
- 确认舵机接线: 黄/橙=信号, 红=VCC, 棕/黑=GND

### 4. 机械臂抖动

- 电源不足: 确保PCA9685外接独立5V
- 增加稳压电容 (100μF电解电容)
- 降低舵机转动速度 (分步移动)

## 三、控制问题

### 1. 悬停时漂移

- 地面纹理不足: 确保地面有清晰纹理(非纯白)
- WiFi干扰: 关闭其他无线设备
- 增大 EKF 的 Q_scale 以信任光流更多

### 2. 扰动估计不准

- 检查 IMU 数据是否正常 (无nan/inf)
- 确认 predict() 和 update() 调用频率一致
- Mahalanobis 阈值适当调低

### 3. 路径规划失败

- 起点/终点是否在障碍物内部?
- 增大 max_iter 到 500
- 确认障碍物坐标单位是**米**不是厘米

## 四、视觉问题

### 1. YOLO 检测不到目标

- 检查模型权重路径是否正确
- 降低 conf_threshold (0.3试试)
- 确认图像是BGR格式 (OpenCV默认)

### 2. 训练时显存不足

```python
# Colab: 减小 batch_size
model.train(data='data.yaml', batch=4, imgsz=320)

# 或冻结更多层
for param in model.model.parameters():
    param.requires_grad = False
```

## 五、紧急处理

```
任何严重异常 → 立即执行:
1. 按 Tello 控制器上的紧急停止按钮
2. 或运行: python -c "from backend.drone.tello_basic import TelloController; c=TelloController(); c.connect(); c.emergency()"
3. 关闭所有终端窗口
4. 等待Tello自动降落
```

## 六、获取帮助

1. 查看日志: `logs/` 目录下的时间戳日志文件
2. 运行测试: `bash scripts/run_tests.sh`
3. 开启调试模式: `python backend/main.py --mode simulation --verbose`
