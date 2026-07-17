"""
数字滤波器 — 对标 Betaflight 的 PT1 低通 + 积分分离

PT1Filter: 一阶低通, y[n] = y[n-1] + alpha * (x[n] - y[n-1])
  用于 D 项滤波, 抑制高频噪声放大

积分分离: 误差大时关闭 I 项, 防止积分饱和 (windup)
"""

import numpy as np


class PT1Filter:
    """一阶低通滤波器 (指数平滑)

    cutoff_hz: 截止频率 (Hz)
    dt: 采样周期 (s)
    """

    def __init__(self, cutoff_hz: float = 20.0, dt: float = 0.1):
        self.dt = dt
        self.set_cutoff(cutoff_hz)
        self._value = 0.0

    def set_cutoff(self, cutoff_hz: float):
        """动态修改截止频率"""
        # alpha = 2 * pi * dt * f_cut / (2 * pi * dt * f_cut + 1)
        rc = 1.0 / (2.0 * np.pi * max(cutoff_hz, 0.01))
        self.alpha = self.dt / (rc + self.dt)

    def update(self, value: float) -> float:
        """输入新值, 返回滤波后输出"""
        self._value = self._value + self.alpha * (value - self._value)
        return self._value

    def reset(self, value: float = 0.0):
        """重置滤波器状态"""
        self._value = value


class IntegralSeparator:
    """积分分离器 — 误差大时冻结积分项

    threshold: 误差超过此值则关闭积分
    """

    def __init__(self, threshold: float = 50.0):
        self.threshold = threshold
        self._frozen = False

    def should_integrate(self, error_magnitude: float) -> bool:
        """检查是否应该累加积分"""
        self._frozen = error_magnitude > self.threshold
        return not self._frozen

    @property
    def is_frozen(self) -> bool:
        return self._frozen


def apply_integral_separation(error: np.ndarray, integral: np.ndarray,
                               threshold: float = 50.0) -> np.ndarray:
    """对3维误差向量应用积分分离

    返回: 分离后的积分项 (冻结位置的对应分量为0)
    """
    result = integral.copy()
    for i in range(3):
        if abs(error[i]) > threshold:
            result[i] = 0.0
    return result
