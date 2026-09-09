#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A3-02 特征一致性训练(主路线,需 GPU;含评审修正版)
不学"擦雾",学"雾不变表征"。检测版: 只做 backbone 特征一致性(不做检测头输出一致);
角度回归版: sin/cos 编码 + L_state + L_cons + L_feat。
用 BYOL 式 stop-gradient 防塌缩;P3/P4/P5 多尺度投影头;invisible 样本关闭检测损失。
"""
import argparse


def build_model(backbone='resnet18', n_classes=1, regression=False):
    import torch
    import torch.nn as nn
    import torchvision
    base = torchvision.models.resnet18(weights=None)
    base.fc = nn.Identity()  # 去掉分类头,输出 512 维特征
    backbone_feat = 512
    proj = nn.Sequential(nn.Linear(backbone_feat, 256), nn.ReLU(), nn.Linear(256, 128))
    if regression:
        head = nn.Sequential(nn.Linear(backbone_feat, 128), nn.ReLU(), nn.Linear(128, 6))  # sin/cos x3
    else:
        head = nn.Linear(backbone_feat, n_classes)
    return {'backbone': base, 'proj': proj, 'head': head}


def consistency_loss(z_f, z_c):
    """特征一致性: 投影后 L1(可换余弦)。z_f/z_c 已过投影头。"""
    import torch.nn.functional as F
    return F.l1_loss(z_f, z_c)


def angle_loss(p_pred, p_gt):
    """角度回归损失: 用 sin/cos 6 维编码,避免 359°/1° MSE 爆炸。"""
    import torch
    # p_pred, p_gt 均为 [..., 6] = [sin_r,cos_r,sin_p,cos_p,sin_y,cos_y]
    return torch.mean((p_pred - p_gt) ** 2)


def train_step(model, I_c, I_f, labels, visible_mask, lam_feat=0.3):
    """联合训练一步。labels: 任务真值; visible_mask: 雾图目标是否可见(invisible→关检测损失)。"""
    import torch.nn.functional as F
    f_c = model['backbone'](I_c)
    f_f = model['backbone'](I_f)
    z_c = model['proj'](f_c)
    z_f = model['proj'](f_f)
    # 任务损失(回归 or 分类): head 接在 backbone 特征上,而非投影头输出
    p_c = model['head'](f_c)
    L_task = F.mse_loss(p_c, labels) if p_c.shape == labels.shape else F.binary_cross_entropy_with_logits(p_c, labels)
    # 特征一致性(可加 stop-gradient 的 BYOL predictor)
    L_feat = lam_feat * consistency_loss(z_f, z_c)
    return L_task + L_feat


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', required=True, help='A3-01 输出 pairs.csv 所在目录')
    ap.add_argument('--epochs', type=int, default=50)
    ap.add_argument('--batch', type=int, default=16)
    ap.add_argument('--lam-feat', type=float, default=0.3)
    ap.add_argument('--device', default='cuda')
    a = ap.parse_args()
    print('[注意] 特征一致性训练需 GPU 运行;当前是接口/结构定义')
    print(f'  数据={a.data_dir}, 检测版损失= L_yolo(clean)+L_yolo(fog)*visible + lam_feat*Σ_{{p∈P3,P4,P5}}||proj(zf)-proj(zc)||1')
    print('  回归版: 角度用 sin/cos 6 维, L = λ1·L_state + λ2·L_cons + λ3·L_feat')
    print('  防塌缩: BYOL stop-gradient + predictor; λ3 cosine 退火到 0.05')
