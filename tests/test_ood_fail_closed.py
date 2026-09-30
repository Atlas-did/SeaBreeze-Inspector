"""Phase 2 验收: OOD 评估协议必须 fail-closed。

审计要点:
  ``backend/vision/train.py`` 在 OOD 集未提供时会**回退到训练 yaml** —— 于是
  实验记录写着 ``eval_protocol=OOD``，实际评估的却是 ID 验证集。这是最危险的
  一类"假指标"：它不会报错，只会给出一个看起来合法、实则口径错误的数字。

修复后: OOD 协议下缺独立冻结数据集(未配置 / 文件不存在) → 直接失败，
绝不允许回退；ID / none 路径不受影响。
"""

import pytest

from backend.vision.train import (
    OODDataUnavailable,
    resolve_eval_data,
    train,
)

ENV = "SEABREEZE_OOD_DATA"


def test_ood_without_configuration_raises(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    with pytest.raises(OODDataUnavailable):
        resolve_eval_data("train.yaml", "OOD")


def test_ood_with_missing_file_raises(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, str(tmp_path / "nope.yaml"))
    with pytest.raises(OODDataUnavailable):
        resolve_eval_data("train.yaml", "OOD")


def test_ood_with_real_file_returns_it(monkeypatch, tmp_path):
    ood = tmp_path / "ood.yaml"
    ood.write_text("path: ood\n", encoding="utf-8")
    monkeypatch.setenv(ENV, str(ood))
    path, source = resolve_eval_data("train.yaml", "OOD")
    assert path == str(ood)
    assert "explicit" in source, "来源必须显式标注, 不能再出现 fallback 字样"


def test_explicit_argument_overrides_env(monkeypatch, tmp_path):
    env_ood = tmp_path / "env.yaml"
    env_ood.write_text("a: 1\n", encoding="utf-8")
    arg_ood = tmp_path / "arg.yaml"
    arg_ood.write_text("b: 2\n", encoding="utf-8")
    monkeypatch.setenv(ENV, str(env_ood))
    path, _ = resolve_eval_data("train.yaml", "OOD", str(arg_ood))
    assert path == str(arg_ood), "显式参数优先于环境变量"


def test_id_protocol_unaffected(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    path, source = resolve_eval_data("train.yaml", "ID")
    assert path == "train.yaml"
    assert source == "train-yaml-val-split"


def test_no_fallback_label_can_be_produced(monkeypatch):
    """回归守卫: 旧实现会返回 "fallback-train-yaml(OOD集未提供)"，必须消失。"""
    monkeypatch.delenv(ENV, raising=False)
    try:
        _, source = resolve_eval_data("train.yaml", "OOD")
    except OODDataUnavailable:
        return
    pytest.fail("OOD 缺数据时必须失败, 而不是返回 {}", source)


def test_train_fails_closed_when_ood_data_absent(monkeypatch, tmp_path):
    """端到端: OOD 协议 + 无 OOD 数据 → 训练入口直接返回 False。"""
    monkeypatch.delenv(ENV, raising=False)
    data_yaml = tmp_path / "data.yaml"
    data_yaml.write_text("path: data\n", encoding="utf-8")
    assert train(str(data_yaml), epochs=1, eval_protocol="OOD") is False
