"""
Physics simulation models - z-up coordinate system (meters, m/s, m/s2)

Rule #3: All simulation physics uses z-up internally.
  Position: [x, y, z], z = altitude, z+ is upward
  Velocity: [vx, vy, vz], vz = vertical velocity, vz+ is upward
  Acceleration: [ax, ay, az], az = vertical acceleration

History: 2026-07 Refactor Phase 2 confirmed z-up,
  eliminating the coordinate fork with backend EKF (z-up cm).

Modules:
  Quadrotor3D: quadrotor point-mass dynamics (z-up, meters)
  WindDisturbance: wind disturbance (Gaussian + sinusoidal, z-up)
  RobotArm3DOF: 3DOF robotic arm (FK, millimeters)
  WindTurbine: turbine geometry (collision detection)
  VirtualSensor: virtual sensors (IMU + optical flow + barometer, with noise + bias drift)
"""



import numpy as np
from backend.hal.interfaces import ArmInterface





class Quadrotor3D:

    """

    四旋翼3D动力学模型。



    状态: [x, y, z, vx, vy, vz, roll, pitch, yaw]

    输入: [thrust, d_roll, d_pitch, d_yaw]

    """



    # 姿态环时间常数 (s) — 模拟真实飞控的姿态响应, 越小响应越快
    ATT_TAU = 0.15
    # 最大倾角 (rad) — 限 roll/pitch, 不限 yaw
    MAX_TILT = 0.5
    # 线性气动阻力系数 (N·s/m) — 提供速度阻尼, 消除"冰上滑行"感
    DRAG_COEF = 0.06



    def __init__(self, mass: float = 0.087, dt: float = 0.1):

        self.mass = mass  # kg (Tello实测87g)

        self.dt = dt  # 默认步长 (可被 step(dt=...) 覆盖)

        self.g = 9.81  # m/s²

        self.state = np.zeros(9)  # pos(3) + vel(3) + attitude(3)

        self.acceleration = np.zeros(3)  # 存储最近一帧的真实加速度 (m/s²)



    def step(self, control: np.ndarray, disturbance: np.ndarray = None,
             dt: float = None):

        """

        推进一步仿真。



        参数:

            control: [thrust(N), roll_des, pitch_des, yaw_rate]
                     roll_des/pitch_des 为期望倾角 (rad), 内部姿态环一阶跟踪;
                     yaw_rate 为偏航角速度 (rad/s)
            disturbance: [fx, fy, fz] (N) — 风等外力
            dt: 本帧步长 (s); None 时用 self.dt。
                调用方应传入真实帧间隔, 避免"仿真时间 vs 墙钟时间"漂移。

        """

        if disturbance is None:

            disturbance = np.zeros(3)

        if dt is None:

            dt = self.dt



        thrust, roll_des, pitch_des, yaw_rate = control



        # 姿态环: 一阶惯性跟踪期望倾角 (替代原来的"速率直接积分")
        k_att = min(1.0, dt / self.ATT_TAU)

        self.state[6] += (np.clip(roll_des, -self.MAX_TILT, self.MAX_TILT)
                          - self.state[6]) * k_att

        self.state[7] += (np.clip(pitch_des, -self.MAX_TILT, self.MAX_TILT)
                          - self.state[7]) * k_att

        self.state[8] += yaw_rate * dt  # yaw 不限幅, 自由旋转



        # 计算推力在world frame中的分量

        roll, pitch, yaw = self.state[6:9]

        # 简化: 推力沿机体Z轴 (小角度近似)

        fx = thrust * np.sin(pitch)

        fy = -thrust * np.sin(roll)

        fz = thrust * np.cos(roll) * np.cos(pitch) - self.mass * self.g



        # 线性气动阻力: F = -c·v (物理手感的关键: 松杆自动减速)

        drag = -self.DRAG_COEF * self.state[3:6]



        # 加速度 (存储供虚拟传感器读取)

        self.acceleration = (np.array([fx, fy, fz]) + disturbance + drag) / self.mass



        # 速度更新

        self.state[3:6] += self.acceleration * dt



        # 位置更新

        self.state[0:3] += self.state[3:6] * dt



        # 高度限制 (触地即停垂直速度, 防止地下反弹鬼畜)

        if self.state[2] < 0:

            self.state[2] = 0.0

            self.state[5] = max(0.0, self.state[5])



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



    def set_velocity(self, vel):

        """直接设置速度 (用于键盘控制)"""

        self.state[3:6] = np.asarray(vel)





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





class RobotArm3DOF(ArmInterface):

    """

    3DOF机械臂仿真模型 — 挂载在无人机下方。

    关节角: [theta1, theta2, theta3] (度)

    """



    def __init__(self, L1=None, L2=None, L3=None):

        # P2-L: 连杆长度从 arm_config.yaml 读取 (单源权威)

        if L1 is None or L2 is None or L3 is None:

            try:

                from backend.arm.arm_kinematics import L1 as _L1, L2 as _L2, L3 as _L3

                L1, L2, L3 = _L1, _L2, _L3

            except Exception:

                L1, L2, L3 = 55, 45, 35

        self.L1 = float(L1)  # mm — 权威来源: arm_config.yaml

        self.L2 = float(L2)

        self.L3 = float(L3)

        self.angles = np.array([90.0, 90.0, 45.0])  # 默认姿态

        self.base_offset = np.array([0.0, 0.0, -0.05])  # 相对无人机底部, 单位m



    def set_angles(self, angles_deg):

        """设置关节角度 (度)"""

        self.angles = np.clip(np.asarray(angles_deg, dtype=float), [0, 30, 0], [180, 150, 135])

    def get_angles(self):
        """Get current joint angles in degrees."""
        return self.angles.copy()


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

    """虚拟传感器 — 增强噪声模型: 高斯 + 零偏漂移 + 随机游走 (对标 gym-pybullet-drones)



    噪声模型:

      - 高斯白噪声 (测量噪声)

      - 零偏 (bias): 缓慢漂移, 模拟温度/振动引起的传感器偏移

      - 随机游走 (random walk): 低频噪声累积, 模拟 MEMS 传感器特性

    """



    def __init__(self, imu_noise=0.05, opt_noise=2.0, bar_noise=10.0,

                 bias_drift_rate=0.001, rw_std=0.005):

        self.imu_noise = imu_noise       # m/s², 高斯噪声标准差

        self.opt_noise = opt_noise       # cm

        self.bar_noise = bar_noise       # cm

        self.bias_drift_rate = bias_drift_rate  # 零偏漂移率 (m/s² per step)

        self.rw_std = rw_std             # 随机游走标准差 (m/s²)



        # 内部状态

        self._accel_bias = np.zeros(3)       # 零偏 (缓慢漂移)

        self._accel_rw = np.zeros(3)         # 随机游走累积



    def _step_bias_rw(self, dt: float = 0.1):

        """更新零偏漂移和随机游走 (每帧调用)"""

        # 零偏: 随机缓慢漂移

        self._accel_bias += np.random.normal(0, self.bias_drift_rate, 3)

        # 限幅: bias 不超过 0.2 m/s²

        self._accel_bias = np.clip(self._accel_bias, -0.2, 0.2)

        # 随机游走: 白噪声积分

        self._accel_rw += np.random.normal(0, self.rw_std, 3) * dt

        # 限幅: random walk 不超过 0.5 m/s²

        self._accel_rw = np.clip(self._accel_rw, -0.5, 0.5)



    def read_imu(self, quad: Quadrotor3D, dt: float = 0.1):

        """读取IMU (加速度, cm/s²) — 含噪声+零偏+随机游走"""

        from backend.utils.units import mps2_to_cmps2

        self._step_bias_rw(dt)

        truth = quad.get_acceleration()

        noise = (np.random.normal(0, self.imu_noise, 3) +

                 self._accel_bias +

                 self._accel_rw)

        return mps2_to_cmps2(truth + noise)



    def read_optical(self, quad: Quadrotor3D):

        """读取光流位置 (cm)"""

        from backend.utils.units import m_to_cm

        return m_to_cm(quad.get_position()[:2]) + np.random.normal(0, self.opt_noise, 2)



    def read_barometer(self, quad: Quadrotor3D):

        """读取气压计高度 (cm)"""

        from backend.utils.units import m_to_cm

        return m_to_cm(quad.get_position()[2]) + np.random.normal(0, self.bar_noise)



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

