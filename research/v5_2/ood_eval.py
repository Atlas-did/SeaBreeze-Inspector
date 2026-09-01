#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ood_eval.py — v5.2 双评估协议的 OOD/ID 评估管线(第三步:按场景分组诊断)

 Implements research/v5_2_数据协议修复方案.md §4:
  - headline metrics via Ultralytics val (comparable with v4/v5 history)
  - per-scene-block / short-side-bucket / aspect-ratio-bucket diagnostics
    (own greedy IoU matcher at a fixed operating point, documented in report)
  - D7 enforcement: `--split ood_test` is ONE-SHOT per pre-registered slot
    ('baseline' = pre-data measurement, 'final' = paper number). A lock file
    (ood_test_EVAL_LOCK_<slot>.json next to the manifest) is written after a
    successful full run and refused afterwards. `--limit` is forbidden on
    ood_test (a partial eval still burns the set). id_val is freely
    re-runnable (dry runs / threshold sweeps live there).

 Usage:
   # dry run / threshold sweeps (freely repeatable):
   python ood_eval.py --split id_val --model data/weights/seabreeze_v3.pt --limit 30
   # FINAL one-shot OOD evaluation (full 425 images, writes lock):
   python ood_eval.py --split ood_test --model runs/v5_2/s1/weights/best.pt

 The model adapter is injectable for tests: tests may monkeypatch
 ood_eval._predict_boxes to return synthetic detections.
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time
from collections import defaultdict

SPLIT_DIR_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v5_2")

VALID_SPLITS = ("id_val", "ood_test")
OOD_SLOTS = ("baseline", "final")   # D7: two pre-registered one-shot slots
LOCK_PREFIX = "ood_test_EVAL_LOCK"

# bucket edges mirror make_v5_2_split.py / split_report.json so numbers line up
SHORT_SIDE_EDGES = (32, 64, 128)          # <=32, <=64, <=128, >128
ASPECT_EDGES = (5.0, 10.0, 20.0)          # <=5, <=10, <=20, >20

DIAG_CONF = 0.25   # operating point for the diagnostic slices (headline uses val's own sweep)
DIOU = 0.5         # IoU threshold for a TP in diagnostic matching


# ---------------------------------------------------------------- manifest

def load_manifest(manifest_path):
    """Return list of dicts with keys image, scene_block_id, sha256.

    Raises ValueError with a clear message on schema problems so unit tests
    and CLI users get the same feedback.
    """
    if not os.path.isfile(manifest_path):
        raise ValueError(f"manifest not found: {manifest_path}")
    rows = []
    with open(manifest_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        for need in ("image", "scene_block_id"):
            if need not in cols:
                raise ValueError(f"manifest missing column '{need}' (has: {cols})")
        for row in reader:
            if not row.get("image"):
                continue
            rows.append({"image": row["image"].strip(),
                         "scene_block_id": row["scene_block_id"].strip(),
                         "sha256": (row.get("sha256") or "").strip()})
    if not rows:
        raise ValueError("manifest has no data rows")
    return rows


def split_dir_for(split_dir_root, split):
    return os.path.join(split_dir_root, split)


def resolve_image(split_dir, rel_image):
    """Manifest stores 'images/train/DJI_x.jpg' (mode-A) or bare names;
    the actual file lives in <split_dir>/images/<name>.jpg — take the
    basename and re-root it inside the split dir (single source of truth:
    the split tree)."""
    return os.path.join(split_dir, "images", os.path.basename(rel_image))


# ---------------------------------------------------------------- buckets

def short_side_bucket(w, h):
    s = min(w, h)
    for e in SHORT_SIDE_EDGES:
        if s <= e:
            return f"<={e}"
    return ">128"


def aspect_bucket(w, h):
    a = max(w, h) / max(1e-9, min(w, h))
    for e in ASPECT_EDGES:
        if a <= e:
            return f"<={e:g}"
    return ">20"


def bucket_label_stats(gt_boxes):
    """gt_boxes: list of (x, y, w, h) in pixels. Returns
    {bucket: [gt indices]} for both bucket families."""
    by_short, by_aspect = defaultdict(list), defaultdict(list)
    for i, (_, _, w, h) in enumerate(gt_boxes):
        by_short[short_side_bucket(w, h)].append(i)
        by_aspect[aspect_bucket(w, h)].append(i)
    return dict(by_short), dict(by_aspect)


# ---------------------------------------------------------------- matching

def iou_xyxy(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def match_detections(gt_xyxy, dets, iou_thr=DIOU):
    """Greedy IoU matching, highest-confidence first.

    gt_xyxy: list of (x1,y1,x2,y2) ground-truth boxes
    dets:    list of dicts {"box": (x1,y1,x2,y2), "conf": float}
    Returns (n_tp, n_fp): each GT matches at most one det and vice versa.
    """
    matched_gt = set()
    tp = 0
    for det in sorted(dets, key=lambda d: -d["conf"]):
        best_iou, best_g = 0.0, -1
        for gi, gt in enumerate(gt_xyxy):
            if gi in matched_gt:
                continue
            v = iou_xyxy(det["box"], gt)
            if v > best_iou:
                best_iou, best_g = v, gi
        if best_g >= 0 and best_iou >= iou_thr:
            matched_gt.add(best_g)
            tp += 1
    return tp, len(dets) - tp


# ---------------------------------------------------------------- adapter

def _predict_boxes(model, image_paths, conf, imgsz):
    """Ultralytics adapter: returns {path: [ {"box":(x1,y1,x2,y2), "conf":c} ]}.

    Kept thin and monkeypatch-friendly for unit tests.
    """
    out = {}
    results = model.predict(image_paths, conf=conf, imgsz=imgsz,
                            verbose=False, device="cpu")
    for path, res in zip(image_paths, results):
        boxes = []
        for b in res.boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0].tolist())
            boxes.append({"box": (x1, y1, x2, y2), "conf": float(b.conf[0])})
        out[path] = boxes
    return out


# ---------------------------------------------------------------- guard

def lock_path_for(split_dir_root, slot):
    return os.path.join(split_dir_root, f"{LOCK_PREFIX}_{slot}.json")


def check_ood_lock(split_dir_root, slot):
    """Raise RuntimeError if this pre-registered OOD slot was already spent."""
    lp = lock_path_for(split_dir_root, slot)
    if os.path.isfile(lp):
        with open(lp, encoding="utf-8") as fh:
            prev = json.load(fh)
        raise RuntimeError(
            f"D7 violation: ood_test slot '{slot}' was already evaluated on "
            f"{prev.get('finished_utc')} with model sha256 "
            f"{str(prev.get('model_sha256') or '?')[:12]}… "
            f"(report: {prev.get('report')}). The OOD test is final and must not be "
            "re-run; if you are sure, this must be an explicit human decision — "
            "delete the lock file by hand after that decision.")


def write_ood_lock(split_dir_root, slot, model_path, report_path, headline):
    lp = lock_path_for(split_dir_root, slot)
    payload = {
        "slot": slot,
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_path": os.path.abspath(model_path),
        "model_sha256": (_sha256_file(model_path)
                         if os.path.isfile(model_path) else None),
        "report": os.path.abspath(report_path),
        "headline": headline,
    }
    with open(lp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return lp


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- diagnostics

def aggregate(entries):
    """entries: list of (tp, fp, fn). Returns P/R/F1 (0.0 when undefined)."""
    tp = sum(e[0] for e in entries)
    fp = sum(e[1] for e in entries)
    fn = sum(e[2] for e in entries)
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}


def build_report(rows, split_dir, model_path, det_by_image, gt_by_image,
                 headline, limit, extra_meta=None):
    """Assemble the diagnostic report: headline + per-scene/per-bucket slices.

    Single honest pass: match_detections_detailed gives each GT its
    tp/fn outcome, which is then aggregated per scene block and per
    geometry bucket (short side / aspect ratio, edges mirror
    split_report.json).
    """
    by_scene, by_short, by_aspect = defaultdict(list), defaultdict(list), defaultdict(list)
    fp_total = 0
    for row in rows:
        path = resolve_image(split_dir, row["image"])
        gt_xyxy, gt_px = gt_by_image[path]
        dets = [d for d in det_by_image.get(path, []) if d["conf"] >= DIAG_CONF]
        tp, fp, matched = match_detections_detailed(gt_xyxy, dets)
        fp_total += fp
        scene = row["scene_block_id"]
        by_scene[scene].append((tp, fp, len(gt_xyxy) - tp))
        for gi, (x, y, w, h) in enumerate(gt_px):
            res = "tp" if gi in matched else "fn"
            by_short[short_side_bucket(w, h)].append((res,))
            by_aspect[aspect_bucket(w, h)].append((res,))

    def slice_outcome(items):
        tp = sum(1 for it in items if it[0] == "tp")
        fn = sum(1 for it in items if it[0] == "fn")
        return aggregate([(tp, 0, fn)])

    scene_slices = {s: aggregate(es) for s, es in sorted(by_scene.items())}
    short_slices = {k: slice_outcome(v) for k, v in sorted(by_short.items())}
    aspect_slices = {k: slice_outcome(v) for k, v in sorted(by_aspect.items())}

    scene_recs = [v["recall"] for v in scene_slices.values() if v["fn"] + v["tp"] > 0]
    verdict = {
        "ood_recall_not_near_zero": bool(scene_recs and max(scene_recs) >= 0.05),
        "scene_spread_detected": bool(scene_recs and (max(scene_recs) - min(scene_recs)) > 0.2),
        "note": "§4.第三步 three-way judgement — read scene_slices, short_slices, "
                "aspect_slices together; a single near-zero scene block with "
                "healthy others = appearance domain shift; uniform collapse = "
                "labels/coverage/resolution.",
    }
    return {
        "meta": {
            "split": os.path.basename(split_dir),
            "model_path": os.path.abspath(model_path),
            "model_sha256": _sha256_file(model_path) if os.path.isfile(model_path) else None,
            "diag_conf": DIAG_CONF, "diag_iou": DIOU,
            "images": len(rows), "limit": limit,
            "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "numbers_are_citable": limit is None and os.path.basename(split_dir) != "ood_test",
            **(extra_meta or {}),
        },
        "headline_val": headline,
        "scene_slices": scene_slices,
        "short_side_recall": short_slices,
        "aspect_ratio_recall": aspect_slices,
        "false_positives_total": fp_total,
        "verdict_hints": verdict,
    }


def match_detections_detailed(gt_xyxy, dets, iou_thr=DIOU):
    """Same as match_detections but also returns the matched GT index set."""
    matched = set()
    tp = 0
    for det in sorted(dets, key=lambda d: -d["conf"]):
        best_iou, best_g = 0.0, -1
        for gi, gt in enumerate(gt_xyxy):
            if gi in matched:
                continue
            v = iou_xyxy(det["box"], gt)
            if v > best_iou:
                best_iou, best_g = v, gi
        if best_g >= 0 and best_iou >= iou_thr:
            matched.add(best_g)
            tp += 1
    return tp, len(dets) - tp, matched


# ---------------------------------------------------------------- gt loader

def load_gt(split_dir, image_path):
    """YOLO-format label: class cx cy w h (normalized). Returns
    ([(x1,y1,x2,y2)...], [(x,y,w,h) px...]) using PIL-free size probe via
    ultralytics cv2. Empty/missing label file = negative image."""
    label = os.path.join(split_dir, "labels",
                         os.path.splitext(os.path.basename(image_path))[0] + ".txt")
    gt_xyxy, gt_px = [], []
    if not os.path.isfile(label):
        return gt_xyxy, gt_px
    import cv2
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"unreadable image: {image_path}")
    H, W = img.shape[:2]
    with open(label, encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 5:
                continue
            _, cx, cy, w, h = (float(p) for p in parts[:5])
            w_px, h_px = w * W, h * H
            x1, y1 = (cx - w / 2) * W, (cy - h / 2) * H
            gt_xyxy.append((x1, y1, x1 + w_px, y1 + h_px))
            gt_px.append((cx * W, cy * H, w_px, h_px))
    return gt_xyxy, gt_px


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="v5.2 dual-protocol evaluator")
    ap.add_argument("--split", choices=VALID_SPLITS, required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--split-dir-root", default=SPLIT_DIR_DEFAULT)
    ap.add_argument("--manifest", default=None,
                    help="defaults to <split-dir-root>/<split>_manifest.csv")
    ap.add_argument("--out", default=None,
                    help="defaults to research/v5_2/report_<split>_<stamp>.json")
    ap.add_argument("--limit", type=int, default=None,
                    help="dry-run size; FORBIDDEN on ood_test")
    ap.add_argument("--slot", choices=OOD_SLOTS, default=None,
                    help="required for ood_test: 'baseline' (pre-registered "
                         "pre-data measurement) or 'final' (paper number); "
                         "each slot is one-shot")
    ap.add_argument("--imgsz", type=int, default=1024)
    args = ap.parse_args(argv)

    split_dir_root = os.path.abspath(args.split_dir_root)
    split_dir = split_dir_for(split_dir_root, args.split)
    manifest = args.manifest or os.path.join(split_dir_root, f"{args.split}_manifest.csv")

    if args.split == "ood_test":
        if not args.slot:
            ap.error("D7: ood_test requires an explicit --slot "
                     f"{'|'.join(OOD_SLOTS)} (each pre-registered slot is one-shot)")
        if args.limit is not None:
            ap.error("D7: --limit is forbidden on ood_test (partial eval burns the set)")
        check_ood_lock(split_dir_root, args.slot)

    rows = load_manifest(manifest)
    if args.limit:
        rows = rows[:args.limit]
    paths = [resolve_image(split_dir, r["image"]) for r in rows]
    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        raise ValueError(f"{len(missing)} manifest images missing on disk, "
                         f"e.g. {missing[:3]}")

    # headline metrics (Ultralytics val needs a dataset yaml). Skipped on
    # limited dry runs — the val API runs the whole split dir and a CPU box
    # has no business doing that; one-shot OOD runs are always full.
    headline = ({}) if args.limit else run_headline_val(args.model, split_dir,
                                                        args.imgsz)

    from ultralytics import YOLO
    model = YOLO(args.model)
    det_by_image = {}
    B = 16
    for i in range(0, len(paths), B):
        det_by_image.update(_predict_boxes(model, paths[i:i + B], DIAG_CONF, args.imgsz))
        print(f"[ood_eval] predictions {min(i + B, len(paths))}/{len(paths)}")

    gt_by_image = {p: load_gt(split_dir, p) for p in paths}
    report = build_report(rows, split_dir, args.model, det_by_image,
                          gt_by_image, headline, args.limit)

    out = args.out or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"report_{args.split}_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"[ood_eval] report -> {out}")

    if args.split == "ood_test":
        lp = write_ood_lock(split_dir_root, args.slot, args.model, out,
                            report["headline_val"])
        print(f"[ood_eval] one-shot lock ({args.slot}) written -> {lp}")
    return 0


def run_headline_val(model_path, split_dir, imgsz):
    """Ultralytics val for the headline P/R/mAP numbers (comparable with
    the v4/v5 history). Returns {} on failure so diagnostics still emit."""
    import tempfile
    import yaml  # ultralytics ships pyyaml
    data_yaml = os.path.join(tempfile.gettempdir(), f"ood_eval_{os.getpid()}.yaml")
    with open(data_yaml, "w", encoding="utf-8") as fh:
        yaml.safe_dump({
            "path": split_dir,
            "train": os.path.join(split_dir, "images"),
            "val": os.path.join(split_dir, "images"),
            "names": {0: "defect"},
        }, fh)
    try:
        from ultralytics import YOLO
        res = YOLO(model_path).val(data=data_yaml, imgsz=imgsz,
                                   verbose=False, device="cpu")
        return {"precision": round(float(res.box.mp), 4),
                "recall": round(float(res.box.mr), 4),
                "mAP50": round(float(res.box.map50), 4),
                "mAP50-95": round(float(res.box.map), 4)}
    except Exception as exc:
        print(f"[ood_eval] headline val failed ({exc!r}); diagnostics only")
        return {}
    finally:
        try:
            os.remove(data_yaml)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
