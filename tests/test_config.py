#!/usr/bin/env python3
"""
配置系统测试 — 验证配置加载、缺失键处理、类型检查
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.utils.config import ConfigLoader


def test_load_yaml():
    """测试 YAML 配置加载"""
    print("[TEST] YAML 配置加载")

    config = ConfigLoader.load("drone_config", config_dir=PROJECT_ROOT / "config")

    # 验证基本结构 (通过属性访问) — 与 drone_config.yaml 实际结构匹配
    assert hasattr(config, "connection"), "应包含 connection 段"
    assert hasattr(config, "flight"), "应包含 flight 段"
    assert hasattr(config, "safety"), "应包含 safety 段"
    assert hasattr(config, "imu_noise"), "应包含 imu_noise 段"
    assert hasattr(config, "mode"), "应包含 mode 段"

    print("  [OK] 所有配置段加载成功")
    print("  [PASS]")


def test_nested_access():
    """测试嵌套配置访问"""
    print("[TEST] 嵌套配置访问")

    config = ConfigLoader.load("drone_config", config_dir=PROJECT_ROOT / "config")

    # 属性式访问嵌套值
    speed = config.flight.default_speed
    assert isinstance(speed, (int, float)), f"default_speed 应为数值, 实际={type(speed)}"
    assert speed > 0, f"default_speed 应>0, 实际={speed}"
    print(f"  flight.default_speed = {speed}")

    # 嵌套字典访问
    boundary = config.safety.boundary
    assert isinstance(boundary.to_dict(), dict), "boundary 应为嵌套配置"
    print(f"  safety.boundary.z_max = {boundary.z_max}cm")

    print("  [PASS]")


def test_missing_key():
    """测试缺失键处理"""
    print("[TEST] 缺失键处理")

    config = ConfigLoader.load("drone_config", config_dir=PROJECT_ROOT / "config")

    # 缺失键返回默认值
    val = config.get("nonexistent_key", default="fallback")
    assert val == "fallback", "缺失键应返回默认值"
    print("  [OK] 缺失键返回默认值")

    # 嵌套属性缺失
    try:
        _ = config.flight.nonexistent_field
        assert False, "应抛出属性错误"
    except AttributeError:
        print("  [OK] 嵌套缺失键抛出AttributeError")

    print("  [PASS]")


def test_type_safety():
    """测试类型转换"""
    print("[TEST] 类型安全")

    config = ConfigLoader.load("drone_config", config_dir=PROJECT_ROOT / "config")

    # 浮点数
    hover_time = config.flight.hover_stabilize_time
    assert isinstance(hover_time, float), f"hover_stabilize_time 应为 float, 实际是 {type(hover_time)}"
    assert hover_time > 0
    print(f"  flight.hover_stabilize_time = {hover_time} (type={type(hover_time).__name__})")

    # 整数
    max_height = config.flight.max_height
    assert isinstance(max_height, int), f"max_height 应为 int, 实际是 {type(max_height)}"
    assert max_height > 0
    print(f"  flight.max_height = {max_height} (type={type(max_height).__name__})")

    # 布尔值
    debug = config.mode.debug
    assert isinstance(debug, bool), f"debug 应为 bool, 实际是 {type(debug)}"
    print(f"  mode.debug = {debug} (type={type(debug).__name__})")

    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  配置系统测试套件")
    print("=" * 50)
    test_load_yaml()
    test_nested_access()
    test_missing_key()
    test_type_safety()
    print("\n[OK] 所有配置测试通过!")
