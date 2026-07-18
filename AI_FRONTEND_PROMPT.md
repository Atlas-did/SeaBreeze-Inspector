# SeaBreeze Inspector — 3D 前端 AI 开发提示词

> 把这个文档完整发给 AI（Cursor/Copilot/Claude/GPT），让它帮你写前端。
> 所有 API 已就绪，前端只需调用即可。

---

## 一、项目背景

SeaBreeze Inspector 是一个**海上风电智能巡检系统**：Tello 无人机挂载 3DOF 机械臂，飞近风机塔筒进行 YOLO 缺陷检测。

- 无人机：Ryze Tello (98×92.5×41mm, 桨径 76mm)
- 机械臂：3DOF (L1=55mm, L2=45mm, L3=35mm, 舵机 SG90)
- 风机：塔筒 φ3m×30m (演示缩放)
- 后端：Python (EKF + PID + SafetyGuard + FK/IK)

## 二、后端 API 接口

**HTTP Bridge 已运行在 `http://localhost:8800`**，静态文件也从这里 serve。

### 2.1 GET /api/state — 实时仿真状态

每 50ms 轮询一次。返回 JSON：

```json
{
  "pos": [0.0, 1.2, 0.0],       // 无人机世界坐标 (x, y, z) 单位: 米
  "vel": [0.05, 0.0, -0.02],    // 速度 (vx, vy, vz) m/s
  "state": "HOVERING",           // IDLE|TAKEOFF|HOVERING|NAVIGATE|INSPECT|RETURN|LAND|EMERGENCY
  "battery": 85.3,              // 电量 0-100%
  "wind": [0.08, 0.03, 0.0],    // 风速 (wx, wy, wz) m/s2
  "arm_angles": [90.0, 90.0, 45.0],  // 机械臂关节角度 [θ1, θ2, θ3] 单位: 度
  "arm_endpoint": [0, -57, 112],     // 末端执行器世界坐标 单位: 毫米 (FK 计算)
  "ekf_mahal": 0.5,             // EKF 马氏距离 (状态估计可信度, <5=正常, >10=异常)
  "safety_tier": "NOMINAL",     // NOMINAL|WARN|EMERGENCY
  "detections": [],             // YOLO 检测结果 (暂为空, 后端 mock)
  "fps": 30,                    // 后端帧率
  "flight_log": [...]           // 最近 100 条飞行日志
}
```

### 2.2 GET /api/command?key=KEY — 发送控制指令

键盘事件通过此接口转发给后端。支持的 key 值：

| key | 功能 |
|-----|------|
| `Space` | 起飞/降落 |
| `KeyW` / `KeyA` / `KeyS` / `KeyD` | 水平移动 |
| `KeyR` | 重置 |
| `KeyE` | 紧急停止 |
| `KeyM` | 启动巡检任务 |
| `ArrowLeft` / `ArrowRight` | 机械臂 θ1 ±3° |
| `ArrowUp` / `ArrowDown` | 机械臂 θ2 ±3° |
| `arm&a0=90&a1=120&a2=60` | 直接设机械臂角度 (滑块用) |

示例：`fetch('/api/command?key=Space')`

### 2.3 GET /api/log — 飞行日志

返回最近 100 条事件日志数组。

---

## 三、3D 场景需求（最重要）

### 3.1 场景元素

1. **海面** — 深蓝色平面 + 雾效 (场景直径 ~300m)
2. **风机塔筒** — 红白相间圆柱体, 位置 (9, 0, -2), 高 12m (演示缩放), 3 片旋转叶片
3. **Tello 无人机** — 白色机身 0.98×0.41×0.925m, 4 个电机臂 + 桨叶 + 摄像头
4. **3DOF 机械臂** — 挂在机腹, 3 段彩色连杆 + 发光关节球 + 红色末端球
5. **风粒子** — 200 个半透明蓝色点, 随风飘移
6. **飞行轨迹** — 蓝色拖尾线, 最多 400 点
7. **参考网格** — 60×60 地面网格

### 3.2 视角控制

- **Orbit 模式** (默认): 鼠标右键旋转, 滚轮缩放, 中键平移
- **追机模式** (按 C 切换): 相机自动跟随无人机后方

### 3.3 HUD 面板

**左侧遥测面板** (250px 宽, 半透明):
- STATE / BATT(带进度条) / POS / VEL / WIND / DIST(距风机) / TARGET / EKF / SAFETY / FPS

**右侧摄像头面板** (330px 宽):
- Canvas 模拟前置摄像头画面 (300×220)
- 靠近风机时显示 mock YOLO 检测框
- 下方检测日志列表

**右侧机械臂面板** (320px 宽):
- 3 个角度滑块 (θ1 0-180°, θ2 15-165°, θ3 0-180°)
- 4 个预设按钮: Home(90,90,90) | 垂直(90,90,0) | 前伸(90,150,60) | 极限(0,15,180)
- 末端执行器实时坐标显示 (mm)

### 3.4 智能巡检流程（必须实现！）

这是整个项目的核心价值——**不是静态展示，而是一个完整的自动化任务**：

```
状态机流程:
IDLE → 按空格起飞 → TAKEOFF → 到达悬停高度 → HOVERING
                                                ↓
                                          按 M 启动任务
                                                ↓
NAVIGATE → 飞到塔筒前方 → INSPECT → 悬停扫描 6 秒(模拟 YOLO 检测)
                                                ↓
                                        RETURN → 自动返航
                                                ↓
                                        LAND → 降落 → IDLE
```

**可视化要求**:
- 每个状态切换时 HUD 的 STATE 字段实时更新
- INSPECT 阶段：右侧摄像头面板出现检测框 (crack/corrosion/rust)
- RETURN 阶段：显示虚线返航路径
- LAND 阶段：无人机缓慢下降至 y=0
- 低电量 (<20%) 自动触发 EMERGENCY，机身红色闪烁

---

## 四、技术栈建议

使用 **Three.js v0.160** (ES Module)：

```html
<script type="importmap">
{
  "imports": {
    "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
    "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
  }
}
</script>
```

**注意**：如果 unpkg CDN 在国内加载慢，替换为本地文件或 npmmirror。

---

## 五、参考项目 (GitHub)

学习这些项目的 3D 无人机仿真实现：

1. **gym-pybullet-drones** (⭐1.2k)
   https://github.com/utiasDSL/gym-pybullet-drones
   → 四旋翼物理模型、PID 控制、风扰动模型

2. **Crazyflie simulation** (⭐500+)
   https://github.com/bitcraze/crazyflie-simulation
   → Webots + ROS 无人机仿真架构

3. **three.js drone simulator**
   https://github.com/search?q=three.js+drone+simulator
   → Three.js 无人机 3D 可视化的参考实现

4. **UAV Inspection Sim**
   https://github.com/search?q=uav+inspection+simulation+three.js
   → 巡检任务流程的参考

---

## 六、现有代码起点

当前 `seabreeze-3d-sim/` 目录下有半成品代码可以参考：
- `js/models.js` — Tello/Arm/Turbine 参数化建模 (尺寸正确, 连杆偏细需加粗)
- `js/hud.js` — HUD 面板绑定 (需改为 API 数据驱动)
- `js/main_api.js` — API 轮询框架 (已有基础结构)
- `js/sim.js` — 前端独立仿真 (现在不需要了, 后端替代)
- `index.html` — 面板布局 HTML
- `css/style.css` — 样式

**重构方向**：保留 models.js 建模代码, 重写 main.js 为纯 API 驱动, 删除 sim.js 的物理逻辑。

---

## 七、验收标准

1. ✅ 打开浏览器 → 看到海面、风机、无人机、机械臂
2. ✅ 按空格 → 无人机升到 1.2m 悬停，桨叶旋转
3. ✅ WASD → 无人机水平移动，轨迹拖尾
4. ✅ 按 M → 自动飞向风机，右侧面板出现检测框
5. ✅ 检测 6 秒后 → 自动返航降落
6. ✅ 机械臂滑块 → 关节实时转动，末端坐标更新
7. ✅ 按 C → 相机切换到追机视角
8. ✅ 低电量 → 自动紧急降落，HUD 红色报警

---

## 八、启动命令

```bash
cd offshore-wind-uav-arm
venv/Scripts/python backend/simulation/http_bridge.py
# 浏览器打开 http://localhost:8800
```
