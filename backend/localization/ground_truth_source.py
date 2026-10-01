"""注入式真值定位源 (审计 P0-B): 仿真 / HIL / 接线验证用。

用途:
  * 把仿真器(或 HIL 台架)已知的真实位置注入真机接口路径, 端到端验证
    "main.py 是否真的把外部定位用在位置环上", 而不需要相机与标记。
  * quality 恒为 1.0 (真值无观测误差), 但时间戳仍受有效期约束 —— 下游的
    有效期判定必须同样作用于真值源, 否则接线验证会掩盖 staleness 缺陷。

时效语义 (CI win/3.11 回归):
  真值 = "此刻的真值"。每次 read() 都按**读取时刻**生成观测, 源对象里不保存
  任何一次性的旧观测, 因此"源创建很久之后才读"不构成过期; 观测年龄只从读取
  时刻起算 (见 test_ground_truth_source_contract)。
  时间戳只要求**单调不减且不超前于时钟**, 见 _now()。
"""

from typing import Callable, Optional, Sequence
import time

import numpy as np

from .base import MAX_AGE_S, LocalizationObservation, LocalizationSource


class GroundTruthLocalizationSource(LocalizationSource):
    """注入式真值位置源。

    position_cm: 初始真值 (cm, z-up)
    provider:    可选回调 () -> 长度 3 的位置 (cm); 给定时优先于 position_cm
                 (HIL 场景: 每个控制周期向仿真器拉当前真值); 返回 None 表示
                 此刻拿不到真值 -> read() 返回 None, 绝不编造坐标
    jitter_cm:   可选高斯噪声标准差 (cm), 用于验证下游的质量/滤波链路;
                 默认 0.0 = 纯真值
    now_fn:      可选时钟 () -> 秒(单调); 默认 time.monotonic。测试可注入以
                 摆脱墙钟/平台时钟粒度, 生产调用方无需传。
    """

    name = "ground-truth"

    def __init__(self, position_cm: Sequence[float] = (0.0, 0.0, 0.0),
                 provider: Optional[Callable[[], Sequence[float]]] = None,
                 jitter_cm: float = 0.0, seed: Optional[int] = None,
                 now_fn: Optional[Callable[[], float]] = None):
        self._position = np.asarray(position_cm, dtype=float).ravel()
        self._provider = provider
        self._jitter = float(jitter_cm)
        self._rng = np.random.default_rng(seed)
        self._now_fn = now_fn
        self._last_ts: Optional[float] = None

    def set_position(self, position_cm: Sequence[float]) -> None:
        """更新真值 (单位 cm, z-up)。"""
        self._position = np.asarray(position_cm, dtype=float).ravel()

    def _now(self) -> float:
        """读取时刻的时间戳: 不倒退, 且不超前于时钟。

        旧实现对同一次时钟读数强制 +1e-6 以制造"严格单调", 在粗粒度单调时钟
        上 (CPython <= 3.12 / Windows GetTickCount64, 粒度约 15.6 ms) 会让同一
        tick 内连续 read() 的时间戳跑到当前时刻之**后** => age < 0 =>
        is_usable() 把最新鲜的真值判为不可用 (CI: win-latest/3.11 上
        LOCALIZATION_UNAVAILABLE; ubuntu 时钟为 ns 粒度故不触发)。
        基类的 is_usable() 要求 0 <= age, 因此这里只保证**不倒退**:
        同一 tick 内两次读取可以给出相同时间戳 (age == 0, 仍然可用),
        这是与墙钟粒度无关的正确语义。
        """
        now = float(time.monotonic() if self._now_fn is None else self._now_fn())
        if self._last_ts is not None and now < self._last_ts:
            now = self._last_ts      # 时钟回拨: 不退步(超前的观测由 is_usable 拒掉)
        self._last_ts = now
        return now

    def read(self) -> Optional[LocalizationObservation]:
        """返回**读取时刻**的真值观测 (quality = 1.0, 时间戳不倒退)。

        每次调用都新建观测: 没有任何"构造期快照"会随时间过期。
        """
        raw = self._provider() if self._provider is not None else self._position
        if raw is None:
            return None                      # 此刻拿不到真值: 返回"没有观测"
        position = np.asarray(raw, dtype=float).ravel().copy()
        if self._jitter > 0 and position.shape == (3,):
            position = position + self._rng.normal(0.0, self._jitter, size=3)
        return LocalizationObservation(position=position, timestamp=self._now(),
                                       quality=1.0, source=self.name)

    def is_healthy(self, max_age_s: float = MAX_AGE_S) -> bool:
        """最新真值观测是否新鲜且质量达标 (用本源的时钟判定年龄)。

        now_fn 未注入时与基类逐字等价 (同为 time.monotonic()); 注入时钟时
        必须用同一个时钟算 age, 否则"可注入时钟"只做了一半。
        """
        obs = self.read()
        return obs is not None and obs.is_usable(max_age_s=max_age_s, now=self._now())
