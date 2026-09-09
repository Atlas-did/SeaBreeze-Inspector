#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A4-01 SAHI 切片推理(需先 pip install sahi + 导出 best.onnx;CPU 可推理但慢)
量化"AP_S 提升 Δ"与"端到端时延增加 Y"。切片参数在 val 上选一次,test 只评一次。
"""
import argparse, time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True, help='best.onnx 或 best.pt')
    ap.add_argument('--image', required=True)
    ap.add_argument('--slice', type=int, default=512)
    ap.add_argument('--overlap', type=float, default=0.33)
    ap.add_argument('--conf', type=float, default=0.25)
    ap.add_argument('--imgsz', type=int, default=640)
    a = ap.parse_args()

    try:
        from sahi import AutoDetectionModel
        from sahi.predict import get_sliced_prediction
    except ImportError:
        raise SystemExit('[ERR] pip install sahi (需 GPU 环境或 CPU 慢跑)')

    model = AutoDetectionModel.from_pretrained(
        model_type='ultralytics', model_path=a.model,
        confidence_threshold=a.conf, image_size=a.imgsz)

    t0 = time.perf_counter()
    result = get_sliced_prediction(
        a.image, model,
        slice_height=a.slice, slice_width=a.slice,
        overlap_height_ratio=a.overlap, overlap_width_ratio=a.overlap,
        postprocess_match_threshold=0.5)
    dt = time.perf_counter() - t0

    print(f'[OK] SAHI 切片推理完成: {len(result.object_prediction_list)} 个目标, 耗时 {dt:.3f}s')
    print(f'     切片={a.slice}, overlap={a.overlap}')
    print('     注意: 端到端时延须在目标设备测 P50/P95/P99,切片数≈面积/(切片²·(1-overlap)²)')


if __name__ == '__main__':
    main()
