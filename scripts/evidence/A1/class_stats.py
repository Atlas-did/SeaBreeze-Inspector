#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A1-02 类别不平衡与尺寸统计(纯本地)
统计每类框数、每档尺寸实例数 → class_stats.csv(不靠目测)。
"""
import argparse, os, csv, glob
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--labels', required=True, help='labels 根目录(含 train/val 或直接目录)')
    ap.add_argument('--out', default='class_stats.csv')
    a = ap.parse_args()

    # 收集所有 label 文件
    files = sorted(glob.glob(os.path.join(a.labels, '**', '*.txt'), recursive=True))
    class_count = {0: 0, 1: 0, 2: 0}
    # 尺寸档: 按 bbox 面积(相对图) S<0.1% M<0.3% L>=0.3%
    size_count = {'S': 0, 'M': 0, 'L': 0}
    per_file = []
    for fn in files:
        n = 0
        with open(fn, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                t = line.split()
                cls = int(t[0]); w = float(t[3]); h = float(t[4])
                area = w * h
                class_count[cls] = class_count.get(cls, 0) + 1
                if area < 0.001: size_count['S'] += 1
                elif area < 0.003: size_count['M'] += 1
                else: size_count['L'] += 1
                n += 1
        per_file.append((os.path.basename(fn), n))

    total = sum(class_count.values())
    with open(a.out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['dim', 'key', 'count', 'ratio'])
        for cls, c in sorted(class_count.items()):
            w.writerow(['class', cls, c, f'{c/total:.3f}'])
        for k, c in sorted(size_count.items()):
            w.writerow(['size', k, c, f'{c/total:.3f}'])
    print(f'[OK] 类别/尺寸统计完成 (label 文件 {len(files)}, 框 {total})')
    for cls, c in sorted(class_count.items()):
        print(f'   class {cls}: {c} ({c/total:.1%})')
    for k, c in sorted(size_count.items()):
        print(f'   size {k}: {c} ({c/total:.1%})')
    print(f'   -> {a.out}')


if __name__ == '__main__':
    main()
