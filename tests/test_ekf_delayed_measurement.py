"""
=============================================================================
EKF 延迟测量 (age_s) — 确定性单元测试
=============================================================================

被测: backend/core/disturbance_observer.py 的
      DisturbanceObserverEKF.update(z, age_s)

覆盖:
  1. age_s=0 (省略 / 关键字 0.0 / 位置 0.0) 与改动前逐位一致, 含 predict(u)+自适应Q
     的多步序列;
  2. age_s 增大时对状态的影响单调减弱 (量化指标与依据见该用例 docstring);
  3. 陈旧测量不会把估计拉回旧值 (与同一测量当作新鲜时对比, 方向明确);
  4. age_s=1e6 时无 NaN/Inf 且修正量≈0, 之后的 predict 仍稳定;
  5. last_measurement_age_s / last_R_scale 如实反映输入;
  6. age_s 为负 / NaN / ±Inf / -0.0 时按 0 处理 (与 age=0 逐位一致)。

全部确定性: 固定随机种子, 不依赖时钟与运行顺序。
=============================================================================
"""

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.disturbance_observer import (  # noqa: E402
    STATE_DIM,
    DisturbanceObserverEKF,
)

POS = slice(0, 3)
Z_SAMPLE = np.array([1.0, -2.0, 0.5, 12.0, -7.0, 30.0])


def _make(**kwargs) -> DisturbanceObserverEKF:
    """构造被测 EKF。"""
    return DisturbanceObserverEKF(**kwargs)


def _clone(ekf: DisturbanceObserverEKF) -> DisturbanceObserverEKF:
    """深拷贝, 用于"同一先验 + 不同 age_s"的受控对比。"""
    return copy.deepcopy(ekf)


def _seed(ekf: DisturbanceObserverEKF, seed: int = 7) -> DisturbanceObserverEKF:
    """给出非平凡且可复现的先验 (x, P), 使更新量足够大、便于比较。"""
    rng = np.random.default_rng(seed)
    ekf.x = rng.normal(0.0, 10.0, STATE_DIM)
    a = rng.normal(0.0, 1.0, (STATE_DIM, STATE_DIM))
    ekf.P = a @ a.T + np.eye(STATE_DIM)
    return ekf


def _run_sequence(ekf: DisturbanceObserverEKF, age=None):
    """
    固定的 predict(u=...) + update 序列; age=None 表示"不传 age_s 参数"。
    返回逐步的 (x, P) 字节快照, 用于逐位比较。
    """
    rng = np.random.default_rng(11)
    snaps = []
    for _ in range(25):
        u = rng.normal(0.0, 5.0, 3)
        z = rng.normal(0.0, 5.0, 6)
        ekf.predict(u=u)
        if age is None:
            ekf.update(z)
        else:
            ekf.update(z, age_s=age)
        snaps.append((ekf.x.tobytes(), ekf.P.tobytes()))
    return snaps


def test_age_zero_is_bit_identical_to_no_argument():
    """age_s=0 / 省略 / 位置传 0.0 三种写法逐位一致 (既有用例的硬守门人)。"""
    f_default, f_kw, f_pos = _make(), _make(), _make()
    f_default.update(Z_SAMPLE)
    f_kw.update(Z_SAMPLE, age_s=0.0)
    f_pos.update(Z_SAMPLE, 0.0)

    assert f_default.x.tobytes() == f_kw.x.tobytes() == f_pos.x.tobytes()
    assert f_default.P.tobytes() == f_kw.P.tobytes() == f_pos.P.tobytes()
    assert f_kw.last_measurement_age_s == 0.0
    assert f_kw.last_R_scale == 1.0

    # 含 predict(u=...)、u 分支与自适应Q的多步序列也必须逐位一致
    assert _run_sequence(_make()) == _run_sequence(_make(), age=0.0)


AGES = [0.0, 0.001, 0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 60.0, 600.0]


def test_influence_weakens_monotonically_with_age():
    """
    量化指标 (主): 位置块的信息增益
        IG(age) = trace(P_prior[pos]) - trace(P_post[pos])
    IG 随 age 单调不增, 即"同一测量对估计的影响单调减弱"。

    依据 (严格, 与数值无关): 卡尔曼更新的信息形式
        P_post⁻¹ = P_prior⁻¹ + Hᵀ R_eff⁻¹ H
    R_eff = R + Q_Δ(age), 而 Q_Δ 半正定且随 age 只增不减 (累积 Σ Fⁱ Q Fⁱᵀ)
    ⇒ R_eff 在 Loewner 序下单调不减 ⇒ R_eff⁻¹ 单调不增 ⇒ P_post 单调不减
    ⇒ trace(P_post[pos]) 单调不减 ⇒ IG 单调不增。
    因此同时直接检查 Loewner 序: P_post(a_{k+1}) - P_post(a_k) ⪰ 0。

    (辅助) 原始修正量 ‖K·ỹ‖ 在跨通道相关下并不是严格单调的 —— 实测 age≈0.5 处
    可比 age=0 大不到 0.1%, 因为 R 膨胀改变了各通道的相对权重而非单纯等比缩放。
    所以单调性以信息增益/Loewner 序为准, 修正量只做粗尺度量级检查。
    """
    base = _seed(_make())
    priors, posts, infos, corrs = [], [], [], []
    for age in AGES:
        f = _clone(base)
        p0, x0 = f.P.copy(), f.x.copy()
        f.update(Z_SAMPLE, age_s=age)
        priors.append(p0)
        posts.append(f.P.copy())
        infos.append(float(np.trace(p0[POS, POS]) - np.trace(f.P[POS, POS])))
        corrs.append(float(np.linalg.norm((f.x - x0)[POS])))

    for i in range(1, len(AGES)):
        assert infos[i] <= infos[i - 1] + 1e-9, (AGES[i - 1], AGES[i], infos[i - 1], infos[i])

    for i in range(1, len(AGES)):
        d = np.linalg.eigvalsh(posts[i] - posts[i - 1])
        assert d.min() >= -1e-9, (AGES[i - 1], AGES[i], float(d.min()))

    # 粗尺度: 修正量确实被压到很小 (age=5s 只剩 <10%)
    assert corrs[AGES.index(5.0)] < 0.1 * corrs[0]


def test_stale_measurement_does_not_pull_estimate_back_to_old_value():
    """
    场景: 先用 10 次 predict 把状态推远 (vx=100cm/s → x=100cm), 然后喂一条
    仍然"报告 x=0"的过期光流/气压测量。

    方向约定: 该测量对应的是 1 秒前的位置 (旧值 0), 当前状态是 100。
      - 当作新鲜 (age=0): 残差 -100 被当成真实偏差, 估计被拉回旧值 (x→~3);
      - 当作延迟 (age=5s): R 膨胀后增益≈0, 估计留在当前值 (x≈100), 即
        "没有被拉回旧值"。
    断言方向: x_stale > x_fresh (旧测量只应提供极弱信息, 不应主导估计)。
    """
    ekf = _make(dt=0.1)
    ekf.x[3] = 100.0  # vx = 100 cm/s
    for _ in range(10):
        ekf.predict()
    assert ekf.x[0] == pytest.approx(100.0, abs=1e-9)

    z_old = np.zeros(6)  # 1 秒前的世界: 位置 0, 加速度/扰动 0

    fresh = _clone(ekf)
    fresh.update(z_old, age_s=0.0)

    stale = _clone(ekf)
    stale.update(z_old, age_s=5.0)

    pull_fresh = abs(fresh.x[0] - ekf.x[0])
    pull_stale = abs(stale.x[0] - ekf.x[0])

    assert pull_fresh > 50.0                 # 新鲜: 被显著拉回旧值
    # 阈值重标定 (2026-10-06, 随 P0-2 R 矩阵单位修复):
    #   延迟抑制用的是 R_eff = R + Q_Δ(age)，是"相加"而非"相乘"。
    #   修复前基础 R 的 IMU 块误为 0.0025（比真值小 1e4 倍），Q_Δ 完全主导，
    #   R_scale 达 66×，陈旧测量几乎被无视（pull_stale≈0.5cm）。
    #   修正 R=625 后基础 R 与 Q_Δ 同量级，R_scale 降到 ~4.5×，
    #   陈旧测量仍保留约 5.7% 权重 —— 这是正确贝叶斯行为（总不确定度 =
    #   测量噪声 + 延迟期间的过程漂移），不是回归。
    #   故改为"相对压制"判据（与 R 的绝对尺度无关），并放宽绝对上限。
    assert pull_stale < 10.0                 # 延迟: 影响被压到 10cm 以内
    assert stale.x[0] > fresh.x[0] + 50.0    # 方向: 延迟结果留在当前值一侧
    assert pull_stale < 0.10 * pull_fresh    # 相对: 影响被压到 10% 以下


def test_extreme_age_is_finite_and_correction_vanishes():
    """
    age_s=1e6 (≈11.6 天) 时: 状态/协方差/P 均有限 (无 NaN/Inf), 修正量≈0,
    且随后的 predict 仍然稳定。1e308 (有限但大到 age/dt 会溢出为 inf) 也必须
    不抛异常 —— 走 MAX_DELAY_STEPS 饱和分支。

    注意 (诚实记录): R 膨胀是各向异性的, 不是"把测量整体置零"。位置通道
    (Q_acc[0:3]) 比加速度通道 (Q_acc[6:9]) 增长快得多 (t³~t⁵ vs t¹), 所以
    位置残差几乎完全被忽略, 而 IMU 加速度通道相对不那么"陈旧", 会留下
    ~1e-6 倍量级的残余修正 —— 这正是"用过程噪声模型而不是魔数"的体现。
    """
    base = _seed(_make())
    fresh = _clone(base)
    fresh.update(Z_SAMPLE, age_s=0.0)
    corr_fresh = float(np.linalg.norm((fresh.x - base.x)[POS]))

    for age in (1e6, 1e9, 1e12, 1e308):
        f = _clone(base)
        f.update(Z_SAMPLE, age_s=age)

        assert np.all(np.isfinite(f.x))
        assert np.all(np.isfinite(f.P))
        assert np.isfinite(f.last_R_scale)
        assert np.isfinite(f.mahalanobis_distance)

        corr = float(np.linalg.norm((f.x - base.x)[POS]))
        assert corr < 1e-4 * corr_fresh, (age, corr, corr_fresh)
        assert corr < 1e-3

        f.predict()  # 极端延迟之后滤波器仍可用
        assert np.all(np.isfinite(f.x)) and np.all(np.isfinite(f.P))


def test_introspection_reflects_age_and_r_scale():
    """
    last_measurement_age_s 如实记录生效年龄; last_R_scale 是 R_eff 相对 R 的
    放大倍数 (迹之比), 且随 age 单调不减、age=0 时恰为 1.0。
    """
    for age in (0.25, 1.0, 4.0):
        f = _seed(_make())
        f.update(Z_SAMPLE, age_s=age)
        assert f.last_measurement_age_s == age
        r_eff = f.R + f._delay_measurement_noise(age)
        expected = float(np.trace(r_eff)) / float(np.trace(f.R))
        assert f.last_R_scale == pytest.approx(expected, rel=1e-12)
        assert f.last_R_scale > 1.0

    scales = []
    for age in (0.0, 0.1, 1.0, 10.0):
        f = _seed(_make())
        f.update(Z_SAMPLE, age_s=age)
        scales.append(f.last_R_scale)
    assert scales[0] == 1.0
    assert all(scales[i] < scales[i + 1] for i in range(len(scales) - 1))


@pytest.mark.parametrize("bad_age", [-1.0, -1e-9, -0.0, float("nan"),
                                     float("inf"), float("-inf")])
def test_invalid_age_is_treated_as_zero(bad_age):
    """
    负值 / NaN / ±Inf / -0.0 一律按 0 处理: 不抛异常, 且结果与 age_s=0 逐位一致,
    自省字段如实回填为 0.0 / 1.0。理由: "未来测量"在因果系统中无定义, 上游时钟
    异常不应打断控制环。
    """
    base = _seed(_make())
    ref = _clone(base)
    ref.update(Z_SAMPLE, age_s=0.0)

    f = _clone(base)
    f.update(Z_SAMPLE, age_s=bad_age)

    assert f.x.tobytes() == ref.x.tobytes()
    assert f.P.tobytes() == ref.P.tobytes()
    assert f.last_measurement_age_s == 0.0
    assert f.last_R_scale == 1.0
