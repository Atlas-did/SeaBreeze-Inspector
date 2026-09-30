"""YOLO训练脚本 — 使用ultralytics API (P1-5: 训练可复现化)

数据增强(ultralytics自动启用):
  - Mosaic: 4图拼接, 丰富场景上下文
  - MixUp: 图像混合, 提升泛化能力
  - 随机翻转/旋转/缩放
  - HSV色彩扰动

可复现性约定:
  - model 默认 "yolo11s.pt": 实验线(YOLO11s)的权重名; 仍可显式传 "yolov8n.pt"
  - seed 默认 42: 设置 random/numpy/torch 随机种子, 并传给 model.train(seed=...)
  - dataset_version: 数据集版本号, 由 scripts/make_manifest.py 生成
  - run_name: 传给 ultralytics 的 name=, 决定 runs/ 下的运行目录名
  - eval_protocol: "ID"(同分布val) / "OOD"(域外集, yaml 由环境变量
    SEABREEZE_OOD_DATA 指定; 未设置时回退到 data_yaml 并在记录中注明) / "none"
  - 训练结束计算权重 SHA256, 写实验记录 JSON, 与 data/model_manifest.json 对齐

用法:
  python backend/vision/train.py --data data.yaml --epochs 200
  python backend/vision/train.py --data data/wind.yaml --dataset-version dv-xxxx \
      --run-name yolo11s-baseline --eval-protocol ID --manifest-out runs/exp.json
"""

import argparse
import hashlib
import json
import os
import random
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MODEL = "yolo11s.pt"
EVAL_PROTOCOLS = ("ID", "OOD", "none")
OOD_DATA_ENV = "SEABREEZE_OOD_DATA"
CHUNK = 1 << 20


def set_seed(seed: int) -> None:
    """设置 random/numpy/torch 随机种子 (库缺失时跳过)."""
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except Exception:  # noqa: BLE001
        pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:  # noqa: BLE001
        pass


def sha256_path(path) -> tuple:
    """文件 -> 内容 SHA256; 目录 -> 相对路径+文件大小的清单指纹.

    返回 (hexdigest, algorithm)。目录指纹不是内容哈希, 只保证清单稳定,
    与 scripts/make_manifest.py 的 path-size-sha256 语义一致。
    """
    p = Path(path)
    if not p.exists():
        return None, "missing"
    h = hashlib.sha256()
    if p.is_file():
        with open(p, "rb") as fh:
            for block in iter(lambda: fh.read(CHUNK), b""):
                h.update(block)
        return h.hexdigest(), "content-sha256"
    files = sorted((x for x in p.rglob("*") if x.is_file()),
                   key=lambda x: x.relative_to(p).as_posix())
    for f in files:
        h.update("{} {}\n".format(f.relative_to(p).as_posix(),
                                  f.stat().st_size).encode("utf-8"))
    return h.hexdigest(), "path-size-sha256"


def git_head(start=None) -> str:
    """仓库 HEAD SHA; 失败返回 'unknown'."""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(start or Path.cwd()),
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def metrics_dict(metrics) -> dict:
    """从 ultralytics 验证结果提取标量指标 (缺失则为 None)."""
    box = getattr(metrics, "box", None) if metrics is not None else None
    if box is None:
        return None
    out = {}
    for key, attr in (("mAP50", "map50"), ("mAP50_95", "map"), ("precision", "mp"),
                      ("recall", "mr")):
        value = getattr(box, attr, None)
        try:
            out[key] = float(value)
        except (TypeError, ValueError):
            out[key] = None
    return out


class OODDataUnavailable(RuntimeError):
    """OOD 协议缺少独立冻结的 OOD 数据集 —— 必须失败, 不允许回退到训练集。"""


def resolve_eval_data(data_yaml: str, protocol: str, ood_data: str = None) -> tuple:
    """按协议决定验证数据: 返回 (yaml_path, source说明)。

    P2 修复(审计): protocol="OOD" 必须真的使用**独立冻结**的 OOD 数据。
    此前 OOD 集未提供时会回退到训练 yaml —— 于是实验记录写着 OOD、
    实际评的却是 ID 验证集, 属于最危险的一类"假指标"。
    现在 fail-closed: 未配置或文件不存在都直接抛 OODDataUnavailable。
    """
    if protocol == "OOD":
        ood = ood_data or os.environ.get(OOD_DATA_ENV)
        if not ood:
            raise OODDataUnavailable(
                "OOD 协议要求独立冻结的 OOD 数据集: 请用 --ood-data 或环境变量 {} "
                "指定 (不允许回退到训练集)".format(OOD_DATA_ENV))
        if not Path(ood).is_file():
            raise OODDataUnavailable("OOD 数据集不存在: {}".format(ood))
        return ood, "explicit:{}".format(ood)
    return data_yaml, "train-yaml-val-split"


def resolve_weight(yolo, weights_out=None) -> str:
    """定位训练产出的 best 权重; weights_out 指定时复制到该路径."""
    trainer = getattr(yolo, "trainer", None)
    best = getattr(trainer, "best", None) if trainer is not None else None
    if not best:
        save_dir = getattr(trainer, "save_dir", None)
        best = Path(save_dir) / "weights" / "best.pt" if save_dir else None
    if not best or not Path(best).is_file():
        return None
    src = Path(best)
    if not weights_out:
        return str(src)
    dest = Path(weights_out)
    if dest.is_dir() or (not dest.exists() and dest.suffix == ""):
        dest = dest / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.resolve() != src.resolve():
        shutil.copy2(src, dest)
    return str(dest)


def train(data_yaml: str, epochs: int = 200, imgsz: int = 640, batch: int = 8,
          device: str = "cpu", resume: bool = False, validate: bool = True,
          model: str = DEFAULT_MODEL, seed: int = 42, dataset_version: str = None,
          run_name: str = None, eval_protocol: str = "ID",
          manifest_out: str = None, weights_out: str = None,
          ood_data: str = None):
    """训练YOLO模型 (P1-13: 增强错误处理和恢复; P1-5: 训练可复现化)

    参数:
        data_yaml: 数据集配置YAML路径
        epochs: 训练轮数
        imgsz: 输入图像尺寸
        batch: 批大小
        device: 设备 (cpu/cuda/mps)
        resume: 是否从checkpoint恢复
        validate: 训练后是否验证
        model: 预训练权重名/路径, 默认yolo11s.pt(实验线); 可传 yolov8n.pt 等
        seed: 随机种子, 同时写入实验记录并传给 ultralytics
        dataset_version: 数据集版本号 (scripts/make_manifest.py 产出的 dataset_version)
        run_name: 运行名, 作为 ultralytics name= 用于区分实验
        eval_protocol: "ID"(同分布val, 默认, 与旧行为一致) | "OOD"(域外集) | "none"
            (关闭评估); 仅当 validate=True 且 protocol != "none" 时才跑 model.val()
        manifest_out: 实验记录 JSON 输出路径, 默认 <save_dir>/experiment_record.json
        weights_out: 训练权重另存路径(文件或目录), 默认使用 trainer 的 best.pt
    """
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERR] 缺少ultralytics库。安装: pip install ultralytics")
        return False

    protocol = str(eval_protocol or "none")
    if protocol not in EVAL_PROTOCOLS:
        print("[ERR] eval_protocol 必须是 {} 之一, 收到 {!r}".format(
            "/".join(EVAL_PROTOCOLS), eval_protocol))
        return False

    # P2 修复(审计): OOD 协议 fail-closed —— 在**开始训练之前**就确认独立冻结的
    # OOD 数据集存在, 避免跑完才发现指标口径不合法(并产出标着 OOD 的假记录)。
    if validate and protocol == "OOD":
        try:
            resolve_eval_data(data_yaml, protocol, ood_data)
        except OODDataUnavailable as e:
            print("[ERR] {}".format(e))
            return False

    repo_root = Path(__file__).resolve().parents[2]
    record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "run_name": run_name,
        "seed": int(seed),
        "epochs": epochs,
        "imgsz": imgsz,
        "batch": batch,
        "device": device,
        "resume": bool(resume),
        "eval_protocol": protocol,
        "dataset_version": dataset_version,
        "git_head": git_head(repo_root),
    }

    set_seed(seed)
    print("[INFO] seed={} model={} eval_protocol={} dataset_version={}".format(
        seed, model, protocol, dataset_version))

    try:
        yolo = YOLO(model)
        print(f"[INFO] 开始训练, epochs={epochs}, device={device}, run_name={run_name}")
        train_kwargs = dict(data=data_yaml, epochs=epochs, imgsz=imgsz, batch=batch,
                            device=device, resume=resume, seed=int(seed))
        if run_name:
            train_kwargs["name"] = run_name
        yolo.train(**train_kwargs)

        metrics = None
        eval_data, eval_source = None, None
        if validate and protocol != "none":
            try:
                eval_data, eval_source = resolve_eval_data(
                    data_yaml, protocol, ood_data)
            except OODDataUnavailable as e:
                print("[ERR] {}".format(e))
                return False
            print("[INFO] 训练完成, 开始验证 ({})...".format(eval_source))
            metrics = yolo.val(data=eval_data)
            box = getattr(metrics, "box", None)
            print("[OK] 验证完成: mAP50={:.3f}".format(
                box.map50 if box else 0.0))
        else:
            print("[OK] 训练完成 (跳过验证)")
    except FileNotFoundError as e:
        print(f"[ERR] 文件缺失: {e}")
        print("提示: 检查 data_yaml 路径是否正确, 数据集是否已准备")
        return False
    except MemoryError:
        print("[ERR] 内存不足, 请减小 batch_size 或 imgsz")
        return False
    except Exception as e:
        print(f"[ERR] 训练失败: {e}")
        print("提示: 在Google Colab上训练可免费用GPU加速")
        return False

    # --- P1-5: 权重 SHA256 + 实验记录留档 (训练已成功, 留档失败不影响返回值) ---
    try:
        weight_path = resolve_weight(yolo, weights_out)
        weight_sha, weight_algo = (sha256_path(weight_path) if weight_path
                                   else (None, "missing"))
        data_sha, data_algo = sha256_path(data_yaml)
        record.update({
            "dataset": {"path": str(data_yaml), "sha256": data_sha,
                        "sha256_algorithm": data_algo,
                        "version": dataset_version},
            "weights": {"path": weight_path, "sha256": weight_sha,
                        "sha256_algorithm": weight_algo,
                        "bytes": (Path(weight_path).stat().st_size
                                  if weight_path else None)},
            "metrics": metrics_dict(metrics),
            "evaluated": metrics is not None,
            "eval_data": eval_data,
            "eval_data_source": eval_source,
            "trainer_save_dir": str(getattr(getattr(yolo, "trainer", None),
                                            "save_dir", "")),
            "outcome": "success",
        })
        if weight_sha is None:
            record["outcome"] = "success-without-weight"
            print("[WARN] 未找到训练权重文件, 记录的 weights.sha256 为空")
        out_path = (Path(manifest_out) if manifest_out
                    else Path(record["trainer_save_dir"] or ".") / "experiment_record.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        print("[OK] 实验记录已写入: {}".format(out_path))
        if weight_sha:
            print("[OK] 权重 SHA256 {} = {}".format(weight_sha, weight_path))
    except Exception as e:  # noqa: BLE001
        print("[WARN] 实验记录写入失败(不影响训练结果): {}".format(e))

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="数据集YAML路径")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help="权重名/路径, 默认 {} (实验线); 兼容 yolov8n.pt".format(
                            DEFAULT_MODEL))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dataset-version", default=None)
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--eval-protocol", default="ID",
                        choices=list(EVAL_PROTOCOLS))
    parser.add_argument("--ood-data", default=None,
                        help="独立冻结的 OOD 数据集 YAML (eval-protocol=OOD 时必填)")
    parser.add_argument("--manifest-out", default=None)
    parser.add_argument("--weights-out", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-validate", action="store_true")
    args = parser.parse_args()
    ok = train(args.data, args.epochs, args.imgsz, args.batch, args.device,
               resume=args.resume, validate=not args.no_validate,
               model=args.model, seed=args.seed,
               dataset_version=args.dataset_version, run_name=args.run_name,
               eval_protocol=args.eval_protocol, manifest_out=args.manifest_out,
               weights_out=args.weights_out, ood_data=args.ood_data)
    raise SystemExit(0 if ok else 1)
