#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CI smoke test: verify simulation headless mode init and run N frames without crash.

Usage:
  SDL_VIDEODRIVER=dummy python scripts/smoke_test_sim.py [--frames 30]
"""

import os
import sys

# Must set before importing pygame
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

    print("[SMOKE] Initializing Simulation (headless)...")
    sim = Simulation(headless=True)
    print("[SMOKE] Simulation headless init OK")

    print("[SMOKE] Running {} frames...".format(frames))
    sim.quad.set_velocity(sim.quad.get_velocity() * 0)
    for i in range(frames):
        try:
            sim.step(dt=1 / 30.0)
        except Exception as e:
            print("[SMOKE] Frame {} error: {}".format(i, e))
            import traceback
            traceback.print_exc()
            sys.exit(1)

    print("[SMOKE] {} frames OK, no crash".format(frames))
    sim.running = False
    import pygame
    pygame.quit()
    print("[SMOKE] Simulation headless smoke test PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
