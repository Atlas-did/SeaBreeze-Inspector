"""速度模式基准脚本自身的守卫（审计 Phase 3）。

基准用于回答"换链路后差多少"，所以它自己必须:
  1. **可复现** —— 同一工况两次运行指标完全一致；
  2. 在**同一协议下**真实区分出两条路径的差别；
  3. 不把仿真结论说成真机结论（见 docs/HIL_PROTOCOL.md）。

为保持测试快，这里把协议帧数压到很小（只验证"机制"，不产出正式基准数字）。
正式基准请跑 `python scripts/bench_sim_modes.py`（结果写 docs/bench/）。
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location(
    "bench_sim_modes", REPO / "scripts" / "bench_sim_modes.py")
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


def _shorten_protocol():
    """把协议压到几十帧，让测试亚秒级完成。"""
    bench.P1_SETTLE_FRAMES = 0
    bench.P1_FRAMES = 60
    bench.P2_FRAMES = 60
    bench.P3_FRAMES = 60


def test_benchmark_is_deterministic():
    """同一工况两次运行必须完全一致（否则基准不可复现）。"""
    _shorten_protocol()
    first = bench.run_case("velocity", 0.0)
    second = bench.run_case("velocity", 0.0)
    assert first == second, "基准结果不可复现: {} != {}".format(first, second)


def test_modes_are_actually_different():
    """两条路径在同一协议下必须给出不同结果（否则基准没有区分度）。"""
    _shorten_protocol()
    legacy = bench.run_case("legacy", 0.0)
    velocity = bench.run_case("velocity", 0.0)
    assert legacy != velocity


def test_velocity_mode_stays_bounded_under_sustained_wind():
    """**安全相关**：持续 2 m/s 风下，速度模式（与真机 RC 同源）必须保持有界。

    实测（protocol v1，正式帧数）：legacy 位置级联在 2 m/s 持续风下横向误差
    可达数百米（发散），而 velocity 模式稳定在个位数厘米量级。
    这里只断言"有界"，避免把具体数字固化成脆弱的回归。
    """
    _shorten_protocol()
    velocity = bench.run_case("velocity", 2.0)
    assert velocity["P1_hover_hold"]["xy_err_max_cm"] < 500.0, \
        "速度模式在持续风下不应发散: {}".format(velocity["P1_hover_hold"])


def test_legacy_divergence_is_recorded_not_hidden():
    """把 legacy 在持续风下发散这个**发现**记下来（不是修好它，而是不许悄悄变）。"""
    _shorten_protocol()
    legacy = bench.run_case("legacy", 2.0)
    xy_max = legacy["P1_hover_hold"]["xy_err_max_cm"]
    assert xy_max > 100.0, (
        "legacy 在 2 m/s 持续风下的横向误差实测为 {}cm；若该行为已被修复，"
        "请更新本条与 docs/bench 里的记录，而不是让它静默变化".format(xy_max))
