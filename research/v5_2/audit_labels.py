#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_labels.py —— v5.2 数据审计表生成器(第一优先级)

目标回答三个问题:
  1. 哪些验证框可能是错误/语义不一致标签;
  2. 当前验证集究竟是「场景域偏移」问题,还是「标签几何」问题;
  3. 下一次 train/id_val/ood_test 应如何划分,才能同时避免 v4 相邻帧泄漏与 v5 验证集过度偏置。

输入(二选一,按 --mode 自动探测):
  mode=split   —— 一个「按 split 分目录」的数据根(ultralytics 风格):
                 <root>/images/{train,val,test}/ 与 <root>/labels/{train,val,test}/
                 图片与标签同名(如 DJI_0236_0_2.jpg / .txt)。
                 以本机 clean_binary_v4_quick 为代表。
  mode=layout  —— 一个扁平 manifest CSV,列须含 image(相对/绝对路径)与 split,
                 label 按 image 同路径换 .txt 推断;vec 由调用方保证。
                 (供 ClawsGO 提供 v5 scene 划分清单后使用)

输出:
  - audit_labels.csv   每张含框图一行,字段见 SCHEMA(含 23 个 ClawsGO 特殊框的 review 置标)
  - audit_labels.json  split 级统计 + 长宽比/短边/贴边直方图 + review 分段计数
  - review_manifest.csv 被判为 uncertain/invalid 的框独立成表(供人工复核,不改动原数据)

审查口径(诚实):
  - 本脚本只做「几何/格式」可判的客观审查;「框内是否真缺陷」是语义判断,脚本不能替人定夺,
    统一落入 review_status=uncertain,由人工在 review_note 填写。
  - 特殊框(长宽比>=10、接触切片边界、以及 ClawsGO 点名的 DJI_0234-0238 / DJI_0249)
    只「置标提醒」,绝不自动删除。
"""
import argparse
import csv
import json
import os
import re

# 输出表字段(与用户给定字段一一对齐)
FIELDS = [
    "image_path",          # 定位图片
    "scene_block_id",      # 判断场景归属(DJI 父编号 / 目录名)
    "split",               # train/val/test
    "n_boxes",             # 统计目标密度
    "box_w", "box_h", "box_area",   # 判断小目标(像素值,按 imgsz 缩放;未给 img 尺寸则存 -1)
    "aspect_ratio",        # 找细长异常框
    "touches_boundary",    # 找切片残框
    "short_side",          # 判断目标是否过小
    "review_status",       # valid / invalid / uncertain
    "review_note",         # 人工复核意见(脚本预留,默认空)
]

# 客观几何阈值
AR_MIN = 10.0          # 长宽比 >= 10 视为「极端细长」置标
SHORT_SIDE_MAX = 16    # 短边 <= 16px 视为「过小」置标(ClawsGO 报告中的小目标口径)
BOUNDARY_EPS = 0.01    # 框边缘距图像边界 < 1% 视为「接触边界」

# ClawsGO 报告点名需优先人工复核的父图(精确匹配)
CLAWGO_PRIORITY_PARENTS = {
    "DJI_0234", "DJI_0235", "DJI_0236", "DJI_0237", "DJI_0238", "DJI_0249",
}


def scene_block_id(name):
    """从文件名提取场景块 ID:DJI_0236_0_2 -> DJI_0236;否则取目录名。"""
    m = re.match(r'(DJI_\d{4})', name)
    if m:
        return m.group(1)
    return os.path.basename(os.path.dirname(name))


def read_yolo_label(path):
    """读一个 YOLO 标签文件,返回 [(cx,cy,w,h)] 归一化坐标。空文件/缺失 -> []。"""
    boxes = []
    if not os.path.exists(path):
        return boxes
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = line.split()
            # YOLO 标签 = class cx cy w h(可能附加 keypoints,取前 5 列)
            if len(p) < 5:
                continue
            try:
                boxes.append(tuple(float(x) for x in p[1:5]))
            except ValueError:
                continue
    return boxes


def img_size(path):
    """返回 (W,H);取不到(无 PIL / 文件缺失)返回 (None,None)。"""
    try:
        from PIL import Image
    except ImportError:
        return (None, None)
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return (None, None)


def classify_box(w, h, ar, touch, short_ok, cx, cy):
    """客观几何审查 -> (review_status, note)。语义不确定统一 uncertain。"""
    notes = []
    # 接触边界 = 残框/越界高风险
    if touch:
        notes.append("touches_boundary")
    if ar >= AR_MIN:
        notes.append(f"extreme_aspect_ratio={ar:.2f}")
    if not short_ok:
        notes.append(f"short_side<=16px")
    if w <= 0 or h <= 0:
        return "invalid", "zero_area"
    # 越界(中心+半宽超 [0,1])视为 invalid
    if not (0.0 <= cx - w / 2 <= 1.0 and 0.0 <= cx + w / 2 <= 1.0 and
            0.0 <= cy - h / 2 <= 1.0 and 0.0 <= cy + h / 2 <= 1.0):
        return "invalid", "out_of_bounds"
    # 其余异常只「置标提醒」,语义待人工:既然脚本无法判真缺陷,统一 uncertain
    if notes:
        return "uncertain", "; ".join(notes)
    return "valid", ""


def scan_split(root, images_rel, labels_rel=None, imgsz=1024):
    """扫描一个 split 目录,返回 {rows: 每框一行, stats}。images_rel/labels_rel 为相对 root 的目录。"""
    img_dir = os.path.join(root, images_rel)
    lab_dir = os.path.join(root, labels_rel or images_rel.replace("images", "labels"))
    if not os.path.isdir(img_dir):
        return {"rows": [], "stats": {}}

    rows = []
    stats = {"images": 0, "positive_images": 0, "boxes": 0,
             "extreme_ar": 0, "touch_boundary": 0, "small_short": 0,
             "invalid": 0, "uncertain": 0, "valid": 0,
             "ar_hist": {}, "short_side_hist": {}}

    for fn in sorted(os.listdir(img_dir)):
        if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        img_path = os.path.join(img_dir, fn)
        stem = os.path.splitext(fn)[0]
        lab_path = os.path.join(lab_dir, stem + ".txt")
        boxes = read_yolo_label(lab_path)
        stats["images"] += 1
        if boxes:
            stats["positive_images"] += 1

        W, H = img_size(img_path)
        scene = scene_block_id(fn)
        # split 名取 images_rel 末段(如 images/train -> train),兼容 win/posix 分隔符
        split_name = images_rel.replace("\\", "/").rstrip("/").split("/")[-1]

        for (cx, cy, w, h) in boxes:
            stats["boxes"] += 1
            # 归一化 -> 像素(优先用真实图尺寸,取不到回退 imgsz)
            use_w = W or imgsz
            use_h = H or imgsz
            pw, ph = w * use_w, h * use_h
            area = pw * ph
            short = min(pw, ph)
            long = max(pw, ph)
            ar = long / short if short > 1e-9 else float("inf")
            touch = (cx - w / 2 < BOUNDARY_EPS or cx + w / 2 > 1 - BOUNDARY_EPS or
                     cy - h / 2 < BOUNDARY_EPS or cy + h / 2 > 1 - BOUNDARY_EPS)
            short_ok = short > SHORT_SIDE_MAX

            status, note = classify_box(w, h, ar, touch, short_ok, cx, cy)

            # ClawsGO 点名的父图:即便几何正常也置 uncertain 提醒人工复核
            if scene in CLAWGO_PRIORITY_PARENTS and status == "valid":
                status = "uncertain"
                note = "ClawsGO priority recheck (no geometric flag)"

            # 直方图
            ar_bin = ">=10" if ar >= 10 else (">=5" if ar >= 5 else "<5")
            stats["ar_hist"][ar_bin] = stats["ar_hist"].get(ar_bin, 0) + 1
            ss_bin = "<=16" if not short_ok else ("<=32" if short <= 32 else ">32")
            stats["short_side_hist"][ss_bin] = stats["short_side_hist"].get(ss_bin, 0) + 1

            if ar >= AR_MIN:
                stats["extreme_ar"] += 1
            if touch:
                stats["touch_boundary"] += 1
            if not short_ok:
                stats["small_short"] += 1
            stats[status] = stats.get(status, 0) + 1

            rows.append({
                "image_path": os.path.relpath(img_path, root),
                "scene_block_id": scene,
                "split": split_name,
                "n_boxes": len(boxes),
                "box_w": round(pw, 2),
                "box_h": round(ph, 2),
                "box_area": round(area, 2),
                "aspect_ratio": round(ar, 4),
                "touches_boundary": 1 if touch else 0,
                "short_side": round(short, 2),
                "review_status": status,
                "review_note": note,
            })

    stats["scene_blocks"] = len({scene_block_id(fn) for fn in os.listdir(img_dir)
                                 if fn.lower().endswith((".jpg", ".jpeg", ".png"))})
    return {"rows": rows, "stats": stats}


def scan_manifest(manifest_path, root="", imgsz=1024):
    """mode=layout:从 manifest CSV 读 image/split,label 按 .txt 推断。
    root 为空时 image 视为绝对/相对 cwd 的路径。"""
    rows = []
    stats = {"images": 0, "positive_images": 0, "boxes": 0,
             "extreme_ar": 0, "touch_boundary": 0, "small_short": 0,
             "invalid": 0, "uncertain": 0, "valid": 0,
             "ar_hist": {}, "short_side_hist": {}, "scene_blocks": 0}
    scenes = set()
    with open(manifest_path, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            img_rel = r["image"]
            split = r["split"]
            img_path = os.path.join(root, img_rel) if root else img_rel
            stem = os.path.splitext(img_path)[0]
            lab_path = stem + ".txt"
            boxes = read_yolo_label(lab_path)
            stats["images"] += 1
            if boxes:
                stats["positive_images"] += 1
            scene = scene_block_id(os.path.basename(img_path))
            scenes.add(scene)
            W, H = img_size(img_path)
            for (cx, cy, w, h) in boxes:
                stats["boxes"] += 1
                use_w, use_h = W or imgsz, H or imgsz
                pw, ph = w * use_w, h * use_h
                area, short, long = pw * ph, min(pw, ph), max(pw, ph)
                ar = long / short if short > 1e-9 else float("inf")
                touch = (cx - w / 2 < BOUNDARY_EPS or cx + w / 2 > 1 - BOUNDARY_EPS or
                         cy - h / 2 < BOUNDARY_EPS or cy + h / 2 > 1 - BOUNDARY_EPS)
                short_ok = short > SHORT_SIDE_MAX
                status, note = classify_box(w, h, ar, touch, short_ok, cx, cy)
                if scene in CLAWGO_PRIORITY_PARENTS and status == "valid":
                    status, note = "uncertain", "ClawsGO priority recheck (no geometric flag)"
                ar_bin = ">=10" if ar >= 10 else (">=5" if ar >= 5 else "<5")
                stats["ar_hist"][ar_bin] = stats["ar_hist"].get(ar_bin, 0) + 1
                ss_bin = "<=16" if not short_ok else ("<=32" if short <= 32 else ">32")
                stats["short_side_hist"][ss_bin] = stats["short_side_hist"].get(ss_bin, 0) + 1
                if ar >= AR_MIN:
                    stats["extreme_ar"] += 1
                if touch:
                    stats["touch_boundary"] += 1
                if not short_ok:
                    stats["small_short"] += 1
                stats[status] = stats.get(status, 0) + 1
                rows.append({
                    "image_path": img_rel,
                    "scene_block_id": scene,
                    "split": split,
                    "n_boxes": len(boxes),
                    "box_w": round(pw, 2), "box_h": round(ph, 2),
                    "box_area": round(area, 2), "aspect_ratio": round(ar, 4),
                    "touches_boundary": 1 if touch else 0,
                    "short_side": round(short, 2),
                    "review_status": status, "review_note": note,
                })
    stats["scene_blocks"] = len(scenes)
    return {"rows": rows, "stats": stats}


def main():
    ap = argparse.ArgumentParser(description="v5.2 标签审计表生成器")
    ap.add_argument("--mode", choices=["split", "layout"], default="split",
                    help="split=按 split 分目录加载; layout=按 manifest CSV 加载")
    ap.add_argument("--root", help="mode=split 时的数据根(含 images/ labels/)")
    ap.add_argument("--manifest", help="mode=layout 时的 manifest CSV 路径")
    ap.add_argument("--imgsz", type=int, default=1024, help="无真实图尺寸时的回退像素")
    ap.add_argument("--out", default="audit_labels.csv")
    ap.add_argument("--json", default="audit_labels.json")
    ap.add_argument("--review-out", default="review_manifest.csv")
    a = ap.parse_args()

    if a.mode == "split":
        if not a.root:
            raise SystemExit("mode=split 需要 --root")
        all_rows, all_stats = [], {}
        for split in ("train", "val", "test"):
            res = scan_split(a.root, f"images/{split}", f"labels/{split}", a.imgsz)
            all_rows += res["rows"]
            all_stats[split] = res["stats"]
    else:
        if not a.manifest:
            raise SystemExit("mode=layout 需要 --manifest")
        res = scan_manifest(a.manifest, root="", imgsz=a.imgsz)
        all_rows, all_stats = res["rows"], {"all": res["stats"]}

    # 写 CSV
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)

    # review 独立表(uncertain + invalid)
    review_rows = [r for r in all_rows if r["review_status"] in ("uncertain", "invalid")]
    with open(a.review_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(review_rows)

    # JSON 报告
    report = {
        "mode": a.mode,
        "total_boxes": len(all_rows),
        "per_split": all_stats,
        "review_summary": {
            "valid": sum(1 for r in all_rows if r["review_status"] == "valid"),
            "uncertain": sum(1 for r in all_rows if r["review_status"] == "uncertain"),
            "invalid": sum(1 for r in all_rows if r["review_status"] == "invalid"),
        },
        "note": ("脚本只做几何/格式客观审查;'框内是否真缺陷'为语义判断,"
                 "几何异常的框统一置 uncertain 待人工"),
    }
    with open(a.json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[OK] 审计 {len(all_rows)} 框 / {len(all_stats)} split")
    print(f"     valid={report['review_summary']['valid']} "
          f"uncertain={report['review_summary']['uncertain']} "
          f"invalid={report['review_summary']['invalid']}")
    print(f"     -> {a.out}")
    print(f"     -> {a.json}")
    print(f"     -> {a.review_out}  (uncertain+invalid, 待人工复核)")


if __name__ == "__main__":
    main()
