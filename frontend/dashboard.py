"""
Tkinter监控面板 — 实时显示无人机状态

选型: Tkinter (Python内置, 无需安装, 跨平台)
布局: 左侧状态面板(电池/高度/坐标), 右侧视频窗口(640x480)
更新: 通过 MessageBus 订阅或 mock 模拟, 100ms刷新
"""

import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

# MessageBus 主题常量
TOPIC_MISSION_STATUS = "mission/status"
TOPIC_DRONE_COMMAND = "drone/command"


class Dashboard:
    """无人机监控面板

    两种模式:
      - 连接 MessageBus: 自动接收 MissionController 的状态推送
      - Mock 模式: 独立运行, 用模拟数据填充

    用法:
      # 连接后端
      dash = Dashboard(bus=mission_controller.bus)
      dash.run()

      # Mock 独立运行
      dash = Dashboard(mock=True)
      dash.run()
    """

    POLL_INTERVAL = 100  # 轮询间隔 (ms)

    def __init__(self, bus=None, mock=False, width=900, height=600):
        self.mock = mock
        self._bus = bus

        self.root = tk.Tk()
        title = "SeaBreeze Inspector — Dashboard"
        if mock:
            title += " [MOCK]"
        self.root.title(title)
        self.root.geometry(f"{width}x{height}")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ---- 左侧状态面板 ----
        self.left_frame = tk.Frame(self.root, width=250, bg="#2c3e50")
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.left_frame.pack_propagate(False)

        tk.Label(self.left_frame, text="System Status", font=("Arial", 16, "bold"),
                 bg="#2c3e50", fg="white").pack(pady=10)

        # 连接状态指示
        self._conn_indicator = tk.Label(
            self.left_frame, text="● DISCONNECTED", font=("Arial", 10),
            bg="#2c3e50", fg="#e74c3c")
        self._conn_indicator.pack(pady=(0, 5))

        # 状态标签 (label_key → tk.Label)
        self.labels = {}
        status_items = [
            ("Flight", "UNKNOWN"),
            ("Battery", "0%"),
            ("Height", "0 cm"),
            ("Pos X", "0 cm"),
            ("Pos Y", "0 cm"),
            ("Pos Z", "0 cm"),
            ("Dist X", "0"),
            ("Dist Y", "0"),
            ("Dist Z", "0"),
            ("Dets", "0"),
        ]
        for name, default in status_items:
            frame = tk.Frame(self.left_frame, bg="#2c3e50")
            frame.pack(fill=tk.X, padx=10, pady=2)
            tk.Label(frame, text=f"{name}:", font=("Arial", 10),
                     bg="#2c3e50", fg="#bdc3c7").pack(side=tk.LEFT)
            label = tk.Label(frame, text=default, font=("Arial", 10, "bold"),
                            bg="#2c3e50", fg="white")
            label.pack(side=tk.RIGHT)
            self.labels[name] = label

        # ---- 右侧视频窗口 ----
        self.right_frame = tk.Frame(self.root, bg="black")
        self.right_frame.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)

        self.video_label = tk.Label(self.right_frame, bg="black")
        self.video_label.pack(expand=True)

        # ---- 按钮区 ----
        btn_frame = tk.Frame(self.left_frame, bg="#2c3e50")
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        tk.Button(btn_frame, text="Takeoff", command=lambda: self._send_cmd("takeoff"),
                  bg="#27ae60", fg="white", font=("Arial", 11, "bold")).pack(
                      fill=tk.X, padx=5, pady=2)
        tk.Button(btn_frame, text="Land", command=lambda: self._send_cmd("land"),
                  bg="#e67e22", fg="white", font=("Arial", 11, "bold")).pack(
                      fill=tk.X, padx=5, pady=2)
        tk.Button(btn_frame, text="EMERGENCY STOP", command=lambda: self._send_cmd("emergency"),
                  bg="#c0392b", fg="white", font=("Arial", 11, "bold")).pack(
                      fill=tk.X, padx=5, pady=2)

        # 命令回调 (本地 fallback)
        self._callbacks = {}

        # 最后收到的状态
        self._last_state = {}
        self._last_msg_time = 0

        # 启动轮询
        if not mock and bus is not None:
            self._start_polling()

    # =========================================================================
    # MessageBus 集成
    # =========================================================================

    def connect_bus(self, bus):
        """连接到消息总线 (pub-sub: 独立订阅, 无竞争)"""
        self._bus = bus
        self._status_sub = bus.subscribe(TOPIC_MISSION_STATUS)
        self.mock = False
        self._start_polling()

    def _start_polling(self):
        """启动定时轮询 MessageBus"""
        self._poll_bus()

    def _poll_bus(self):
        """从 pub-sub 总线拉取最新状态 (非阻塞, 独立队列)"""
        import time
        if not hasattr(self, '_status_sub') or self._status_sub is None:
            self.root.after(self.POLL_INTERVAL, self._poll_bus)
            return

        latest = self._status_sub.read_latest()

        if latest is not None:
            self._last_msg_time = time.time()
            self._last_state = latest.data
            self.update(latest.data)
            self._conn_indicator.config(text="● CONNECTED", fg="#27ae60")

        # 检测超时
        if time.time() - self._last_msg_time > 2.0 and self._last_msg_time > 0:
            self._conn_indicator.config(text="● TIMEOUT", fg="#f39c12")

        self.root.after(self.POLL_INTERVAL, self._poll_bus)

    # =========================================================================
    # 命令
    # =========================================================================

    def register_callback(self, event: str, callback):
        """注册按钮回调 (无 MessageBus 时的本地回退)"""
        self._callbacks[event] = callback

    def _send_cmd(self, cmd):
        """发送命令: 优先通过 MessageBus, 回退到本地回调"""
        if self._bus is not None:
            self._bus.publish(TOPIC_DRONE_COMMAND,
                              {"command": cmd}, source="dashboard")
            return
        # 回退
        if cmd in self._callbacks:
            self._callbacks[cmd]()

    # =========================================================================
    # 状态更新
    # =========================================================================

    def update(self, state: dict):
        """更新状态显示 (从 MessageBus 或手动调用)"""
        pos = state.get("position", [0, 0, 0])
        dist = state.get("disturbance", [0, 0, 0])

        mapping = {
            "Flight": state.get("flight_state", state.get("state", "UNKNOWN")),
            "Battery": f"{state.get('battery', 0)}%",
            "Height": f"{state.get('height', 0):.0f} cm",
            "Pos X": f"{pos[0]:.0f} cm",
            "Pos Y": f"{pos[1]:.0f} cm",
            "Pos Z": f"{pos[2]:.0f} cm",
            "Dist X": f"{dist[0]:.1f}",
            "Dist Y": f"{dist[1]:.1f}",
            "Dist Z": f"{dist[2]:.1f}",
            "Dets": str(state.get("detection_count", 0)),
        }
        for key, value in mapping.items():
            if key in self.labels:
                self.labels[key].config(text=str(value))

    def update_video(self, frame: np.ndarray):
        """更新视频帧"""
        if frame is None:
            return
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame)
        img = img.resize((640, 480), Image.LANCZOS)
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_label.imgtk = imgtk
        self.video_label.configure(image=imgtk)

    # =========================================================================
    # 生命周期
    # =========================================================================

    def run(self):
        self.root.mainloop()

    def _on_close(self):
        """关闭窗口"""
        self.root.quit()
        self.root.destroy()


# =========================================================================
# 独立运行入口
# =========================================================================

if __name__ == "__main__":
    import random

    dash = Dashboard(mock=True)
    print("[Dashboard] Mock 模式启动 — 模拟数据每 500ms 刷新")

    def mock_update():
        dash.update({
            "flight_state": random.choice(["IDLE", "HOVERING", "NAVIGATE"]),
            "battery": random.randint(30, 100),
            "height": random.randint(50, 200),
            "position": [random.uniform(-100, 100) for _ in range(3)],
            "disturbance": [random.uniform(-5, 5) for _ in range(3)],
            "detection_count": random.randint(0, 3),
        })
        dash.root.after(500, mock_update)

    dash.root.after(500, mock_update)
    dash.run()
