"""`scripts/annotate_pytest_failures.py` 的回归（审计 D10 可观测性）。

背景：CI 的 Tests 步骤**日志**需要登录才能读，但 **check-run 注解是公开可读的**。
该脚本把 JUnit XML 的失败项打成 `::error ...` 注解，使"看不到日志"也能定位失败用例。
这里锁死它的解析与输出格式。
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "annotate_pytest_failures.py"

SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="3" failures="1" errors="1">
<testcase classname="tests.test_runtime" name="test_takeoff_reaches_hover">
  <failure message="AssertionError: assert 'IDLE' == 'HOVERING'">trace</failure>
</testcase>
<testcase classname="tests.test_rc_uplink_timeout" name="test_new_arrival">
  <error message="RuntimeError: boom">trace</error>
</testcase>
<testcase classname="tests.test_fidelity_wiring" name="test_ok"/>
</testsuite></testsuites>
"""


def _run(tmp_path, xml_text=SAMPLE):
    report = tmp_path / "report.xml"
    report.write_text(xml_text, encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPT), str(report)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc


def test_emits_public_annotations_for_failures_and_errors(tmp_path):
    proc = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    # 失败与 error 都要被抓到, 且带 repo 相对文件路径(注解 file= 需要)
    assert "::error file=tests/test_runtime.py,title=pytest::test_takeoff_reaches_hover" in out
    assert "::error file=tests/test_rc_uplink_timeout.py,title=pytest::test_new_arrival" in out
    # 通过的用例不得出现
    assert "test_ok" not in out
    # 首行错误信息要带出来(否则注解没有诊断价值)
    assert "assert 'IDLE' == 'HOVERING'" in out


def test_missing_report_is_a_warning_not_a_crash(tmp_path):
    proc = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "nope.xml")],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    assert "::warning::" in proc.stdout


def test_all_green_report_emits_notice(tmp_path):
    xml = SAMPLE.replace('<failure message="AssertionError: assert \'IDLE\' == \'HOVERING\'">trace</failure>', "")
    xml = xml.replace('<error message="RuntimeError: boom">trace</error>', "")
    proc = _run(tmp_path, xml)
    assert proc.returncode == 0, proc.stderr
    assert "::notice::" in proc.stdout


def test_malformed_report_is_a_warning_not_a_crash(tmp_path):
    """测试步骤被超时/取消时 pytest 可能留下**残缺 XML** —— 注解步骤不得二次失败。

    （run #6 的 windows 腿就是这种情况: 注解步骤本身 failed, 把真正原因盖住了。）
    """
    proc = _run(tmp_path, "<testsuites><testsuite><testcase name='x'")
    assert proc.returncode == 0, proc.stderr
    assert "::warning::" in proc.stdout
