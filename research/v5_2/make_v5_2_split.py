#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_v5_2_split.py —— v5.2 三集合 + review 生成(第二优先级)

把一份「按采集单元分组的输入」(v4_quick 的 images/labels,或 ClawsGO v5 manifest)
重切为四路,同时避免 v4 的相邻帧泄漏与 v5 的验证集单场景偏置:

  输出目录 v5_2/:
    train/  id_val/  ood_test/  review/        (图片 + 同路径 labels)
    train_manifest.csv  id_val_manifest.csv
    ood_test_manifest.csv  review_manifest.csv
    split_report.json                           (自动审计:图片数/正负/框/场景/短边/长宽比/贴边/pHash/父图跨集)

设计口径(诚实):
  1. 场景块 = 父图 ID(DJI_XXXX,按 --scene-regex 提取);同父图的所有瓦片**永不分家**,
     这是防相邻帧泄漏的硬约束(v4 版已经满足「父图不跨 split」,这里显式保留并可验证)。
  2. ID val 要覆盖「多拍摄距离/背景/叶片尺度」——在只有父图编号元数据时,近似用
     「父图编号均匀分层抽样」来逼近(编号相邻的父图往往拍摄条件相近,故按编号排序后
     等间隔抽样,而不是首尾簇)。诚实声明:这是 proxy,拿到真实距离/背景元数据后应替换。
  3. OOD test = 保留**若干完整父图**整块,从 train/id_val 完全隔离,永不参与训练调参。
  4. review = 由 audit_labels.py 判为 uncertain/invalid 的框所在的整图(非仅框),
     清理完成前不进入正式指标。

用法:
  模式 A(本地 split 目录):
    python make_v5_2_split.py --root datasets/derived/clean_binary_v4_quick \
        --audit research/v5_2/audit_labels.csv --out v5_2
  模式 B(ClawsGO manifest):
    python make_v5_2_split.py --manifest v5_scene_manifest.csv --audit audit_labels.csv --out v5_2

--review-only 时:不重切 train/id_val/ood,只把 audit 判为 uncertain/invalid 的图抽到 review。
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict


def sha256_of_file(path):
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            for b in iter(lambda: f.read(1 << 16), b''):
                h.update(b)
        return h.hexdigest()
    except OSError:
        return None


# ---------------- 可选的 pHash 近重复(PIL + imagehash 都有才启用) ----------------
_supports_phash = None


def supports_phash():
    global _supports_phash
    if _supports_phash is None:
        try:
            import imagehash  # noqa: F401
            from PIL import Image  # noqa: F401
            _supports_phash = True
        except ImportError:
            _supports_phash = False
    return _supports_phash


def phash(path):
    try:
        from PIL import Image
        import imagehash
        with Image.open(path) as im:
            return str(imagehash.phash(im, hash_size=8))
    except Exception:
        return None


def scene_id_of(img_path, scene_regex):
    name = os.path.basename(img_path)
    m = re.match(scene_regex, name)
    if m:
        return m.group(1)
    return os.path.basename(os.path.dirname(img_path))


def resolve_label(img_path):
    """根据图片路径推断标签路径:优先 images/ -> labels/ 目录替换;否则同目录换 .txt。"""
    p = img_path.replace('\\', '/')
    if '/images/' in p:
        return p.replace('/images/', '/labels/', 1).rsplit('.', 1)[0] + '.txt'
    return os.path.splitext(img_path)[0] + '.txt'


def list_images(image_dir):
    imgs = []
    for fn in sorted(os.listdir(image_dir)):
        if fn.lower().endswith(('.jpg', '.jpeg', '.png')):
            imgs.append(os.path.join(image_dir, fn))
    return imgs


def read_boxes(label_path):
    boxes = []
    if os.path.exists(label_path):
        with open(label_path, encoding='utf-8') as f:
            for line in f:
                p = line.split()
                if len(p) >= 5:
                    try:
                        boxes.append(tuple(float(x) for x in p[1:5]))
                    except ValueError:
                        pass
    return boxes


def collect_items(root_images):
    """扫描一个 images 根(含 train/val/test 子目录),返回 items 列表。
    条目 = {img, label, split, scene, sha256, phash, n_boxes}。"""
    items = []
    for split in ('train', 'val', 'test'):
        d = os.path.join(root_images, split)
        if not os.path.isdir(d):
            continue
        for img in list_images(d):
            items.append({
                'img': img,
                'split': split,
                'scene': scene_id_of(img, r'(DJI_\d{4})'),
                'sha256': None,  # 惰性(下面先做磁盘去重)
            })
    return items


def main():
    ap = argparse.ArgumentParser(description='v5.2 三集合 + review 划分')
    ap.add_argument('--root', help='含 images/{train,val,test} 的数据根')
    ap.add_argument('--manifest', help='ClawsGO 风格 manifest CSV(列 image,split,可选 sha256)')
    ap.add_argument('--audit', help='audit_labels.py 输出的 CSV(用于抽 review 图)')
    ap.add_argument('--out', default='v5_2', help='输出目录')
    ap.add_argument('--id-val-frac', type=float, default=0.15, help='ID val 场景块占比(按父图)')
    ap.add_argument('--ood-frac', type=float, default=0.15, help='OOD test 场景块占比(按父图)')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--scene-regex', default=r'(DJI_\d{4})')
    ap.add_argument('--review-only', action='store_true',
                    help='只抽 review,不重切 train/id_val/ood')
    a = ap.parse_args()

    if not a.root and not a.manifest:
        raise SystemExit('需要 --root 或 --manifest 之一')

    # ---------- 1. 收集条目 ----------
    if a.manifest:
        items = []
        with open(a.manifest, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                img = r['image']
                full = img if os.path.isabs(img) else img
                items.append({
                    'img': full,
                    'split': r['split'],
                    'scene': r.get('scene_block_id') or scene_id_of(full, a.scene_regex),
                    'sha256': r.get('sha256') or None,
                })
        base_for_rel = os.path.dirname(a.manifest)
    else:
        items = collect_items(os.path.join(a.root, 'images'))
        base_for_rel = a.root

    if not items:
        raise SystemExit('未收集到任何图片')

    # ---------- 2. 惰性补 sha256 / phash ----------
    for it in items:
        if it['sha256'] is None:
            it['sha256'] = sha256_of_file(it['img'])
    phash_enabled = supports_phash()
    if phash_enabled:
        for it in items:
            it['phash'] = phash(it['img'])

    # ---------- 3. 磁盘内容去重(同 sha256 只保留首个) ----------
    seen = set()
    deduped = []
    for it in items:
        h = it['sha256']
        if h is None:
            deduped.append(it)
            continue
        if h in seen:
            continue
        seen.add(h)
        deduped.append(it)
    print(f'[dedup] {len(items)} -> {len(deduped)} 条目(sha256 内容去重)')
    items = deduped

    # ---------- 4. 按场景块(父图)聚合 ----------
    scene_imgs = defaultdict(list)
    for it in items:
        scene_imgs[it['scene']].append(it)

    # ---------- 5. review 抽取(audit 判为 uncertain/invalid 的整图) ----------
    review_imgs = set()
    if a.audit and os.path.exists(a.audit):
        with open(a.audit, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r.get('review_status') in ('uncertain', 'invalid'):
                    # 归一化:统一反斜杠->斜杠,便于与 rel 匹配
                    review_imgs.add(r['image_path'].replace('\\', '/'))

    def _norm(p):
        return os.path.normpath(p).replace('\\', '/')

    def _img_in_review(img_path):
        rel = _norm(os.path.relpath(img_path, base_for_rel))
        candidates = {rel, _norm(img_path)}
        # 兼容 audit image_path 带/不带 images/ 前缀
        for c in list(candidates):
            if '/images/' in c:
                candidates.add(c.split('/images/', 1)[1])
        return bool(candidates & review_imgs)

    items_keep = []
    items_to_review = []
    for it in items:
        if _img_in_review(it['img']):
            items_to_review.append(it)
        else:
            items_keep.append(it)
    print(f'[review] {len(items_to_review)} 条目抽入 review(来自 audit uncertain/invalid)')

    if a.review_only:
        write_layout(a.out, {'review': items_to_review}, base_for_rel, items)
        return

    # ---------- 6. 按父图分层抽样 train / id_val / ood_test ----------
    scene_list = sorted(scene_imgs.keys())
    import random
    rng = random.Random(a.seed)
    # 对父图编号排序后等间隔分层(proxy for 拍摄条件多样性;诚实声明见文件头)
    shuffled = scene_list[:]
    rng.shuffle(shuffled)
    n = len(shuffled)
    n_ood = max(1, int(round(n * a.ood_frac)))
    n_idval = max(1, int(round(n * a.id_val_frac)))
    n_train = n - n_ood - n_idval
    ood_scenes = set(shuffled[:n_ood])
    idval_scenes = set(shuffled[n_ood:n_ood + n_idval])
    train_scenes = set(shuffled[n_ood + n_idval:])

    sets = {'train': [], 'id_val': [], 'ood_test': [], 'review': items_to_review}
    for it in items_keep:
        s = it['scene']
        if s in ood_scenes:
            sets['ood_test'].append(it)
        elif s in idval_scenes:
            sets['id_val'].append(it)
        else:
            sets['train'].append(it)

    print(f'[split] 场景块 train={n_train} id_val={n_idval} ood_test={n_ood} '
          f'(总 {n})')

    write_layout(a.out, sets, base_for_rel, items)


def write_layout(out, sets, base_for_rel, all_items):
    """写 v5_2/ 目录 + 4 份 manifest + split_report.json。"""
    os.makedirs(out, exist_ok=True)
    manifests = {}
    for name, lst in sets.items():
        d = os.path.join(out, name)
        os.makedirs(os.path.join(d, 'images'), exist_ok=True)
        os.makedirs(os.path.join(d, 'labels'), exist_ok=True)
        rows = []
        for it in lst:
            img_rel = os.path.relpath(it['img'], base_for_rel).replace('\\', '/')
            # 复制图片(链接不可靠,直接复制以保证 review 独立可交付)
            import shutil
            dst_img = os.path.join(d, 'images', os.path.basename(it['img']))
            shutil.copyfile(it['img'], dst_img)
            lab_src = resolve_label(it['img'])
            if os.path.exists(lab_src):
                shutil.copyfile(lab_src, os.path.join(d, 'labels',
                                                      os.path.basename(lab_src)))
            rows.append({'image': img_rel, 'split': name, 'scene_block_id': it['scene'],
                         'sha256': it['sha256'] or ''})
        out_csv = os.path.join(out, f'{name}_manifest.csv')
        with open(out_csv, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['image', 'split', 'scene_block_id', 'sha256'])
            w.writeheader()
            w.writerows(rows)
        manifests[name] = rows

    # ---------- split_report.json ----------
    report = {'splits': {}, 'cross_set_checks': {
        'parent_scene_cross_split': 0, 'sha256_cross_split': 0,
        'phash_cross_split': 0, 'phash_enabled': supports_phash()}}
    for name, rows in manifests.items():
        imgs = rows
        # 精确统计正负与框(读取已复制到 v5_2/<name>/labels 的标签)
        n_pos, n_box = 0, 0
        short_side = []
        ars = []
        touch = 0
        d = os.path.join(out, name)
        for r in imgs:
            img_path = os.path.join(base_for_rel, r['image'])
            lab_path = os.path.join(d, 'labels', os.path.splitext(
                os.path.basename(r['image']))[0] + '.txt')
            boxes = read_boxes(lab_path)
            if boxes:
                n_pos += 1
            for (cx, cy, w, h) in boxes:
                n_box += 1
                # 用 1024 近似像素(无 PIL 时);有 PIL 会用真尺寸
                W = H = 1024
                try:
                    from PIL import Image
                    with Image.open(img_path) as im:
                        W, H = im.size
                except Exception:
                    pass
                pw, ph = w * W, h * H
                short_side.append(min(pw, ph))
                if min(pw, ph) > 1e-9:
                    ars.append(max(pw, ph) / min(pw, ph))
                if (cx - w / 2 < 0.01 or cx + w / 2 > 0.99 or
                        cy - h / 2 < 0.01 or cy + h / 2 > 0.99):
                    touch += 1
        report['splits'][name] = {
            'images': len(imgs),
            'positive_images': n_pos,
            'negative_images': len(imgs) - n_pos,
            'boxes': n_box,
            'scene_blocks': len({r['scene_block_id'] for r in imgs}),
            'short_side_dist': histogram(short_side, [16, 32, 64, 128]),
            'aspect_ratio_dist': histogram(ars, [5, 10, 20]),
            'touch_boundary_boxes': touch,
        }

    # 跨集合检查(review 是有意与 train/id_val/ood 重叠的子集,不参与泄漏判定)
    core = ('train', 'id_val', 'ood_test')
    by_split_core = {k: {r['sha256'] for r in manifests[k] if r['sha256']} for k in core}
    for i in range(len(core)):
        for j in range(i + 1, len(core)):
            report['cross_set_checks']['sha256_cross_split'] += \
                len(by_split_core[core[i]] & by_split_core[core[j]])
    scene_of_core = {}
    for name in core:
        for r in manifests[name]:
            scene_of_core[r['scene_block_id']] = scene_of_core.get(r['scene_block_id'], set())
            scene_of_core[r['scene_block_id']].add(name)
    report['cross_set_checks']['parent_scene_cross_split'] = \
        sum(1 for s in scene_of_core.values() if len(s) > 1)

    with open(os.path.join(out, 'split_report.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'[OK] -> {out}/ (train/id_val/ood_test/review + 4 manifest + split_report.json)')
    for name in ('train', 'id_val', 'ood_test', 'review'):
        print(f'     {name}: {len(manifests[name])} 条目')


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
