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

    # Tello SDK状态字段: pitch roll yaw vgx vgy vgz templ temph tof h bat baro
    imu_accel = np.array([
        float(raw_state.get("vgx", 0)),  # 近似
        float(raw_state.get("vgy", 0)),
        float(raw_state.get("vgz", 0)),
    ])

    return {
        "acceleration": imu_accel,  # cm/s² (近似)
        "velocity": np.array([
            float(raw_state.get("vgx", 0)),
            float(raw_state.get("vgy", 0)),
            float(raw_state.get("vgz", 0)),
        ]),
        "height": float(raw_state.get("h", 0)),  # cm
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
