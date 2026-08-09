#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""启动前依赖检查 — CI 早期失败, 避免跑到一半才发现环境问题。

检查项:
  1. Python 版本 >= 3.8
  2. 必需的第三方库 (pygame, numpy, ultralytics, cv2, yaml)
  3. 配置文件存在 (drone_config.yaml, yolo_config.yaml, arm_config.yaml)
  4. YOLO 模型权重文件存在 (可选, 缺失仅告警)
  5. 目录结构完整性
  6. SDL/headless 环境 (CI 模式下强制检查)

用法:
  python scripts/check_deps.py           # 标准检查
  python scripts/check_deps.py --ci      # CI 模式 (headless 检查 + 权重必检)
  python scripts/check_deps.py --json    # JSON 输出 (供 CI 解析)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_PROJ_ROOT = Path(__file__).resolve().parents[1]
os.chdir(str(_PROJ_ROOT))
sys.path.insert(0, str(_PROJ_ROOT))


def _ok(msg: str) -> str:
    return f"  [OK]  {msg}"


def _warn(msg: str) -> str:
    return f"  [WARN]  {msg}"


def _err(msg: str) -> str:
    return f"  [FAIL]  {msg}"


def check_python() -> tuple[bool, str]:
    """检查 Python 版本 >= 3.8"""
    v = sys.version_info
    if v >= (3, 8):
        return True, _ok(f"Python {v.major}.{v.minor}.{v.micro}")
    return False, _err(f"Python {v.major}.{v.minor}.{v.micro} (需要 >= 3.8)")


def check_imports() -> list[tuple[bool, str]]:
    """检查关键依赖是否可导入"""
    results = []
    for mod_name, pip_name, required in [
        ("numpy", "numpy", True),
        ("yaml", "pyyaml", True),
        ("cv2", "opencv-python", True),
        ("pygame", "pygame", False),  # CI 不需要 pygame 窗口
        ("ultralytics", "ultralytics", False),  # 训练/推理用, 非必须
    ]:
        try:
            __import__(mod_name)
            results.append((True, _ok(f"{pip_name} 可用")))
        except ImportError:
            if required:
                results.append((False, _err(f"{pip_name} 缺失 — 请运行: pip install {pip_name}")))
            else:
                results.append((True, _warn(f"{pip_name} 未安装 (可选依赖)")))
    return results


def check_config_files() -> list[tuple[bool, str]]:
    """检查配置文件是否存在"""
    config_dir = _PROJ_ROOT / "config"
    results = []
    for cfg_name in ["drone_config.yaml", "yolo_config.yaml", "arm_config.yaml"]:
        path = config_dir / cfg_name
        if path.exists():
            results.append((True, _ok(f"config/{cfg_name}")))
        else:
            results.append((False, _err(f"config/{cfg_name} 缺失")))
    return results


def check_model_weights(ci_mode: bool = False) -> list[tuple[bool, str]]:
    """检查 YOLO 模型权重文件"""
    weights_dir = _PROJ_ROOT / "data" / "weights"
    results = []
    if not weights_dir.exists():
        if ci_mode:
            results.append((False, _err("data/weights/ 目录缺失 (CI 模式下必须存在或可下载)")))
        else:
            results.append((True, _warn("data/weights/ 目录不存在 (将使用 mock 检测)")))
        return results

    found = list(weights_dir.glob("*.pt"))
    if found:
        for w in found:
            results.append((True, _ok(f"data/weights/{w.name}")))
    else:
        if ci_mode:
            results.append((False, _err("data/weights/ 为空 (CI 模式下需要模型权重)")))
        else:
            results.append((True, _warn("data/weights/ 为空 (将使用 mock 检测)")))
    return results


def check_directories() -> list[tuple[bool, str]]:
    """检查关键目录结构"""
    required_dirs = [
        "backend", "backend/utils", "backend/vision", "backend/simulation",
        "backend/mission", "backend/core", "backend/drone", "backend/arm",
        "backend/hal", "backend/runtime",
        "config", "data", "logs", "tests",
    ]
    results = []
    for d in required_dirs:
        path = _PROJ_ROOT / d
        if path.is_dir():
            results.append((True, _ok(d)))
        else:
            results.append((False, _err(f"{d}/ 目录缺失")))
    return results


def check_headless_env(ci_mode: bool = False) -> tuple[bool, str]:
    """检查 headless/CI 环境变量"""
    sdl_driver = os.environ.get("SDL_VIDEODRIVER", "")
    if ci_mode and sdl_driver != "dummy":
        return False, _err(
            "CI 模式下 SDL_VIDEODRIVER 应设为 'dummy', "
            f"当前值: '{sdl_driver or '(未设置)'}'"
        )
    if sdl_driver == "dummy":
        return True, _ok("SDL_VIDEODRIVER=dummy (headless 就绪)")
    return True, _ok("SDL 正常 (GUI 模式)")


def check_backend_imports() -> list[tuple[bool, str]]:
    """验证后端关键模块可以导入 (无语法错误)"""
    results = []
    modules_to_check = [
        ("backend.utils.config", "ConfigLoader"),
        ("backend.utils.bus", "MessageBus"),
        ("backend.mission.states", "MissionState"),
        ("backend.mission.safety", "FailsafeMonitor"),
        ("backend.simulation.models", "Quadrotor3D"),
        ("backend.runtime.loop", "SimRuntime"),
    ]
    for mod_name, attr in modules_to_check:
        try:
            mod = __import__(mod_name, fromlist=[attr])
            getattr(mod, attr)
            results.append((True, _ok(f"{mod_name} 可导入")))
        except Exception as e:
            results.append((False, _err(f"{mod_name} 导入失败: {e}")))
    return results


def main():
    ci_mode = "--ci" in sys.argv
    json_mode = "--json" in sys.argv

    all_checks = []
    fatal = False

    def add(ok: bool, msg: str):
        nonlocal fatal
        if not ok:
            fatal = True
        all_checks.append({"status": "ok" if ok else "fail", "message": msg})
        if not json_mode:
            print(msg)

    if not json_mode:
        print("=" * 60)
        print("  SeaBreeze Inspector — 依赖检查")
        print("  CI 模式: {}".format("是" if ci_mode else "否"))
        print("=" * 60)
        print()

    # Python 版本
    ok, msg = check_python()
    add(ok, msg)

    # 第三方库
    for ok, msg in check_imports():
        add(ok, msg)

    # 后端模块导入
    if not json_mode:
        print()
    for ok, msg in check_backend_imports():
        add(ok, msg)

    # 配置文件
    if not json_mode:
        print()
    for ok, msg in check_config_files():
        add(ok, msg)

    # 模型权重
    for ok, msg in check_model_weights(ci_mode=ci_mode):
        add(ok, msg)

    # 目录结构
    if not json_mode:
        print()
    for ok, msg in check_directories():
        add(ok, msg)

    # Headless
    if not json_mode:
        print()
    ok, msg = check_headless_env(ci_mode=ci_mode)
    add(ok, msg)

    if not json_mode:
        print()
        if fatal:
            print("=" * 60)
            print("  [FAIL] 检查失败 — 请修复以上错误后重试")
            print("=" * 60)
        else:
            print("=" * 60)
            print("  [OK] 所有检查通过")
            print("=" * 60)

    if json_mode:
        print(json.dumps({
            "overall": "fail" if fatal else "pass",
            "checks": all_checks,
        }, ensure_ascii=False, indent=2))

    sys.exit(1 if fatal else 0)


if __name__ == "__main__":
    main()
