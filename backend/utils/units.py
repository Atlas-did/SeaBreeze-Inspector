"""
统一单位与坐标系工具 — 消灭项目中的 100×/10× 手工转换错误

=============================================================================
全项目约定 (铁律 #3, 2026-07 重构确立)
=============================================================================

长度/速度单位:
  - 后端内部 (mission/core/EKF/controller):   厘米 cm, cm/s     ← 内部唯一
  - 仿真物理 (simulation/models.py):           米 m, m/s          ← Phase 2 起
  - 机械臂 (arm/):                             毫米 mm
  - Web 前端边界 (api 层):                     米 m, m/s

坐标系 ("上"方向):
  - 后端/仿真:  z-up, 高度 = pos[2]   ← Phase 2 起统一 (Quadrotor3D 将改为 z-up)
  - Web 前端 (three.js): y-up, 高度 = pos[1]
  - 边界转换只在 api 层做, 用 yup_m_to_zup_cm() / zup_cm_to_yup_m()

  ⚠️ 历史遗留: 当前 Quadrotor3D 内部是 y-up (高度=pos[1]), Phase 2 会翻转为 z-up。
     在 Phase 2 完成前, 仿真→后端的注入点仍按各仿真现有手工约定处理,
     新代码一律按 z-up 写。

所有跨模块转换必须经过本模块函数, 禁止手工乘除 (发现即 code review 打回)。
=============================================================================
"""

from typing import List, Union

import numpy as np

Vec = Union[float, np.ndarray, List]


# =============================================================================
# 长度转换
# =============================================================================

def m_to_cm(val: Vec) -> Union[float, np.ndarray]:
    """米 → 厘米"""
    return np.asarray(val, dtype=float) * 100.0

def cm_to_m(val: Vec) -> Union[float, np.ndarray]:
    """厘米 → 米"""
    return np.asarray(val, dtype=float) / 100.0

def mm_to_cm(val: Vec) -> Union[float, np.ndarray]:
    """毫米 → 厘米"""
    return np.asarray(val, dtype=float) / 10.0

def cm_to_mm(val: Vec) -> Union[float, np.ndarray]:
    """厘米 → 毫米"""
    return np.asarray(val, dtype=float) * 10.0

def m_to_mm(val: Vec) -> Union[float, np.ndarray]:
    """米 → 毫米"""
    return np.asarray(val, dtype=float) * 1000.0

def mm_to_m(val: Vec) -> Union[float, np.ndarray]:
    """毫米 → 米"""
    return np.asarray(val, dtype=float) / 1000.0


# =============================================================================
# 速度/加速度转换
# =============================================================================

def mps_to_cmps(val: Vec) -> Union[float, np.ndarray]:
    """m/s → cm/s"""
    return np.asarray(val, dtype=float) * 100.0

def cmps_to_mps(val: Vec) -> Union[float, np.ndarray]:
    """cm/s → m/s"""
    return np.asarray(val, dtype=float) / 100.0

def mps2_to_cmps2(val: Vec) -> Union[float, np.ndarray]:
    """m/s² → cm/s²"""
    return np.asarray(val, dtype=float) * 100.0

def cmps2_to_mps2(val: Vec) -> Union[float, np.ndarray]:
    """cm/s² → m/s²"""
    return np.asarray(val, dtype=float) / 100.0


# =============================================================================
# 坐标系边界转换 (Phase 2 接入 api 层; 此处先行提供唯一实现)
# =============================================================================
# 约定:
#   后端/仿真 z-up: [x, y, z], 高度 = z
#   Web three.js y-up: [x, y, z], 高度 = y
# 映射 (右手系保持, 仅换"上"轴):
#   z-up [x, y, z]  →  y-up [x, z, -y]
#   y-up [x, y, z]  →  z-up [x, -z, y]

def zup_cm_to_yup_m(pos_cm_zup: Vec) -> np.ndarray:
    """后端位置 (cm, z-up) → Web 位置 (m, y-up)。

    用法 (api 层序列化 /api/state 时调用, 唯一转换点):
        web_pos = zup_cm_to_yup_m(mc.current_pos)
    """
    x, y, z = np.asarray(pos_cm_zup, dtype=float) / 100.0
    return np.array([x, z, -y])


def yup_m_to_zup_cm(pos_m_yup: Vec) -> np.ndarray:
    """Web 位置 (m, y-up) → 后端位置 (cm, z-up)。"""
    x, y, z = np.asarray(pos_m_yup, dtype=float)
    return np.array([x, -z, y]) * 100.0


def zup_m_to_yup_m(pos_m_zup: Vec) -> np.ndarray:
    """仿真位置 (m, z-up) → Web 位置 (m, y-up)。"""
    x, y, z = np.asarray(pos_m_zup, dtype=float)
    return np.array([x, z, -y])


def yup_m_to_zup_m(pos_m_yup: Vec) -> np.ndarray:
    """Web 位置 (m, y-up) → 仿真位置 (m, z-up)。"""
    x, y, z = np.asarray(pos_m_yup, dtype=float)
    return np.array([x, -z, y])
