#!/usr/bin/env python3
"""命令层测试 — FlightCommand / CommandResult / 瞬时指令执行。

覆盖:
  - schema 往返（to_dict / from_dict / to_dict JSON 可序列化）
  - 对 MockTello 执行 takeoff 等瞬时指令（不依赖硬件）
  - 动态指令 driver 协议识别
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from backend.drone.commands import (
    AltitudeHoldDriver,
    FlightCommand,
    CommandResult,
    execute_instant,
    run_altitude_hold,
)
from backend.drone.tello_basic import MockTello


def test_command_roundtrip():
    cmd = FlightCommand(op="altitude_hold", params={"target_m": 1.5},
                        note="sea-breeze baseline")
    d = cmd.to_dict()
    assert d["op"] == "altitude_hold"
    assert FlightCommand.from_dict(d).to_dict() == d


def test_result_json_serializable_and_evidence_level():
    r = CommandResult(op="takeoff", backend="mock", accepted=True,
                      target_m=1.5, measured_m=1.5, error_m=0.0,
                      steady_std_m=0.0, settled=True, state="HOVERING",
                      sim_seconds=1.0, seed=42, note="simulation-only")
    d = json.loads(json.dumps(r.to_dict()))
    assert d["evidence_level"] == "simulation-only"
    assert d["source"] == "SeaBreeze-Inspector"
    assert d["target_m"] == 1.5


def test_result_evidence_level_real_flight_not_downgraded():
    """F08: 真机数据显式标 real-flight 时,to_dict 原样保留,不得吞成 simulation-only。"""
    r = CommandResult(op="altitude_hold", backend="tello", accepted=True,
                      target_m=1.5, measured_m=1.48, error_m=0.02,
                      settled=True, evidence_level="real-flight")
    d = json.loads(json.dumps(r.to_dict()))
    assert d["evidence_level"] == "real-flight"


def test_instant_takeoff_on_mock():
    tello = MockTello()
    cmd = FlightCommand(op="takeoff", note="mock instant")
    r = execute_instant(tello, cmd)
    assert r.accepted is True
    assert r.backend == "MockTello"
    assert tello.is_flying is True


def test_instant_unsupported_op_raises():
    tello = MockTello()
    with pytest.raises(ValueError):
        execute_instant(tello, FlightCommand(op="flip"))


def test_run_altitude_hold_rejected_driver_skips_settle():
    """F01: set_target_altitude 被拒(False)时不调 settle, settled=False,不产出误导证据。"""
    class RejectingDriver:
        def backend_name(self):
            return "rejecting"
        def set_target_altitude(self, meters):
            return False
        def settle(self, seconds, dt=0.02):
            raise AssertionError("settle must not be called when accepted=False")
    r = run_altitude_hold(RejectingDriver(), target_m=1.5, settle_s=5.0, seed=42)
    assert r.accepted is False
    assert r.settled is False
    assert r.measured_m is None and r.error_m is None
