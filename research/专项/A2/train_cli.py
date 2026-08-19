#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2-01 训练 CLI(需 GPU 运行;参数诚实——每个旋钮命令行可见、训练后回读 args.yaml 自检)

默认值与 v4 对齐(model=yolo11s.pt, imgsz=1024, batch=8, epochs=200, seed=0)。
多轮训练(binary/multi × 11s/8s)时,除刻意变化的项外其余参数在命令行显式一致。

用法(云 GPU):
  python train_cli.py --model yolo11s.pt --data data/processed/wind_turbine_defect_binary.yaml \
      --imgsz 1024 --batch 8 --epochs 200 --seed 0 --project runs/binary --name v11s-1024
"""
import argparse
import os
import glob


def main():
    ap = argparse.ArgumentParser(description='YOLO 训练(GPU 接口;参数诚实,训练后自检 args.yaml)')
    ap.add_argument('--model', default='yolo11s.pt', help='yolo11n/s/m.pt(默认 yolo11s,与 v4 一致)')
    ap.add_argument('--data', required=True)
    ap.add_argument('--imgsz', type=int, default=1024)
    ap.add_argument('--batch', type=int, default=8)
    ap.add_argument('--epochs', type=int, default=200)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--project', default='runs/binary')
    ap.add_argument('--name', required=True)
    ap.add_argument('--fl_gamma', type=float, default=0.0,
                    help='focal loss 伽马(0=关闭;类别不平衡时 1.5~2.0)')
    ap.add_argument('--device', default='0', help='GPU 号或 cpu')
    ap.add_argument('--patience', type=int, default=50, help='早停轮数(固定预算口径)')
    # 增强参数显式化(默认值与 v4 一致),多轮对比时每个影响结果的旋钮都可在命令行复现
    ap.add_argument('--fliplr', type=float, default=0.5)
    ap.add_argument('--mosaic', type=float, default=1.0)
    ap.add_argument('--hsv_h', type=float, default=0.015)
    ap.add_argument('--hsv_s', type=float, default=0.7)
    ap.add_argument('--hsv_v', type=float, default=0.4)
    a = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit('[ERR] 需先 pip install ultralytics(在 GPU 环境)')

    model = YOLO(a.model)
    # 固定 seed + 显式 project/name,保证可复现;fl_gamma 是 ultralytics 原生 focal loss 参数
    model.train(
        data=a.data, imgsz=a.imgsz, batch=a.batch, epochs=a.epochs,
        seed=a.seed, project=a.project, name=a.name,
        device=a.device, patience=a.patience,
        fl_gamma=a.fl_gamma,
        fliplr=a.fliplr, mosaic=a.mosaic,
        hsv_h=a.hsv_h, hsv_s=a.hsv_s, hsv_v=a.hsv_v,
    )
    print(f'[OK] 训练完成: {a.project}/{a.name} (model={a.model}, imgsz={a.imgsz}, seed={a.seed})')

    # 训练后自检:回读 args.yaml 确认关键参数生效,暴露"传了没生效"的坑
    _check_args_effective(a)


def _check_args_effective(a):
    import yaml
    runs = sorted(glob.glob(os.path.join(a.project, a.name, 'args.yaml')))
    if not runs:
        print('[WARN] 未找到 args.yaml,参数生效性未自检(project/name 是否与训练一致?)')
        return
    cfg = yaml.safe_load(open(runs[-1], encoding='utf-8'))
    keys = ['model', 'imgsz', 'epochs', 'seed', 'fl_gamma', 'fliplr', 'mosaic',
            'hsv_h', 'hsv_s', 'hsv_v']
    got = {k: cfg.get(k) for k in keys}
    print(f'[CHECK] 训练参数确认(来自 args.yaml): {got}')
    # 断言 fl_gamma 生效(重点自检项)
    if abs(float(cfg.get('fl_gamma', 0.0)) - a.fl_gamma) >= 1e-6:
        raise SystemExit(f'[FAIL] fl_gamma 未生效: 期望 {a.fl_gamma}, args.yaml={cfg.get("fl_gamma")}')
    print('[CHECK] fl_gamma 生效确认 OK')


if __name__ == '__main__':
    main()
