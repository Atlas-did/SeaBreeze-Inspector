"""HIL 冒烟脚本: 手动验证真机 RC 速度控制链 (P0-2)。

默认**不连真机**: 用记录型假底层对象跑通 connect -> takeoff -> set_velocity -> land,
打印收到的 RC 帧数与实测发送频率。
传 --real 才会真正连接 Tello(需先连上 Tello WiFi, 且现场无人)。

用法:
    venv\\Scripts\\python.exe scripts\\hil_smoke.py            # 离线自检
    venv\\Scripts\\python.exe scripts\\hil_smoke.py --real     # 真机
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.drone.tello_basic import TelloController  # noqa: E402


class RecordingTello:
    """记录 send_rc_control 的假底层对象(离线自检用)。"""

    def __init__(self):
        self.frames = []

    def connect(self):
        return True

    def takeoff(self):
        return True

    def land(self):
        return True

    def emergency(self):
        return True

    def move_down(self, dist):
        return True

    def send_rc_control(self, lr, fb, ud, yaw):
        self.frames.append((time.time(), int(lr), int(fb), int(ud), int(yaw)))

    def send_keepalive(self):
        pass

    def get_battery(self):
        return 100

    def get_height(self):
        return 100


def make_controller(real: bool):
    # 两条路径都必须 mock=False: 真机分支才会 attach 底层对象并启动 20Hz 线程。
    ctl = TelloController(mock=False)
    if real:
        return ctl, None
    fake = RecordingTello()
    import types
    module = types.ModuleType("djitellopy")
    module.Tello = lambda *a, **k: fake
    sys.modules["djitellopy"] = module
    return ctl, fake


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="真正连接 Tello(危险)")
    ap.add_argument("--vz", type=int, default=20, help="上升速度 cm/s (默认 20)")
    ap.add_argument("--hold", type=float, default=1.5, help="持续下发秒数")
    args = ap.parse_args()

    ctl, fake = make_controller(args.real)
    if not ctl.connect():
        print("[SMOKE] connect 失败")
        return 1
    if not ctl.takeoff():
        print("[SMOKE] takeoff 失败")
        return 1

    t0 = time.time()
    ctl.set_velocity(0, 0, args.vz)
    time.sleep(args.hold)
    rate = len(fake.frames) / max(1e-6, time.time() - t0) if fake else float("nan")
    ctl.land()
    ctl.release()

    if fake:
        target = (0, 0, args.vz, 0)
        n = sum(1 for f in fake.frames if f[1:] == target)
        zeros = sum(1 for f in fake.frames if f[1:] == (0, 0, 0, 0))
        print("[SMOKE] RC 帧总数={} 其中速度帧={} 归零帧={}".format(
            len(fake.frames), n, zeros))
        print("[SMOKE] 实测发送频率 ≈ {:.1f} Hz (期望 {})".format(
            rate, ctl._rc.SEND_RATE_HZ))
        print("[SMOKE] 状态={} 结果={}".format(
            ctl.state.name, "OK" if n >= 5 and zeros >= 1 else "FAIL"))
        return 0 if n >= 5 and zeros >= 1 else 1

    print("[SMOKE] 真机流程完成, 状态={}".format(ctl.state.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
