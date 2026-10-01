"""跨文件共享的测试基础设施（审计 D16）。

**问题**：多个用例逐帧驱动 `SimRuntime` / `MissionController`，而 `FailsafeMonitor` 用
**墙钟 `time.time()`** 计算心跳间隔（`backend/mission/safety.py`）。在慢 runner（CI 的
2 核机）上，几十帧真可能花掉 > `timeout_land = 1.0s`，于是安全层按设计跳闸 → 机体下降 →
与用例断言无关的失真。CI 上已两次出现这类 flake。

**做法**：只替换**时间源**，安全检查逻辑一行不改 —— 冻结后 `elapsed` 恒为 0，等价于
"这段仿真里墙钟没有走动"，本机负载无法再影响结论。需要**真正制造超时跳闸**的用例不受影响
（它们直接回拨 `guard._last_heartbeat`，与时钟无关）。

**用法**：在需要的测试模块顶部加一行 `pytestmark = pytest.mark.no_wall_clock`。
新增用例若逐帧驱动 runtime / mission，请一并加上（这是 D16 的约定）。
"""

import time as _time

import pytest


class FrozenSafetyClock:
    """冻结的墙钟：只提供 `time()`（FailsafeMonitor 唯一用到的时间源），且永不前进。"""

    def __init__(self, now=None):
        self._now = _time.time() if now is None else now

    def time(self):
        return self._now

    def advance(self, seconds):
        self._now += seconds
        return self._now


def freeze_safety_clock(monkeypatch, clock=None):
    """把 `backend.mission.safety` 的时间源换成冻结时钟，返回该时钟（可 advance）。"""
    import backend.mission.safety as safety_mod

    clock = clock or FrozenSafetyClock()
    monkeypatch.setattr(safety_mod, "time", clock)
    return clock


@pytest.fixture(autouse=True)
def _freeze_safety_wall_clock_by_marker(request, monkeypatch):
    """仅在标了 `no_wall_clock` 的用例上冻结安全层墙钟（在构造 runtime 之前生效）。"""
    if request.node.get_closest_marker("no_wall_clock") is not None:
        freeze_safety_clock(monkeypatch)
