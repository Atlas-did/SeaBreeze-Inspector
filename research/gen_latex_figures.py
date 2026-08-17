#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成论文成本对比图(对数刻度)+ 汇总所有论文用图到 latex 项目目录。"""
import os
import shutil
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LATEX_DIR = os.path.join(ROOT, "latex_thesis")
FIG_DIR = os.path.join(LATEX_DIR, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

# 成本对比(对数)
cats = ["商用闭源巡检\n(Percepto/Skydio)", "工业级无人机套件\n(PX4+LiDAR+RTK)", "SeaBreeze-Inspector\n(Tello + 机械臂)"]
costs = [700000, 40000, 1000]
fig, ax = plt.subplots(figsize=(7, 4.2))
bars = ax.bar(cats, costs, color=["#c0504d", "#4472c4", "#2e9e5b"], width=0.55)
ax.set_yscale("log")
ax.set_ylabel("总成本 (¥, 对数刻度)", fontsize=10)
ax.set_title("系统成本对比(对数刻度)", fontsize=13, weight="bold")
for b, c in zip(bars, costs):
    ax.text(b.get_x() + b.get_width() / 2, c * 1.15, f"¥{c:,.0f}", ha="center", fontsize=9, weight="bold")
ax.set_ylim(100, 2_000_000)
ax.grid(axis="y", linestyle="--", alpha=0.4)
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "cost_comparison.png"), dpi=150)
plt.close(fig)

# 数据集规模图
fig, ax = plt.subplots(figsize=(5.5, 3.6))
splits = ["train", "val"]
counts = [13034, 2494]
bars = ax.bar(splits, counts, color=["#4472c4", "#e8a33d"], width=0.5)
for b, c in zip(bars, counts):
    ax.text(b.get_x() + b.get_width() / 2, c + 200, f"{c:,}", ha="center", fontsize=10, weight="bold")
ax.set_ylabel("图像数", fontsize=10)
ax.set_title("风机缺陷数据集划分(3 类缺陷)", fontsize=12, weight="bold")
ax.grid(axis="y", linestyle="--", alpha=0.4)
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "dataset_split.png"), dpi=150)
plt.close(fig)

# 复制已有图
base = os.path.join(ROOT, "SeaBreeze Inspector", "offshore-wind-uav-arm")
copies = {
    os.path.join(ROOT, "figures", "architecture.png"): "architecture.png",
    os.path.join(ROOT, "figures", "control_loop.png"): "control_loop.png",
    os.path.join(ROOT, "figures", "state_machine.png"): "state_machine.png",
    os.path.join(ROOT, "figures", "arm_kinematics.png"): "arm_kinematics.png",
    os.path.join(base, "data", "processed", "disturbance_comparison.png"): "disturbance_comparison.png",
    os.path.join(base, "data", "processed", "step_response.png"): "step_response.png",
    os.path.join(base, "data", "processed", "rrt_star_path.png"): "rrt_star_path.png",
    os.path.join(base, "runs", "detect", "val", "confusion_matrix.png"): "confusion_matrix.png",
    os.path.join(base, "runs", "detect", "val", "BoxPR_curve.png"): "boxpr_curve.png",
}
for src, dst in copies.items():
    if os.path.isfile(src):
        shutil.copy2(src, os.path.join(FIG_DIR, dst))
        print(f"[copy] {dst} ({os.path.getsize(src)} bytes)")
    else:
        print(f"[MISSING] {src}")

print("\nfigures dir:")
for f in sorted(os.listdir(FIG_DIR)):
    print("  -", f)
