#!/usr/bin/env python3
"""自家仿真高度保持基准测试 — SimRuntimeDriver / run_altitude_hold。

目标: 用统一口径给出 SeaBreeze 自己的稳态高度误差参考数，
并验证可复现（同种子两次运行结果一致）。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from backend.drone.commands import run_altitude_hold
from backend.simulation.altitude_driver import build_sim_driver


def test_altitude_hold_ideal_is_deterministic():
    """静风理想模型：同种子两次运行稳态误差一致（可复现性）。"""
    driver1 = build_sim_driver(calm=True)
    r1 = run_altitude_hold(driver1, target_m=1.5, settle_s=20.0, seed=42)
    driver2 = build_sim_driver(calm=True)
    r2 = run_altitude_hold(driver2, target_m=1.5, settle_s=20.0, seed=42)
    assert r1.accepted is True and r2.accepted is True
    assert r1.state == "HOVERING" and r2.state == "HOVERING"
    assert r1.measured_m is not None and r2.measured_m is not None
    # 静风 + 近零噪声：稳态应精确落在目标附近（容差放宽到 5mm）
    assert abs(r1.error_m) < 0.005, f"理想工况误差应≈0，实际 {r1.error_m}"
    # 可复现性：同种子两次运行稳态误差一致
    assert abs(r1.error_m - r2.error_m) < 1e-9, \
        f"同种子两次运行应一致，实际 {r1.error_m} vs {r2.error_m}"


def test_altitude_hold_windy_is_nonzero():
    """带风工况：误差非零且量级合理，作为保真度对比的参考。"""
    driver = build_sim_driver(calm=False)
    r = run_altitude_hold(driver, target_m=1.5, settle_s=30.0, seed=7)
    assert r.settled is True
    assert r.steady_std_m is not None
    # 0.5m/s 顺风 + 阵风：高度应低于目标，误差为正且 < 0.3m（级联 P 控制上限）
    assert 0.0 < r.error_m < 0.3, f"带风误差应为正且<0.3m，实际 {r.error_m}"


def test_result_contains_measurement_protocol_fields():
    driver = build_sim_driver(calm=True)
    r = run_altitude_hold(driver, target_m=1.0, settle_s=10.0, seed=42)
    d = r.to_dict()
    for key in ("op", "backend", "target_m", "measured_m", "error_m",
                "steady_std_m", "settled", "sim_seconds", "seed", "evidence_level"):
        assert key in d
    assert d["backend"] == "sim"
    assert d["evidence_level"] == "simulation-only"
    assert d["sim_seconds"] == 10.0
