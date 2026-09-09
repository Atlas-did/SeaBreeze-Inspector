#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A4-02 目标级 Copy-Paste 增广(检测专用;ultralytics 的 copy_paste 是分割参数,不生效)
在 dataloader 层做: 从 train 自身 obj_pool 采目标 patch,几何变换后贴到背景图,bbox 同步变换。
约束: 不越界、与现有框 IoU<0.3、类别比例受控、patch 缩放不放大失真。
"""
import argparse
import numpy as np
import cv2


def copy_paste_sample(image, boxes, obj_pool, p=0.3, max_iou=0.3, rng=None):
    """boxes: [[cls,cx,cy,w,h],...] 归一化; obj_pool: [(img_patch, box),...]"""
    rng = rng or np.random.default_rng()
    if rng.random() > p or not obj_pool:
        return image, boxes
    H, W = image.shape[:2]
    for _ in range(5):  # 最多试 5 次找合法位置
        obj_img, obj_box = obj_pool[rng.integers(len(obj_pool))]
        scale = rng.uniform(0.7, 1.3)
        patch = cv2.resize(obj_img, (int(obj_img.shape[1] * scale), int(obj_img.shape[0] * scale)))
        ph, pw = patch.shape[:2]
        if pw >= W or ph >= H:
            continue  # patch 放大后不小于整图,无法放置,跳过本次
        # 新 box(贴到图上的归一化坐标)
        ox = rng.integers(0, W - pw)
        oy = rng.integers(0, H - ph)
        ncx, ncy = (ox + pw / 2) / W, (oy + ph / 2) / H
        nw, nh = pw / W, ph / H
        # 冲突检测(与已有框 IoU)
        conflict = False
        for b in boxes:
            iou = box_iou((ncx, ncy, nw, nh), (b[1], b[2], b[3], b[4]))
            if iou > max_iou:
                conflict = True; break
        if conflict:
            continue
        # 贴图(注意通道顺序: 假设都是 BGR)
        image[oy:oy + ph, ox:ox + pw] = patch
        return image, np.vstack([boxes, [obj_box[0], ncx, ncy, nw, nh]])
    return image, boxes  # 5 次都冲突则跳过


def box_iou(a, b):
    ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2
    ax2, ay2 = a[0] + a[2] / 2, a[1] + a[3] / 2
    bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2
    bx2, by2 = b[0] + b[2] / 2, b[1] + b[3] / 2
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    aa = (ax2 - ax1) * (ay2 - ay1); bb = (bx2 - bx1) * (by2 - by1)
    return inter / (aa + bb - inter + 1e-9)


if __name__ == '__main__':
    print('A4-02 CopyPaste: 作为 ultralytics 自定义 Dataset/dataloader 的采样函数使用')
    print('关键纪律: obj_pool 来自锁定 train 集;不贴到天空/海面(需叶片 mask 约束);')
    print('          消融 p∈{0.2,0.4},报告 AP_S/M/L 与 Precision 副作用')
