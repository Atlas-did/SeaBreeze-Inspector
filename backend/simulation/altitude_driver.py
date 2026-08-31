"""自家仿真高度保持驱动 — SimRuntimeDriver。

把 SimRuntime 包装成 commands.AltitudeHoldDriver：
  1) set_target_altitude(meters) → mc.takeoff(height=cm) 设定绝对目标高度；
  2) settle(seconds, dt) → 按 50Hz 步进 SimRuntime，返回稳态高度统计。

测量口径与 OmniSim 公共测试对齐：稳态取最后 5 秒高度均值。
风况由构造参数控制；静风理想模型下稳态误差应趋于 0（无积分器的级联 P
控制在零噪声下精确归零），带风时给出非零的保真度参考。
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np


class SimRuntimeDriver:
    """实现 AltitudeHoldDriver 协议（协议见 backend.drone.commands）。"""

    def __init__(self, mc: Any, runtime: Any):
        self._mc = mc
        self._runtime = runtime
        self._z_trace: List[float] = []
        self._last_state = "IDLE"

    def backend_name(self) -> str:
        return "sim"

    def set_target_altitude(self, meters: float) -> bool:
        accepted = self._mc.takeoff(height=meters * 100.0)  # mc.target_pos 以 cm 计
        return bool(accepted)

    def settle(self, seconds: float, dt: float = 0.02) -> Dict[str, Any]:
        # F05 注：这里 n_steps = 物理步数（仿真时间驱动，SimRuntime.step 各步）。
        # 与 OmniSim adapter.settle 的 n_steps = HTTP 轮询次数（墙钟驱动）语义不同，
        # 跨后端对比时勿把两者当同一种“步数”。
        # SimRuntime.step 内部把 dt clamp 到 min(0.02, dt)（见 loop.py:108），
        # 这里必须用同一个有效步长，否则稳态窗口(5s)与 n_steps 会算错。
        sim_dt = min(0.02, dt) if dt > 0 else 0.02
        n = max(1, int(seconds / sim_dt))
        self._z_trace = []
        for _ in range(n):
            out = self._runtime.step(sim_dt, set())  # 无按键：纯物理 + 任务管线
            self._z_trace.append(float(out["pos"][2]))
            self._last_state = str(out["state"])

        tail = np.asarray(self._z_trace[-max(1, int(5.0 / sim_dt)):])
        return {
            "altitude_m": float(tail.mean()),
            "std_m": float(tail.std()),
            "final_m": float(self._z_trace[-1]),
            "state": self._last_state,
            "n_steps": n,
        }


def build_sim_driver(calm: bool = True) -> SimRuntimeDriver:
    """按仓库标准装配方式构建自家仿真驱动（与后端 simulation.py 一致）。

    calm=True  → 零风、近零传感器噪声：测量控制器自身的稳态高度误差。
    calm=False → 0.5 m/s 顺风 + 阵风：作为保真度对比的带风参考。
    """
    from backend.main import MissionController
    from backend.runtime.loop import SimRuntime
    from backend.simulation.models import (
        Quadrotor3D,
        RobotArm3DOF,
        VirtualSensor,
        WindDisturbance,
    )

    mc = MissionController(mode="simulation", mock=True)
    quad = Quadrotor3D()
    if calm:
        wind = WindDisturbance(base_wind=np.zeros(3), freq=0.0, gust_amp=0.0)
    else:
        wind = WindDisturbance(base_wind=np.array([0.5, 0.2, 0.0]),
                               freq=0.1, gust_amp=0.2)
    sensor = VirtualSensor(imu_noise=0.001, opt_noise=0.02, bar_noise=0.01,
                           bias_drift_rate=0.0, rw_std=0.0)
    arm = RobotArm3DOF()
    runtime = SimRuntime(mc, quad, wind, arm, sensor)
    return SimRuntimeDriver(mc, runtime)
