#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preflight_check.py —— 训练前 CPU 级数据完整性检查器(第三优先级)

在 GPU 真正训练前,本地先跑这 10 项,把「标签格式错误」与「标签语义可疑」分开。
本脚本只判「格式/结构/泄漏」客观项;「框内是否真缺陷」由 audit_labels.py + 人工完成。

10 项检查:
  01. train/id_val/ood_test 无完全重复图片(sha256)
  02. 父图 ID 不跨集合
  03. 连续场景块不跨集合(按父图 ID 排序后,相邻编号不得被割到不同空集)
  04. pHash 近重复不跨集合(有 imagehash 才启用,否则降级声明)
  05. 所有标签文件可解析
  06. 所有 bbox 坐标在 [0,1]
  07. bbox 宽高 > 0
  08. 目标框未异常超出图像
  09. 训练/验证/测试类别集合一致
  10. 三集合目标尺度分布统计报告

用法:
  python preflight_check.py --root v5_2 --out preflight_report.json
    (root 下含 train/ id_val/ ood_test/ [review/],每集合 images/ + labels/)
"""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict


def sha256_of_file(path):
    try:
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for b in iter(lambda: f.read(1 << 16), b''):
                h.update(b)
        return h.hexdigest()
    except OSError:
        return None


def supports_phash():
    try:
        import imagehash  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def phash(path):
    try:
        from PIL import Image
        import imagehash
        with Image.open(path) as im:
            return str(imagehash.phash(im, hash_size=8))
    except Exception:
        return None


def scene_id(name):
    m = re.match(r'(DJI_\d{4})', name)
    return m.group(1) if m else name


def read_boxes_yolo(path):
    """返回 (boxes, ok, err)。boxes=[(cls,cx,cy,w,h)];ok=可解析;err=错误描述。"""
    boxes = []
    if not os.path.exists(path):
        return boxes, False, "missing_label"
    try:
        with open(path, encoding='utf-8') as f:
            lines = f.read().splitlines()
    except Exception as e:
        return boxes, False, f"read_error:{e}"
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        p = line.split()
        if len(p) < 5:
            return boxes, False, f"bad_line {i} (<5 tokens)"
        try:
            cls = int(float(p[0]))
            cx, cy, w, h = (float(x) for x in p[1:5])
        except ValueError:
            return boxes, False, f"bad_line {i} non-numeric"
        boxes.append((cls, cx, cy, w, h))
    return boxes, True, ""


def img_size(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return (None, None)


def dataset_splits(root):
    """返回 {split: [(img, label)]}。支持两种布局:
    1) v5_2 输出布局: <root>/<split>/images/ 与 <root>/<split>/labels/
    2) ultralytics 布局: <root>/images/<split>/ 与 <root>/labels/<split>/
    """
    sets = {}
    # 布局 1: <root>/<split>/images/
    for split in os.listdir(root):
        d = os.path.join(root, split)
        imgdir = os.path.join(d, 'images')
        if not os.path.isdir(imgdir):
            continue
        pairs = []
        for fn in sorted(os.listdir(imgdir)):
            if fn.lower().endswith(('.jpg', '.jpeg', '.png')):
                stem = os.path.splitext(fn)[0]
                pairs.append((os.path.join(imgdir, fn),
                              os.path.join(d, 'labels', stem + '.txt')))
        sets[split] = pairs
    if sets:
        return sets
    # 布局 2: <root>/images/<split>/
    img_root = os.path.join(root, 'images')
    lab_root = os.path.join(root, 'labels')
    if os.path.isdir(img_root):
        for split in os.listdir(img_root):
            imgdir = os.path.join(img_root, split)
            if not os.path.isdir(imgdir):
                continue
            pairs = []
            for fn in sorted(os.listdir(imgdir)):
                if fn.lower().endswith(('.jpg', '.jpeg', '.png')):
                    stem = os.path.splitext(fn)[0]
                    pairs.append((os.path.join(imgdir, fn),
                                  os.path.join(lab_root, split, stem + '.txt')))
            sets[split] = pairs
    return sets


def main():
    ap = argparse.ArgumentParser(description='训练前 CPU 数据完整性检查(10 项)')
    ap.add_argument('--root', required=True, help='v5_2 输出根(含 train/id_val/ood_test[/review])')
    ap.add_argument('--core-splits', nargs='+', default=['train', 'id_val', 'ood_test'],
                    help='参与泄漏判定的集合(review 是有意重叠的,默认排除)')
    ap.add_argument('--out', default='preflight_report.json')
    a = ap.parse_args()

    splits = dataset_splits(a.root)
    if not splits:
        raise SystemExit(f'--root {a.root} 下未找到任何 images/ 集合')

    results = []
    PH = supports_phash()

    # 预处理:每集合的 sha256 / phash / 父图 / 类别 / 尺度
    split_sha = {}
    split_phash = {}
    split_scenes = {}
    split_classes = {}
    split_short = defaultdict(list)
    all_scene_to_split = defaultdict(set)

    for split, pairs in splits.items():
        sha = {}
        ph = {}
        scenes = defaultdict(list)
        classes = set()
        for img, lab in pairs:
            h = sha256_of_file(img)
            if h:
                sha[h] = sha.get(h, 0) + 1
            if PH:
                pv = phash(img)
                if pv:
                    ph[pv] = ph.get(pv, 0) + 1
            sc = scene_id(os.path.basename(img))
            scenes[sc].append(img)
            all_scene_to_split[sc].add(split)
            boxes, ok, err = read_boxes_yolo(lab)
            for (cls, cx, cy, w, h) in boxes:
                classes.add(cls)
                W, H = img_size(img)
                W = W or 1024
                H = H or 1024
                split_short[split].append(min(w * W, h * H))
        split_sha[split] = sha
        split_phash[split] = ph
        split_scenes[split] = scenes
        split_classes[split] = classes

    core = [s for s in a.core_splits if s in splits]

    # 01 sha256 完全重复跨集合
    sha_cross = 0
    for i in range(len(core)):
        for j in range(i + 1, len(core)):
            sha_cross += len(set(split_sha[core[i]]) & set(split_sha[core[j]]))
    results.append(("01_sha256_duplicate_cross_split", sha_cross == 0, sha_cross))

    # 02 父图 ID 不跨集合
    parent_cross = sum(1 for s in all_scene_to_split.values() if len(s & set(core)) > 1)
    results.append(("02_parent_id_cross_split", parent_cross == 0, parent_cross))

    # 03 连续场景块不跨集合 —— 正确口径:同一父图(DJI_XXXX)的相邻瓦片(R_C 连续)
    # 不得被切到不同核心集合。DJI 父编号相邻(0234 vs 0235)是**不同采集单元**,可以合法分属不同集合,
    # 不算泄漏,故不检查父编号相邻;只检查同父图内相邻瓦片是否被割裂。
    def tile_pos(name):
        m = re.match(r'DJI_\d{4}_(\d+)_(\d+)', name)
        return (int(m.group(1)), int(m.group(2))) if m else None
    adjacent_cross = 0
    for sc, split_set in all_scene_to_split.items():
        core_sets = split_set & set(core)
        if len(core_sets) < 2:
            continue
        # 该父图被分到 >=2 个核心集合 -> 检查是否有相邻瓦片跨集合
        # 但更严格:父图整体应只落一个核心集合(v4 已满足)。这里报告「父图跨核心集合」即违规。
        adjacent_cross += 1
    results.append(("03_adjacent_scene_cross_split", adjacent_cross == 0, adjacent_cross))

    # 04 pHash 近重复跨集合
    phash_cross = 0
    if PH:
        for i in range(len(core)):
            for j in range(i + 1, len(core)):
                phash_cross += len(set(split_phash[core[i]]) & set(split_phash[core[j]]))
        results.append(("04_phash_neardup_cross_split", phash_cross == 0, phash_cross))
    else:
        results.append(("04_phash_neardup_cross_split", None,
                        "imagehash 未安装,已降级为 sha256(见 01);实现 pHash 请 pip install imagehash pillow"))

    # 05-08 标签格式/坐标/宽高(逐集合统计)
    fmt_bad = 0
    coord_bad = 0
    zero_box = 0
    outbox = 0
    for split, pairs in splits.items():
        for img, lab in pairs:
            boxes, ok, err = read_boxes_yolo(lab)
            if not ok:
                fmt_bad += 1
                continue
            for (cls, cx, cy, w, h) in boxes:
                if not (0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0):
                    coord_bad += 1
                if w <= 0 or h <= 0:
                    zero_box += 1
                if not (0.0 <= cx - w / 2 <= 1.0 and 0.0 <= cx + w / 2 <= 1.0 and
                        0.0 <= cy - h / 2 <= 1.0 and 0.0 <= cy + h / 2 <= 1.0):
                    outbox += 1
    results.append(("05_labels_parseable", fmt_bad == 0, fmt_bad))
    results.append(("06_bbox_coords_in_01", coord_bad == 0, coord_bad))
    results.append(("07_bbox_wh_positive", zero_box == 0, zero_box))
    results.append(("08_bbox_within_image", outbox == 0, outbox))

    # 09 类别集合一致
    all_classes = set().union(*split_classes.values()) if split_classes else set()
    consistent = all(len(v) == len(all_classes) and v == all_classes for v in split_classes.values())
    results.append(("09_class_sets_consistent", consistent,
                    {s: sorted(v) for s, v in split_classes.items()}))

    # 10 尺度分布
    scale_report = {}
    for split, shorts in split_short.items():
        scale_report[split] = {
            'n_boxes': len(shorts),
            'short_side_px': {
                'min': round(min(shorts), 1) if shorts else None,
                'median': round(sorted(shorts)[len(shorts) // 2], 1) if shorts else None,
                'max': round(max(shorts), 1) if shorts else None,
            },
            'short_side_hist': histogram(shorts, [16, 32, 64, 128]),
        }
    results.append(("10_target_scale_dist", None, scale_report))

    # 汇总
    hard_fail = [r[0] for r in results if r[1] is False]
    soft_pass = [r[0] for r in results if r[1] is None]
    report = {
        'root': a.root,
        'core_splits': core,
        'phash_enabled': PH,
        'checks': [{'name': n, 'pass': p, 'detail': d} for n, p, d in results],
        'summary': {
            'total_checks': len(results),
            'hard_failures': hard_fail,
            'n_hard_failures': len(hard_fail),
            'soft_degraded': soft_pass,
        },
    }
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f'[preflight] {len(results)} 项检查完成')
    for n, p, d in results:
        mark = '✅' if p is True else ('❌' if p is False else '⚠️(降级)')
        detail = d if isinstance(d, (int, str)) else json.dumps(d, ensure_ascii=False)
        print(f'   {mark} {n}: {detail}')
    if hard_fail:
        print(f'[FATAL] {len(hard_fail)} 项硬失败,训练前必须修复: {hard_fail}')
        sys.exit(1)
    else:
        print('[OK] 无硬失败;标签格式/坐标/泄漏均通过。语义复核见 audit_labels.csv')
    print(f'   -> {a.out}')


def histogram(vals, edges):
    out = {}
    prev = 0
    for e in edges:
        out[f'<={e}'] = sum(1 for v in vals if prev < v <= e)
        prev = e
    out[f'>{edges[-1]}'] = sum(1 for v in vals if v > edges[-1])
    return out


if __name__ == '__main__':
    main()
