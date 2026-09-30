"""生成清单与环境锁 (P1-5 训练可复现化).

用法:
  venv\\Scripts\\python.exe scripts\\make_manifest.py
  venv\\Scripts\\python.exe scripts\\make_manifest.py --data-root data/processed

产物 (默认写在仓库根):
  data/dataset_manifest.json  数据集条目清单 + 稳定摘要 + dataset_version
  data/model_manifest.json    data/weights/*.pt 的权威字段(SHA256/字节数) +
                              非权威 mtime(informational) + 预留 training/eval
  environment.lock            python 版本 + 平台 + pip freeze 全量输出

权威 / 非权威 (审计第 7 条: 干净克隆上的发布流水线必须能跑):
  权威   = 内容指纹(SHA256 + 字节数)、数据集摘要与 dataset_version、声明的协议;
  非权威 = generated_at、mtime_ns/mtime_utc(权重从受控仓库下载/拷贝/git checkout
           后必然改变, 因此只放进 informational, **不参与一致性校验**)、绝对路径、
           平台串、补丁版本、pip freeze 全量行。
  校验方见 scripts/verify_model_manifest.py 等三个校验器里的 IGNORED_KEYS 清单。

摘要算法 (两种语义严格区分, JSON 的 digest.algorithm 字段显式标注):
  content-sha256       单文件: 直接对其字节做 SHA256 —— 真实内容哈希
  content-sha256-tree  目录且总字节 <= 阈值: 按相对路径排序, 依次喂入
                       relpath(UTF-8) + b"\\x00" + 文件字节, 再整体 SHA256 —— 真实内容哈希
  path-size-sha256     目录/文件超过阈值: 仅按 "相对路径 文件大小" 构造清单后 SHA256,
                       是清单指纹而非内容哈希; 内容变了但大小不变时它不会变
"""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DATA_ROOTS = ("data/processed", "data/raw")
DEFAULT_WEIGHTS_DIR = "data/weights"
DEFAULT_THRESHOLD_MB = 200.0
SCHEMA_VERSION = 1
CHUNK = 1 << 20

ALGO_CONTENT = "content-sha256"
ALGO_CONTENT_TREE = "content-sha256-tree"
ALGO_PATH_SIZE = "path-size-sha256"

# 运行期产物: 不是数据集内容, 必须排除。
# 否则 dataset_version 会随每次运行/测试变化(实测 data/processed/logs 有 145 个
# 运行日志 640MB, 每次跑测试都新增), 使版本号无法作为可信锚点。
RUNTIME_ARTIFACT_DIRS = frozenset({"logs", "omnisim", "test_results"})
RUNTIME_ARTIFACT_FILE_SUFFIXES = (".png",)


def runtime_artifact_reason(child: Path):
    """若是运行期产物则返回排除原因, 否则返回 None。"""
    if child.is_dir() and child.name in RUNTIME_ARTIFACT_DIRS:
        return "运行期产物目录(日志/仿真输出/测试结果), 不属于数据集内容"
    if child.is_file() and child.suffix.lower() in RUNTIME_ARTIFACT_FILE_SUFFIXES:
        return "运行期生成的图片(测试/验证产出), 不属于数据集内容"
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_root(cli_value=None) -> Path:
    if cli_value:
        return Path(cli_value).resolve()
    return Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _tree_files(root: Path):
    files = [p for p in root.rglob("*") if p.is_file()]
    files.sort(key=lambda p: p.relative_to(root).as_posix())
    return files


def sha256_tree_content(root: Path, files) -> str:
    """目录内容哈希: relpath\\0 + 文件字节, 按 relpath 排序. 真实内容哈希."""
    h = hashlib.sha256()
    for p in files:
        h.update(p.relative_to(root).as_posix().encode("utf-8"))
        h.update(b"\x00")
        with open(p, "rb") as fh:
            for block in iter(lambda: fh.read(CHUNK), b""):
                h.update(block)
    return h.hexdigest()


def sha256_path_size(root: Path, files) -> str:
    """清单指纹: 只依赖相对路径与文件大小, 不是内容哈希."""
    h = hashlib.sha256()
    for p in files:
        rel = p.relative_to(root).as_posix()
        h.update("{} {}\n".format(rel, p.stat().st_size).encode("utf-8"))
    return h.hexdigest()


def entry_record(abs_path: Path, rel_path: str, threshold_bytes: int) -> dict:
    """一个条目 = 数据根目录下的一个顶层文件或子目录."""
    if abs_path.is_dir():
        files = _tree_files(abs_path)
        root = abs_path
        kind = "dir"
    else:
        files = [abs_path]
        root = abs_path.parent
        kind = "file"
    total_bytes = sum(p.stat().st_size for p in files)
    rec = {"path": rel_path, "type": kind, "files": len(files), "bytes": total_bytes}
    if total_bytes <= threshold_bytes:
        if kind == "file":
            rec["digest"] = {"algorithm": ALGO_CONTENT, "value": sha256_file(abs_path)}
            rec["digest_note"] = "文件字节的 SHA256（真实内容哈希）"
        else:
            rec["digest"] = {
                "algorithm": ALGO_CONTENT_TREE,
                "value": sha256_tree_content(root, files),
            }
            rec["digest_note"] = "目录内容哈希（relpath+字节，真实内容哈希）"
    else:
        rec["digest"] = {
            "algorithm": ALGO_PATH_SIZE,
            "value": sha256_path_size(root, files),
        }
        rec["digest_note"] = "仅相对路径+文件大小的清单指纹，非内容哈希"
    return rec


def build_dataset_manifest(root: Path, data_roots, threshold_mb: float,
                           dataset_version=None) -> dict:
    threshold_bytes = int(threshold_mb * 1024 * 1024)
    roots = []
    for rel_root in data_roots:
        abs_root = (root / rel_root)
        if not abs_root.is_dir():
            roots.append({"path": rel_root, "exists": False, "entries": [],
                          "excluded": [], "excluded_count": 0})
            continue
        entries = []
        excluded = []
        for child in sorted(abs_root.iterdir(), key=lambda p: p.name):
            reason = runtime_artifact_reason(child)
            if reason is not None:
                excluded.append({
                    "path": child.relative_to(root).as_posix(),
                    "reason": reason,
                })
                continue
            entries.append(entry_record(child, child.relative_to(root).as_posix(),
                                        threshold_bytes))
        roots.append({
            "path": rel_root,
            "exists": True,
            "entries": entries,
            "excluded": excluded,
            "excluded_count": len(excluded),
            "files": sum(e["files"] for e in entries),
            "bytes": sum(e["bytes"] for e in entries),
        })
    fp = hashlib.sha256()
    for r in roots:
        for e in r["entries"]:
            fp.update(json.dumps([e["path"], e["type"], e["files"], e["bytes"],
                                  e["digest"]["algorithm"], e["digest"]["value"]],
                                 ensure_ascii=False).encode("utf-8"))
    version = dataset_version or ("dv-" + fp.hexdigest()[:16])
    return {
        "manifest_type": "dataset",
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "generator": "scripts/make_manifest.py",
        "dataset_version": version,
        "dataset_version_source": "explicit" if dataset_version else "derived-from-entries",
        "digest_policy": {
            "size_threshold_bytes": threshold_bytes,
            "size_threshold_mb": threshold_mb,
            "small_entry_algorithm": ALGO_CONTENT_TREE,
            "large_entry_algorithm": ALGO_PATH_SIZE,
            "large_entry_is_content_hash": False,
        },
        "exclusion_policy": {
            "note": "运行期产物不计入 dataset_version, 否则版本号会随每次运行/测试变化",
            "directories": sorted(RUNTIME_ARTIFACT_DIRS),
            "file_suffixes": list(RUNTIME_ARTIFACT_FILE_SUFFIXES),
            "affects_version": False,
        },
        "roots": roots,
    }


#: 重新生成清单时允许"按内容继承"的人工登记字段 (见 model_entry 的保留规则)
PROVENANCE_KEYS = ("training", "eval", "release_candidate",
                   "registered_by", "registered_at", "notes")


def model_entry(path: Path, root: Path, existing: dict = None) -> dict:
    """一个权重条目。权威字段 = path/file/bytes/sha256/training/eval。

    mtime 只写进 ``informational``: 权重的 mtime 会在下载/拷贝/git checkout
    后改变(CI 里是刚下载的), 拿它做判据会让干净克隆上的发布流水线必然失败,
    因此各校验器显式忽略它(见 verify_model_manifest.IGNORED_KEYS)。

    existing: 既有清单里对应的条目; 用于按内容保留人工登记的 provenance。
    """
    st = path.stat()
    digest = sha256_file(path)
    entry = {
        "path": path.relative_to(root).as_posix(),
        "file": path.name,
        "bytes": st.st_size,
        "sha256": digest,
        "training": None,
        "eval": None,
        "informational": {
            "authority": "非权威: 仅供参考, 不参与任何一致性校验",
            "mtime_ns": st.st_mtime_ns,
            "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }
    # provenance 保留规则: 重新生成清单**不得**抹掉人工登记的发布信息, 否则
    # "登记 provenance" 毫无意义(每次 make_manifest 都写回 null)。
    # 但只能按内容继承 —— 权重被替换/重训后 sha256 变化, 却继承旧声明等于伪造
    # provenance, 所以 sha256 不同时显式清空并记录原因。
    if isinstance(existing, dict):
        same_content = (str(existing.get("sha256", "")).lower() == digest.lower())
        if same_content:
            for key in PROVENANCE_KEYS:
                if existing.get(key) is not None:
                    entry[key] = existing[key]
            entry["informational"]["provenance"] = "已从既有清单继承(sha256 未变)"
        elif existing.get("training") or existing.get("eval") or \
                existing.get("release_candidate"):
            entry["informational"]["provenance"] = (
                "已清空: sha256 与既有清单不同(权重内容已变), 旧 provenance 不再适用")
    return entry


def build_model_manifest(root: Path, weights_dir: str, existing_models=None) -> dict:
    abs_dir = root / weights_dir
    # 既有清单的条目索引 (按仓库相对路径与文件名两种键, 便于匹配)
    prior = {}
    for m in (existing_models or []):
        if isinstance(m, dict):
            for key in (m.get("path"), m.get("file")):
                if key:
                    prior[str(key)] = m
    models, ignored = [], []
    if abs_dir.is_dir():
        for p in sorted(abs_dir.iterdir(), key=lambda p: p.name):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if p.name.startswith(".") or p.suffix.lower() != ".pt":
                ignored.append({"path": rel,
                                "reason": "dotfile-placeholder" if p.name.startswith(".")
                                else "not-a-.pt-file"})
                continue
            models.append(model_entry(p, root, prior.get(rel) or prior.get(p.name)))
    return {
        "manifest_type": "model",
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "generator": "scripts/make_manifest.py",
        "weights_dir": weights_dir,
        "weights_dir_exists": abs_dir.is_dir(),
        "digest": {"algorithm": "sha256", "scope": "file-bytes"},
        "authority": {
            "authoritative": ["models[].sha256", "models[].bytes", "models[].path",
                              "models[].release_candidate", "models[].training",
                              "models[].eval"],
            "informational": ["generated_at", "models[].informational",
                              "ignored", "weights_dir_exists", "digest_note"],
            "note": "权威=内容指纹(SHA256+字节数)与 release provenance; "
                    "mtime 只是信息, 下载/拷贝/checkout 后必然改变",
        },
        "ignored": ignored,
        "models": models,
    }


def load_existing_models(out_root: Path):
    """读既有 model_manifest.json 的 models[] —— 用于保留人工登记的 provenance。

    读不到/格式不对时返回空列表(等价旧行为: 全新生成), 绝不因此报错中断。
    """
    path = out_root / "data" / "model_manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    models = data.get("models")
    return models if isinstance(models, list) else []


def pip_freeze() -> tuple:
    cmd = [sys.executable, "-m", "pip", "freeze", "--disable-pip-version-check"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode == 0:
            return proc.stdout, ""
        return "", (proc.stderr or "").strip() or f"exit {proc.returncode}"
    except Exception as exc:  # noqa: BLE001
        fallback = subprocess.run([sys.executable, "-m", "pip", "list", "--format=freeze"],
                                  capture_output=True, text=True)
        return fallback.stdout, f"pip freeze failed: {exc}"


def build_environment_lock() -> str:
    frozen, err = pip_freeze()
    lines = [
        "# environment.lock - generated by scripts/make_manifest.py",
        f"generated_at: {now_iso()}",
        f"python_version: {platform.python_version()}",
        f"python_implementation: {platform.python_implementation()}",
        f"python_executable: {sys.executable}",
        f"platform: {platform.platform()}",
        f"pip_freeze_error: {err}" if err else "pip_freeze_error: none",
        "# --- pip freeze ---",
    ]
    body = frozen.replace("\r\n", "\n").strip("\n")
    if body:
        lines.append(body)
    return "\n".join(lines) + "\n"


def dumps(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成数据集/模型清单与环境锁")
    ap.add_argument("--data-root", action="append", default=None,
                    help="数据根目录(仓库相对, 可重复), 默认 data/processed 与 data/raw")
    ap.add_argument("--weights-dir", default=DEFAULT_WEIGHTS_DIR)
    ap.add_argument("--size-threshold-mb", type=float, default=DEFAULT_THRESHOLD_MB)
    ap.add_argument("--dataset-version", default=None, help="显式数据集版本号")
    ap.add_argument("--repo-root", default=None)
    ap.add_argument("--output-root", default=None,
                    help="产物写入目录(默认=仓库根); 扫描仍以仓库根为准")
    args = ap.parse_args(argv)

    root = repo_root(args.repo_root)
    out_root = Path(args.output_root).resolve() if args.output_root else root
    data_roots = args.data_root or [r for r in DEFAULT_DATA_ROOTS
                                    if (root / r).is_dir()] or [DEFAULT_DATA_ROOTS[0]]

    ds = build_dataset_manifest(root, data_roots, args.size_threshold_mb,
                                args.dataset_version)
    # 关键: 传入既有清单, 让人工登记的 provenance 按内容继承(sha256 未变才继承)
    mm = build_model_manifest(root, args.weights_dir, load_existing_models(out_root))
    lock = build_environment_lock()

    write_text(out_root / "data" / "dataset_manifest.json", dumps(ds))
    write_text(out_root / "data" / "model_manifest.json", dumps(mm))
    write_text(out_root / "environment.lock", lock)

    print("[OK] data/dataset_manifest.json  dataset_version={}".format(
        ds["dataset_version"]))
    for r in ds["roots"]:
        print("     - {}: files={} bytes={}".format(r["path"], r.get("files", 0),
                                                    r.get("bytes", 0)))
    print("[OK] data/model_manifest.json   {} 个权重, {} 个忽略".format(
        len(mm["models"]), len(mm["ignored"])))
    for m in mm["models"]:
        print("     - {} {} bytes sha256={}".format(m["file"], m["bytes"],
                                                    m["sha256"][:16]))
    print("[OK] environment.lock          python={} lines={}".format(
        platform.python_version(), lock.count("\n")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
