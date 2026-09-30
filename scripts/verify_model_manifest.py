"""模型清单权威校验器 —— 发布流水线的模型闸门 (干净克隆可跑).

权威判据 (只有这些能让本脚本非 0 退出):
  1. 清单存在且可解析;
  2. 每个权重条目登记了 64 位 hex 的 sha256 与 bytes;
  3. 权重文件存在, 且字节数 / SHA256 与清单登记一致 (内容指纹);
  4. release_candidate: true 的条目必须具备完整 training/eval provenance
     —— 数据集版本 / 模型系列 / 输入尺寸 / epoch / ID 指标 / OOD 指标。
     这为"训练前先登记 provenance"提供机制: 想发版, 先登记来源。

非权威 (IGNORED_KEYS, 一律不参与判定, 逐项给出理由):
  generated_at          每次生成清单都会变, 与内容无关;
  mtime_ns / mtime_utc  文件系统时间戳: 权重从受控仓库下载 / 拷贝 / git
                        checkout 之后必然改变, 干净克隆里与生成清单时不可能
                        相同 —— 拿它做判据会让发布流水线必然失败(审计第 7 条);
  informational         信息性子树(mtime 与人类可读附注住在这里);
  weights_dir_exists    派生字段(目录是否在磁盘上), 已被逐条目存在性检查取代;
  ignored               说明性字段(哪些文件被有意忽略), 与内容指纹无关;
  digest_note           说明性字段(摘要算法语义), 与内容指纹无关。

用法::
  python scripts/verify_model_manifest.py [--root .]
  python scripts/verify_model_manifest.py --manifest-only   # 只验清单自洽, 不读磁盘权重

退出码: 0=通过; 1=权威判据不满足; 2=清单缺失/不可解析(环境未提供清单)。
"""
import argparse
import hashlib
import json
from pathlib import Path

CHUNK = 1 << 20
DEFAULT_MANIFEST = "data/model_manifest.json"
DEFAULT_WEIGHTS_DIR = "data/weights"

IGNORED_KEYS = {
    "generated_at": "生成时间戳, 每次生成都变",
    "mtime_ns": "文件系统时间戳, 下载/拷贝/checkout 后必然改变",
    "mtime_utc": "同上, mtime 的人类可读形式",
    "informational": "信息性子树(mtime 与人类可读附注)",
    "weights_dir_exists": "派生字段, 由逐条目存在性检查取代",
    "ignored": "说明性字段(被忽略的文件清单)",
    "digest_note": "说明性字段(摘要算法语义)",
}

# release_candidate 必须登记的 provenance 字段 (机制: 训练前先登记)。
PROVENANCE_REQUIRED = {
    "training": ("dataset_version", "model_series", "input_size", "epochs"),
    "eval": ("id_metric", "id_value", "ood_metric", "ood_value"),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "清单不存在: {}".format(path)
    except Exception as exc:  # noqa: BLE001
        return None, "清单无法解析: {} ({})".format(path, exc)


def _blank(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def provenance_problems(entry: dict):
    """权威判据 4: release_candidate 的 provenance 必须完整。"""
    name = entry.get("file") or entry.get("path") or "<unnamed>"
    if not entry.get("release_candidate"):
        return []
    problems = []
    for block, keys in PROVENANCE_REQUIRED.items():
        data = entry.get(block)
        if not isinstance(data, dict):
            problems.append("{}: release_candidate=true 但缺少 {} provenance".format(name, block))
            continue
        missing = [k for k in keys if _blank(data.get(k))]
        if missing:
            problems.append("{}: {} provenance 缺少 {}".format(name, block, ", ".join(missing)))
    return problems


def entry_path(entry: dict, root: Path, weights_dir: str) -> Path:
    rel = entry.get("path")
    if rel:
        return root / str(rel)
    return root / weights_dir / str(entry.get("file", ""))


def content_problems(entry: dict, root: Path, weights_dir: str):
    """权威判据 2/3: 登记完整 + 磁盘内容与登记一致。"""
    name = entry.get("file") or entry.get("path") or "<unnamed>"
    problems = []
    expected_sha = str(entry.get("sha256") or "").lower()
    hexdigits = set("0123456789abcdef")
    if len(expected_sha) != 64 or not set(expected_sha) <= hexdigits:
        problems.append("{}: 清单未登记合法的 sha256(64 位 hex) —— 拒绝发布".format(name))
    size = entry.get("bytes")
    if not isinstance(size, int) or size < 0:
        problems.append("{}: 清单未登记 bytes(字节数)".format(name))
    path = entry_path(entry, root, weights_dir)
    if not path.is_file():
        problems.append("{}: 权重文件不存在: {}".format(name, path))
        return problems
    actual_sha = sha256_file(path)
    actual_size = path.stat().st_size
    if actual_sha != expected_sha:
        problems.append("{}: SHA256 不匹配 清单={} 实际={}".format(name, expected_sha, actual_sha))
    if isinstance(size, int) and actual_size != size:
        problems.append("{}: 字节数不匹配 清单={} 实际={}".format(name, size, actual_size))
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="按内容指纹校验模型清单")
    ap.add_argument("--root", default=None)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--weights-dir", default=None)
    ap.add_argument("--manifest-only", action="store_true",
                    help="只校验清单自洽与 provenance, 不读磁盘权重")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    manifest_path = Path(args.manifest) if args.manifest else root / DEFAULT_MANIFEST
    manifest, err = load_manifest(manifest_path)
    if err:
        print("[FAIL] 模型清单不可用: {}".format(err))
        print("       发布要求受控清单随发布源提供 —— 权重按清单登记的 SHA256 拉取")
        return 2

    entries = manifest.get("models") or []
    weights_dir = args.weights_dir or manifest.get("weights_dir") or DEFAULT_WEIGHTS_DIR
    problems = []
    if not entries:
        problems.append("清单里没有任何权重条目")
    for entry in entries:
        problems.extend(provenance_problems(entry))
        if not args.manifest_only:
            problems.extend(content_problems(entry, root, weights_dir))

    if problems:
        print("[FAIL] 模型清单校验失败: {} 条".format(len(problems)))
        for line in problems:
            print("       - {}".format(line))
        return 1

    mode = "仅清单自洽" if args.manifest_only else "内容指纹"
    checked = 0 if args.manifest_only else len(entries)
    print("[OK] 模型清单校验通过 ({}): {} 个条目, {} 个权重按 SHA256+字节数核对".format(
        mode, len(entries), checked))
    print("[INFO] 已忽略非权威字段: {}".format(", ".join(sorted(IGNORED_KEYS))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
