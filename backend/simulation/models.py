"""
仿真模型定义 — 四旋翼动力学 + 风扰动 + 虚拟传感器
"""

import numpy as np


class Quadrotor3D:
    """
    四旋翼3D动力学模型。

    状态: [x, y, z, vx, vy, vz, roll, pitch, yaw]
    输入: [thrust, d_roll, d_pitch, d_yaw]
    """

    def __init__(self, mass: float = 0.087, dt: float = 0.1):
        self.mass = mass  # kg (Tello实测87g)
        self.dt = dt
        self.g = 9.81  # m/s²
        self.state = np.zeros(9)  # pos(3) + vel(3) + attitude(3)
        self.acceleration = np.zeros(3)  # 存储最近一帧的真实加速度 (m/s²)

    def step(self, control: np.ndarray, disturbance: np.ndarray = None):
        """
        推进一步仿真。

        参数:
            control: [thrust(N), d_roll, d_pitch, d_yaw] (弧度/秒)
            disturbance: [fx, fy, fz] (N)
        """
        if disturbance is None:
            disturbance = np.zeros(3)

        thrust, d_roll, d_pitch, d_yaw = control

        # 姿态更新 (简单积分)
        self.state[6] += d_roll * self.dt   # roll
        self.state[7] += d_pitch * self.dt  # pitch
        self.state[8] += d_yaw * self.dt    # yaw

        # 限制姿态角
        self.state[6:9] = np.clip(self.state[6:9], -np.pi/3, np.pi/3)

        # 计算推力在world frame中的分量
        roll, pitch, yaw = self.state[6:9]
        # 简化: 推力主要沿Z轴
        fx = thrust * np.sin(pitch)
        fy = -thrust * np.sin(roll)
        fz = thrust * np.cos(roll) * np.cos(pitch) - self.mass * self.g

        # 加速度 (存储供虚拟传感器读取)
        self.acceleration = np.array([fx, fy, fz]) / self.mass + disturbance / self.mass

        # 速度更新
        self.state[3:6] += self.acceleration * self.dt

        # 位置更新
        self.state[0:3] += self.state[3:6] * self.dt

        # 高度限制
        self.state[2] = max(0, self.state[2])

    def get_position(self):
        return self.state[0:3].copy()

    def get_acceleration(self):
        """返回最近一帧的真实加速度 (m/s²)"""
        return self.acceleration.copy()

    def get_velocity(self):
        return self.state[3:6].copy()

    def get_attitude(self):
        return self.state[6:9].copy()

    def set_position(self, pos):
        self.state[0:3] = np.asarray(pos)


class WindDisturbance:
    """风扰动模型 — 正弦波动 + 阵风"""

    def __init__(self, base_wind=np.array([0.05, 0.02, 0.0]),
                 freq=0.5, gust_amp=0.03):
        self.base_wind = base_wind  # N (Tello 87g = 0.087kg, 0.05N ≈ 0.57m/s²)
        self.freq = freq
        self.gust_amp = gust_amp
        self.t = 0.0

    def sample(self, dt: float):
        self.t += dt
        gust = self.gust_amp * np.sin(2 * np.pi * self.freq * self.t)
        return self.base_wind + np.array([gust, gust * 0.5, 0.0])


class RobotArm3DOF:
    """
    3DOF机械臂仿真模型 — 挂载在无人机下方。
    关节角: [theta1, theta2, theta3] (度)
    """

    def __init__(self, L1=60, L2=50, L3=40):
        self.L1 = L1  # mm
        self.L2 = L2
        self.L3 = L3
        self.angles = np.array([90.0, 90.0, 45.0])  # 默认姿态
        self.base_offset = np.array([0.0, 0.0, -0.05])  # 相对无人机底部, 单位m

    def set_angles(self, angles_deg):
        """设置关节角度 (度)"""
        self.angles = np.clip(np.asarray(angles_deg, dtype=float), [0, 30, 0], [180, 150, 135])

    def get_endpoint(self):
        """计算末端位置 (相对机械臂基座, 单位m)"""
        from backend.arm.arm_kinematics import FK
        pos_mm = FK(self.angles[0], self.angles[1], self.angles[2])
        return pos_mm / 1000.0  # mm→m


class WindTurbine:
    """风机塔筒模型 — 圆柱形障碍物"""

    def __init__(self, center_xy=(0.0, 0.0), radius=3.0, height=30.0):
        self.center = np.asarray(center_xy)  # (x,y) 单位m
        self.radius = radius  # m
        self.height = height  # m

    def check_collision(self, pos):
        """检查点是否在塔筒内"""
        h_dist = np.linalg.norm(pos[:2] - self.center)
        return h_dist < self.radius and 0 <= pos[2] <= self.height

    def get_surface_point(self, angle_deg, height_m, offset=1.0):
        """
        获取塔筒表面某点 (用于巡检目标)。
        angle_deg: 角度 (0=正x方向)
        height_m: 高度
        offset: 距离表面偏移 (m)
        """
        rad = np.radians(angle_deg)
        x = self.center[0] + (self.radius + offset) * np.cos(rad)
        y = self.center[1] + (self.radius + offset) * np.sin(rad)
        z = np.clip(height_m, 0, self.height)
        return np.array([x, y, z])


class VirtualSensor:
    """虚拟传感器 — 读取仿真状态并加噪声"""

    def __init__(self, imu_noise=0.05, opt_noise=2.0, bar_noise=10.0):
        self.imu_noise = imu_noise  # m/s²
        self.opt_noise = opt_noise  # cm
        self.bar_noise = bar_noise  # cm

    def read_imu(self, quad: Quadrotor3D):
        """读取IMU (加速度, m/s²)"""
        return quad.get_acceleration() + np.random.normal(0, self.imu_noise, 3)

    def read_optical(self, quad: Quadrotor3D):
        """读取光流位置"""
        return quad.get_position()[:2] * 100 + np.random.normal(0, self.opt_noise, 2)  # m→cm

    def read_barometer(self, quad: Quadrotor3D):
        """读取气压计高度"""
        return quad.get_position()[2] * 100 + np.random.normal(0, self.bar_noise)  # m→cm

    def read_all(self, quad: Quadrotor3D):
        """读取全部传感器"""
        imu = self.read_imu(quad)
        opt = self.read_optical(quad)
        bar = self.read_barometer(quad)
        return {
            "imu": imu,
            "optical": opt,
            "barometer": bar,
            "ekf_z": np.concatenate([imu, opt, [bar]]),
        }
