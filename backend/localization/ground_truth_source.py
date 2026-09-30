"""注入式真值定位源 (审计 P0-B): 仿真 / HIL / 接线验证用。

用途:
  * 把仿真器(或 HIL 台架)已知的真实位置注入真机接口路径, 端到端验证
    "main.py 是否真的把外部定位用在位置环上", 而不需要相机与标记。
  * quality 恒为 1.0 (真值无观测误差), 但时间戳仍严格单调 —— 下游的
    有效期判定必须同样作用于真值源, 否则接线验证会掩盖 staleness 缺陷。
"""

from typing import Callable, Optional, Sequence
import time

import numpy as np

from .base import LocalizationObservation, LocalizationSource


class GroundTruthLocalizationSource(LocalizationSource):
    """注入式真值位置源。

    position_cm: 初始真值 (cm, z-up)
    provider:    可选回调 () -> 长度 3 的位置 (cm); 给定时优先于 position_cm
                 (HIL 场景: 每个控制周期向仿真器拉当前真值)
    jitter_cm:   可选高斯噪声标准差 (cm), 用于验证下游的质量/滤波链路;
                 默认 0.0 = 纯真值
    """

    name = "ground-truth"

    def __init__(self, position_cm: Sequence[float] = (0.0, 0.0, 0.0),
                 provider: Optional[Callable[[], Sequence[float]]] = None,
                 jitter_cm: float = 0.0, seed: Optional[int] = None):
        self._position = np.asarray(position_cm, dtype=float).ravel()
        self._provider = provider
        self._jitter = float(jitter_cm)
        self._rng = np.random.default_rng(seed)
        self._last_ts: Optional[float] = None

    def set_position(self, position_cm: Sequence[float]) -> None:
        """更新真值 (单位 cm, z-up)。"""
        self._position = np.asarray(position_cm, dtype=float).ravel()

    def _now(self) -> float:
        """严格单调的时间戳: 单调时钟 + 不小于上一次 + 1e-6 s。

        同一时钟两次调用可能取到相同值 (尤其 Windows 上时钟粒度较大),
        加上下界保证下游"时间戳必须单调"的假设在任何平台都成立。
        """
        ts = time.monotonic()
        if self._last_ts is not None and ts <= self._last_ts:
            ts = self._last_ts + 1e-6
        self._last_ts = ts
        return ts

    def read(self) -> LocalizationObservation:
        """返回当前真值观测 (quality = 1.0, 时间戳严格单调)。"""
        raw = self._provider() if self._provider is not None else self._position
        position = np.asarray(raw, dtype=float).ravel().copy()
        if self._jitter > 0 and position.shape == (3,):
            position = position + self._rng.normal(0.0, self._jitter, size=3)
        return LocalizationObservation(position=position, timestamp=self._now(),
                                       quality=1.0, source=self.name)
