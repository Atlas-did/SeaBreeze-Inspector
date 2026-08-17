#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A3-03 任务驱动去雾联合优化(Baseline,需 GPU;与 A3-02 特征一致性互斥,作为对照)
联合端到端: 去雾网(估计 t,A 重建) + 检测头;L = L_yolo + λr·L_recon(像素,可选)。
去雾网学"让检测更好"而非"像素还原";推理延迟翻倍,论文须报告端到端时延。
"""
import argparse
import numpy as np


def dehaze_network():
    """传输估计型轻量去雾网(<2M): 输出 t(1通道) + A(3通道),重建 J=(I-A)/t+A。"""
    import torch.nn as nn
    return nn.Sequential(
        nn.Conv2d(3, 16, 3, padding=1), nn.ReLU(),
        nn.Conv2d(16, 16, 3, padding=1), nn.ReLU(),
        nn.Conv2d(16, 4, 3, padding=1), nn.Sigmoid(),  # 4 通道: t + A(3)
    )


def reconstruct(I_f, t, A):
    t = t.clamp(0.05, 1.0)
    return (I_f - A) / t + A


def total_loss(L_yolo, J_hat, I_c, lam_r=0.05):
    import torch.nn.functional as F
    return L_yolo + lam_r * F.l1_loss(J_hat, I_c)  # λr 控制"任务驱动 vs 像素还原"


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', required=True)
    ap.add_argument('--lam-r', type=float, default=0.05)
    a = ap.parse_args()
    print('[注意] 任务驱动去雾是 Baseline(需 GPU);本文方法是 A3-02 特征一致性')
    print(f'  损失: L = L_yolo(D(G(If))) + {a.lam_r}·L_recon(J_hat, I_c)')
    print('  关键: 报告端到端时延(去雾+检测 串行);去雾引入的 FN 单独审计')
    print('  不可见样本(invisible_flag=1): 对 L_yolo 降权,保留 L_recon')
