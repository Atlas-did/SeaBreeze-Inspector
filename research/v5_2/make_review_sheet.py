#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_review_sheet.py —— 把待复核框裁剪拼成一张对照图,供人工逐框目检。

输入:audit CSV(含 image_path + box_w/box_h 归一化为像素前的数值丢失,这里直接从标签重算)
更简单可靠:直接读 labels + images,对每个 uncertain/invalid 框画红框,拼成 contact sheet。

用法:
  python make_review_sheet.py --root <v5数据根> --scenes DJI_0234 DJI_0235 DJI_0236 DJI_0237 DJI_0238 DJI_0249 --out review_sheet.png
"""
import argparse
import os
import re
import sys

from PIL import Image, ImageDraw

SCENE_RE = re.compile(r'(DJI_\d{4})')


def read_boxes_yolo(path):
    boxes = []
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                p = line.split()
                if len(p) >= 5:
                    try:
                        boxes.append(tuple(float(x) for x in p[1:5]))
                    except ValueError:
                        pass
    return boxes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--scenes', nargs='+', required=True)
    ap.add_argument('--splits', nargs='+', default=['val', 'train', 'test'])
    ap.add_argument('--out', default='review_sheet.png')
    ap.add_argument('--cell', type=int, default=256, help='每格缩略边长')
    ap.add_argument('--cols', type=int, default=6)
    ap.add_argument('--max', type=int, default=60, help='最多采集张数')
    a = ap.parse_args()

    targets = set(a.scenes)
    # 收集匹配图片(优先 val)
    collected = []
    for split in a.splits:
        idir = os.path.join(a.root, 'images', split)
        ldir = os.path.join(a.root, 'labels', split)
        if not os.path.isdir(idir):
            continue
        for fn in sorted(os.listdir(idir)):
            if not fn.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            m = SCENE_RE.match(fn)
            if not m or m.group(1) not in targets:
                continue
            boxes = read_boxes_yolo(os.path.join(ldir, os.path.splitext(fn)[0] + '.txt'))
            if boxes:
                collected.append((split, os.path.join(idir, fn), boxes))
            if len(collected) >= a.max:
                break
        if len(collected) >= a.max:
            break

    if not collected:
        print('未采集到任何带框的目标图片')
        return

    # 拼 contact sheet
    cols = a.cols
    rows = (len(collected) + cols - 1) // cols
    cell = a.cell
    sheet = Image.new('RGB', (cols * (cell + 4) + 4, rows * (cell + 28) + 4), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)

    for i, (split, img_path, boxes) in enumerate(collected):
        r, c = divmod(i, cols)
        x0 = 4 + c * (cell + 4)
        y0 = 4 + r * (cell + 28)
        try:
            im = Image.open(img_path).convert('RGB')
        except Exception as e:
            continue
        W, H = im.size
        # 缩略
        scale = min(cell / W, cell / H)
        tw, th = int(W * scale), int(H * scale)
        im = im.resize((tw, th))
        sheet.paste(im, (x0, y0))
        # 画框(缩放后)
        d = ImageDraw.Draw(sheet)
        for (cx, cy, w, h) in boxes:
            x1 = x0 + int((cx - w / 2) * tw)
            y1 = y0 + int((cy - h / 2) * th)
            x2 = x0 + int((cx + w / 2) * tw)
            y2 = y0 + int((cy + h / 2) * th)
            d.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=2)
        # 标签
        ars = []
        for (cx, cy, w, h) in boxes:
            pw, ph = w * W, h * H
            ars.append(f"{max(pw, ph) / min(pw, ph):.1f}" if min(pw, ph) > 1e-9 else "inf")
        label = f"{os.path.basename(img_path)} ar={'/'.join(ars)}"
        draw.text((x0, y0 + cell + 4), label, fill=(30, 30, 30))

    sheet.save(a.out)
    print(f'[OK] {len(collected)} 框图 -> {a.out} ({cols}x{rows} grid)')
    print(f'     场景: {sorted(targets)}')


if __name__ == '__main__':
    main()
