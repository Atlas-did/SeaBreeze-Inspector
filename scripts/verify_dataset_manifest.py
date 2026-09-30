"""数据集清单摘要校验器 (内容摘要为权威; 数据集目录缺失时也能给出明确结论).

权威判据:
  1. 清单存在且可解析;
  2. 每个条目的 路径/类型/文件数/字节数/摘要算法/摘要值 与当前磁盘内容一致;
  3. dataset_version_source=derived-from-entries 时, 登记的 dataset_version
     必须等于按条目重新推出的版本(数据集锚点)。

非权威 (IGNORED_KEYS, 不参与判定, 逐项给出理由):
  generated_at            生成时间戳, 每次生成都变;
  digest_note             说明性字段(摘要算法语义);
  exclusion_policy        说明性策略字段(affects_version 已声明为 False);
  dataset_version_source  记录版本号来源, 不是内容;
  roots[].excluded        被排除的运行期产物(日志/仿真输出/测试产图), 不参与版本;
  roots[].excluded_count  上述排除项的数量, 派生字段。

数据集不可用与内容不一致是两件事, 用不同退出码区分(审计第 7 条):
  0 = 摘要一致;
  1 = 摘要不一致 / 清单自相矛盾;
  2 = 清单缺失或不可解析(环境未提供清单);
  3 = 清单登记的数据集目录在磁盘上不存在(环境未提供数据集, 不是"对不上")。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_manifest as mm  # noqa: E402

DEFAULT_MANIFEST = "data/dataset_manifest.json"

IGNORED_KEYS = {
    "generated_at": "生成时间戳, 每次生成都变",
    "digest_note": "说明性字段(摘要算法语义)",
    "exclusion_policy": "说明性策略字段, affects_version=False",
    "dataset_version_source": "版本号来源的记录, 不是内容",
    "excluded": "运行期产物排除清单, 不参与 dataset_version",
    "excluded_count": "派生字段(排除项数量)",
}


def load_manifest(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "清单不存在: {}".format(path)
    except Exception as exc:  # noqa: BLE001
        return None, "清单无法解析: {} ({})".format(path, exc)


def project(manifest: dict) -> dict:
    """只保留权威字段的投影 —— 比对永远只看内容指纹。"""
    roots = []
    for root_rec in manifest.get("roots") or []:
        entries = []
        for entry in root_rec.get("entries") or []:
            digest = entry.get("digest") or {}
            entries.append({
                "path": entry.get("path"),
                "type": entry.get("type"),
                "files": entry.get("files"),
                "bytes": entry.get("bytes"),
                "algorithm": digest.get("algorithm"),
                "digest": digest.get("value"),
            })
        roots.append({"path": root_rec.get("path"),
                      "exists": root_rec.get("exists"), "entries": entries})
    return {"roots": roots}


def diff(expected, actual, path="", out=None):
    """递归比对权威投影, 差异写入 out 列表。"""
    if out is None:
        out = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            sub = "{}.{}".format(path, key) if path else str(key)
            if key not in expected:
                out.append("{}: 清单缺失, 实际存在".format(sub))
            elif key not in actual:
                out.append("{}: 清单有, 实际缺失".format(sub))
            else:
                diff(expected[key], actual[key], sub, out)
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            out.append("{}: 条目数 清单={} 实际={}".format(path, len(expected), len(actual)))
        for i in range(min(len(expected), len(actual))):
            diff(expected[i], actual[i], "{}[{}]".format(path, i), out)
    elif expected != actual:
        out.append("{}: 清单={!r} 实际={!r}".format(path, expected, actual))
    return out


def missing_roots(manifest: dict, root: Path):
    """清单声明存在、但磁盘上已不存在的数据根目录。"""
    return [str(rec.get("path")) for rec in manifest.get("roots") or []
            if rec.get("exists") and not (root / str(rec.get("path"))).is_dir()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="校验数据集清单的内容摘要")
    ap.add_argument("--root", default=None)
    ap.add_argument("--manifest", default=None)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    manifest_path = Path(args.manifest) if args.manifest else root / DEFAULT_MANIFEST
    manifest, err = load_manifest(manifest_path)
    if err:
        print("[FAIL] 数据集清单不可用: {}".format(err))
        print("       退出码 2 = 环境未提供清单(不是内容不一致)")
        return 2

    absent = missing_roots(manifest, root)
    if absent:
        print("[N/A]  数据集目录不存在: {}".format(", ".join(absent)))
        print("       退出码 3 = 环境未提供数据集, 无法比对内容摘要(不是内容不一致)")
        print("       如需比对: 先在具备数据集的机器/CI 上恢复数据, 再重跑本脚本")
        return 3

    roots = [str(rec.get("path")) for rec in manifest.get("roots") or []]
    if not roots:
        print("[FAIL] 清单未登记任何数据根目录")
        return 1

    policy = manifest.get("digest_policy") or {}
    threshold = float(policy.get("size_threshold_mb", mm.DEFAULT_THRESHOLD_MB))
    explicit = manifest.get("dataset_version_source") == "explicit"
    actual = mm.build_dataset_manifest(
        root, roots, threshold, manifest.get("dataset_version") if explicit else None)

    diffs = diff(project(manifest), project(actual), "roots")
    if not explicit and manifest.get("dataset_version") != actual.get("dataset_version"):
        diffs.append("dataset_version: 清单={!r} 重算={!r}".format(
            manifest.get("dataset_version"), actual.get("dataset_version")))

    if diffs:
        print("[FAIL] 数据集摘要不一致: {} 处".format(len(diffs)))
        for line in diffs[:40]:
            print("       - {}".format(line))
        if len(diffs) > 40:
            print("       ... 其余 {} 处略".format(len(diffs) - 40))
        return 1

    entries = sum(len(rec.get("entries") or []) for rec in manifest.get("roots") or [])
    print("[OK] 数据集清单校验通过: {} 个根目录 / {} 个条目, dataset_version={}".format(
        len(roots), entries, manifest.get("dataset_version")))
    print("[INFO] 已忽略非权威字段: {}".format(", ".join(sorted(IGNORED_KEYS))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
