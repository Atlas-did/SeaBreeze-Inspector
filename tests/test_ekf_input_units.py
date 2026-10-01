"""EKF 控制输入的**量纲与语义**回归（审计 D3）。

背景（我方在核验外部深度解读时发现，审计方未提到）：
  `DisturbanceObserverEKF.predict(u)` 的 `u` 语义是**控制加速度 (cm/s²)** —— 它会把
  加速度状态 `x[AX:AX+3]` **直接设成 u**，并把该状态的协方差压到 0.01、交叉协方差清零
  （见 backend/core/disturbance_observer.py 的 predict）。其原理是
  `IMU观测 = a + d = u + d ⇒ d̂ = IMU − u`。

  而 `MissionController._last_control_output` 是控制器的**速度指令 (cm/s)**
  （`_send_control` 注释：真机经 RCManager 20Hz 下发；模拟记录速度指令）。
  把速度指令当控制加速度喂进去，数值量级相近、不会报错，但会让 `d̂` **系统性偏差** ——
  属于最难发现的一类静默错误。

本文件锁死：真机路径**不得**把速度指令当控制加速度；没有控制加速度来源时传 `None`。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402

from backend.main import MissionController  # noqa: E402


def _mc():
    mc = MissionController(mode="simulation", mock=True)
    mc.logger.start_session = lambda *a, **k: None
    mc.logger.log_frame = lambda *a, **k: None
    return mc


def _spy_predict(mc):
    """记录每次 predict 收到的 u。"""
    seen = []
    real = mc.ekf.predict

    def spy(u=None, **kw):
        seen.append(u)
        return real(u=u, **kw)

    mc.ekf.predict = spy
    return seen


def test_mock_path_feeds_the_control_acceleration_channel():
    """仿真/mock: 传的必须是控制加速度通道(`_last_control_accel`, cm/s²)。"""
    mc = _mc()
    seen = _spy_predict(mc)
    mc.mock = True
    mc._last_control_accel = np.array([1.0, 2.0, 3.0])
    mc._last_control_output = np.array([50.0, 0.0, 0.0])   # 速度指令(cm/s), 不得被当作 u

    mc._update_inner()

    assert seen, "predict 未被调用"
    assert seen[-1] is not None, "mock 路径应提供控制加速度"
    assert np.allclose(np.asarray(seen[-1], dtype=float), [1.0, 2.0, 3.0]), \
        "mock 路径喂的不是控制加速度通道: {}".format(seen[-1])


def test_real_path_never_feeds_a_velocity_command_as_acceleration():
    """真机: 没有控制加速度来源 -> 必须传 None, 而不是把速度指令(cm/s)当加速度。"""
    mc = _mc()
    seen = _spy_predict(mc)
    mc.mock = False
    # 真机路径不会更新 _last_control_accel(只有 SimRuntime 会回喂), 这里显式清空
    mc._last_control_accel = np.zeros(3)
    mc._last_control_output = np.array([80.0, 0.0, 0.0])   # 速度指令: 若被当作 u 就是量纲错误

    mc._update_inner()

    assert seen, "predict 未被调用"
    assert seen[-1] is None, (
        "真机路径把速度指令当控制加速度喂给了 EKF(静默污染 d̂), 实际 u={}".format(seen[-1]))
