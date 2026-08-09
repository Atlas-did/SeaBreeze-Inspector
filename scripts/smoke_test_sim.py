#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CI smoke test: 验证 simulation headless 模式可初始化并运行 N 帧不崩溃。

用法:
  SDL_VIDEODRIVER=dummy python scripts/smoke_test_sim.py [--frames 30]
"""

import os
import sys

# 必须在导入 pygame 之前设置
os.environ["SDL_VIDEODRIVER"] = "dummy"

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ_ROOT)


def main():
    frames = 30
    if "--frames" in sys.argv:
        idx = sys.argv.index("--frames")
        if idx + 1 < len(sys.argv):
            frames = int(sys.argv[idx + 1])

    from backend.simulation.simulation import Simulation

    print("[SMOKE] 初始化 Simulation (headless)...")
    sim = Simulation(headless=True)
    print("[SMOKE] Simulation headless init 成功")

    print(f"[SMOKE] 运行 {frames} 帧...")
    sim.quad.set_velocity(sim.quad.get_velocity() * 0)
    for i in range(frames):
        try:
            sim.step(dt=1 / 30.0)
        except Exception as e:
            print(f"[SMOKE] 第 {i} 帧异常: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    print(f"[SMOKE] {frames} 帧运行成功, 无崩溃")
    sim.running = False
    import pygame
    pygame.quit()
    print("[SMOKE] Simulation headless smoke test 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
