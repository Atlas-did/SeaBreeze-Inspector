#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A1-01 三分类→单类缺陷检测:标签重映射 + 数据审计(纯本地,无 GPU)
用法: python remap_to_binary.py --data-root <data/raw> --out <binary_dataset> --log audit_log.csv
审计: 未知类别/坐标越界/零面积框;重映射只把类别置 0,框坐标原样保留。
"""
import argparse, os, csv, glob, hashlib


def sha256(fn):
    h = hashlib.sha256()
    with open(fn, 'rb') as f:
        for b in iter(lambda: f.read(1 << 16), b''):
            h.update(b)
    return h.hexdigest()


def remap_file(src, dst):
    boxes_in = boxes_out = 0
    errors = []
    ok = []
    with open(src, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            toks = line.split()
            boxes_in += 1
            try:
                cls = int(toks[0])
                x, y, w, h = map(float, toks[1:5])
                assert cls in {0, 1, 2}, f'未知类别 {cls}'
                assert 0 < x < 1 and 0 < y < 1, f'中心越界 {toks}'
                assert 0 < w <= 1 and 0 < h <= 1, f'尺寸越界 {toks}'
                assert w * h > 0, '零面积'
                ok.append(' '.join(['0'] + toks[1:5]))  # 类别置 0
                boxes_out += 1
            except Exception as e:
                errors.append(f'{line} -> {e}')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w', encoding='utf-8') as f:
        f.write('\n'.join(ok) + ('\n' if ok else ''))
    return boxes_in, boxes_out, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-root', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--log', default='audit_log.csv')
    a = ap.parse_args()

    total_in = total_out = 0
    err_rows = []
    for split in ('train', 'val'):
        labdir = os.path.join(a.data_root, split, 'labels')
        for lbl in sorted(glob.glob(os.path.join(labdir, '*.txt'))):
            rel = os.path.relpath(lbl, a.data_root)
            dst = os.path.join(a.out, rel)
            b_in, b_out, errs = remap_file(lbl, dst)
            total_in += b_in; total_out += b_out
            for e in errs:
                err_rows.append([rel, e])
    with open(a.log, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['label_file', 'error'])
        w.writerows(err_rows)
    print(f'[OK] 重映射完成: 框 {total_in} -> {total_out} (应相等), 错误 {len(err_rows)} 条')
    print(f'     审计日志: {a.log}, 输出: {a.out}')


if __name__ == '__main__':
    main()
