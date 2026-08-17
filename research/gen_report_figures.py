#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_report_figures.py —— 为项目总结报告生成技术配图(matplotlib,中文)。

生成:
  1. figures/architecture.png      系统分层架构图
  2. figures/control_loop.png      控制闭环数据流图
  3. figures/state_machine.png     8 状态任务状态机
  4. figures/arm_kinematics.png    3-DOF 机械臂运动学示意
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Rectangle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "figures")
os.makedirs(OUT, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

C_LAYER = "#EAF1FB"   # 层背景
C_BOX = "#2F5597"     # 主色
C_BOX2 = "#4472C4"
C_ACC = "#C00000"     # 强调
C_LINE = "#555555"


def box(ax, x, y, w, h, text, fc=C_BOX2, tc="white", fs=9, ec="none", bold=False):
    b = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.02",
                       fc=fc, ec=ec, lw=1.2 if ec != "none" else 0)
    ax.add_patch(b)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc, weight="bold" if bold else "normal", wrap=True)
    return (x, y, w, h)


def arrow(ax, p1, p2, color=C_LINE, style="-|>", lw=1.4):
    a = FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=13,
                        color=color, lw=lw, shrinkA=0, shrinkB=0)
    ax.add_patch(a)


def new_ax(w=12, h=8):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    return fig, ax


# ───────────────────────────────────────────────────────────── 1. 架构图
def fig_architecture():
    fig, ax = new_ax(13, 9)
    layers = [
        ("应用层 (演示/交互)", [
            ("Web 3D 仿真\n(Three.js)", C_BOX2), ("桌面仪表盘\n(Tkinter)", C_BOX2),
            ("桌面仿真\n(Pygame)", C_BOX2), ("HTTP 桥\n(REST/JSON)", C_BOX2)]),
        ("决策层 (使命与安全)", [
            ("任务状态机\n(8 态 FSM)", C_BOX), ("RRT* 路径规划\n(cKDTree)", C_BOX),
            ("分层安全监控\n(WARN/LAND/KILL)", C_BOX)]),
        ("算法层 (核心)", [
            ("EKF 扰动观测器\n(12 状态)", C_BOX2), ("前馈-PID 控制器\n(抗饱和/积分分离)", C_BOX2),
            ("YOLOv8-Nano\n缺陷检测", C_BOX2), ("机械臂 FK/IK\n(3-DOF)", C_BOX2)]),
        ("抽象层 (HAL / 总线)", [
            ("DroneInterface", "#8EAADB"), ("ArmInterface", "#8EAADB"),
            ("VisionInterface", "#8EAADB"), ("MessageBus\n(pub-sub)", "#8EAADB")]),
        ("硬件层", [
            ("DJI Tello\n(87g)", "#B4C7E7"), ("Arduino Nano\n+PCA9685+SG90", "#B4C7E7"),
            ("传感器\n(IMU/光流/气压)", "#B4C7E7")]),
    ]
    y = 84
    lh = 15
    gap = 2.2
    for i, (label, boxes) in enumerate(layers):
        # 层标签
        ax.text(1, y + lh - 2, label, fontsize=9.5, color="#1F3864", weight="bold",
                va="top", ha="left")
        n = len(boxes)
        bw = 90 / n
        for j, (txt, fc) in enumerate(boxes):
            x = 5 + j * bw
            box(ax, x, y, bw - 2.2, lh - 4, txt, fc=fc, fs=8.5)
        y -= (lh + gap)
    # 层间箭头
    ax.text(98, 96, "数据流向", fontsize=8, color=C_LINE, rotation=90, va="top")
    fig.suptitle("SeaBreeze Inspector 系统分层架构", fontsize=14, weight="bold", y=0.99)
    fig.savefig(os.path.join(OUT, "architecture.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ───────────────────────────────────────────────────────────── 2. 控制闭环
def fig_control_loop():
    fig, ax = new_ax(13, 7.5)
    # 主闭环: 传感器 -> EKF -> PID -> 执行 -> 物理 -> 传感器
    box(ax, 4, 58, 20, 16, "传感器\nIMU / 光流 / 气压\n(真机 Tello / 仿真 VirtualSensor)", fc=C_BOX2, fs=8)
    box(ax, 40, 58, 20, 16, "EKF 扰动观测器\n(12 状态, 自适应 Q)", fc=C_BOX, fs=8.5)
    box(ax, 76, 58, 20, 16, "前馈-PID 控制器\nv_cmd = PID + Kff·d_est", fc=C_BOX, fs=8.5)
    box(ax, 40, 8, 20, 16, "无人机物理\n(Tello / 质点动力学)", fc="#8EAADB", fs=8.5)
    box(ax, 76, 8, 20, 16, "执行器\nTelloController /\nSimDroneAdapter", fc="#8EAADB", fs=8.5)
    # 规划/状态机 上方
    box(ax, 4, 30, 20, 14, "RRT* 路径规划\n(路径点)", fc="#B4C7E7", fs=8)
    box(ax, 40, 30, 20, 14, "任务状态机\n(8 态 FSM, 10Hz)", fc="#B4C7E7", fs=8)
    box(ax, 76, 30, 20, 14, "分层安全监控\nFailsafeMonitor", fc="#B4C7E7", fs=8)

    arrow(ax, (24, 66), (40, 66))          # 传感器 -> EKF
    arrow(ax, (60, 66), (76, 66))          # EKF -> PID
    arrow(ax, (86, 58), (86, 24))          # PID -> 执行器
    arrow(ax, (76, 24), (60, 16))          # 执行器 -> 物理
    arrow(ax, (40, 24), (14, 24)); arrow(ax, (14, 24), (14, 58))  # 物理 -> 传感器(反馈)
    arrow(ax, (14, 44), (40, 44))          # RRT* -> 状态机
    arrow(ax, (50, 44), (50, 58))          # 状态机 -> EKF/PID(目标点)
    arrow(ax, (60, 44), (86, 44))          # 状态机 -> 安全
    arrow(ax, (86, 44), (86, 58))          # 安全 -> 干预
    ax.text(50, 52, "目标点 + 扰动估计", fontsize=8, color=C_LINE, ha="center")
    ax.text(14, 26, "状态反馈", fontsize=8, color=C_ACC, ha="center")
    fig.suptitle("控制闭环数据流 (10 Hz)", fontsize=14, weight="bold", y=0.99)
    fig.savefig(os.path.join(OUT, "control_loop.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ───────────────────────────────────────────────────────────── 3. 状态机
def fig_state_machine():
    fig, ax = new_ax(12, 6)
    states = [
        ("IDLE", 3, 55), ("TAKEOFF", 18, 55), ("HOVERING", 33, 55),
        ("NAVIGATE", 48, 55), ("INSPECT", 63, 55), ("RETURN", 78, 55),
        ("LAND", 90, 55),
    ]
    for name, x, y in states:
        box(ax, x, y, 11, 14, name, fc=C_BOX2, fs=9, bold=True)
    for i in range(len(states) - 1):
        arrow(ax, (states[i][1] + 11, 62), (states[i + 1][1], 62))
    # EMERGENCY
    box(ax, 48, 18, 20, 14, "EMERGENCY\n(任意态可进入)", fc=C_ACC, fs=9, bold=True)
    arrow(ax, (48, 62), (54, 32), color=C_ACC)
    arrow(ax, (70, 62), (62, 32), color=C_ACC)
    ax.text(50, 45, "急停(可恢复)", fontsize=8, color=C_ACC, ha="center")
    fig.suptitle("任务状态机 (8 态 FSM)", fontsize=14, weight="bold", y=0.99)
    fig.savefig(os.path.join(OUT, "state_machine.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ───────────────────────────────────────────────────────────── 4. 机械臂运动学
def fig_arm():
    fig, ax = new_ax(12, 8)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.axis("off")
    # 底座 + 大臂 + 小臂(2D 侧视示意)
    base = Rectangle((42, 8), 16, 8, fc="#4472C4", ec="none")
    ax.add_patch(base)
    ax.text(50, 12, "底座 θ1 回转", fontsize=8, color="white", ha="center", weight="bold")
    # 关节1
    j1 = (50, 16)
    # 大臂 L1=55 (画到 45°)
    import numpy as np
    L1, L2, L3 = 26, 22, 14
    th2 = np.radians(55); th3 = np.radians(35)
    j2 = (j1[0] + L1 * np.cos(th2), j1[1] + L1 * np.sin(th2))
    j3 = (j2[0] + L2 * np.cos(th2 + th3), j2[1] + L2 * np.sin(th2 + th3))
    ee = (j3[0] + L3 * np.cos(th2 + th3), j3[1] + L3 * np.sin(th2 + th3))
    ax.plot([j1[0], j2[0]], [j1[1], j2[1]], lw=5, color="#2F5597", solid_capstyle="round")
    ax.plot([j2[0], j3[0]], [j2[1], j3[1]], lw=4.2, color="#4472C4", solid_capstyle="round")
    ax.plot([j3[0], ee[0]], [j3[1], ee[1]], lw=3.4, color="#8EAADB", solid_capstyle="round")
    for p, lab in [(j1, "θ1 底座"), (j2, "θ2 大臂"), (j3, "θ3 小臂"), (ee, "末端执行器")]:
        ax.plot(*p, "o", ms=7, color=C_ACC, zorder=5)
        ax.text(p[0] + 2, p[1] + 1, lab, fontsize=9, color="black")
    ax.text(j2[0] + 1, (j1[1] + j2[1]) / 2, "L1=55mm", fontsize=8, color="#2F5597")
    ax.text((j2[0] + j3[0]) / 2, (j2[1] + j3[1]) / 2, "L2=45mm", fontsize=8, color="#4472C4")
    # 关节限位
    ax.text(3, 90, "关节限位(度):\nθ1 ∈ [0,180]  底座回转\nθ2 ∈ [30,150] 大臂俯仰\nθ3 ∈ [0,135] 小臂俯仰",
            fontsize=9, va="top")
    fig.suptitle("3-DOF 机械臂运动学示意 (FK: r = L1·cosθ2 + L23·cos(θ2+θ3))", fontsize=12.5, weight="bold", y=0.99)
    fig.savefig(os.path.join(OUT, "arm_kinematics.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    fig_architecture()
    fig_control_loop()
    fig_state_machine()
    fig_arm()
    print(f"[OK] 图片已生成到 {OUT}")
    for f in sorted(os.listdir(OUT)):
        print("  -", f)
