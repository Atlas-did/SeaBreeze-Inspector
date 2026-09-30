"""外部定位 (审计 P0-B)。

对外契约见 base.py; 可用实现:
  * ArucoLocalizationSource   —— 机载相机 + ArUco 标记 (真实可用)
  * GroundTruthLocalizationSource —— 注入式真值 (仿真/HIL/接线验证)

cv2 不可用时, 包仍可导入, 只是不导出 ArUco 源。
"""

from .base import (
    MAX_AGE_S,
    MIN_QUALITY,
    LocalizationObservation,
    LocalizationSource,
)
from .ground_truth_source import GroundTruthLocalizationSource

try:  # opencv 是可选的: 无相机/无 cv2 的环境仍能使用真值源与契约
    from .aruco_source import ArucoLocalizationSource
except ImportError:  # pragma: no cover - 仅在无 opencv 环境下触发
    ArucoLocalizationSource = None  # type: ignore[assignment]

__all__ = [
    "MAX_AGE_S",
    "MIN_QUALITY",
    "LocalizationObservation",
    "LocalizationSource",
    "GroundTruthLocalizationSource",
    "ArucoLocalizationSource",
]
