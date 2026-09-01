#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""临时检查:读 audit_v5_labels.csv,看 val 的 review 分布与 scene_04/10 明细。"""
import csv
import collections
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PATH = sys.argv[1]
rows = list(csv.DictReader(open(PATH, encoding='utf-8')))

print('=== 按 split 的 review_status 分布 ===')
for s in ('train', 'val', 'test'):
    r = [x for x in rows if x['split'] == s]
    c = collections.Counter(x['review_status'] for x in r)
    print(f"  {s}: 框={len(r)} valid={c['valid']} uncertain={c['uncertain']} invalid={c['invalid']}")

print()
print('=== val 中 scene_04(DJI_0234-0251) 的框明细 ===')
v = [x for x in rows if x['split'] == 'val']
for x in v:
    if x['scene_block_id'].startswith('DJI_023'):
        print(f"  {x['image_path']} w={x['box_w']} h={x['box_h']} ar={x['aspect_ratio']} "
              f"short={x['short_side']} touch={x['touches_boundary']} -> {x['review_status']} | {x['review_note']}")

print()
print('=== val 中 scene_10(DJI_0685-0713) 统计 ===')
c10 = [x for x in v if x['scene_block_id'][4:].isdigit() and 685 <= int(x['scene_block_id'][4:]) <= 713]
c04 = [x for x in v if x['scene_block_id'][4:].isdigit() and 234 <= int(x['scene_block_id'][4:]) <= 251]
print(f'  scene_04 框数 = {len(c04)}')
print(f'  scene_10 框数 = {len(c10)}')
print(f'  scene_10 review = {collections.Counter(x["review_status"] for x in c10)}')
print(f'  scene_04 review = {collections.Counter(x["review_status"] for x in c04)}')

print()
print('=== val 全部 uncertain/invalid 明细(所有场景) ===')
for x in v:
    if x['review_status'] != 'valid':
        print(f"  {x['scene_block_id']} {x['image_path']} ar={x['aspect_ratio']} short={x['short_side']} "
              f"touch={x['touches_boundary']} -> {x['review_status']} | {x['review_note']}")
