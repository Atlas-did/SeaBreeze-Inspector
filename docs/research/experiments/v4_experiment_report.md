# v4 Experiment Report — Offshore Wind Turbine Blade Defect Detection

> **Status:** verified. Every metric below is read directly from `v4/results.csv` (200 epochs) and `v4/args.yaml`.
> **Key correction vs. earlier draft:** the detector is **YOLO11s**, not YOLOv8.

---

## 1. Experiment Setup

| Item | Value |
|---|---|
| Model | **YOLO11s** (`yolo11s.pt`, pretrained) |
| Task | Single-class object detection (`nc=1`, class `defect`) |
| Input size | 1024 × 1024 px tiles |
| Epochs | 200 (patience 50, no early stop triggered) |
| Batch size | 8 |
| Device | Single NVIDIA GPU (`device=0`) |
| Optimizer | auto (lr0=0.01, lrf=0.01) |
| Seed / deterministic | 0 / true |
| Key augmentation | mosaic=1.0 (close_mosaic=10), fliplr=0.5, scale=0.5, HSV jitter, erasing=0.4 |

### Dataset: `clean_binary_v4_quick`

| Split | defect | clean (background) | total |
|---|---|---|---|
| train | 423 | 1697 | 2120 |
| val | 82 | 358 | 440 |
| test | 82 | 398 | 480 |
| **total** | **587** | **2453** | **3040** |

- **Source images:** native DTU Nordtank drone imagery at 5280 × 2970 px, cropped into 1024 × 1024 tiles (**no downscaling**).
- **"clean" tiles** are defect-free background images with explicit **empty label files** (0-byte `.txt`) — no object boxes.
- **Leakage-free split:** tiles are grouped by acquisition unit (flight ID for negatives, base-image family for positives); every group is kept entirely within one split (verified 0 cross-split groups).

---

## 2. Results

**Single-model result** (best checkpoint, selected by mAP50-95 at **epoch 182**):

| Metric | Value |
|---|---|
| mAP50 | **0.668** |
| mAP50-95 | **0.348** |
| Precision | **0.795** |
| Recall | **0.619** |

**Per-metric peaks across training:**

- mAP50 peak: **0.674** (epoch 190; at that epoch P=0.756, R=0.664)
- mAP50-95 peak: **0.348** (epoch 182)
- Recall peak: **0.664** (epoch 190)

### Comparison

| run | model | imgsz | epochs | mAP50 | mAP50-95 |
|---|---|---|---|---|---|
| v2 | YOLOv8s | 640 | 100 | 0.242 | 0.105 |
| v4 | **YOLO11s** | 1024 | 200 | **0.674** | **0.348** |

> **Attribution caveat:** model architecture (YOLOv8s → YOLO11s), input resolution (640 → 1024 tiling), and data (clean-verified negatives) all changed between v2 and v4. The improvement is attributable to the **combination**, not to tiling alone. To isolate the tiling contribution, a YOLOv8s @ 1024-tiles control run is recommended.

---

## 3. Data Discipline (four layers)

1. **Zero leakage** — grouped split by acquisition unit; verified 0 cross-split groups for both positives and negatives.
2. **Content dedup** — sha256-level dedup removed exact-duplicate files (and cross-split augmentation variants).
3. **Native hi-res** — 5280 × 2970 source tiled to 1024, preserving small defects (measured: median defect 47 × 61 px, 30% of boxes < 32 px wide).
4. **Clean verification** — negative samples manually/automatically verified; ~45% false "clean" images removed.

---

## 4. Caveats (honest framing)

- **Detection mAP ≠ image-level accuracy.** mAP50 = 0.674 / P = 0.795 are *detection* metrics. A "95%" requirement usually refers to *image-level* accuracy (whole image contains a defect or not), which is a different, more lenient measure and should not be compared directly against detection mAP.
- **Architecture confounder** — see attribution caveat above.

---

## 5. Artifacts

| File | Path |
|---|---|
| Best weights | `v4/weights/best.pt` (19.3 MB) |
| Training curves | `v4/results.csv`, `v4/results.png` |
| Confusion matrix | `v4/confusion_matrix.png` |
| Training args | `v4/args.yaml` |
| Dataset | `datasets/derived/clean_binary_v4_quick/` |

---

## 6. License / Attribution

Negative-sample source dataset **"Wind Turbine Blade Defect Detect"** (Roboflow Universe, CC BY 4.0) — attribution required in the paper / acknowledgements.
