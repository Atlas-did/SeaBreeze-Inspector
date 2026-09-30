"""从受控模型仓库按 SHA256 拉取权重（model-release-ci 专用）。

设计要点（审计 Phase 2）:
  * 权重不入 git（.gitignore 排除 ``*.pt``），也不能用 ``.ci-placeholder.pt`` 冒充；
  * 因此发布流水线必须**从受控仓库按清单登记的 SHA256 拉取**，再逐文件校验；
  * 未配置仓库地址 / 下载失败 / 哈希不匹配 —— **一律非 0 退出**（fail-closed）。

用法::

    python scripts/fetch_weights.py --manifest data/model_manifest.json \
        --dest data/weights --base-url "$MODEL_BASE_URL"

支持 ``http(s)://`` 与 ``file://``（后者便于离线自测）。
单个条目可用 ``source_url`` 覆盖 ``base-url``。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_url(entry: dict, base_url):
    """决定某个权重的下载地址: 条目自带 source_url 优先, 否则拼 base_url。"""
    explicit = entry.get("source_url") or entry.get("url")
    if explicit:
        return str(explicit)
    if base_url:
        name = entry.get("file") or Path(str(entry.get("path", ""))).name
        return base_url.rstrip("/") + "/" + str(name)
    return None


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("file://"):
        # file:///D:/... 直接切片会留下前导斜杠 -> Windows 上是非法路径
        # (WinError 123)。必须经 url2pathname 转换。
        local = url2pathname(unquote(urlparse(url).path))
        shutil.copy2(Path(local), dest)
        return
    if "://" not in url:                       # 本地路径（便于离线自测）
        shutil.copy2(Path(url), dest)
        return
    with urllib.request.urlopen(url, timeout=60) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="按 SHA256 拉取并校验模型权重")
    ap.add_argument("--manifest", default="data/model_manifest.json")
    ap.add_argument("--dest", default="data/weights")
    ap.add_argument("--base-url", default=None,
                    help="受控模型仓库根地址; 也可用环境变量 MODEL_BASE_URL")
    args = ap.parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print("[ERR] 模型清单不存在: {}".format(manifest_path))
        return 2
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        print("[ERR] 模型清单无法解析: {} ({})".format(manifest_path, e))
        return 2

    entries = manifest.get("models") or []
    if not entries:
        print("[ERR] 清单里没有任何权重条目: {}".format(manifest_path))
        return 2

    base_url = args.base_url or os.environ.get("MODEL_BASE_URL")
    dest_dir = Path(args.dest)
    failures = []

    for entry in entries:
        name = entry.get("file") or Path(str(entry.get("path", ""))).name or "<unnamed>"
        expected = str(entry.get("sha256") or "").lower()
        url = resolve_url(entry, base_url)
        target = dest_dir / name

        if not url:
            print("[ERR] {}: 未配置模型仓库地址 (--base-url 或 MODEL_BASE_URL)".format(name))
            failures.append(name)
            continue
        if not expected:
            print("[ERR] {}: 清单缺少 sha256, 无法校验 —— 拒绝拉取".format(name))
            failures.append(name)
            continue

        try:
            download(url, target)
        except Exception as e:
            print("[ERR] {}: 下载失败 {} ({})".format(name, url, e))
            failures.append(name)
            continue

        actual = sha256_file(target)
        if actual != expected:
            print("[ERR] {}: SHA256 不匹配 期望={} 实际={}".format(name, expected, actual))
            failures.append(name)
            continue
        print("[OK] {} sha256={} bytes={}".format(name, actual, target.stat().st_size))

    if failures:
        print("[FAIL] {} 个权重未通过校验: {}".format(len(failures), ", ".join(failures)))
        return 1
    print("[OK] 全部 {} 个权重已拉取并通过 SHA256 校验".format(len(entries)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
