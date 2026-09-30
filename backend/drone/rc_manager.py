"""
RC 管理器 — 持续发送速度指令 + 超时自动归零 (对标 DJITelloPy 的 send_rc_control)

用法:
    rc = RCManager(drone_controller)
    rc.start()
    rc.set_command(lr=0, fb=0, ud=30, yaw=0)  # 上升
    # ... 3秒无新指令后自动归零归零
    rc.stop()
"""

from __future__ import annotations

import threading
import time
from typing import Optional


class RCManager:
    """RC 控制生命周期管理器

    特性:
      - 独立线程 20Hz 持续发送 rc_control
      - 0.5s 无新指令自动归零 (防止无人机飞丢)
      - keepalive: 每隔 3s 发一次 command 维持连接
    """

    SEND_RATE_HZ = 20           # 发送频率
    ZERO_TIMEOUT = 0.5          # 超时归零 (s)
    KEEPALIVE_INTERVAL = 3.0    # keepalive 间隔 (s)

    def __init__(self, drone_controller=None, mock: bool = False):
        self._drone = drone_controller
        self._mock = mock
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # 当前指令
        self._cmd = {"lr": 0, "fb": 0, "ud": 0, "yaw": 0}
        self._last_cmd_time = 0.0
        self._last_keepalive = 0.0

        # P0-2 可观测性: mock 模式下也记录"实际下发的 RC 指令",
        # 否则无法在离线测试中证明速度控制真的生效(而不是又走了位移指令)。
        # P0-C 补完: 发送失败必须**可见** —— 此前 `except Exception: pass` 让
        # 失败帧与成功帧长得一模一样("界面在发速度、飞机却没反应"时无据可依)。
        self.send_failures = 0
        self.last_send_error = None
        self.last_rc: tuple = (0, 0, 0, 0)
        self.rc_log: list = []
        self._log_max = 200

    def attach(self, drone):
        """绑定底层 djitellopy 对象 (真机 connect 成功后调用)"""
        self._drone = drone

    def start(self):
        """启动 RC 发送线程"""
        if self._running:
            return
        self._running = True
        self._last_cmd_time = time.time()
        self._last_keepalive = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止发送 (发送归零指令后退出)"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        # 发送一次归零
        self._send_zero()

    def set_command(self, lr: float = 0, fb: float = 0,
                    ud: float = 0, yaw: float = 0):
        """设置速度指令 (cm/s, 范围 -100~100)"""
        with self._lock:
            self._cmd = {
                "lr": max(-100, min(100, int(lr))),
                "fb": max(-100, min(100, int(fb))),
                "ud": max(-100, min(100, int(ud))),
                "yaw": max(-100, min(100, int(yaw))),
            }
            self._last_cmd_time = time.time()
            # P0-2: 记录"意图下发的指令"(限幅后), mock 模式下没有发送线程,
            # 离线测试据此断言速度控制确实被调用。
            self.last_cmd = (self._cmd["lr"], self._cmd["fb"],
                             self._cmd["ud"], self._cmd["yaw"])

    def _loop(self):
        """RC 发送主循环 (20Hz)"""
        while self._running:
            now = time.time()
            elapsed = now - self._last_cmd_time

            with self._lock:
                if elapsed > self.ZERO_TIMEOUT:
                    # 超时归零
                    cmd = {"lr": 0, "fb": 0, "ud": 0, "yaw": 0}
                else:
                    cmd = dict(self._cmd)

            # 发送
            self._send_rc(cmd["lr"], cmd["fb"], cmd["ud"], cmd["yaw"])

            # keepalive
            if now - self._last_keepalive > self.KEEPALIVE_INTERVAL:
                self._send_keepalive()
                self._last_keepalive = now

            time.sleep(1.0 / self.SEND_RATE_HZ)

    def _note_send_failure(self, what, exc):
        """记录一次发送失败(不打断发送线程, 但必须留下痕迹)。"""
        self.send_failures += 1
        self.last_send_error = "{}: {}".format(what, exc)
        if self.send_failures in (1, 10, 100):
            print("[WARN] RC {} 发送失败 (第 {} 次): {}".format(
                what, self.send_failures, exc))

    def _send_rc(self, lr, fb, ud, yaw):
        """发送 RC 控制指令"""
        # P0-2: 无论 mock 与否都留痕 —— 离线测试据此断言"确实走的是速度控制"
        self.last_rc = (int(lr), int(fb), int(ud), int(yaw))
        with self._lock:
            self.rc_log.append(self.last_rc)
            if len(self.rc_log) > self._log_max:
                del self.rc_log[:-self._log_max]
        if self._mock:
            return
        if self._drone and hasattr(self._drone, 'send_rc_control'):
            try:
                self._drone.send_rc_control(lr, fb, ud, yaw)
            except Exception as e:
                self._note_send_failure("rc", e)

    def _send_keepalive(self):
        """发送 keepalive (保持连接)"""
        if self._mock:
            return
        if self._drone and hasattr(self._drone, 'send_keepalive'):
            try:
                self._drone.send_keepalive()
            except Exception as e:
                self._note_send_failure("keepalive", e)

    def _send_zero(self):
        """发送归零指令"""
        if self._mock:
            return
        if self._drone and hasattr(self._drone, 'send_rc_control'):
            try:
                self._drone.send_rc_control(0, 0, 0, 0)
            except Exception as e:
                self._note_send_failure("zero", e)
