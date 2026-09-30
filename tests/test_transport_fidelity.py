#!/usr/bin/env python3
"""传输层保真度扩展测试: 采样时间戳/年龄 + 上行指令链路 + 突发丢包 (审计 §14.4)。

全部确定性: 只按**仿真时钟**步进 (now = k*dt), 不 sleep、不读墙钟; 固定 seed 的
random.Random 在 CPython 上跨版本稳定 (Mersenne Twister 的输出序列有文档承诺),
所以断言在 CI 上可复现。

本文件只 import backend.simulation.transport_model (不 import backend.main /
runtime.loop): 传输层是纯离散的, 这样这些用例不会被并发的接线改动带崩。
"""

import math
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402  (sys.path 注入后才能 import backend)

from backend.simulation.transport_model import (  # noqa: E402
    ActuatorLag,
    CommandTransportModel,
    SensorTransportModel,
)

DT = 0.02  # 50Hz, 与 SimRuntime 的 sim_dt 一致


def _sensor_drop_sequence(loss_model, seed, n=5000, drop_rate=0.2,
                          mean_burst_len=10.0):
    """逐帧 push+poll, 返回逐帧是否**丢包** (True=没交付)。"""
    m = SensorTransportModel(drop_rate=drop_rate, seed=seed,
                             loss_model=loss_model,
                             mean_burst_len=mean_burst_len)
    out = []
    for k in range(1, n + 1):
        m.push(np.array([float(k)]), k * DT)
        out.append(m.poll(k * DT) is None)
    return out


def _drop_runs(seq):
    """连续丢包的游程长度列表 (含末尾未闭合的游程)。"""
    runs, cur = [], 0
    for dropped in seq:
        if dropped:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    return runs


def _command_delivery_sequence(m, n=200):
    """逐帧 (本帧下发的指令是否在本帧交付) —— 每条指令名唯一, 故可区分。"""
    out = []
    for k in range(1, n + 1):
        cmd = "c%d" % k
        m.push(cmd, k * DT)
        out.append(m.poll(k * DT) == cmd)
    return out


class _LegacyDropDecision:
    """扩展前 SensorTransportModel 的丢包判定逐字复刻 (iid 伯努利)。

    同一个 random.Random(seed) 流, 每个交付机会恰好消耗一个随机数, 判定式与
    扩展前完全相同 —— 用它证明 loss_model="iid" 时序列**逐位**不变。
    """

    def __init__(self, drop_rate, seed=0):
        self.drop_rate = drop_rate
        self._rng = random.Random(seed)

    def decide(self):
        return self.drop_rate > 0.0 and self._rng.random() < self.drop_rate


# =============================================================================
# A. 样本时间戳 / 年龄 (审计 §14.4: 测量有多旧)
# =============================================================================

def test_last_sample_time_is_the_sampling_instant_not_the_delivery_instant():
    """延迟 L=0.1, dt=0.02 下逐帧核对: 第 k 帧交付的是第 k-5 帧**采样**的样本。

    容差 1e-9: 帧网格上的算术只有浮点舍入 (~1e-17), 而判错一帧的误差是
    dt=0.02 —— 差 7 个数量级, 容差既不脆弱也没有模糊空间。
    """
    m = SensorTransportModel(latency_s=0.1)
    for k in range(0, 31):
        now = k * DT
        m.push(np.array([float(k)]), now)
        m.poll(now)
        if k < 5:
            assert m.last_sample_time() is None          # 还没交付过
        else:
            assert abs(m.last_sample_time() - (k - 5) * DT) < 1e-9
            assert abs(m.last_age(now) - 0.1) < 1e-9     # 年龄 == 单程延迟
            assert m.last_sample_time() < m.last_delivery_time()
    # 单包版本: push 不等于交付; 交付后 age 是延迟而不是 0
    s = SensorTransportModel(latency_s=0.1)
    s.push(np.array([1.0]), 0.0)
    assert s.last_sample_time() is None and s.last_age(0.05) is None
    assert s.poll(5 * DT) is not None
    assert s.last_sample_time() == 0.0                   # 原始采样时刻, 不是 0.1
    assert s.last_delivery_time() == 5 * DT
    assert abs(s.last_age(5 * DT) - 5 * DT) < 1e-12
    assert s.last_age(5 * DT) > 0.09


def test_last_age_is_none_until_first_delivery_and_after_reset():
    """从未交付 (含全丢包) -> None; reset() 后回到 None; 零延迟时年龄恒为 0。"""
    m = SensorTransportModel(latency_s=0.1)
    assert m.last_sample_time() is None and m.last_age(10.0) is None
    m.push(np.array([1.0]), 0.0)
    assert m.last_age(10.0) is None          # 已 push 但尚未交付, 仍是 None
    assert m.poll(0.1) is not None
    assert abs(m.last_age(0.5) - 0.5) < 1e-12
    m.reset()
    assert m.last_sample_time() is None and m.last_age(0.5) is None
    never = SensorTransportModel(drop_rate=1.0, seed=3)
    for k in range(1, 21):
        never.push(np.array([float(k)]), k * DT)
        assert never.poll(k * DT) is None
    assert never.last_sample_time() is None and never.last_age(99.0) is None
    # 默认参数 (latency=0): 直通 + 年龄为 0, poll 语义与扩展前一致
    z = SensorTransportModel()
    sample = np.array([7.0])
    z.push(sample, 3.0)
    assert z.poll(3.0) is sample
    assert z.last_sample_time() == 3.0 and z.last_age(3.0) == 0.0
    assert z.poll(3.0) is None


# =============================================================================
# B. 上行指令链路 CommandTransportModel
# =============================================================================

def test_command_delay_line_is_ceil_latency_over_dt():
    """延迟交付步数 k = ceil(L/dt) (与传感器延迟线同一约定); 到达后保持。"""
    for latency in (0.0, 0.03, 0.1):
        m = CommandTransportModel(latency_s=latency)
        assert m.poll(0.0) is None                # 冷启动: 还没有指令到达
        m.push("hover", 0.0)
        arrivals = [k for k in range(1, 11) if m.poll(k * DT) is not None]
        assert arrivals[0] == max(1, math.ceil(latency / DT))
        assert arrivals == list(range(arrivals[0], 11))   # 指令是状态, 反复可见
        assert m.last_command == "hover"
        assert m.delivery_count == 1 and m.drop_count == 0
        assert m.last_delivery_time() == arrivals[0] * DT
    # 新指令覆盖旧指令 (按到达先后, 越晚到达者胜出)
    n = CommandTransportModel(latency_s=0.04)
    n.push("a", 0.0)          # 到达 0.04
    n.push("b", 0.02)         # 到达 0.06
    assert n.poll(0.04) == "a"
    assert n.poll(0.06) == "b"
    assert (n.delivery_count, n.drop_count) == (2, 0)


def test_command_drop_rate_extremes():
    """drop_rate=1.0: poll() 恒 None; drop_rate=0.0: 逐帧交付该帧指令。"""
    never = CommandTransportModel(drop_rate=1.0, seed=0)
    always = CommandTransportModel(drop_rate=0.0)
    for k in range(1, 51):
        cmd = "cmd%d" % k
        never.push(cmd, k * DT)
        always.push(cmd, k * DT)
        assert never.poll(k * DT) is None
        assert always.poll(k * DT) == cmd
    assert (never.delivery_count, never.drop_count) == (0, 50)
    assert (always.delivery_count, always.drop_count) == (50, 0)
    assert never.last_command is None and never.last_delivery_time() is None
    assert always.last_command == "cmd50"
    assert always.last_delivery_time() == 50 * DT


def test_command_drop_keeps_previous_command_visible():
    """被丢掉的指令不返回: poll 仍给出上一条成功到达的指令 (调用方决定归零)。

    判定不依赖具体随机取值: 逐帧对照"本帧唯一指令名是否被 poll 到", 只在确实
    出现丢包帧时断言 poll 返回的正是上一次交付过的那条。
    """
    m = CommandTransportModel(drop_rate=0.3, seed=0)
    last, drops = None, 0
    for k in range(1, 101):
        cmd = "cmd%d" % k
        m.push(cmd, k * DT)
        got = m.poll(k * DT)
        if got == cmd:
            last = cmd
        else:
            drops += 1
            assert got == last            # 丢包帧: 上一条保持可见 (冷启动时为 None)
    assert drops == m.drop_count > 0
    assert m.delivery_count + m.drop_count == 100
    assert m.last_command == last


# =============================================================================
# C. 突发丢包 Gilbert-Elliott (统计特性)
# =============================================================================

def test_burst_loss_makes_longer_drop_runs_than_iid_at_equal_drop_rate():
    """同 seed 同 drop_rate(0.2)、n=5000: GE 的游程显著长于 i.i.d.。

    判定与容差依据: i.i.d. 的丢包游程服从均值 1/(1-d)=1.25 的几何分布, GE
    (mean_burst_len=10) 的理论游程均值就是 10, 相差约 8 倍。两条断言都只取
    **量级** (游程均值 > 3x, 最长游程 >= 5x): 实测 9.72 vs 1.26 (7.7x) 与
    75 vs 5 (15x), 余量 2.6x / 3x。这样既能挡住"忘了接 GE 状态机"的回归
    (那时两条序列同分布, 比值 ≈ 1), 又不依赖固定 seed 的具体取值。
    另外两条前提也必须成立: 整体丢包率不被突发改变 (仍是 drop_rate), 且同 seed
    逐位可复现。
    """
    iid = _sensor_drop_sequence("iid", seed=0)
    ge = _sensor_drop_sequence("gilbert-elliott", seed=0, mean_burst_len=10.0)
    for seq in (iid, ge):
        assert abs(sum(seq) / len(seq) - 0.2) < 0.03     # 只改变"怎么丢"
    runs_i, runs_g = _drop_runs(iid), _drop_runs(ge)
    mean_i = sum(runs_i) / len(runs_i)
    mean_g = sum(runs_g) / len(runs_g)
    assert mean_g > 3 * mean_i
    assert max(runs_g) >= 5 * max(runs_i)
    assert len(runs_g) < len(runs_i)          # 零散丢包被合并成少数长游程
    assert ge == _sensor_drop_sequence("gilbert-elliott", seed=0,
                                       mean_burst_len=10.0)
    assert iid == _sensor_drop_sequence("iid", seed=0)


def test_measured_mean_burst_len_matches_setting():
    """设定 mean_burst_len=L 时实测游程均值在同一量级 (0.2 丢包率, 20000 帧)。

    容差依据: 游程长度服从均值 L、标准差 sqrt(L^2-L) 的几何分布 (p_bg=1/L);
    n=20000, pi_bad=0.2 时约有 n*pi_bad/L 个游程, L=10 -> ~400 个, 均值标准误
    ≈ sqrt(90)/20 ≈ 0.48, 取 ±max(0.5, 0.3L) (=3.0, 约 6σ) 仍能挡住把 p_bg 写反
    (那时均值会是 L^2 量级) 或漏乘 1/L 的错误。固定 seed=7 实测: L=2 -> 1.981,
    L=10 -> 10.324, 偏差 0.019 / 0.324。整体丢包率的容差另外说明: 突发使丢包
    计数自相关, 有效标准误被放大 (L=10 时膨胀因子 (1+rho)/(1-rho) ≈ 15, 有效
    SE ≈ 0.011), 取 ±0.03 约 2.7σ。
    """
    for burst_len in (2.0, 10.0):
        seq = _sensor_drop_sequence("gilbert-elliott", seed=7, n=20000,
                                    drop_rate=0.2, mean_burst_len=burst_len)
        runs = _drop_runs(seq)
        assert abs(sum(seq) / len(seq) - 0.2) < 0.03
        mean_run = sum(runs) / len(runs)
        assert abs(mean_run - burst_len) < max(0.5, 0.3 * burst_len)
        assert min(runs) == 1                 # 每个突发都有起点, 不会全是连接段


def test_mean_burst_len_one_removes_burstiness_but_keeps_drop_rate():
    """mean_burst_len=1 -> 游程恒为 1, 丢包率仍 ≈ drop_rate (最不突发的边界)。

    说明 (不能含糊的地方): p_bad_to_good = 1/L = 1 使"连续两次丢弃"概率精确为
    0, 所以最长游程**恒等于 1**, 用 == 断言; 丢包率由稳态式 pi_bad = drop_rate
    保证, 实测 0.1983 (n=20000 的二项标准误 ≈ 0.0028, 取 ±0.03 ≈ 10σ)。
    因此它与 i.i.d. 只是**一阶等价** (相同的边际丢包率、记忆长度 1), 并非同一
    分布: i.i.d. 在 d=0.2 下游程均值是 1/(1-d)=1.25 且存在长度 >=2 的游程
    (本用例顺带断言这一点), L=1 的 GE 则是"丢弃互不相邻"的边界。
    """
    seq = _sensor_drop_sequence("gilbert-elliott", seed=0, n=20000,
                                drop_rate=0.2, mean_burst_len=1.0)
    runs = _drop_runs(seq)
    assert set(runs) == {1}
    assert abs(sum(seq) / len(seq) - 0.2) < 0.03
    runs_iid = _drop_runs(_sensor_drop_sequence("iid", seed=0, n=20000))
    assert max(runs_iid) > 1
    assert sum(runs_iid) / len(runs_iid) > 1.05


# =============================================================================
# D. 默认关闭: iid 与扩展前逐位一致 + 同 seed 可复现
# =============================================================================

def test_iid_loss_model_reproduces_pre_extension_bernoulli_sequence():
    """loss_model="iid" (含不传参的默认) 与扩展前判定式逐帧逐位一致。

    对照物是扩展前 poll() 里那两行判定 (push 后立即 poll, latency=0 时每帧恰好
    一次交付机会)。同时覆盖 drop_rate=0: 关闭时必须一个随机数都不取, 这样
    "默认路径不改变已发表数字"在 RNG 层面也成立。
    """
    for seed in (0, 1, 7, 12345):
        for drop_rate in (0.0, 0.05, 0.3, 0.75, 1.0):
            legacy = _LegacyDropDecision(drop_rate, seed)
            default = SensorTransportModel(drop_rate=drop_rate, seed=seed)
            explicit = SensorTransportModel(drop_rate=drop_rate, seed=seed,
                                            loss_model="iid")
            assert default.loss_model == "iid" and default.mean_burst_len == 1.0
            for k in range(1, 301):
                expected_drop = legacy.decide()
                sample = np.array([float(k)])
                default.push(sample, k * DT)
                explicit.push(sample, k * DT)
                assert (default.poll(k * DT) is None) == expected_drop
                assert (explicit.poll(k * DT) is None) == expected_drop
    # 非 iid 的取值必须是显式非法名 (fail fast, 不静默退化成 iid)
    try:
        SensorTransportModel(loss_model="gilbert")
    except ValueError as exc:
        assert "loss_model" in str(exc)
    else:
        raise AssertionError("未知 loss_model 应当抛 ValueError")


def test_seeded_loss_is_reproducible_and_reset_restores_the_stream():
    """两个模型同 seed 逐位复现; reset() 后重放同一条序列; 换 seed 序列不同。"""

    def ge_run(seed):
        m = SensorTransportModel(drop_rate=0.3, seed=seed,
                                 loss_model="gilbert-elliott",
                                 mean_burst_len=6.0)
        return _sensor_drop_sequence("gilbert-elliott", seed=seed, n=200,
                                     drop_rate=0.3, mean_burst_len=6.0), m

    first, m = ge_run(5)
    assert 0 < sum(first) < len(first)
    assert first == ge_run(5)[0]
    assert first != ge_run(6)[0]
    m.reset()
    assert m.delivery_count == 0 and m.drop_count == 0            # 计数归零
    assert m.last_sample_time() is None and m.last_age(1.0) is None
    assert ge_run(5)[0] == first                                  # reset 可复现同一条
    # 上行链路同样可复现, 且 reset 后 last_command 归位
    a = CommandTransportModel(drop_rate=0.4, seed=2, loss_model="gilbert-elliott",
                              mean_burst_len=4.0)
    b = CommandTransportModel(drop_rate=0.4, seed=2, loss_model="gilbert-elliott",
                              mean_burst_len=4.0)
    seq_a = _command_delivery_sequence(a, 200)
    assert seq_a == _command_delivery_sequence(b, 200)
    assert 0 < sum(seq_a) < len(seq_a)          # 有交付也有丢包
    a.reset()
    assert a.last_command is None and a.delivery_count == 0 and a.drop_count == 0
    assert _command_delivery_sequence(a, 200) == seq_a


# =============================================================================
# E. ActuatorLag 语义未被扩展破坏
# =============================================================================

def test_actuator_lag_semantics_unchanged():
    """tau=0 严格直通; 1τ 达到 1-1/e ≈ 63.2% (容差同既有测试 0.005)。"""
    lag = ActuatorLag(tau_s=0.0)
    cmd = np.array([1.0, -2.5, 3.0])
    assert np.array_equal(lag.update(cmd, DT), cmd)
    lag.update(np.array([9.0, 9.0, 9.0]), DT)          # 先制造不同的内部状态
    assert np.array_equal(lag.update(cmd, DT), cmd)
    tau, dt = 0.5, 0.005
    m = ActuatorLag(tau_s=tau)
    v = 0.0
    for _ in range(int(round(tau / dt))):              # 100 步正好 1τ
        v = float(m.update(np.array([1.0, 0.0, 0.0]), dt)[0])
    assert abs(v - (1.0 - math.exp(-1.0))) < 0.005
    assert abs(ActuatorLag(tau_s=0.0).update(cmd, DT)[0] - cmd[0]) < 1e-15
