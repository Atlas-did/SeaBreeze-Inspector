"""环境协议校验器 —— 只认"声明的协议", 不认本机路径/平台/补丁号.

权威判据 (只有这些能让本脚本非 0 退出):
  1. 解释器的 major.minor 落在声明范围 (DECLARED_PYTHON_REQUIRES, 可被
     --python-requires 或 environment.lock 的 python_requires 覆盖);
  2. environment.lock 若登记了 python_version, 其 major.minor 也必须在范围内;
  3. environment.lock 若登记了 requirements_sha256, 必须与当前
     requirements.txt + requirements-dev.txt 的内容指纹一致(依赖漂移检测);
  4. requirements.txt / requirements-dev.txt 必须存在(协议无法评估即失败)。

非权威 (IGNORED_FIELDS, 一律不参与判定, 逐项给出理由):
  python_executable      本机绝对路径, 干净克隆/CI/他人机器上必然不同;
  platform               Windows-... / Linux-... 串, 跨平台矩阵必然不同;
  python_implementation  CPython/PyPy 属实现细节, 协议只约束版本范围;
  python_version 的补丁号 3.11.9 与 3.11.13 不是协议差异(只比 major.minor);
  generated_at           生成时间戳;
  pip_freeze 全量行       "装了哪些包"的现场快照, 因机器而异;
  pip_freeze_error       信息性诊断。

没有 environment.lock 时(干净克隆、未生成锁)仍必须能跑:
只校验解释器版本与需求文件存在性, 退出 0。
退出码: 0=通过; 1=违反声明协议。
"""
import argparse
import hashlib
import platform
from pathlib import Path

# 声明协议: 允许的 Python 主次版本范围(与 code-ci 矩阵 3.11/3.12 及本机 3.14 兼容)。
DECLARED_PYTHON_REQUIRES = ">=3.10,<3.15"
REQUIREMENTS_FILES = ("requirements.txt", "requirements-dev.txt")

IGNORED_FIELDS = {
    "python_executable": "本机绝对路径, 干净克隆/CI 上必然不同",
    "platform": "平台串, 跨平台矩阵必然不同",
    "python_implementation": "实现细节, 协议只约束版本范围",
    "python_version.patch": "补丁号不是协议差异(只比 major.minor)",
    "generated_at": "生成时间戳",
    "pip_freeze": "现场依赖快照, 因机器而异",
    "pip_freeze_error": "信息性诊断",
}


def major_minor(text: str):
    """'3.11.9' -> (3, 11); 解析不出返回 None。"""
    parts = str(text).strip().split(".")
    try:
        return (int(parts[0]), int(parts[1]))
    except (IndexError, ValueError):
        return None


def parse_requires(spec: str):
    """'>=3.10,<3.15' -> [('>=', (3, 10)), ('<', (3, 15))]。"""
    constraints = []
    for token in str(spec).replace(" ", "").split(","):
        if not token:
            continue
        for op in (">=", "<=", "==", ">", "<"):
            if token.startswith(op):
                version = major_minor(token[len(op):])
                if version is None:
                    raise ValueError("无法解析版本约束: {!r}".format(token))
                constraints.append((op, version))
                break
        else:
            raise ValueError("无法解析版本约束: {!r}".format(token))
    return constraints


def satisfies(version, constraints) -> bool:
    for op, bound in constraints:
        if op == ">=" and not version >= bound:
            return False
        if op == ">" and not version > bound:
            return False
        if op == "<=" and not version <= bound:
            return False
        if op == "<" and not version < bound:
            return False
        if op == "==" and version != bound:
            return False
    return True


def parse_lock(path: Path) -> dict:
    """读取 environment.lock 的头部键值(其余行——含 pip freeze——只当信息)。"""
    fields = {}
    for line in path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n"):
        if line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def requirements_fingerprint(root: Path):
    """requirements*.txt 的内容指纹(统一换行, 跨平台稳定)。"""
    h = hashlib.sha256()
    for rel in REQUIREMENTS_FILES:
        path = root / rel
        if not path.is_file():
            return None, rel
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(path.read_bytes().replace(b"\r\n", b"\n"))
        h.update(b"\x00")
    return h.hexdigest(), None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="校验声明的环境协议")
    ap.add_argument("--root", default=None)
    ap.add_argument("--lock", default=None)
    ap.add_argument("--python-requires", default=None,
                    help="覆盖声明范围, 例如 '>=3.11,<3.13'")
    ap.add_argument("--print-fingerprint", action="store_true",
                    help="打印 requirements 内容指纹(用于登记到 environment.lock)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    lock_path = Path(args.lock) if args.lock else root / "environment.lock"
    lock = parse_lock(lock_path) if lock_path.is_file() else None

    spec = args.python_requires or (lock or {}).get("python_requires") or DECLARED_PYTHON_REQUIRES
    try:
        constraints = parse_requires(spec)
    except ValueError as exc:
        print("[FAIL] 声明的 Python 范围无法解析: {}".format(exc))
        return 1

    problems = []
    running = major_minor(platform.python_version())
    if running is None or not satisfies(running, constraints):
        problems.append("解释器 Python {} 越界: 声明范围 {}{}".format(
            platform.python_version(), spec,
            "" if lock else " (无 environment.lock, 用内置声明)"))

    if lock is None:
        print("[INFO] 未发现 environment.lock (干净克隆): 只校验声明协议与解释器版本")
    elif lock.get("python_version"):
        recorded = major_minor(lock["python_version"])
        if recorded is None or not satisfies(recorded, constraints):
            problems.append("environment.lock 登记 python_version={} 越界: 声明范围 {}".format(
                lock["python_version"], spec))
    else:
        print("[INFO] environment.lock 未登记 python_version(非权威字段, 不参与判定)")

    fingerprint, missing = requirements_fingerprint(root)
    if fingerprint is None:
        problems.append("需求文件缺失: {} —— 无法评估依赖协议".format(missing))
    else:
        if args.print_fingerprint:
            print("[INFO] requirements_sha256 = {}".format(fingerprint))
        declared = (lock or {}).get("requirements_sha256")
        if declared and declared.lower() != fingerprint:
            problems.append("requirements 指纹不一致: lock={} 实际={}".format(
                declared.lower(), fingerprint))
        elif declared:
            print("[INFO] requirements 指纹与 environment.lock 登记一致")
        elif lock is None:
            print("[INFO] 没有 environment.lock: requirements 指纹无处登记, "
                  "本轮只校验解释器版本与需求文件存在性")
        else:
            print("[INFO] environment.lock 未登记 requirements_sha256(旧格式): 已跳过指纹比对")

    if problems:
        print("[FAIL] 环境协议校验失败: {} 条".format(len(problems)))
        for line in problems:
            print("       - {}".format(line))
        return 1

    print("[OK] 环境协议通过: Python 要求 {} (解释器 {})".format(
        spec, platform.python_version()))
    print("[INFO] 已忽略非权威字段: {}".format(", ".join(sorted(IGNORED_FIELDS))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
