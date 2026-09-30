"""校验「部署到底加载哪个权重」——真实存在、且已在模型清单登记（model-release-ci 用）。

审计 Phase 2: 此前 ``config/yolo_config.yaml`` 仍指向已被泄漏审计否决的
``seabreeze_v3.pt``，而训练默认已改为 yolo11s —— 配置与实验口径不一致，
且 ``model_manifest.json`` 并不构成发布凭证。本脚本把这一步变成可校验的门:

  1) ``yolo_config.yaml`` 的 ``model.weights_path`` 必须存在；
  2) 该文件 SHA256 必须与 ``data/model_manifest.json`` 登记一致；
  3) 未登记的权重 = 不可发布（失败）。

退出码: 0 通过 / 2 权重缺失 / 3 未登记 / 4 哈希不一致。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def deployed_weights_path(root: Path) -> str:
    """读取 config/yolo_config.yaml 里的 model.weights_path。"""
    import yaml

    cfg_path = root / "config" / "yolo_config.yaml"
    if not cfg_path.is_file():
        raise FileNotFoundError("部署配置不存在: {}".format(cfg_path))
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return str((cfg.get("model") or {}).get("weights_path") or "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="校验部署权重已登记且哈希一致")
    ap.add_argument("--root", default=None, help="仓库根目录(默认脚本上级)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]

    try:
        weights_path = deployed_weights_path(root)
    except Exception as e:
        print("[ERR] {}".format(e))
        return 2
    if not weights_path:
        print("[ERR] config/yolo_config.yaml 未配置 model.weights_path")
        return 2

    target = Path(weights_path)
    if not target.is_absolute():
        target = root / target
    if not target.is_file():
        print("[ERR] 部署配置指向的权重不存在: {} "
              "(干净克隆里 .pt 被 .gitignore 排除, 需由 model-release-ci 拉取)".format(
                  weights_path))
        return 2

    manifest_path = root / "data" / "model_manifest.json"
    if not manifest_path.is_file():
        print("[ERR] 模型清单不存在: {}".format(manifest_path))
        return 3
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("models") or []

    entry = None
    for e in entries:
        if e.get("file") == target.name or e.get("path") == weights_path:
            entry = e
            break
    if entry is None:
        print("[ERR] 部署权重未在 model_manifest.json 登记, 不可发布: {} "
              "(已登记: {})".format(target.name, ", ".join(
                  str(e.get("file")) for e in entries) or "无"))
        return 3

    expected = str(entry.get("sha256") or "").lower()
    actual = sha256_file(target)
    if not expected or actual != expected:
        print("[ERR] 部署权重 SHA256 与清单不一致: 期望={} 实际={}".format(expected, actual))
        return 4

    print("[OK] 部署权重已登记且哈希一致: {} sha256={}".format(target.name, actual))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
