"""P1-3b 验收测试: 运行产物不得污染数据集锚点。

背景(本轮新发现):
  `data/processed` 同时装着数据集描述、**运行日志**(实测 145 个 / 640 MB)、
  仿真输出与测试产图 —— 于是 `dataset_manifest` 的 `dataset_version` 每跑一次
  测试就变(140→146 文件), "这份结果用的是哪个数据集"失去可信锚点。

修复:
  * 运行日志改到 `data/logs`(`FlightLogger.DEFAULT_LOG_DIR`);
  * `make_manifest` 显式排除运行期产物(目录 `logs/` `omnisim/` `test_results/`
    与 `*.png`), 在 JSON 里记录 `exclusion_policy` 与逐条原因,
    且排除项**不参与** `dataset_version`。
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.utils.logger import DEFAULT_LOG_DIR  # noqa: E402
from scripts.make_manifest import runtime_artifact_reason  # noqa: E402


def test_logger_default_dir_is_not_inside_dataset_root():
    """运行日志目录必须已移出数据集目录。"""
    p = Path(DEFAULT_LOG_DIR)
    assert p.name == "logs"
    assert "processed" not in p.parts, "运行日志不得写在数据集目录里: {}".format(p)
    assert p.parent.name == "data", "应位于 data/logs, 实际 {}".format(p)


def test_runtime_dirs_are_excluded(tmp_path):
    for name in ("logs", "omnisim", "test_results"):
        d = tmp_path / name
        d.mkdir()
        assert runtime_artifact_reason(d), "{} 应被排除".format(name)


def test_runtime_png_excluded_but_dataset_content_kept(tmp_path):
    """测试产图排除, 但真实数据集内容不得被误排。"""
    png = tmp_path / "rrt_star_path.png"
    png.write_bytes(b"x")
    assert runtime_artifact_reason(png), "测试产图应被排除"

    yaml = tmp_path / "wind_turbine_defect.yaml"
    yaml.write_text("path: x\n", encoding="utf-8")
    assert runtime_artifact_reason(yaml) is None, "数据集描述不得被排除"

    for name in ("train", "val"):
        d = tmp_path / name
        d.mkdir()
        assert runtime_artifact_reason(d) is None, "{} 不得被排除".format(name)


def test_manifest_records_exclusion_policy_and_excludes_artifacts():
    mf = REPO / "data" / "dataset_manifest.json"
    if not mf.exists():
        pytest.skip("dataset_manifest.json 尚未生成")
    data = json.loads(mf.read_text(encoding="utf-8"))

    assert data["exclusion_policy"]["affects_version"] is False
    assert "logs" in data["exclusion_policy"]["directories"]

    proc = next(r for r in data["roots"] if r["path"] == "data/processed")
    paths = [e["path"] for e in proc["entries"]]
    assert not any(p.endswith(".png") for p in paths), paths
    assert not any(p.endswith("/logs") for p in paths), paths
    assert proc["excluded_count"] >= 1, "应记录被排除的运行产物"
    # 真正的内容必须仍在: 数据集描述 yaml
    assert any(p.endswith("wind_turbine_defect.yaml") for p in paths), paths
