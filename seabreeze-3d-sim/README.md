# SeaBreeze Inspector — 3D 巡检仿真 (Three.js)

> 对应 `3D_SIMULATION_OPTIONS.md` 方案 4（Three.js + Web 面板）的落地实现。
> 纯静态页面，无需构建、无需安装，浏览器直接打开。

## 运行

由于用了 ES Module + importmap，需要通过 HTTP 服务打开（不能直接双击 html）：

```bash
cd seabreeze-3d-sim
python -m http.server 8000
# 浏览器打开 http://localhost:8000
```

## 操作

| 按键 | 功能 |
|------|------|
| 空格 | 起飞 / 降落 |
| W A S D | 水平移动 |
| PgUp / PgDn | 升降（与机械臂方向键解耦，对应 06 文档 N4 修复） |
| M | 巡检任务（飞向风机 → 叶片巡检 6s → 自动返航降落） |
| E | 急停（自由落体演示） |
| R | 重置 |
| ← → ↑ ↓ | 机械臂 θ1/θ2 微调 |
| 鼠标拖拽/滚轮 | 旋转视角 / 缩放 |

右下滑块面板：三关节角度 + 预设姿态 + FK 末端坐标实时显示（mm）。

## 文件结构

```
seabreeze-3d-sim/
├── index.html      # 页面 + HUD 布局
├── css/style.css   # 面板样式
└── js/
    ├── models.js   # Tello/机械臂/风机/环境 参数化建模 (尺寸与代码库一致)
    ├── sim.js      # 物理 + 任务状态机 (PD 控制律与后端同构, 阻尼负号!)
    ├── hud.js      # 遥测/机械臂面板绑定
    └── main.js     # 渲染主循环 (轨迹拖尾/风粒子/桨叶动画)
```

## 与 Python 后端的关系

当前是**浏览器端独立演示版**：物理与控制律在 `sim.js` 内实现（结构对齐
`MissionController`：同样的 8 状态机、Kp/Kd 位置环 PD、正弦阵风+随机游走进动力学）。
后续要接真后端，按方案 4 的架构加 WebSocket 即可：

```
Python (EKF/PID/Quad.step)  ──ws──→  sim.js 的 sim.step() 替换为后端状态渲染
```

建议消息格式：`{"pos":[x,y,z], "vel":[...], "state":"HOVERING", "battery":82, "arm":[90,90,45]}`，
JS 侧只保留渲染与输入转发。

## 配套 Blender 脚本

`../seabreeze_models_bpy.py.txt`（重命名为 `.py` 后 `blender -b -P` 运行）可程序化生成
同尺寸模型并导出 GLB —— 之后把 `models.js` 里的程序化建模换成 `GLTFLoader` 加载
`seabreeze_models.glb`，即完成"Blender 资产 → Web 仿真"的闭环。
