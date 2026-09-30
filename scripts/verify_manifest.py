"""发布校验总入口: 依次调用三个权威校验器并汇总 (P1-5 / 外部审计第 7 条).

三个校验器各自职责单一, 也可独立运行:
  scripts/verify_model_manifest.py    权重内容指纹(SHA256+字节数) + release provenance
  scripts/verify_dataset_manifest.py  数据集内容摘要 + dataset_version 锚点
  scripts/verify_environment.py       声明协议(Python 主次版本范围 + requirements 指纹)

本文件只做编排, 不再"重新生成清单后逐字段比对" —— 那正是审计第 7 条的缺陷:
  * make_manifest 曾把 mtime_ns/mtime_utc 写进模型条目, 而 CI 里的权重是刚
    下载的, mtime 必然不同 → 干净克隆上必然失败;
  * environment.lock 含本机绝对路径 / 平台串 / 补丁版本 → ubuntu+3.11 上必然不同。

权威 = 内容指纹(权重 SHA256+字节数)、数据集摘要、声明的协议与版本范围;
非权威 = generated_at、mtime、informational 子树、绝对路径、平台串、补丁版本、
         pip freeze 全量行与说明性 note/policy 字段(各校验器内 IGNORED_* 有逐项理由)。

用法::
  python scripts/verify_manifest.py [--repo-root .] [--only models|dataset|env]
退出码: 0=三项全部通过; 1=有任一项未通过(逐项打印子校验器退出码与分类)。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_dataset_manifest as vds  # noqa: E402
import verify_environment as venvcheck  # noqa: E402
import verify_model_manifest as vmod  # noqa: E402

CHECKS = (
    ("models", vmod, "模型清单(内容指纹)"),
    ("dataset", vds, "数据集清单(内容摘要)"),
    ("env", venvcheck, "环境协议(声明范围+requirements 指纹)"),
)

# 子校验器退出码语义(各脚本 docstring 有完整定义)。
CLASS = {0: "通过", 1: "不一致", 2: "清单缺失(环境未提供)", 3: "数据不可用(环境未提供)"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="发布校验总入口")
    ap.add_argument("--repo-root", default=None)
    ap.add_argument("--only", choices=[name for name, _, _ in CHECKS], default=None)
    args = ap.parse_args(argv)

    root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    print("[INFO] 校验仓库: {}".format(root))

    codes = {}
    for name, module, label in CHECKS:
        if args.only and name != args.only:
            continue
        print("\n=== {}: {} ===".format(name, label))
        codes[name] = module.main(["--root", str(root)])

    print("\n[SUMMARY] " + "  ".join(
        "{}={}({})".format(name, code, CLASS.get(code, "未知"))
        for name, code in codes.items()))
    failed = [name for name, code in codes.items() if code != 0]
    if failed:
        print("[FAIL] 未全部通过: {}".format(", ".join(failed)))
        return 1
    print("[OK] 全部通过: 权重内容指纹 / 数据集摘要 / 环境协议")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
