#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bench_detection_fps.py — 缺陷检测推理帧率基准（评分项：≥20fps，7 分）

用法（Windows，PowerShell，需 venv 里有 ultralytics）：
    venv\\Scripts\\python.exe verify_scripts\\bench_detection_fps.py ^
        --model runs\\detect\\v5_2_yolo11s_1024_seed42\\weights\\best.pt ^
        --images C:\\path\\to\\some\\images --imgsz 1024 --n 50

输出：每图推理 ms + 汇总（fps / ms / 峰值）。三档 imgsz（640/1024/1280）可对比。

诚实原则：
    - 本机无 GPU、CPU 推理——20fps 在 CPU 上达不到是预期的。如实测量、如实写。
    - 报告里："仿真/开发环境 CPU 推理 X.X fps；部署按 20fps 需 GPU 或模型压缩"。
    - 脚本不含任何"假装达标"的逻辑。fps 不足就写不足，并给出达标路径建议。
"""
import argparse
import csv
import glob
import os
import time

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--images", required=True,
                    help="图片目录或单张图路径")
    ap.add_argument("--imgsz", type=int, default=1024)
    ap.add_argument("--n", type=int, default=50, help="采样图片数")
    ap.add_argument("--warmup", type=int, default=3, help="预热轮数（不算入统计）")
    ap.add_argument("--out", default="det_fps_result")
    args = ap.parse_args()

    if os.path.isdir(args.images):
        exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp")
        files = [f for e in exts for f in glob.glob(os.path.join(args.images, e))]
    elif os.path.isfile(args.images):
        files = [args.images]
    else:
        print("!! --images 路径不存在。")
        return 2
    files = sorted(files)[: args.n]
    if not files:
        print("!! 目录下没有图片。")
        return 3
    print(f"[1/3] 找到 {len(files)} 张图，加载模型 {args.model}")

    from ultralytics import YOLO
    model = YOLO(args.model)
    print(f"[2/3] 预热 {args.warmup} 轮…")
    for i in range(args.warmup):
        _ = model.predict(files[0], imgsz=args.imgsz, verbose=False, device="cpu")

    print(f"[3/3] 正式测 {len(files)} 张 @{args.imgsz}…")
    times_ms = []
    for f in files:
        t0 = time.perf_counter()
        _ = model.predict(f, imgsz=args.imgsz, verbose=False, device="cpu")
        times_ms.append((time.perf_counter() - t0) * 1000)

    import statistics
    total_s = sum(times_ms) / 1000.0
    fps = len(times_ms) / total_s if total_s > 0 else 0.0
    summary = {
        "protocol": "detection inference throughput (CPU)",
        "model": args.model,
        "imgsz": args.imgsz,
        "n_images": len(files),
        "mean_ms_per_img": round(statistics.mean(times_ms), 1),
        "median_ms_per_img": round(statistics.median(times_ms), 1),
        "p95_ms_per_img": round(sorted(times_ms)[int(len(times_ms) * 0.95) - 1], 1),
        "max_ms_per_img": round(max(times_ms), 1),
        "fps": round(fps, 2),
        "target_fps": 20.0,
        "meets_20fps": fps >= 20.0,
        "note": "CPU 推理。若未达 20fps：报告如实写，达标路径=GPU/导出 TensorRT/降 imgsz/模型蒸馏",
    }
    print(f"\n  平均 {summary['mean_ms_per_img']} ms/图 → {fps:.2f} fps")
    print(f"  20fps 目标: {'达成' if summary['meets_20fps'] else '未达成'}（如实记录，勿虚报）")

    with open(args.out + "_summary.json", "w", encoding="utf-8") as fh:
        import json
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    with open(args.out + "_per_image.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["image", "ms"])
        for f, ms in zip(files, times_ms):
            w.writerow([f, round(ms, 1)])
    print(f"  输出: {args.out}_summary.json / {args.out}_per_image.csv")
    print("\n→ 填进报告草稿 5.2 / 7.3：fps 与 ms/图，达标路径见 note。")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
