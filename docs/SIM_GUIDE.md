# 仿真平台操作手册

## 一、引擎选型

| 引擎 | 3D效果 | 学习成本 | 性能 | 包体 | Windows兼容 | 资料 | 推荐 |
|------|--------|---------|------|------|-------------|------|------|
| **Pygame** | **中** | **低** | **高** | **小** | **好** | **多** | **★★★★★** |
| Pyglet | 高 | 中 | 高 | 小 | 好 | 少 | ★★★ |
| Panda3D | 很高 | 高 | 中 | 大 | 好 | 中 | ★★ |
| Three.js | 很高 | 中 | 中 | - | 跨平台 | 多 | ★★★ |
| Matplotlib | 低 | 极低 | 低 | 小 | 好 | 多 | ★ |

**选择 Pygame**：零外部依赖（除pygame外纯NumPy），学习资料丰富，快速可掌握。

## 二、3D投影原理

采用**等轴测投影（Isometric Projection）**：

```python
import numpy as np

def project_3d_to_2d(x, y, z, screen_w=1280, screen_h=720):
    """
    等轴测投影: (x,y,z) -> (screen_x, screen_y)
    """
    # 旋转45度后正交投影
    iso_x = (x - y) * np.cos(np.radians(30))
    iso_y = (x + y) * np.sin(np.radians(30)) - z

    # 缩放到屏幕坐标
    scale = 4  # 像素/米
    offset_x = screen_w // 2
    offset_y = screen_h // 3

    screen_x = int(iso_x * scale + offset_x)
    screen_y = int(iso_y * scale + offset_y)

    return screen_x, screen_y
```

## 三、操作说明

### 键盘控制

| 按键 | 功能 |
|------|------|
| W / Up | 向前飞行 |
| S / Down | 向后飞行 |
| A / Left | 向左飞行 |
| D / Right | 向右飞行 |
| Q | 向左旋转 (yaw -) |
| E | 向右旋转 (yaw +) |
| Space | 悬停 |
| T | 起飞 |
| L | 降落 |
| Esc | 退出仿真 |

### 鼠标控制

| 操作 | 功能 |
|------|------|
| 拖拽 | 旋转视角 |
| 滚轮 | 缩放 |

### 显示内容

- **蓝色四旋翼**：无人机当前位置和姿态
- **绿色线段**：机械臂（从机身下方伸出）
- **灰色圆柱**：风机塔筒
- **红色箭头**：海风扰动力方向和大小
- **白色虚线**：飞行轨迹
- **黄色方框**：YOLO 检测到虚拟缺陷时的标注

## 四、启动方式

```bash
# 纯仿真模式
python backend/main.py --mode simulation

# 调整目标点
python backend/main.py --mode simulation --target "15,0,20"
```

## 五、性能优化

目标：普通笔记本 > 20 FPS

```python
# 降低分辨率 (默认 1280x720)
# 可在 config/drone_config.yaml 修改:
simulation:
  window_width: 1024
  window_height: 768
  fps_target: 30
```

## 六、截图保存

按 `P` 键保存当前画面到 `data/screenshots/`
