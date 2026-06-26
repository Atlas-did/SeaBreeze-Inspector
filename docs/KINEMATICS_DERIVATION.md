# 3DOF 机械臂运动学推导

## 一、坐标系定义

```
世界坐标系 (World Frame):
  原点 O: 机械臂底座中心
  Z轴: 竖直向上
  X轴: 机械臂正前方 (theta1=90度时末端指向X正方向)
  Y轴: 左手系确定 (theta1=90度时末端指向Y正方向)

关节定义:
  theta1: 底座旋转角 (0~180度), 绕Z轴
  theta2: 大臂俯仰角 (30~150度), 绕Y轴
  theta3: 小臂相对俯仰角 (0~135度), 相对大臂

连杆参数:
  L1 = 60mm (大臂)
  L2 = 50mm (小臂)
  L3 = 40mm (末端延伸)
  L23 = L2 + L3 = 90mm (小臂+末端共线总长度)
```

## 二、正运动学 (FK)

### 2.1 推导过程

**Step 1: 腕部位置 (L1 末端)**

大臂 L1 与水平面夹角为 theta2:
```
r_wrist = L1 * cos(theta2)          # 腕部水平距离
z_wrist = L1 * sin(theta2)          # 腕部高度
```

**Step 2: 末端位置 (L23 末端)**

小臂+末端与水平面夹角为 theta2 + theta3:
```
r_total = L1*cos(theta2) + L23*cos(theta2 + theta3)   # 总水平距离
z_total = L1*sin(theta2) + L23*sin(theta2 + theta3)   # 总高度
```

**Step 3: 底座旋转**

theta1 将水平距离投影到 X-Y 平面:
```
x = r_total * cos(theta1)
y = r_total * sin(theta1)
z = z_total
```

### 2.2 完整公式

```python
def FK(theta1, theta2, theta3):
    t1, t2, t3 = rad(theta1), rad(theta2), rad(theta3)
    r = L1*cos(t2) + L23*cos(t2 + t3)
    x = r * cos(t1)
    y = r * sin(t1)
    z = L1*sin(t2) + L23*sin(t2 + t3)
    return (x, y, z)
```

## 三、逆运动学 (IK)

### 3.1 求解策略

由于 L2 和 L3 共线，系统简化为2连杆平面臂 + 底座旋转。

**Step 1: theta1 (解析解)**
```
theta1 = atan2(y, x)
```

**Step 2: 腕部目标位置**
```
r_target = sqrt(x^2 + y^2)    # 腕部水平距离
z_target = z                   # 腕部高度 (末端高度 = 腕部高度)
```

**Step 3: 2连杆解析IK (余弦定理)**

目标: 腕部到达 (r_target, z_target)
连杆: L1 (角度 t2), L23 (角度 t2+t3)

令 d = 腕部到原点的距离:
```
d^2 = r_target^2 + z_target^2
```

由余弦定理求 t3:
```
cos(t3) = (d^2 - L1^2 - L23^2) / (2 * L1 * L23)
t3 = arccos( clip(cos(t3), -1, 1) )
```

求 t2:
```
alpha = atan2(z_target, r_target)   # 目标方向角
beta = arccos( (d^2 + L1^2 - L23^2) / (2 * L1 * d) )
t2 = alpha - beta
```

### 3.2 处理多解

余弦定理给出一个 elbow-up 解。由于关节限制，我们通过数值优化自动选择最优解。

### 3.3 数值IK (实现方案)

为保证100%一致性，采用数值优化 + 多初始猜测:

```python
def IK(x, y, z):
    # 1. theta1 = atan2(y, x) (解析)
    # 2. (t2, t3) 用 L-BFGS-B 数值优化
    # 3. 100个初始猜测点覆盖工作空间
    # 4. 选择误差最小的解
```

## 四、雅可比矩阵

速度关系: dp/dt = J * dtheta/dt

```
J = [dx/dt1  dx/dt2  dx/dt3]
    [dy/dt1  dy/dt2  dy/dt3]
    [dz/dt1  dz/dt2  dz/dt3]
```

各元素:
```
r = L1*cos(t2) + L23*cos(t2+t3)
s123 = L1*sin(t2) + L23*sin(t2+t3)

dx/dt1 = -sin(t1) * r
dx/dt2 = -cos(t1) * s123
dx/dt3 = -cos(t1) * L23*sin(t2+t3)

dy/dt1 = cos(t1) * r
dy/dt2 = -sin(t1) * s123
dy/dt3 = -sin(t1) * L23*sin(t2+t3)

dz/dt1 = 0
dz/dt2 = L1*cos(t2) + L23*cos(t2+t3)
dz/dt3 = L23*cos(t2+t3)
```

## 五、工作空间

```
最大水平 reach = L1 + L23 = 60 + 90 = 150mm
最小水平 reach = |L1 - L23| = 30mm (theta3=0时)
最大高度 = L1 + L23 = 150mm (theta2=theta3=90)
最小高度 = L1*sin(30) = 30mm (theta2=30, theta3=-30但受限于0)

实际工作空间:
  r ∈ [约20, 150] mm
  z ∈ [约30, 150] mm
  theta1 ∈ [0, 180] 度 (半圆)
```

## 六、奇异点

```
1. r = 0 (机械臂竖直向上):
   - theta2+theta3 = 90度 且 L1*cos(t2) = L23*cos(t2+t3)
   - 此时theta1不可定 (退化)

2. 关节极限位置:
   - theta1=0 或 180: 工作空间边界
   - theta2=30: 最低俯角
   - theta3=0: 臂完全伸直
```
