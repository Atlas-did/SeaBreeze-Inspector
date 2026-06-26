# API 接口文档 — 模块输入输出规范

> 本文档定义了所有后端模块的公共接口，供开发者遵循。
> 每个模块的接口包含：函数名、参数列表、返回值类型、可能抛出的异常。

---

## 一、Tello无人机控制模块（backend/drone/）

负责与DJI Tello无人机的通信，包括起飞/降落/移动和视频流获取。

| 函数名 | 参数 | 返回值 | 异常类型 | 说明 |
|--------|------|--------|----------|------|
| `TelloController.connect()` | `wifi_prefix: str = "Tello"`, `timeout: int = 10` | `bool` | `ConnectionError`, `TimeoutError` | 连接Tello WiFi热点 |
| `TelloController.disconnect()` | 无 | `None` | `RuntimeError` | 断开连接并清理资源 |
| `TelloController.takeoff()` | 无 | `bool` | `RuntimeError` | 发送起飞指令 |
| `TelloController.land()` | 无 | `bool` | `RuntimeError` | 发送降落指令 |
| `TelloController.move(direction, distance)` | `direction: str` (up/down/forward/back/left/right), `distance: int` (20-500 cm) | `bool` | `ValueError`, `RuntimeError` | 向指定方向移动指定距离 |
| `TelloController.rotate_cw(degrees)` | `degrees: int` (1-360) | `bool` | `ValueError` | 顺时针旋转 |
| `TelloController.rotate_ccw(degrees)` | `degrees: int` (1-360) | `bool` | `ValueError` | 逆时针旋转 |
| `TelloController.hover()` | 无 | `bool` | `RuntimeError` | 原地悬停 |
| `TelloController.get_frame()` | 无 | `numpy.ndarray \| None` | `RuntimeError` | 获取一帧视频画面 (H×W×3, BGR) |
| `TelloController.get_state()` | 无 | `dict[str, int]` | `RuntimeError` | 获取飞行状态字典（高度、电量、速度等） |
| `TelloController.get_imu_data()` | 无 | `dict[str, float]` | `RuntimeError` | 获取IMU原始数据（加速度、姿态角） |
| `TelloController.set_speed(speed)` | `speed: int` (10-100 cm/s) | `bool` | `ValueError` | 设置飞行速度 |
| `TelloController.stream_on()` | 无 | `None` | `RuntimeError` | 开启视频流 |
| `TelloController.stream_off()` | 无 | `None` | `RuntimeError` | 关闭视频流 |

**飞行状态字典键：**
```python
{
    "h": int,       # 高度 (cm)
    "bat": int,     # 电量百分比 (0-100)
    "vgx": int,     # X方向速度 (cm/s)
    "vgy": int,     # Y方向速度 (cm/s)
    "vgz": int,     # Z方向速度 (cm/s)
    "yaw": int,     # 偏航角 (度)
    "pitch": int,   # 俯仰角 (度)
    "roll": int,    # 横滚角 (度)
}
```

**IMU数据字典键：**
```python
{
    "agx": float,   # X轴加速度 (m/s²)
    "agy": float,   # Y轴加速度 (m/s²)
    "agz": float,   # Z轴加速度 (m/s²)
    "pitch": float, # 俯仰角 (度)
    "roll": float,  # 横滚角 (度)
    "yaw": float,   # 偏航角 (度)
}
```

---

## 二、机械臂控制模块（backend/arm/）

负责通过Arduino Nano + PCA9685控制3DOF机械臂的舵机运动。

| 函数名 | 参数 | 返回值 | 异常类型 | 说明 |
|--------|------|--------|----------|------|
| `ArmController.connect()` | `port: str = ""`, `baudrate: int = 115200` | `bool` | `serial.SerialException`, `TimeoutError` | 连接Arduino串口 |
| `ArmController.disconnect()` | 无 | `None` | 无 | 断开串口连接 |
| `ArmController.set_joint_angle(joint, angle)` | `joint: str` (base/shoulder/elbow), `angle: int` (0-180) | `bool` | `ValueError`, `serial.SerialException` | 设置单个关节角度 |
| `ArmController.set_joint_angles(angles)` | `angles: dict[str, int]` (如 `{"base": 90, "shoulder": 45, "elbow": 30}`) | `bool` | `ValueError`, `serial.SerialException` | 同时设置三个关节角度 |
| `ArmController.get_current_angles()` | 无 | `dict[str, int]` | `serial.SerialException` | 获取当前三个关节的实际角度 |
| `ArmController.move_to_pose(pose, speed_dps)` | `pose: tuple[int, int, int]` (base, shoulder, elbow), `speed_dps: int = 60` | `bool` | `ValueError`, `serial.SerialException` | 平滑移动到目标姿态 |
| `ArmController.reset_position()` | 无 | `bool` | `serial.SerialException` | 恢复到默认归中姿态 |
| `ArmController.emergency_stop()` | 无 | `None` | 无 | 紧急停止所有舵机 |

**角度字典格式：**
```python
{"base": int, "shoulder": int, "elbow": int}  # 每个值范围 0-180
```

---

## 三、扰动观测器模块（backend/core/disturbance_observer.py）

使用扩展卡尔曼滤波器（EKF）估计外部扰动（风、船晃等）。

| 函数名 | 参数 | 返回值 | 异常类型 | 说明 |
|--------|------|--------|----------|------|
| `DisturbanceObserver.__init__(config)` | `config: Config` (从 drone_config.yaml 加载) | `DisturbanceObserver` | `ConfigKeyError` | 用配置初始化EKF参数 |
| `DisturbanceObserver.predict(dt)` | `dt: float` (时间步长，秒) | `numpy.ndarray` (12维状态向量) | `RuntimeError` | EKF预测步 |
| `DisturbanceObserver.update(measurement)` | `measurement: numpy.ndarray` (6维观测：位置×3 + 加速度×3) | `numpy.ndarray` (12维状态向量) | `RuntimeError`, `ValueError` | EKF更新步 |
| `DisturbanceObserver.get_state()` | 无 | `dict[str, float]` | 无 | 获取当前完整状态估计 |
| `DisturbanceObserver.get_disturbance()` | 无 | `numpy.ndarray` (3维：dx, dy, dz) | 无 | 获取扰动力估计值 |
| `DisturbanceObserver.reset()` | 无 | `None` | 无 | 重置EKF到初始状态 |

**状态向量定义 (12维)：**
```python
[x, y, z,          # 位置 (cm)
 vx, vy, vz,       # 速度 (cm/s)
 ax, ay, az,       # 加速度 (cm/s²)
 dx, dy, dz]       # 扰动力估计 (N)
```

---

## 四、前馈补偿控制器模块（backend/core/feedforward_controller.py）

结合PID反馈和扰动前馈，输出最终控制量。

| 函数名 | 参数 | 返回值 | 异常类型 | 说明 |
|--------|------|--------|----------|------|
| `FeedforwardController.__init__(config)` | `config: Config` | `FeedforwardController` | `ConfigKeyError` | 初始化PID和前馈增益 |
| `FeedforwardController.compute(target_pos, current_pos, disturbance, dt)` | `target_pos: numpy.ndarray`(3维), `current_pos: numpy.ndarray`(3维), `disturbance: numpy.ndarray`(3维), `dt: float` | `numpy.ndarray` (3维控制量) | `ValueError` | 计算总控制输出 |
| `FeedforwardController.compute_feedback(target_pos, current_pos, dt)` | 同上（不含disturbance） | `numpy.ndarray` (3维) | `ValueError` | 仅计算PID反馈部分 |
| `FeedforwardController.compute_feedforward(disturbance)` | `disturbance: numpy.ndarray` (3维) | `numpy.ndarray` (3维) | `ValueError` | 仅计算前馈补偿部分 |
| `FeedforwardController.reset()` | 无 | `None` | 无 | 重置PID积分项和历史误差 |

---

## 五、RRT* 轨迹规划模块（backend/core/trajectory_planning.py）

在3D空间中生成从起点到目标点的无碰撞最优路径。

| 函数名 | 参数 | 返回值 | 异常类型 | 说明 |
|--------|------|--------|----------|------|
| `RRTStarPlanner.__init__(config)` | `config: Config` | `RRTStarPlanner` | `ConfigKeyError` | 初始化规划参数 |
| `RRTStarPlanner.plan(start, goal, obstacles)` | `start: numpy.ndarray`(3维), `goal: numpy.ndarray`(3维), `obstacles: list[numpy.ndarray]`(每个4维: [x,y,z,radius]) | `numpy.ndarray` (N×3路径点) | `ValueError`, `RuntimeError` | 执行RRT*路径规划 |
| `RRTStarPlanner.plan_async(start, goal, obstacles)` | 同上 | `asyncio.Future` | `ValueError` | 异步执行规划，不阻塞主线程 |
| `RRTStarPlanner.smooth_path(path)` | `path: numpy.ndarray` (N×3) | `numpy.ndarray` (M×3, M≤N) | `ValueError` | 路径平滑后处理 |
| `RRTStarPlanner.check_collision(point, obstacles)` | `point: numpy.ndarray`(3维), `obstacles: list` | `bool` | 无 | 检查点是否与障碍物碰撞 |
| `RRTStarPlanner.set_bounds(x_min, x_max, y_min, y_max, z_min, z_max)` | 6个浮点数边界 | `None` | `ValueError` | 动态设置规划空间边界 |

---

## 六、YOLO缺陷检测模块（backend/vision/）

基于YOLOv8-Nano的风机叶片缺陷检测。

| 函数名 | 参数 | 返回值 | 异常类型 | 说明 |
|--------|------|--------|----------|------|
| `DefectDetector.__init__(config)` | `config: Config` (从 yolo_config.yaml 加载) | `DefectDetector` | `ConfigKeyError`, `FileNotFoundError` | 加载模型权重 |
| `DefectDetector.detect(image)` | `image: numpy.ndarray` (H×W×3, BGR) | `list[DetectionResult]` | `ValueError` | 单张图片推理 |
| `DefectDetector.detect_batch(images)` | `images: list[numpy.ndarray]` | `list[list[DetectionResult]]` | `ValueError` | 批量推理 |
| `DefectDetector.detect_video_frame(frame)` | `frame: numpy.ndarray` | `tuple[numpy.ndarray, list[DetectionResult]]` | `ValueError` | 视频帧推理+画框 |
| `DefectDetector.get_class_names()` | 无 | `list[str]` | 无 | 获取所有类别名称 |
| `DefectDetector.set_confidence(threshold)` | `threshold: float` (0.0-1.0) | `None` | `ValueError` | 动态调整置信度阈值 |

**DetectionResult 数据结构：**
```python
@dataclass
class DetectionResult:
    class_id: int           # 类别ID (0=crack, 1=corrosion, 2=leading_edge_damage)
    class_name: str         # 类别名称
    confidence: float       # 置信度 (0.0-1.0)
    bbox: list[int]         # 检测框 [x1, y1, x2, y2] (像素坐标)
    severity: str \| None   # 严重程度 (light/moderate/severe)，可选
```

---

## 七、Pygame仿真模块（backend/simulation/）

纯软件仿真环境，无需任何硬件即可运行和调试算法。

| 函数名 | 参数 | 返回值 | 异常类型 | 说明 |
|--------|------|--------|----------|------|
| `Simulation.__init__(config)` | `config: Config` | `Simulation` | `ConfigKeyError` | 初始化仿真场景 |
| `Simulation.run()` | 无 | `None` | `KeyboardInterrupt` | 启动主循环（阻塞） |
| `Simulation.step(dt)` | `dt: float` (秒) | `dict[str, Any]` | `RuntimeError` | 单步推进仿真 |
| `Simulation.get_drone_state()` | 无 | `dict[str, Any]` | 无 | 获取无人机仿真状态 |
| `Simulation.set_drone_target(pos)` | `pos: numpy.ndarray` (3维目标位置) | `None` | `ValueError` | 设置无人机目标点 |
| `Simulation.add_wind(disturbance)` | `disturbance: numpy.ndarray` (3维力向量) | `None` | 无 | 添加风扰动 |
| `Simulation.toggle_pause()` | 无 | `bool` | 无 | 暂停/继续仿真 |
| `Simulation.render()` | 无 | `numpy.ndarray \| None` | `RuntimeError` | 渲染当前帧画面 |

**仿真状态字典：**
```python
{
    "position": numpy.ndarray,      # 位置 [x, y, z] cm
    "velocity": numpy.ndarray,      # 速度 [vx, vy, vz] cm/s
    "attitude": numpy.ndarray,      # 姿态 [roll, pitch, yaw] 度
    "disturbance": numpy.ndarray,   # 扰动力 [dx, dy, dz] N
    "battery": float,               # 模拟电量百分比
    "is_flying": bool,              # 是否处于飞行状态
}
```

---

## 八、配置加载器（backend/utils/config.py）

统一配置加载工具，所有模块的配置均通过此接口获取。

| 函数名 | 参数 | 返回值 | 异常类型 | 说明 |
|--------|------|--------|----------|------|
| `ConfigLoader.load(name, config_dir, use_cache, apply_env_override)` | `name: str` (不含.yaml), `config_dir: str \| Path \| None = None`, `use_cache: bool = True`, `apply_env_override: bool = True` | `Config` | `ConfigError`, `ConfigKeyError`, `ConfigTypeError` | 加载并返回配置对象 |
| `ConfigLoader.reload(name, **kwargs)` | 同 `load` | `Config` | 同 `load` | 强制重新加载（忽略缓存） |
| `ConfigLoader.clear_cache()` | 无 | `None` | 无 | 清除所有配置缓存 |

**环境变量覆盖命名规则：**
```
UAVARM_{CONFIG_NAME}__{SECTION}__{KEY} = value

示例：
    UAVARM_DRONE_CONFIG__FLIGHT__DEFAULT_SPEED=30
    → 覆盖 drone_config.yaml 中 flight.default_speed 的值

布尔值写法：
    UAVARM_DRONE_CONFIG__MODE__DEBUG=true
```

---

## 九、飞行日志记录器（backend/utils/logger.py）

CSV格式的飞行数据记录，便于后续分析和图表绘制。

| 函数名 | 参数 | 返回值 | 异常类型 | 说明 |
|--------|------|--------|----------|------|
| `FlightLogger.__init__(log_dir, session_name)` | `log_dir: Path \| None = None`, `session_name: str \| None = None` | `FlightLogger` | 无 | 初始化记录器 |
| `FlightLogger.start_session()` | 无 | `None` | 无 | 开始新会话（写CSV头部） |
| `FlightLogger.log_frame(position, disturbance, detections, extra)` | `position: tuple[float, float, float]`, `disturbance: tuple[float, float, float]`, `detections: list[dict] \| None = None`, `extra: dict \| None = None` | `None` | `RuntimeError` | 记录一帧数据 |
| `FlightLogger.save()` | 无 | `Path` | 无 | 刷盘并返回文件路径 |
| `FlightLogger.stop()` | 无 | `Path` | 无 | 停止记录并保存 |

**支持 with 语句自动管理：**
```python
with FlightLogger() as logger:
    logger.log_frame(position=(0, 0, 100), disturbance=(0.1, 0.2, 0.0))
# 退出时自动保存
```

---

## 十、全局异常体系

```
ConfigError（配置错误基类）
├── ConfigKeyError      → 配置键不存在或路径错误
├── ConfigTypeError     → 配置值类型不匹配
└── ConfigFileError     → 配置文件读写/解析错误

HardwareError（硬件错误基类）
├── DroneConnectionError   → Tello连接失败
├── DroneCommandError      → Tello指令执行失败
├── ArmConnectionError     → Arduino串口连接失败
└── ArmCommandError        → 舵机控制失败

AlgorithmError（算法错误基类）
├── EKFDivergenceError     → EKF滤波发散
├── PlanningError          → 路径规划失败（无路径或超时）
└── DetectionError         → 检测推理失败
```

---

*文档版本: v1.0 | 2026年6月*
