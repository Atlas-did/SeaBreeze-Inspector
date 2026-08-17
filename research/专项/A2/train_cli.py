#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2-01 训练 CLI(接口已排好,需 GPU 运行)
扩展仓库 train.py: 支持 --model --project --name --seed --cls_pw --device,禁手工改文件丢记录。

用法(云 GPU):
  python train_cli.py --model yolov8s.pt --data data/processed/wind_turbine_defect_binary.yaml \
      --imgsz 1280 --batch 8 --epochs 200 --seed 0 --project runs/binary --name v8s-1280
"""
import argparse


def main():
    ap = argparse.ArgumentParser(description='YOLO 训练(GPU 接口)')
    ap.add_argument('--model', default='yolov8n.pt', help='yolov8n/s/m.pt')
    ap.add_argument('--data', required=True)
    ap.add_argument('--imgsz', type=int, default=1280)
    ap.add_argument('--batch', type=int, default=8)
    ap.add_argument('--epochs', type=int, default=200)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--project', default='runs/binary')
    ap.add_argument('--name', required=True)
    ap.add_argument('--cls_pw', type=float, default=1.0, help='类别权重倍率(1.0=默认自动按频率)')
    ap.add_argument('--device', default='0', help='GPU 号或 cpu')
    ap.add_argument('--patience', type=int, default=50, help='早停轮数(固定预算口径)')
    a = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit('[ERR] 需先 pip install ultralytics(在 GPU 环境)')

    model = YOLO(a.model)
    # 固定 seed + 显式 project/name,保证可复现
    model.train(
        data=a.data, imgsz=a.imgsz, batch=a.batch, epochs=a.epochs,
        seed=a.seed, project=a.project, name=a.name,
        device=a.device, patience=a.patience,
        # 增强与 v3 一致(fliplr/mosaic/hsv)
        fliplr=0.5, mosaic=1.0,
        hsv_h=0.015, hsv_s=0.7, hsv_v=0.4,
    )
    print(f'[OK] 训练完成: {a.project}/{a.name} (model={a.model}, imgsz={a.imgsz}, seed={a.seed})')


if __name__ == '__main__':
    main()
