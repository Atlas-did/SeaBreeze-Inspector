"""外部定位源统一契约 (审计 P0-B)。

工程约定 (与 backend/main.py 的 current_pos 一致):
  * 位置单位: 厘米 cm;  坐标系: z-up (position[2] = 高度)
  * 时间戳: time.monotonic() 秒 (单调时钟, 不受系统时间跳变影响)

铁律: 送入位置环的观测必须同时携带 时间戳 + 质量分 + 有效期。
否则下游无法区分"真实外部定位"与"上一帧 EKF 估计的自我循环"
(真机 _get_sensor_data 把 current_pos 当光流输入即是后者)。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import time

import numpy as np

# ---------------------------------------------------------------------------
# 阈值 (模块常量, 取值理由见下)
# ---------------------------------------------------------------------------
# MAX_AGE_S = 0.3 s: 主控循环 dt = 0.1 s (10 Hz, backend/main.py)。
#   3 个控制周期是位置环可用性的上限 —— 以 100 cm/s 速度上限计, 0.3 s 的
#   陈旧坐标意味着真值已漂移 > 30 cm, 继续闭环会把无人机追向错误目标。
#   下限由传感器速率给出: Tello 视频约 30 fps (33 ms/帧), 0.3 s 留 9 帧余量,
#   足以覆盖抖动/丢帧, 又不会放过真正的链路中断。
MAX_AGE_S = 0.3

# MIN_QUALITY = 0.3: ArUco 质量分 = 重投影误差项 × 标记数项 (见 aruco_source)。
#   0.3 约等于"单标记(0.5) + 重投影误差 4.5 px" 或 "双标记 + 7 px"; 更差
#   说明角点已不可信, 必须回退到不依赖位置的自动状态。
MIN_QUALITY = 0.3


@dataclass
class LocalizationObservation:
    """一次外部定位观测 (cm, z-up)。

    position: 长度 3 的 np.ndarray, 单位 cm, z-up
    timestamp: time.monotonic() 秒; 传 None 则取当前时刻
    quality: 0..1 的可解释置信度 (0 = 不可用)
    source: 产生该观测的源名称
    """

    position: np.ndarray
    timestamp: Optional[float] = None
    quality: float = 0.0
    source: str = "unknown"

    def __post_init__(self) -> None:
        # 只做规范化, 不抛异常: nan/维度错误由 is_usable() 判为不可用,
        # 让"坏观测"和"没有观测"在类型上可区分。
        self.position = np.asarray(self.position, dtype=float).ravel()
        if self.timestamp is None:
            self.timestamp = time.monotonic()
        self.timestamp = float(self.timestamp)
        self.quality = float(self.quality)
        self.source = str(self.source)

    def age(self, now: Optional[float] = None) -> float:
        """观测年龄 (s, >=0 表示来自过去)。"""
        return (time.monotonic() if now is None else float(now)) - self.timestamp

    def is_finite(self) -> bool:
        """维度为 3 且三轴全部有限 (nan/inf 一律视为无效)。"""
        return self.position.shape == (3,) and bool(np.all(np.isfinite(self.position)))

    def is_usable(self, max_age_s: float = MAX_AGE_S,
                  min_quality: float = MIN_QUALITY,
                  now: Optional[float] = None) -> bool:
        """统一判定: 维度/有限性 + 质量分 + 有效期, 三者全过才算可用。"""
        if not self.is_finite():
            return False
        if not np.isfinite(self.quality) or self.quality < min_quality:
            return False
        age = self.age(now)
        return bool(np.isfinite(age) and 0.0 <= age <= max_age_s)

    def to_dict(self) -> dict:
        return {"position": self.position.tolist(),
                "timestamp": self.timestamp,
                "quality": self.quality,
                "source": self.source}


class LocalizationSource(ABC):
    """外部定位源接口。

    实现只需提供 read(); is_healthy() 默认基于 read() 的最新观测判定。
    read() 返回 None 表示"本帧没有可信观测" —— 绝不允许返回占位坐标。
    """

    name = "localization-source"

    @abstractmethod
    def read(self) -> Optional[LocalizationObservation]:
        """返回最新观测, 或 None (无观测/解算失败)。"""
        raise NotImplementedError

    def is_healthy(self, max_age_s: float = MAX_AGE_S) -> bool:
        """最新观测是否新鲜且质量达标 (False = 禁止依赖位置的自动状态)。"""
        obs = self.read()
        return obs is not None and obs.is_usable(max_age_s=max_age_s)
