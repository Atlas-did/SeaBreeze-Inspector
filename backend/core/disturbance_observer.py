"""
=============================================================================
扩展卡尔曼滤波器 (EKF) — 12维全状态扰动观测器
=============================================================================

技术选型: 12维全状态EKF (方案A)
  状态: X = [x,y,z, vx,vy,vz, ax,ay,az, dx,dy,dz]^T
  观测: Z = [ax_imu,ay_imu,az_imu, x_opt,y_opt,z_bar]^T

  选择理由:
  1. 笔记本CPU运行NumPy，单次predict+update约0.05-0.2ms
     控制周期100ms(10Hz)，计算资源充足
  2. 4个3×3分块对角结构，物理意义清晰，便于教学
  3. 3维扰动全部独立估计，前馈补偿信号完整

数学模型: 常加速度模型(CA Model) + 扰动随机游走
  状态方程: X_{k+1} = F @ X_k + w_k
  观测方程: Z_k = H @ X_k + v_k  (线性，无需EKF线性化)

自适应Q/R: 当Mahalanobis距离超过阈值时，临时增大Q以更快跟踪突变扰动
=============================================================================
"""

from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

import numpy as np


# =============================================================================
# 状态索引常量（提高代码可读性）
# =============================================================================

# 位置 (索引 0,1,2)
IDX_X, IDX_Y, IDX_Z = 0, 1, 2
# 速度 (索引 3,4,5)
IDX_VX, IDX_VY, IDX_VZ = 3, 4, 5
# 加速度 (索引 6,7,8)
IDX_AX, IDX_AY, IDX_AZ = 6, 7, 8
# 扰动 (索引 9,10,11)
IDX_DX, IDX_DY, IDX_DZ = 9, 10, 11

# 状态维度
STATE_DIM = 12
# 观测维度 (3维IMU加速度 + 2维光流位置 + 1维气压计高度)
MEAS_DIM = 6


class DisturbanceObserverEKF:
    """
    12维扩展卡尔曼滤波器扰动观测器。

    状态向量 (12维):
        [x, y, z, vx, vy, vz, ax, ay, az, dx, dy, dz]^T
        └─位置─┘ └─速度─┘ └─加速度─┘ └─扰动─┘

    观测向量 (6维):
        [ax_imu, ay_imu, az_imu, x_opt, y_opt, z_bar]^T
        └─IMU加速度─┘ └─光流位置─┘ └─气压高度┘

    用法:
        ekf = DisturbanceObserverEKF(dt=0.1)

        # 预测步 (控制周期开始前)
        ekf.predict()

        # 更新步 (传感器数据到达后)
        z = np.array([ax, ay, az, x_pos, y_pos, z_alt])
        ekf.update(z)

        # 获取估计结果
        state = ekf.get_state()
        disturbance = ekf.get_disturbance()
    """

    def __init__(
        self,
        dt: float = 0.1,
        Q: Optional[np.ndarray] = None,
        R: Optional[np.ndarray] = None,
        P0: Optional[np.ndarray] = None,
        enable_adaptive: bool = True,
        adaptive_threshold: float = 12.59,
        adaptive_alpha: float = 0.3,
    ) -> None:
        """
        初始化EKF。

        参数:
            dt: 采样周期 (秒), 默认0.1s对应10Hz控制频率
            Q: 过程噪声协方差矩阵 (12×12), None时使用默认值
            R: 观测噪声协方差矩阵 (6×6), None时使用默认值
            P0: 初始状态协方差矩阵 (12×12), None时使用默认值
            enable_adaptive: 是否启用自适应Q
            adaptive_threshold: Mahalanobis距离阈值
                (χ²₆的95%分位数=12.59, χ²₆的99%分位数=16.81)
            adaptive_alpha: Q增大系数 (0.1-0.5), 越大响应越快但越不稳
        """
        self.dt = dt
        self.enable_adaptive = enable_adaptive
        self.adaptive_threshold = adaptive_threshold
        self.adaptive_alpha = adaptive_alpha

        # -----------------------------------------------------------------
        # 初始化状态转移矩阵 F (12×12)
        # -----------------------------------------------------------------
        # F采用分块对角结构，由4个3×3块组成:
        #   F = [I₃    dt·I₃    ½dt²·I₃   ½dt²·I₃]
        #       [0₃     I₃      dt·I₃     dt·I₃  ]
        #       [0₃     0₃       I₃        0₃    ]
        #       [0₃     0₃       0₃        I₃    ]
        self.F = self._build_state_transition_matrix(dt)

        # -----------------------------------------------------------------
        # 初始化观测矩阵 H (6×12)
        # -----------------------------------------------------------------
        # IMU观测加速度+扰动的叠加 (ax_imu = ax + dx)
        # 光流/气压计观测位置 (x_opt = x)
        self.H = self._build_observation_matrix()

        # -----------------------------------------------------------------
        # 初始化过程噪声协方差 Q (12×12)
        # -----------------------------------------------------------------
        if Q is not None:
            self.Q = Q.copy()
        else:
            # 默认Q: 对角阵，各状态的过程噪声独立
            self.Q = np.diag([
                0.01, 0.01, 0.01,      # 位置噪声 (cm²)
                0.10, 0.10, 0.10,      # 速度噪声 (cm/s)²
                1.00, 1.00, 1.00,      # 加速度噪声 (cm/s²)²
                0.50, 0.50, 0.50,      # 扰动噪声 (cm/s²)²
            ])

        # 保存原始Q（自适应Q时需要用原始值恢复）
        self.Q_base = self.Q.copy()

        # -----------------------------------------------------------------
        # 初始化观测噪声协方差 R (6×6)
        # -----------------------------------------------------------------
        if R is not None:
            self.R = R.copy()
        else:
            # 默认R: IMU噪声较小，光流位置噪声中等，气压计高度噪声较大
            self.R = np.diag([
                0.0025, 0.0025, 0.0025,  # IMU加速度 (0.05 m/s²)²
                4.0, 4.0,                # 光流位置 (2cm)²
                100.0,                   # 气压计高度 (10cm)²
            ])

        # -----------------------------------------------------------------
        # 初始化状态向量 X (12维)
        # -----------------------------------------------------------------
        # 初始状态全部为零（假设从静止开始）
        self.x = np.zeros(STATE_DIM)

        # -----------------------------------------------------------------
        # 初始化状态协方差矩阵 P (12×12)
        # -----------------------------------------------------------------
        if P0 is not None:
            self.P = P0.copy()
        else:
            # 初始不确定度: 位置较确定，速度和加速度较不确定，扰动最不确定
            self.P = np.diag([
                10.0, 10.0, 10.0,       # 位置: ±10cm 不确定
                100.0, 100.0, 100.0,    # 速度: ±100cm/s 不确定
                1000.0, 1000.0, 1000.0, # 加速度: ±1000cm/s² 不确定
                100.0, 100.0, 100.0,    # 扰动: ±100cm/s² 不确定
            ])

        # -----------------------------------------------------------------
        # 上一步的控制输入 (用于update中从IMU观测减去控制量)
        self._last_u: Optional[np.ndarray] = None

        # 运行统计
        # -----------------------------------------------------------------
        self._step_count = 0
        self._last_mahalanobis2 = 0.0
        self._is_adaptive_active = False
        self._timing_history: list[float] = []

    # =========================================================================
    # 矩阵构建
    # =========================================================================

    @staticmethod
    def _build_state_transition_matrix(dt: float) -> np.ndarray:
        """
        构建状态转移矩阵 F (12×12)。

        数学公式 (分块矩阵形式):
            F = [I₃    dt·I₃    ½dt²·I₃   ½dt²·I₃]
                [0₃     I₃      dt·I₃     dt·I₃  ]
                [0₃     0₃       I₃        0₃    ]
                [0₃     0₃       0₃        I₃    ]

        其中 I₃ = 3×3单位矩阵, 0₃ = 3×3零矩阵。
        """
        F = np.eye(STATE_DIM)
        I3 = np.eye(3)

        # 位置 ← 速度:  F[0:3, 3:6] = dt * I₃
        F[0:3, 3:6] = dt * I3

        # 位置 ← 加速度: F[0:3, 6:9] = 0.5 * dt² * I₃
        F[0:3, 6:9] = 0.5 * dt**2 * I3

        # 位置 ← 扰动:  F[0:3, 9:12] = 0.5 * dt² * I₃
        F[0:3, 9:12] = 0.5 * dt**2 * I3

        # 速度 ← 加速度: F[3:6, 6:9] = dt * I₃
        F[3:6, 6:9] = dt * I3

        # 速度 ← 扰动:  F[3:6, 9:12] = dt * I₃
        F[3:6, 9:12] = dt * I3

        return F

    @staticmethod
    def _build_observation_matrix() -> np.ndarray:
        """
        构建观测矩阵 H (6×12)。

        观测模型 (线性):
            ax_imu = ax + dx   → H[0, 6]=1, H[0, 9]=1
            ay_imu = ay + dy   → H[1, 7]=1, H[1,10]=1
            az_imu = az + dz   → H[2, 8]=1, H[2,11]=1
            x_opt  = x         → H[3, 0]=1
            y_opt  = y         → H[4, 1]=1
            z_bar  = z         → H[5, 2]=1

        维度: 6×12 (6个观测 × 12个状态)
        """
        H = np.zeros((MEAS_DIM, STATE_DIM))

        # IMU加速度观测: ax_imu = ax + dx
        H[0, IDX_AX] = 1.0   # ax
        H[0, IDX_DX] = 1.0   # dx

        # IMU加速度观测: ay_imu = ay + dy
        H[1, IDX_AY] = 1.0   # ay
        H[1, IDX_DY] = 1.0   # dy

        # IMU加速度观测: az_imu = az + dz
        H[2, IDX_AZ] = 1.0   # az
        H[2, IDX_DZ] = 1.0   # dz

        # 光流位置观测: x_opt = x
        H[3, IDX_X] = 1.0

        # 光流位置观测: y_opt = y
        H[4, IDX_Y] = 1.0

        # 气压计高度观测: z_bar = z
        H[5, IDX_Z] = 1.0

        return H

    # =========================================================================
    # 预测步 (Predict)
    # =========================================================================

    def predict(self, u: Optional[np.ndarray] = None) -> np.ndarray:
        """
        EKF预测步。

        数学公式:
            x̂ₖ₋ = F @ x̂ₖ₋₁₊          (状态预测)
            Pₖ₋ = F @ Pₖ₋₁₊ @ Fᵀ + Q  (协方差预测)

        参数:
            u: 控制输入 (3维控制加速度, cm/s²), 默认None。
               如果提供, 将其设为已知加速度状态,
               使EKF能从 IMU - u 中分离出扰动估计。
               原理: IMU观测 = ax + dx = u + dx → dx = IMU - u

        返回:
            预测后的状态向量 (12维)
        """
        # 保存控制输入供update使用
        self._last_u = np.asarray(u, dtype=float) if u is not None else None

        # 如果有控制输入, 设置加速度状态为已知控制值
        if u is not None and len(u) >= 3:
            self.x[IDX_AX:IDX_AX+3] = u[:3]

        # 状态预测: x_pred = F @ x
        self.x = self.F @ self.x

        # 协方差预测: P_pred = F @ P @ F.T + Q
        self.P = self.F @ self.P @ self.F.T + self.Q

        # 如果有控制输入, 压缩加速度状态的协方差
        # 相当于告诉EKF: "ax=u 几乎是确定已知的, IMU残差全归因于扰动dx"
        if u is not None and len(u) >= 3:
            self.P[IDX_AX, IDX_AX] = 0.01
            self.P[IDX_AY, IDX_AY] = 0.01
            self.P[IDX_AZ, IDX_AZ] = 0.01
            for i in range(STATE_DIM):
                if i != IDX_AX:
                    self.P[IDX_AX, i] = 0.0
                    self.P[i, IDX_AX] = 0.0
                if i != IDX_AY:
                    self.P[IDX_AY, i] = 0.0
                    self.P[i, IDX_AY] = 0.0
                if i != IDX_AZ:
                    self.P[IDX_AZ, i] = 0.0
                    self.P[i, IDX_AZ] = 0.0

        # 确保P对称正定 (数值稳定性)
        self.P = 0.5 * (self.P + self.P.T)

        self._step_count += 1
        return self.x.copy()

    # =========================================================================
    # 更新步 (Update)
    # =========================================================================

    def update(self, z: np.ndarray) -> np.ndarray:
        """
        EKF更新步。

        数学公式:
            ỹ = z - H @ x̂ₖ₋              (残差/新息)
            S = H @ Pₖ₋ @ Hᵀ + R         (残差协方差)
            K = Pₖ₋ @ Hᵀ @ S⁻¹            (卡尔曼增益)
            x̂ₖ₊ = x̂ₖ₋ + K @ ỹ            (状态更新)
            Pₖ₊ = (I - K @ H) @ Pₖ₋      (协方差更新)

        参数:
            z: 观测向量 (6维)
               [ax_imu, ay_imu, az_imu, x_opt, y_opt, z_barometer]

        返回:
            更新后的状态向量 (12维)
        """
        z = np.asarray(z, dtype=float)
        if z.shape != (MEAS_DIM,):
            raise ValueError(f"观测向量维度错误: 期望({MEAS_DIM},), 得到{z.shape}")

        # 如果有控制输入, 从IMU观测中减去已知控制量
        z_adjusted = z.copy()
        if self._last_u is not None and len(self._last_u) >= 3:
            z_adjusted[0:3] -= self._last_u[0:3]

        # 预测观测: z_pred = H @ x
        z_pred = self.H @ self.x
        if self._last_u is not None and len(self._last_u) >= 3:
            # IMU预测 = dx_pred (ax部分已在z_adjusted中减去)
            z_pred[0:3] = self.x[IDX_DX:IDX_DX+3]

        # 残差 (新息): y_tilde = z_adjusted - z_pred
        y_tilde = z_adjusted - z_pred

        # 残差协方差: S = H @ P @ H.T + R
        S = self.H @ self.P @ self.H.T + self.R

        # 自适应Q: 检测残差异常
        if self.enable_adaptive:
            self._adaptive_Q_adjustment(y_tilde, S)

        # 卡尔曼增益: K = P @ H.T @ S^{-1}
        # 使用np.linalg.solve避免显式求逆 (数值更稳定)
        # K = P @ H.T @ inv(S)  →  K.T = inv(S) @ H @ P.T
        # 等价于解线性方程组: S @ K.T = H @ P.T
        try:
            K_T = np.linalg.solve(S, self.H @ self.P.T)
            K = K_T.T
        except np.linalg.LinAlgError:
            # S奇异时使用伪逆
            K = self.P @ self.H.T @ np.linalg.pinv(S)

        # 状态更新: x = x + K @ y_tilde
        self.x = self.x + K @ y_tilde

        # 协方差更新 (Joseph形式, 数值更稳定):
        # P = (I - K @ H) @ P @ (I - K @ H).T + K @ R @ K.T
        I_KH = np.eye(STATE_DIM) - K @ self.H
        self.P = I_KH @ self.P @ I_KH.T + K @ self.R @ K.T

        # 确保P对称正定
        self.P = 0.5 * (self.P + self.P.T)

        return self.x.copy()

    # =========================================================================
    # 自适应Q机制
    # =========================================================================

    def _adaptive_Q_adjustment(
        self, y_tilde: np.ndarray, S: np.ndarray
    ) -> None:
        """
        自适应Q调整: 当Mahalanobis距离超过阈值时临时增大Q。

        数学原理:
            D² = ỹᵀ @ S^{-1} @ ỹ   (Mahalanobis距离)
            D² ~ χ²₆ (自由度6的卡方分布)
            阈值: χ²₆(0.95) = 12.59

            if D² > threshold:
                scale = 1 + α * (D²/threshold - 1)
                Q = Q_base * scale
            else:
                Q = Q_base  (恢复正常)

        参数:
            y_tilde: 残差向量 (6维)
            S: 残差协方差矩阵 (6×6)
        """
        try:
            # Mahalanobis距离: D² = y_tilde.T @ inv(S) @ y_tilde
            # 使用solve避免显式求逆
            D2 = float(y_tilde @ np.linalg.solve(S, y_tilde))
        except (np.linalg.LinAlgError, ValueError):
            D2 = 0.0

        self._last_mahalanobis2 = D2

        if D2 > self.adaptive_threshold:
            # 残差异常: 增大Q使滤波器更快跟踪
            scale = 1.0 + self.adaptive_alpha * (
                D2 / self.adaptive_threshold - 1.0
            )
            # 限制最大scale (防止Q过大导致滤波器发散)
            scale = min(scale, 10.0)
            self.Q = self.Q_base * scale
            self._is_adaptive_active = True
        else:
            # 残差正常: 恢复原始Q
            self.Q = self.Q_base.copy()
            self._is_adaptive_active = False

    # =========================================================================
    # 便捷查询方法
    # =========================================================================

    def get_state(self) -> Dict[str, np.ndarray]:
        """
        获取当前完整状态估计。

        返回:
            {
                "position": [x, y, z] (cm),
                "velocity": [vx, vy, vz] (cm/s),
                "acceleration": [ax, ay, az] (cm/s²),
                "disturbance": [dx, dy, dz] (cm/s²),
                "full_state": 12维完整向量,
            }
        """
        return {
            "position": self.x[IDX_X:IDX_X+3].copy(),
            "velocity": self.x[IDX_VX:IDX_VX+3].copy(),
            "acceleration": self.x[IDX_AX:IDX_AX+3].copy(),
            "disturbance": self.x[IDX_DX:IDX_DX+3].copy(),
            "full_state": self.x.copy(),
        }

    def get_disturbance(self) -> np.ndarray:
        """
        获取扰动估计值 (3维)。

        返回:
            [dx, dy, dz] 扰动等效加速度 (cm/s²)
        """
        return self.x[IDX_DX:IDX_DX+3].copy()

    def get_position(self) -> np.ndarray:
        """获取位置估计 (3维, cm)"""
        return self.x[IDX_X:IDX_X+3].copy()

    def get_velocity(self) -> np.ndarray:
        """获取速度估计 (3维, cm/s)"""
        return self.x[IDX_VX:IDX_VX+3].copy()

    def get_covariance(self) -> np.ndarray:
        """获取状态协方差矩阵 P (12×12)"""
        return self.P.copy()

    def get_disturbance_covariance(self) -> np.ndarray:
        """获取扰动估计的协方差 (3×3)"""
        return self.P[IDX_DX:IDX_DX+3, IDX_DX:IDX_DX+3].copy()

    # =========================================================================
    # 调试信息
    # =========================================================================

    @property
    def mahalanobis_distance(self) -> float:
        """上一次的Mahalanobis距离"""
        return float(np.sqrt(max(0, self._last_mahalanobis2)))

    @property
    def is_adaptive_active(self) -> bool:
        """自适应Q是否当前激活"""
        return self._is_adaptive_active

    @property
    def step_count(self) -> int:
        """已执行的步数"""
        return self._step_count

    def reset(self) -> None:
        """重置EKF到初始状态"""
        self.x = np.zeros(STATE_DIM)
        self.P = np.diag([
            10.0, 10.0, 10.0,
            100.0, 100.0, 100.0,
            1000.0, 1000.0, 1000.0,
            100.0, 100.0, 100.0,
        ])
        self.Q = self.Q_base.copy()
        self._step_count = 0
        self._last_mahalanobis2 = 0.0
        self._is_adaptive_active = False
        self._timing_history.clear()

    def timing_report(self) -> Dict[str, float]:
        """返回运行时间统计"""
        if not self._timing_history:
            return {"mean_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0, "count": 0}
        arr = np.array(self._timing_history) * 1000  # 转毫秒
        return {
            "mean_ms": float(np.mean(arr)),
            "min_ms": float(np.min(arr)),
            "max_ms": float(np.max(arr)),
            "count": len(arr),
        }
