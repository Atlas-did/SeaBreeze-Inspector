#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D1-01 参数化运动模糊核生成(纯本地,证据层 L3)
线性运动核 K(θ,L) + 抖动项 σj;生成模糊配对图 + pairs.csv。
"""
import numpy as np
import cv2
import argparse, os, csv


def motion_kernel(L, theta, sigma_j=0.0, k=None):
    L = max(int(L), 2)
    k = k or int(L) + 4
    a, b = np.cos(np.deg2rad(theta)), np.sin(np.deg2rad(theta))
    img = np.zeros((k, k), dtype=np.float32)
    for s in np.linspace(-L / 2, L / 2, max(L, 2)):
        x = int(round(k / 2 + s * a))
        y = int(round(k / 2 + s * b))
        if 0 <= x < k and 0 <= y < k:
            img[y, x] = 1.0
    if sigma_j > 0:
        img += np.random.normal(0, sigma_j, img.shape)
    return img / (img.sum() + 1e-9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--lengths', default='4,8,12,16,24')
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    img = cv2.imread(a.image)
    if img is None:
        raise SystemExit('读图失败')
    lengths = [int(x) for x in a.lengths.split(',')]
    rng = np.random.default_rng(0)
    pairs = []
    base = os.path.splitext(os.path.basename(a.image))[0]
    cv2.imwrite(os.path.join(a.outdir, f'{base}_clean.png'), img)
    for L in lengths:
        theta = rng.uniform(0, 360)
        ker = motion_kernel(L, theta, sigma_j=0.0)
        blur = cv2.filter2D(img, -1, ker, borderType=cv2.BORDER_REFLECT)
        name = f'{base}_blur_L{L}.png'
        cv2.imwrite(os.path.join(a.outdir, name), blur)
        pairs.append([f'{base}_clean.png', name, f'{theta:.1f}', L, 0])
    with open(os.path.join(a.outdir, 'blur_pairs.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['clean', 'blurred', 'theta', 'L_px', 'seed'])
        w.writerows(pairs)
    print(f'[OK] 运动模糊生成 {len(lengths)} 档 -> {a.outdir}')


if __name__ == '__main__':
    main()
