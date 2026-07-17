"""
=============================================================================
前馈补偿控制器 — PID反馈 + 扰动前馈
=============================================================================

技术选型:
  底层接口: send_rc_control速度指令 (模式B)
    - 连续控制, 10Hz定时发送, 适合闭环跟踪
    - 串级结构: 位置环输出速度指令 → Tello SDK
    - WiFi延迟100-200ms用"低通滤波+预测补偿"策略

控制框图:
                    ┌─────────┐
  target_pos ──────→│  位置环  │ (PID)
                    │  e→v_cmd │
                    └────┬────┘
                         v
  ┌────────────────────────────────────────┐
  │  v_cmd = Kp*e + Ki*∫e + Kd*ė + Kff*d │
  │         + 前馈补偿(扰动估计)            │
  └────────────────────────────────────────┘
                         │
                    ┌────┴────┐
                    │  限幅    │ [-100, 100]
                    └────┬────┘
                         v
                    ┌─────────┐
  disturbance ──────→│  前馈项  │ Kff * d_est
  (from EKF)        └────┬────┘
                         │
                    ┌────┴──────────┐
                    │ send_rc_control │ → Tello
                    │ (lr, fb, ud, 0) │
                    └─────────────────┘

参数来源: config/drone_config.yaml
=============================================================================
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np


class FeedforwardController:
    """
    PID反馈 + 扰动前馈补偿控制器。

    控制律:
        v_cmd = Kp * e + Ki * ∫e + Kd * ė + Kff * d_est

    其中:
        e = target_pos - current_pos    (位置误差)
        ∫e 为积分项 (累积误差)
        ė = -current_vel                (误差变化率, 假设目标静止)
        d_est = 扰动估计 (来自EKF)
        v_cmd 为输出速度指令 (cm/s)

    输出限幅: [-max_speed, max_speed] (默认±100 cm/s, 对应Tello SDK的±100)
    死区: |e| < 2cm 时视为到位, 输出0
    """

    def __init__(
        self,
        Kp: float = 2.0,
        Ki: float = 0.1,
        Kd: float = 1.0,
        Kff: float = -1.0,
        dt: float = 0.1,
        max_speed: float = 100.0,
        dead_zone: float = 2.0,
        integral_limit: float = 50.0,
        enable_ff: bool = True,
    ) -> None:
        """
        初始化控制器。

        参数:
            Kp: 比例增益
            Ki: 积分增益
            Kd: 微分增益
            Kff: 前馈增益 (扰动补偿系数, -1.0表示完全补偿: v_cmd -= d_est)
            dt: 控制周期 (秒)
            max_speed: 输出速度上限 (cm/s, Tello SDK范围为-100~100)
            dead_zone: 死区阈值 (cm), |e|<dead_zone视为到位
            integral_limit: 积分上限 (防止积分饱和)
            enable_ff: 是否启用前馈补偿
        """
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.Kff = Kff
        self.dt = dt
        self.max_speed = max_speed
        self.dead_zone = dead_zone
        self.integral_limit = integral_limit
        self.enable_ff = enable_ff

        # 积分项 (3维: x, y, z)
        self.integral = np.zeros(3)

        # 上一步误差 (用于微分计算)
        self.prev_error = np.zeros(3)

        # 上一步是否饱和 (用于积分抗饱和)
        self._was_saturated = False

    def compute(
        self,
        target_pos: np.ndarray,
        current_pos: np.ndarray,
        disturbance_est: Optional[np.ndarray] = None,
        current_vel: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, Dict]:
        """
        计算控制输出。

        参数:
            target_pos: 目标位置 (3维, cm)
            current_pos: 当前位置 (3维, cm)
            disturbance_est: 扰动估计 (3维, cm/s²), 来自EKF
            current_vel: 当前速度 (3维, cm/s), 用于微分项

        返回:
            (control_output, info_dict)
            - control_output: 速度指令 (3维, cm/s), 已限幅
            - info_dict: 调试信息字典
        """
        target_pos = np.asarray(target_pos, dtype=float)
        current_pos = np.asarray(current_pos, dtype=float)

        # 1. 计算位置误差
        error = target_pos - current_pos

        # 2. 死区处理: 误差<2cm视为已到位
        if np.linalg.norm(error) < self.dead_zone:
            return np.zeros(3), {
                "error": error,
                "dead_zone_active": True,
                "pid_output": np.zeros(3),
                "ff_output": np.zeros(3),
                "total_output": np.zeros(3),
            }

        # 3. PID项计算
        # 比例项: Kp * e
        P_term = self.Kp * error

        # 积分项: Ki * ∫e (梯形积分)
        if not self._was_saturated:
            # 抗饱和: 只有输出未饱和时才累加积分
            self.integral += error * self.dt
            # 积分限幅
            self.integral = np.clip(
                self.integral, -self.integral_limit, self.integral_limit
            )
        I_term = self.Ki * self.integral

        # 微分项: Kd * ė = Kd * (-vel) (假设目标速度为0)
        if current_vel is not None:
            vel = np.asarray(current_vel, dtype=float)
            D_term = -self.Kd * vel
        else:
            # 用误差差分近似
            D_term = self.Kd * (error - self.prev_error) / self.dt

        pid_output = P_term + I_term + D_term

        # 4. 前馈补偿项: Kff * d_est
        ff_output = np.zeros(3)
        if self.enable_ff and disturbance_est is not None:
            d_est = np.asarray(disturbance_est, dtype=float)
            ff_output = self.Kff * d_est

        # 5. 总输出
        total_output = pid_output + ff_output

        # 6. 输出限幅
        output_norm = np.linalg.norm(total_output)
        if output_norm > self.max_speed:
            # 等比例缩放, 保持方向不变
            total_output = total_output * (self.max_speed / output_norm)
            self._was_saturated = True
        else:
            self._was_saturated = False

        # 保存误差用于下一步微分
        self.prev_error = error.copy()

        info = {
            "error": error.copy(),
            "P_term": P_term,
            "I_term": I_term,
            "D_term": D_term,
            "pid_output": pid_output,
            "ff_output": ff_output,
            "total_output": total_output.copy(),
            "dead_zone_active": False,
            "saturated": self._was_saturated,
        }

        return total_output, info

    def reset(self) -> None:
        """重置控制器状态 (积分项、误差历史)"""
        self.integral = np.zeros(3)
        self.prev_error = np.zeros(3)
        self._was_saturated = False

    @classmethod
    def from_config(cls, config=None) -> "FeedforwardController":
        """从 drone_config.yaml 加载控制器参数

        用法:
            ctrl = FeedforwardController.from_config()          # 自动加载 config
            ctrl = FeedforwardController.from_config(cfg_obj)   # 传入 Config 对象
        """
        if config is None:
            try:
                from backend.utils.config import ConfigLoader
                config = ConfigLoader.load("drone_config")
            except Exception:
                config = None

        # 辅助函数: 安全取嵌套属性
        def _get(cfg, path, default):
            if cfg is None:
                return default
            try:
                keys = path.split(".")
                val = cfg
                for k in keys:
                    val = getattr(val, k)
                return val
            except (AttributeError, KeyError):
                return default

        return cls(
            Kp=_get(config, "controller.Kp", 2.0),
            Ki=_get(config, "controller.Ki", 0.1),
            Kd=_get(config, "controller.Kd", 1.0),
            Kff=-1.0,
            dt=_get(config, "flight.hover_stabilize_time", 2.0) / 20.0,
            max_speed=_get(config, "flight.max_speed", 50),
        )
