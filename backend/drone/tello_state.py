"""
Tello状态解析 — 提取IMU数据供EKF使用
"""

import numpy as np


def parse_tello_state(raw_state: dict) -> dict:
    """
    解析Tello状态包, 返回标准化状态字典。

    输入: djitellopy返回的原始状态字典
    输出: EKF可用的标准化状态
    """
    if not raw_state:
        return {}

    # Tello SDK 状态字段: pitch roll yaw vgx vgy vgz templ temph tof h bat baro
    # P1-E: vg* 单位是 dm/s (分米/秒), 需 ×10 转为 cm/s
    vgx = float(raw_state.get("vgx", 0)) * 10   # dm/s → cm/s
    vgy = float(raw_state.get("vgy", 0)) * 10
    vgz = float(raw_state.get("vgz", 0)) * 10

    return {
        "acceleration": np.array([vgx, vgy, vgz]),  # cm/s (速度差分近似)
        "velocity": np.array([vgx, vgy, vgz]),       # cm/s
        "height": float(raw_state.get("h", 0)),      # cm
        "battery": int(raw_state.get("bat", 0)),
        "temperature": int(raw_state.get("templ", 0)),
    }


def get_state_dict(tello_obj) -> dict:
    """从Tello对象获取标准化状态"""
    if tello_obj is None:
        return {}
    try:
        raw = tello_obj.get_current_state()
        return parse_tello_state(raw)
    except Exception as e:
        print(f"[WARN] 状态读取失败: {e}")
        return {}
