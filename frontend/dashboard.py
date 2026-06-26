"""
Tkinter监控面板 — 实时显示无人机状态

选型: Tkinter (Python内置, 无需安装, 跨平台)
  布局: 左侧状态面板(电池/高度/坐标), 右侧视频窗口(640x480)
  更新: 100ms刷新
"""

import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk


class Dashboard:
    """
    无人机监控面板 — 4区域布局。
    支持 --mock 模式: 无真实硬件时用模拟数据填充UI。
    """

    def __init__(self, width=900, height=600, mock=False):
        self.mock = mock  # Mock模式: 使用模拟数据
        self.root = tk.Tk()
        self.root.title("无人机-机械臂协同系统监控面板" + (" [MOCK]" if mock else ""))
        self.root.geometry(f"{width}x{height}")

        # 左侧状态面板
        self.left_frame = tk.Frame(self.root, width=250, bg="#2c3e50")
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.left_frame.pack_propagate(False)

        # 标题
        tk.Label(self.left_frame, text="系统状态", font=("Arial", 16, "bold"),
                 bg="#2c3e50", fg="white").pack(pady=10)

        # 状态标签
        self.labels = {}
        status_items = [
            ("飞行状态", "UNKNOWN"),
            ("电池", "0%"),
            ("高度", "0 cm"),
            ("位置X", "0 cm"),
            ("位置Y", "0 cm"),
            ("位置Z", "0 cm"),
            ("扰动X", "0"),
            ("扰动Y", "0"),
            ("扰动Z", "0"),
            ("检测数", "0"),
        ]

        for name, default in status_items:
            frame = tk.Frame(self.left_frame, bg="#2c3e50")
            frame.pack(fill=tk.X, padx=10, pady=3)
            tk.Label(frame, text=f"{name}:", font=("Arial", 11),
                     bg="#2c3e50", fg="#bdc3c7").pack(side=tk.LEFT)
            label = tk.Label(frame, text=default, font=("Arial", 11, "bold"),
                            bg="#2c3e50", fg="white")
            label.pack(side=tk.RIGHT)
            self.labels[name] = label

        # 右侧视频窗口
        self.right_frame = tk.Frame(self.root, bg="black")
        self.right_frame.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)

        self.video_label = tk.Label(self.right_frame, bg="black")
        self.video_label.pack(expand=True)

        # 按钮区
        btn_frame = tk.Frame(self.left_frame, bg="#2c3e50")
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        tk.Button(btn_frame, text="起飞", command=lambda: self._send_cmd("takeoff"),
                  bg="#27ae60", fg="white").pack(fill=tk.X, padx=5, pady=2)
        tk.Button(btn_frame, text="降落", command=lambda: self._send_cmd("land"),
                  bg="#e74c3c", fg="white").pack(fill=tk.X, padx=5, pady=2)
        tk.Button(btn_frame, text="紧急停止", command=lambda: self._send_cmd("emergency"),
                  bg="#c0392b", fg="white").pack(fill=tk.X, padx=5, pady=2)

        self._callbacks = {}

    def register_callback(self, event: str, callback):
        """注册按钮回调"""
        self._callbacks[event] = callback

    def _send_cmd(self, cmd):
        if cmd in self._callbacks:
            self._callbacks[cmd]()

    def update(self, state: dict):
        """更新状态显示"""
        mapping = {
            "飞行状态": state.get("flight_state", "UNKNOWN"),
            "电池": f"{state.get('battery', 0)}%",
            "高度": f"{state.get('height', 0)} cm",
            "位置X": f"{state.get('position', [0,0,0])[0]:.1f} cm",
            "位置Y": f"{state.get('position', [0,0,0])[1]:.1f} cm",
            "位置Z": f"{state.get('position', [0,0,0])[2]:.1f} cm",
            "扰动X": f"{state.get('disturbance', [0,0,0])[0]:.2f}",
            "扰动Y": f"{state.get('disturbance', [0,0,0])[1]:.2f}",
            "扰动Z": f"{state.get('disturbance', [0,0,0])[2]:.2f}",
            "检测数": str(state.get("detection_count", 0)),
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

    def run(self):
        self.root.mainloop()
