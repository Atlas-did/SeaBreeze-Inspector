"""把 pytest 的 JUnit XML 失败项转成 GitHub Actions 注解（`::error ...`）。

**为什么需要它**（审计 D10 的可观测性要求）：
CI 的 Tests 步骤**日志**需要登录才能读，但 **check-run 注解是公开可读的**
（`GET /repos/{owner}/{repo}/check-runs/{id}/annotations`）。把失败用例名与首行错误做成注解，
即使拿不到日志也能直接定位失败用例 —— 本轮多次因为看不到用例名而只能靠猜。

用法：
    python scripts/annotate_pytest_failures.py pytest-report.xml
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

#: GitHub 每个步骤的 error 注解有数量上限，超出部分只在日志里列出
MAX_ANNOTATIONS = 10


def collect_failures(xml_path):
    """从 JUnit XML 收集 (文件, 用例名, 首行错误)。"""
    root = ET.parse(str(xml_path)).getroot()
    rows = []
    for case in root.iter("testcase"):
        node = case.find("failure")
        tag = "failure"
        if node is None:
            node = case.find("error")
            tag = "error"
        if node is None:
            continue
        text = (node.get("message") or "").strip()
        first_line = text.splitlines()[0] if text else tag
        classname = case.get("classname", "") or ""
        file_hint = classname.replace(".", "/") + ".py" if classname else "tests"
        rows.append((file_hint, case.get("name", "?"), first_line))
    return rows


def main(argv):
    if len(argv) < 2:
        print("usage: annotate_pytest_failures.py <junit-xml>")
        return 2
    path = Path(argv[1])
    if not path.exists():
        print("::warning::找不到 JUnit 报告 {}（测试可能未跑到写报告就中断）".format(path))
        return 0
    try:
        rows = collect_failures(path)
    except ET.ParseError as exc:
        # 测试步骤被超时/取消时, pytest 可能只留下**残缺 XML** —— 这属于"报告不可用",
        # 不该让注解步骤本身再失败一次(否则真正原因会被二次错误覆盖)。见 run #6 windows 腿。
        print("::warning::JUnit 报告无法解析（{}）：{}".format(exc, path))
        return 0
    if not rows:
        print("::notice::JUnit 报告里没有失败用例")
        return 0
    print("失败用例共 {} 条：".format(len(rows)))
    for file_hint, name, msg in rows:
        print("  - {}::{} — {}".format(file_hint, name, msg[:200]))
    for file_hint, name, msg in rows[:MAX_ANNOTATIONS]:
        print("::error file={},title=pytest::{} — {}".format(file_hint, name, msg[:300]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
