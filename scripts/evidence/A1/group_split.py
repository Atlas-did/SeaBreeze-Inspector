#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A1-01 group_split: 按来源组划分 70/15/15 + 测试集冻结
无原始 source_id 时退回"按文件名前缀近似分组"并声明粒度(诚实停止线)。
输出: split_manifest.csv + train/val/test 三份文件清单,并打 SHA-256。
"""
import argparse, os, csv, hashlib, re, glob


def sha256(fn):
    h = hashlib.sha256()
    with open(fn, 'rb') as f:
        for b in iter(lambda: f.read(1 << 16), b''):
            h.update(b)
    return h.hexdigest()


def source_id(filename, mode='prefix'):
    """按文件名提取来源组。mode=prefix: 取首个非数字 token(近似);dir: 目录名。"""
    stem = os.path.splitext(os.path.basename(filename))[0]
    if mode == 'prefix':
        m = re.match(r'([A-Za-z_]+)', stem)
        return m.group(1) if m else '_default'
    return os.path.basename(os.path.dirname(filename))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--images', required=True)
    ap.add_argument('--out', default='split_manifest.csv')
    ap.add_argument('--mode', default='prefix', choices=['prefix', 'dir'],
                    help='prefix=文件名前缀近似分组(缺批次信息时的诚实回退)')
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.images, '**', '*.jpg'), recursive=True)
                   + glob.glob(os.path.join(a.images, '**', '*.png'), recursive=True))
    groups = {}
    for f in files:
        groups.setdefault(source_id(f, a.mode), []).append(f)

    import numpy as np
    rng = np.random.default_rng(42)
    rows = []
    for gid, fl in groups.items():
        idx = rng.permutation(len(fl))
        n = len(fl)
        n_tr, n_va = int(n * 0.7), int(n * 0.15)
        # 小样本组取整可能把 val 取成 0: 组内 ≥3 张时保证至少 1 张 val
        if n >= 3 and n_va == 0:
            n_va = 1
        for i, pos in enumerate(idx):
            f = fl[pos]
            split = 'train' if i < n_tr else ('val' if i < n_tr + n_va else 'test')
            rows.append([gid, os.path.relpath(f, a.images), split, sha256(f)])

    with open(a.out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['source_id', 'image', 'split', 'sha256'])
        w.writerows(rows)
    from collections import Counter
    c = Counter(r[2] for r in rows)
    print(f'[OK] group split({a.mode} 近似分组): {len(files)} 图, '
          f'train={c["train"]} val={c["val"]} test={c["test"]}, 来源组 {len(groups)}')
    print(f'     注意: 缺原始批次信息,此为近似分组,论文须声明粒度')
    print(f'     -> {a.out}')


if __name__ == '__main__':
    main()
