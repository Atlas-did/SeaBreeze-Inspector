#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A3-01 clean 清晰度筛选 + 雾后目标可见性标记(纯本地)
1. 拉普拉斯方差评估清晰度,筛掉本来有雾/模糊/过曝的图(clean 基底纪律);
2. 对每张 clean 生成雾变体,按目标框区域对比度计算 invisible_flag。
输出: sharpness.csv(排序) + pairs.csv(clean, fog, beta, invisible_flag)
"""
import argparse, os, csv, glob
import numpy as np
import cv2

sys_path_ok = True
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def laplacian_sharpness(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def add_fog(img, A=(0.70, 0.75, 0.82), beta=1.0):
    arr = img.astype(np.float32) / 255.0
    h, w = arr.shape[:2]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    d = y / max(h - 1, 1)  # 伪深度: 上缘远
    t = np.exp(-beta * d)[..., None]
    t = np.clip(t, 0.05, 1.0)
    out = arr * t + np.array(A, dtype=np.float32).reshape(1, 1, 3) * (1 - t)
    return (np.clip(out, 0, 1) * 255).astype(np.uint8)


def bbox_contrast(img, box):
    h, w = img.shape[:2]
    x, y, bw, bh = box
    x1, y1 = int((x - bw / 2) * w), int((y - bh / 2) * h)
    x2, y2 = int((x + bw / 2) * w), int((y + bh / 2) * h)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    roi = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    return float(roi.std())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--images', required=True)
    ap.add_argument('--labels', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--min-sharpness', type=float, default=50.0)
    ap.add_argument('--betas', default='0.5,1.0,1.5,2.0')
    ap.add_argument('--contrast-thresh', type=float, default=8.0)
    ap.add_argument('--max', type=int, default=None, help='最多处理前 N 张(默认全部)')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    betas = [float(b) for b in a.betas.split(',')]
    imgs = sorted(glob.glob(os.path.join(a.images, '*.jpg')) + glob.glob(os.path.join(a.images, '*.png')))
    if a.max is not None:
        imgs = imgs[:a.max]
    rows = []
    pairs = []
    for img_path in imgs:
        img = cv2.imread(img_path)
        if img is None:
            continue
        sharp = laplacian_sharpness(img)
        stem = os.path.splitext(os.path.basename(img_path))[0]
        rows.append([stem, f'{sharp:.1f}'])
        if sharp < a.min_sharpness:
            continue  # 不合格,不进 clean 池
        # 读标签框
        lbl = os.path.join(a.labels, stem + '.txt')
        boxes = []
        if os.path.isfile(lbl):
            with open(lbl, encoding='utf-8') as lf:
                for line in lf:
                    t = line.split()
                    if len(t) >= 5:
                        boxes.append(tuple(map(float, t[1:5])))
        # 生成雾 + 可见性
        for beta in betas:
            fog = add_fog(img, beta=beta)
            cv2.imwrite(os.path.join(a.out, f'{stem}_b{beta}.png'), fog)
            if boxes:
                c_fog = max(bbox_contrast(fog, b) for b in boxes)
                invisible = 1 if c_fog < a.contrast_thresh else 0
            else:
                invisible = 0
            pairs.append([stem, f'{stem}_b{beta}.png', beta, 'fog', invisible])

    with open(os.path.join(a.out, 'sharpness.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['image', 'laplacian_var']); w.writerows(rows)
    with open(os.path.join(a.out, 'pairs.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['clean', 'fog', 'beta', 'type', 'invisible_flag']); w.writerows(pairs)
    print(f'[OK] 清晰度筛选 + 雾合成 + 可见性: {len(rows)} 图, {len(pairs)} 配对')


if __name__ == '__main__':
    main()
