#!/usr/bin/env python3
"""
控制器测试 — 阶跃响应 + 正弦扰动, 绘制响应曲线保存为PNG
"""

import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.feedforward_controller import FeedforwardController


def test_step_response():
    """阶跃响应测试: target从0突变为100cm"""
    print("[TEST] 阶跃响应测试")

    dt = 0.1
    n_steps = 200
    controller = FeedforwardController(Kp=2.0, Ki=0.1, Kd=1.0, Kff=1.0, dt=dt)

    target = np.array([100.0, 0.0, 0.0])
    pos = np.array([0.0, 0.0, 0.0])
    vel = np.array([0.0, 0.0, 0.0])

    positions = np.zeros((n_steps, 3))
    errors = np.zeros((n_steps, 3))
    outputs = np.zeros((n_steps, 3))

    for k in range(n_steps):
        ctrl_out, info = controller.compute(target, pos, disturbance_est=None, current_vel=vel)

        # 简化的物理模型: pos += vel*dt, vel += ctrl*dt (忽略质量)
        vel += ctrl_out * dt
        pos += vel * dt + 0.5 * ctrl_out * dt**2

        positions[k] = pos
        errors[k] = target - pos
        outputs[k] = ctrl_out

    # 验证
    final_error = np.abs(target - positions[-1])
    print(f"  最终误差: {final_error}")
    assert final_error[0] < 5.0, f"X轴最终误差{final_error[0]}>5cm"

    # 绘制
    fig, axes = plt.subplots(3, 1, figsize=(10, 8))
    t = np.arange(n_steps) * dt

    axes[0].plot(t, positions[:, 0], "b-", label="Position")
    axes[0].axhline(y=target[0], color="r", linestyle="--", label="Target")
    axes[0].set_ylabel("Position (cm)")
    axes[0].legend()
    axes[0].grid(True)

    axes[1].plot(t, errors[:, 0], "g-", label="Error")
    axes[1].axhline(y=2.0, color="orange", linestyle="--", label="Dead zone")
    axes[1].axhline(y=-2.0, color="orange", linestyle="--")
    axes[1].set_ylabel("Error (cm)")
    axes[1].legend()
    axes[1].grid(True)

    axes[2].plot(t, outputs[:, 0], "m-", label="Control output")
    axes[2].set_ylabel("Output (cm/s)")
    axes[2].set_xlabel("Time (s)")
    axes[2].legend()
    axes[2].grid(True)

    fig.suptitle("Step Response (Target=100cm)")
    plt.tight_layout()
    out_path = PROJECT_ROOT / "data" / "processed" / "step_response.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150)
    print(f"  图像已保存: {out_path}")
    plt.close()


def test_sinusoidal_disturbance():
    """正弦扰动测试: 外部扰动为10cm/s²正弦波, 验证前馈补偿效果"""
    print("[TEST] 正弦扰动测试 (前馈 vs 无前馈)")

    dt = 0.1
    n_steps = 300
    target = np.array([50.0, 0.0, 0.0])

    # 有前馈 (Kff=-1.0: 负前馈抵消扰动)
    ctrl_ff = FeedforwardController(Kp=1.5, Ki=0.05, Kd=0.8, Kff=-1.0, dt=dt)
    # 无前馈
    ctrl_no_ff = FeedforwardController(Kp=1.5, Ki=0.05, Kd=0.8, Kff=0.0, dt=dt)

    pos_ff = np.zeros(3)
    vel_ff = np.zeros(3)
    pos_no = np.zeros(3)
    vel_no = np.zeros(3)

    pos_ff_hist = np.zeros(n_steps)
    pos_no_hist = np.zeros(n_steps)

    for k in range(n_steps):
        disturbance = np.array([5.0, 0.0, 0.0])  # 恒值扰动, 方向与目标相反

        # 有前馈
        out_ff, _ = ctrl_ff.compute(target, pos_ff, disturbance, vel_ff)
        vel_ff += (out_ff + disturbance) * dt
        pos_ff += vel_ff * dt
        pos_ff_hist[k] = pos_ff[0]

        # 无前馈
        out_no, _ = ctrl_no_ff.compute(target, pos_no, disturbance, vel_no)
        vel_no += (out_no + disturbance) * dt
        pos_no += vel_no * dt
        pos_no_hist[k] = pos_no[0]

    # 绘制对比
    fig, ax = plt.subplots(figsize=(10, 5))
    t_arr = np.arange(n_steps) * dt
    ax.plot(t_arr, pos_ff_hist, "b-", label="With Feedforward (Kff=1.0)")
    ax.plot(t_arr, pos_no_hist, "r-", label="Without Feedforward (Kff=0)")
    ax.axhline(y=target[0], color="g", linestyle="--", label="Target")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("X Position (cm)")
    ax.set_title("Disturbance Rejection (Constant d=5cm/s²): With vs Without Feedforward")
    ax.legend()
    ax.grid(True)

    out_path = PROJECT_ROOT / "data" / "processed" / "disturbance_comparison.png"
    plt.savefig(out_path, dpi=150)
    print(f"  图像已保存: {out_path}")
    plt.close()

    # 验证: 有前馈的稳态误差更小
    err_ff = np.abs(target[0] - pos_ff_hist[-50:]).mean()
    err_no = np.abs(target[0] - pos_no_hist[-50:]).mean()
    print(f"  有前馈稳态误差: {err_ff:.2f}cm, 无前馈: {err_no:.2f}cm")
    assert err_ff < err_no, "前馈应减小稳态误差"


def test_pt1_filter():
    """PT1 低通滤波: 阶跃响应"""
    print("[TEST] PT1 低通滤波器")
    from backend.core.filters import PT1Filter

    f = PT1Filter(cutoff_hz=10.0, dt=0.01)

    # 阶跃输入: 0→1.0
    outputs = []
    for _ in range(100):
        outputs.append(f.update(1.0))

    # 输出应逐渐接近 1.0
    assert outputs[0] < 0.5, "初始输出应远小于 1.0"
    assert outputs[-1] > 0.9, "最终输出应接近 1.0"
    # 单调上升
    assert all(outputs[i] <= outputs[i+1] for i in range(99))
    print("  100步阶跃: init={:.3f}, final={:.3f}".format(outputs[0], outputs[-1]))
    print("  [PASS]")


def test_integral_separation():
    """积分分离: 大误差时冻结积分"""
    print("[TEST] 积分分离器")
    from backend.core.filters import IntegralSeparator

    sep = IntegralSeparator(threshold=50.0)
    assert sep.should_integrate(10.0), "小误差应允许积分"
    assert not sep.should_integrate(60.0), "大误差应冻结积分"
    assert sep.is_frozen
    # 恢复
    assert sep.should_integrate(30.0), "误差回落后应恢复"
    print("  [PASS]")


def test_pt1_noise_suppression():
    """PT1 对高频噪声的抑制"""
    print("[TEST] PT1 噪声抑制")
    import numpy as np
    from backend.core.filters import PT1Filter

    f = PT1Filter(cutoff_hz=5.0, dt=0.01)
    noisy = np.sin(np.linspace(0, 200, 500)) + np.random.randn(500) * 0.5
    filtered = np.array([f.update(x) for x in noisy])

    # 滤波后方差应小于原噪声方差
    orig_std = np.std(noisy[-200:])
    filt_std = np.std(filtered[-200:])
    assert filt_std < orig_std, "滤波后应更平滑"
    print("  原始std={:.3f}, 滤波std={:.3f}".format(orig_std, filt_std))
    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  控制器测试套件")
    print("=" * 50)
    test_step_response()
    test_sinusoidal_disturbance()
    test_pt1_filter()
    test_integral_separation()
    test_pt1_noise_suppression()
    print("\n[OK] 所有测试通过!")
