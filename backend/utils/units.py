"""
统一单位转换工具 — 消灭项目中的 100×/10× 手工转换错误

本项目使用三套单位体系:
  - 仿真 (simulation/models.py): 米 (m)
  - EKF/Controller (core/):          厘米 (cm)  ← 推荐内部统一使用
  - 机械臂 (arm/):                   毫米 (mm)

所有跨模块转换都应通过本模块的函数, 禁止手工乘除。
"""

from typing import Union, List

import numpy as np

# =============================================================================
# 长度转换
# =============================================================================

def m_to_cm(val: Union[float, np.ndarray, List]) -> Union[float, np.ndarray]:
    """米 → 厘米"""
    return np.asarray(val, dtype=float) * 100.0

def cm_to_m(val: Union[float, np.ndarray, List]) -> Union[float, np.ndarray]:
    """厘米 → 米"""
    return np.asarray(val, dtype=float) / 100.0

def mm_to_cm(val: Union[float, np.ndarray, List]) -> Union[float, np.ndarray]:
    """毫米 → 厘米"""
    return np.asarray(val, dtype=float) / 10.0

def cm_to_mm(val: Union[float, np.ndarray, List]) -> Union[float, np.ndarray]:
    """厘米 → 毫米"""
    return np.asarray(val, dtype=float) * 10.0

def m_to_mm(val: Union[float, np.ndarray, List]) -> Union[float, np.ndarray]:
    """米 → 毫米"""
    return np.asarray(val, dtype=float) * 1000.0

def mm_to_m(val: Union[float, np.ndarray, List]) -> Union[float, np.ndarray]:
    """毫米 → 米"""
    return np.asarray(val, dtype=float) / 1000.0


# =============================================================================
# 速度/加速度转换
# =============================================================================

def mps_to_cmps(val: Union[float, np.ndarray, List]) -> Union[float, np.ndarray]:
    """m/s → cm/s"""
    return np.asarray(val, dtype=float) * 100.0

def cmps_to_mps(val: Union[float, np.ndarray, List]) -> Union[float, np.ndarray]:
    """cm/s → m/s"""
    return np.asarray(val, dtype=float) / 100.0

def mps2_to_cmps2(val: Union[float, np.ndarray, List]) -> Union[float, np.ndarray]:
    """m/s² → cm/s²"""
    return np.asarray(val, dtype=float) * 100.0

def cmps2_to_mps2(val: Union[float, np.ndarray, List]) -> Union[float, np.ndarray]:
    """cm/s² → m/s²"""
    return np.asarray(val, dtype=float) / 100.0
