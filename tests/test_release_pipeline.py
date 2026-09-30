"""Phase 2 验收: 发布流水线的闸门（离线可跑，不需要网络）。

审计要点:
  * 权重被 ``.gitignore`` 排除（``*.pt``）→ 干净克隆里没有真实权重；
  * 此前 CI 依赖 ``.ci-placeholder.pt`` 才能"通过" = **假通过**；
    收紧成过滤占位文件后，干净克隆又会整体失败（测试阶段根本到不了）；
  * 正解 = 拆两条流水线:
      code-ci          不需要权重（--no-weights）;
      model-release-ci 从受控仓库按 SHA256 拉取后再验证。
本文件把这两条口径与两个新脚本的 fail-closed 行为锁住。
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WF = REPO / ".github" / "workflows"
SCRIPTS = REPO / "scripts"


def _run(script, *args):
    """在受控编码下运行脚本。

    子进程默认用 Windows 控制台编码(GBK)写 stdout, 若按 UTF-8 解码会变成
    替换字符, 断言中文提示就会假失败 —— 所以显式要求 UTF-8 输出。
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env)


# ---------- 流水线拆分口径 ----------

def test_single_workflow_is_replaced_by_two():
    assert not (WF / "test.yml").exists(), \
        "旧的单条流水线应已被 code-ci / model-release-ci 取代"
    assert (WF / "code-ci.yml").is_file()
    assert (WF / "model-release-ci.yml").is_file()


def test_code_ci_never_requires_weights():
    text = (WF / "code-ci.yml").read_text(encoding="utf-8")
    assert "check_deps.py --ci --no-weights" in text
    # 任何"要求权重"的依赖检查都不允许出现在代码流水线里
    for line in text.splitlines():
        if "check_deps.py --ci" in line:
            assert "--no-weights" in line, line


def test_model_release_ci_fetches_pinned_weights_and_requires_them():
    text = (WF / "model-release-ci.yml").read_text(encoding="utf-8")
    assert "fetch_weights.py" in text, "必须从受控仓库拉取权重"
    assert "verify_manifest.py" in text, "必须校验清单"
    assert "check_deployment_config.py" in text, "必须校验部署配置指向的权重"
    assert "MODEL_BASE_URL" in text, "仓库地址必须来自配置"
    assert "check_deps.py --ci" in text and "--no-weights" not in text, \
        "发布流水线必须真的要求权重"


# ---------- fetch_weights.py 的 fail-closed ----------

def test_fetch_weights_fails_without_registry(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps({"models": [{"file": "a.pt", "sha256": "0" * 64}]}),
        encoding="utf-8")
    proc = _run("fetch_weights.py", "--manifest", str(manifest),
                "--dest", str(tmp_path / "dest"))
    assert proc.returncode != 0, "未配置仓库地址时不得成功"
    assert "未配置模型仓库地址" in proc.stdout


def test_fetch_weights_fails_when_sha256_missing(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"models": [{"file": "a.pt"}]}), encoding="utf-8")
    proc = _run("fetch_weights.py", "--manifest", str(manifest),
                "--dest", str(tmp_path / "dest"),
                "--base-url", tmp_path.as_uri())
    assert proc.returncode != 0
    assert "缺少 sha256" in proc.stdout


def test_fetch_weights_downloads_and_verifies(tmp_path):
    payload = b"not-a-real-model-but-bytes-are-what-matters"
    src = tmp_path / "a.pt"
    src.write_bytes(payload)
    good = hashlib.sha256(payload).hexdigest()
    manifest = tmp_path / "m.json"
    dest = tmp_path / "dest"

    manifest.write_text(
        json.dumps({"models": [{"file": "a.pt", "sha256": good}]}), encoding="utf-8")
    ok = _run("fetch_weights.py", "--manifest", str(manifest),
              "--dest", str(dest), "--base-url", tmp_path.as_uri())
    assert ok.returncode == 0, ok.stdout
    assert (dest / "a.pt").read_bytes() == payload

    # 哈希不匹配 -> 必须失败
    manifest.write_text(
        json.dumps({"models": [{"file": "a.pt", "sha256": "0" * 64}]}), encoding="utf-8")
    bad = _run("fetch_weights.py", "--manifest", str(manifest),
               "--dest", str(tmp_path / "dest2"), "--base-url", tmp_path.as_uri())
    assert bad.returncode != 0
    assert "SHA256 不匹配" in bad.stdout


# ---------- 部署配置闸门 ----------

def _fake_repo(tmp_path, weight_name, manifest_entry):
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "weights").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "yolo_config.yaml").write_text(
        "model:\n  weights_path: data/weights/{}\n".format(weight_name),
        encoding="utf-8")
    payload = b"deployed-weights"
    (tmp_path / "data" / "weights" / weight_name).write_bytes(payload)
    models = []
    if manifest_entry:
        models.append({"file": weight_name, "sha256": manifest_entry(payload)})
    (tmp_path / "data" / "model_manifest.json").write_text(
        json.dumps({"models": models}), encoding="utf-8")
    return payload


def test_deployment_gate_passes_when_registered_and_matching(tmp_path):
    sha = lambda p: hashlib.sha256(p).hexdigest()  # noqa: E731
    _fake_repo(tmp_path, "seabreeze_test.pt", sha)
    proc = _run("check_deployment_config.py", "--root", str(tmp_path))
    assert proc.returncode == 0, proc.stdout


def test_deployment_gate_rejects_unregistered_weight(tmp_path):
    _fake_repo(tmp_path, "seabreeze_test.pt", None)      # 清单里没有该权重
    proc = _run("check_deployment_config.py", "--root", str(tmp_path))
    assert proc.returncode != 0
    assert "未在 model_manifest.json 登记" in proc.stdout


def test_deployment_gate_rejects_hash_mismatch(tmp_path):
    _fake_repo(tmp_path, "seabreeze_test.pt", lambda p: "0" * 64)
    proc = _run("check_deployment_config.py", "--root", str(tmp_path))
    assert proc.returncode != 0
    assert "SHA256 与清单不一致" in proc.stdout


# ---------- lint 门禁（Phase 2 收尾） ----------

def test_code_ci_lint_is_blocking_not_report_only():
    """审计的原始批评: CI 的 lint 用 report-only 开关, 质量问题不会阻断合入。

    注意: 只检查**命令行**, 不检查注释 —— 注释里可以(也应该)说明这个开关被去掉了。
    """
    text = (WF / "code-ci.yml").read_text(encoding="utf-8")
    assert "flake8" in text, "code-ci 必须包含 lint 步骤"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue                      # 注释允许提及历史开关
        if "flake8" in stripped and "--exit-zero" in stripped:
            pytest.fail("lint 仍是 report-only, 不会阻断合入: " + stripped)


def test_backend_and_scripts_are_lint_clean():
    """把 flake8 = 0 变成测试守着 —— 否则 lint 债会重新长回来。

    tests/ 额外忽略 E402: 测试必须先 `sys.path.insert(...)` 才能 import backend.*,
    这是设计使然, 不是坏味道。
    """
    probe = subprocess.run([sys.executable, "-m", "flake8", "--version"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("flake8 未安装")
    targets = (("backend", "E501,W503"),
               ("scripts", "E501,W503"),
               ("tests", "E501,W503,E402"))
    for target, ignore in targets:
        proc = subprocess.run(
            [sys.executable, "-m", "flake8", target, "--count",
             "--max-line-length=120", "--extend-ignore=" + ignore],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(REPO))
        assert proc.returncode == 0, "{} 存在 lint 问题:\n{}".format(
            target, proc.stdout[-2000:])


# ---------- 审计第 7 条: 干净克隆上的发布流水线可运行性 ----------
# 缺陷: verify_manifest 曾"重新生成清单后逐字段比对"(只忽略 generated_at),
# 而 make_manifest 把 mtime_ns/mtime_utc 写进条目 —— CI 里的权重是刚下载的,
# mtime 必然不同; environment.lock 又含本机绝对路径/平台串/补丁版本。
# 现在权威 = 内容指纹(SHA256+字节数), mtime/路径/平台/补丁号一律非权威。

def _write_model_repo(root, entries, weights):
    """在 tmp 目录造一份最小仓库: data/model_manifest.json + data/weights/*。"""
    (root / "data" / "weights").mkdir(parents=True, exist_ok=True)
    for name, payload in weights.items():
        (root / "data" / "weights" / name).write_bytes(payload)
    (root / "data" / "model_manifest.json").write_text(
        json.dumps({"manifest_type": "model", "schema_version": 1,
                    "generated_at": "2026-01-01T00:00:00Z",
                    "weights_dir": "data/weights", "models": entries}),
        encoding="utf-8")


def _model_entry(name, payload, **extra):
    entry = {"path": "data/weights/" + name, "file": name, "bytes": len(payload),
             "sha256": hashlib.sha256(payload).hexdigest()}
    entry.update(extra)
    return entry


def test_clean_clone_verification_ignores_mtime(tmp_path):
    """干净克隆模拟: mtime 被改写(下载/checkout)后校验仍必须返回 0。"""
    payload = b"weights-bytes"
    _write_model_repo(tmp_path, [_model_entry(
        "a.pt", payload, mtime_ns=1, mtime_utc="2000-01-01T00:00:00Z",
        training=None, eval=None)], {"a.pt": payload})
    weight = tmp_path / "data" / "weights" / "a.pt"
    os.utime(weight, (0, 0))
    assert int(weight.stat().st_mtime) != 1, "前置条件: mtime 必须已被改动"

    proc = _run("verify_model_manifest.py", "--root", str(tmp_path))
    assert proc.returncode == 0, proc.stdout


def test_model_verifier_rejects_sha256_mismatch(tmp_path):
    payload = b"weights-bytes"
    entry = _model_entry("a.pt", payload)
    entry["sha256"] = "0" * 64
    _write_model_repo(tmp_path, [entry], {"a.pt": payload})
    proc = _run("verify_model_manifest.py", "--root", str(tmp_path))
    assert proc.returncode == 1
    assert "SHA256 不匹配" in proc.stdout


def test_model_verifier_rejects_bytes_and_missing_file(tmp_path):
    payload = b"0123456789"
    entry = _model_entry("a.pt", payload)
    entry["bytes"] = len(payload) + 1
    _write_model_repo(tmp_path, [entry], {"a.pt": payload})
    proc = _run("verify_model_manifest.py", "--root", str(tmp_path))
    assert proc.returncode == 1 and "字节数不匹配" in proc.stdout

    missing = _model_entry("b.pt", payload)
    _write_model_repo(tmp_path, [missing], {"a.pt": payload})
    proc = _run("verify_model_manifest.py", "--root", str(tmp_path))
    assert proc.returncode == 1 and "权重文件不存在" in proc.stdout


# 完整 provenance: 数据集版本 / 模型系列 / 输入尺寸 / epoch / ID 指标 / OOD 指标。
COMPLETE_PROVENANCE = {
    "training": {"dataset_version": "dv-b1b73e88f59e51c1", "model_series": "seabreeze-v3",
                 "input_size": [640, 640], "epochs": 100},
    "eval": {"id_metric": "mAP50", "id_value": 0.83, "ood_metric": "mAP50-ood",
             "ood_value": 0.61},
}


def test_release_candidate_requires_full_provenance(tmp_path):
    """想发版就得先登记来源: release_candidate=true 但 provenance 为空 -> 失败。"""
    payload = b"w"
    entry = _model_entry("a.pt", payload, release_candidate=True)
    _write_model_repo(tmp_path, [entry], {"a.pt": payload})
    proc = _run("verify_model_manifest.py", "--root", str(tmp_path))
    assert proc.returncode == 1, proc.stdout
    assert "provenance" in proc.stdout

    partial = _model_entry("a.pt", payload, release_candidate=True,
                           training=dict(COMPLETE_PROVENANCE["training"], epochs=None),
                           eval=COMPLETE_PROVENANCE["eval"])
    _write_model_repo(tmp_path, [partial], {"a.pt": payload})
    proc = _run("verify_model_manifest.py", "--root", str(tmp_path))
    assert proc.returncode == 1 and "epochs" in proc.stdout


def test_release_candidate_with_complete_provenance_passes(tmp_path):
    payload = b"w"
    entry = _model_entry("a.pt", payload, release_candidate=True, **COMPLETE_PROVENANCE)
    _write_model_repo(tmp_path, [entry], {"a.pt": payload})
    proc = _run("verify_model_manifest.py", "--root", str(tmp_path))
    assert proc.returncode == 0, proc.stdout


def _fake_env_repo(root, lock_text):
    """假仓库: 需求文件 + 一份 environment.lock。"""
    (root / "requirements.txt").write_text("numpy>=1.26.0\n", encoding="utf-8")
    (root / "requirements-dev.txt").write_text("pytest>=7.4.0\n", encoding="utf-8")
    (root / "environment.lock").write_text(lock_text, encoding="utf-8")


def _lock(python_version, executable, platform_line):
    return ("# environment.lock - 本地生成\n"
            "generated_at: 2026-01-01T00:00:00Z\n"
            "python_version: {}\n"
            "python_implementation: CPython\n"
            "python_executable: {}\n"
            "platform: {}\n"
            "pip_freeze_error: none\n"
            "# --- pip freeze ---\n"
            "numpy==1.26.4\n").format(python_version, executable, platform_line)


def test_environment_ignores_paths_platform_and_patch_version(tmp_path):
    """本机绝对路径 / 平台串 / 补丁号全变 -> 协议级校验仍必须通过。"""
    variants = [
        _lock("3.11.9", r"D:\SeaBreeze Inspector\venv\Scripts\python.exe",
              "Windows-11-10.0.26200-SP0"),
        _lock("3.12.13", "/home/runner/work/repo/venv/bin/python",
              "Linux-6.5.0-1025-azure-x86_64-with-glibc2.35"),
        _lock("3.10.14", "/opt/hostedtoolcache/Python/3.10.14/x64/bin/python",
              "macOS-14.5-arm64-arm-64bit"),
    ]
    for i, text in enumerate(variants):
        case = tmp_path / "case{}".format(i)
        case.mkdir()
        _fake_env_repo(case, text)
        proc = _run("verify_environment.py", "--root", str(case))
        assert proc.returncode == 0, proc.stdout


def test_environment_is_sensitive_to_declared_python_major_minor(tmp_path):
    _fake_env_repo(tmp_path, _lock("3.9.7", "/usr/bin/python3", "Linux-6.1-x86_64"))
    proc = _run("verify_environment.py", "--root", str(tmp_path))
    assert proc.returncode == 1, proc.stdout
    assert "越界" in proc.stdout


def _dataset_repo(root, payload):
    processed = root / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "a.bin").write_bytes(payload)
    entry = {"path": "data/processed/a.bin", "type": "file", "files": 1,
             "bytes": len(payload),
             "digest": {"algorithm": "content-sha256",
                        "value": hashlib.sha256(payload).hexdigest()}}
    (root / "data" / "dataset_manifest.json").write_text(json.dumps({
        "manifest_type": "dataset", "schema_version": 1,
        "generated_at": "2026-01-01T00:00:00Z",
        "dataset_version": "dv-test", "dataset_version_source": "explicit",
        "digest_policy": {"size_threshold_mb": 200.0},
        "roots": [{"path": "data/processed", "exists": True, "entries": [entry]}]}),
        encoding="utf-8")


def test_dataset_verifier_passes_on_matching_content(tmp_path):
    _dataset_repo(tmp_path, b"abc")
    proc = _run("verify_dataset_manifest.py", "--root", str(tmp_path))
    assert proc.returncode == 0, proc.stdout


def test_dataset_verifier_detects_same_size_content_change(tmp_path):
    _dataset_repo(tmp_path, b"abc")
    (tmp_path / "data" / "processed" / "a.bin").write_bytes(b"abd")  # 同大小, 内容变
    proc = _run("verify_dataset_manifest.py", "--root", str(tmp_path))
    assert proc.returncode == 1, proc.stdout
    assert "digest" in proc.stdout


def test_dataset_verifier_missing_dataset_is_not_a_mismatch(tmp_path):
    """数据集目录缺失 = "跑不了"(3), 清单缺失 = "没清单"(2); 都不是"对不上"(1)。"""
    _dataset_repo(tmp_path, b"abc")
    (tmp_path / "data" / "processed" / "a.bin").unlink()
    (tmp_path / "data" / "processed").rmdir()
    proc = _run("verify_dataset_manifest.py", "--root", str(tmp_path))
    assert proc.returncode == 3, proc.stdout
    assert "数据集目录不存在" in proc.stdout

    empty = tmp_path / "empty"
    empty.mkdir()
    proc = _run("verify_dataset_manifest.py", "--root", str(empty))
    assert proc.returncode == 2, proc.stdout
    assert "清单不存在" in proc.stdout


# ---------- 总入口的编排契约 ----------

def test_total_entry_orchestrates_verifiers_and_summarizes(tmp_path):
    proc = _run("verify_manifest.py", "--repo-root", str(tmp_path))
    assert proc.returncode == 1, proc.stdout
    assert "[SUMMARY]" in proc.stdout
    assert "未全部通过" in proc.stdout

    only = _run("verify_manifest.py", "--repo-root", str(tmp_path), "--only", "models")
    assert "dataset=" not in only.stdout
    assert "models=2" in only.stdout, only.stdout


def test_workflows_are_parseable_yaml():
    """CI 文件必须先是合法 YAML —— 例如 name 里裸写冒号会让整条流水线无法加载。"""
    yaml = pytest.importorskip("yaml")
    for name in ("code-ci.yml", "model-release-ci.yml"):
        yaml.safe_load((WF / name).read_text(encoding="utf-8"))


def test_code_ci_runs_protocol_check_but_no_data_or_weight_checks():
    text = (WF / "code-ci.yml").read_text(encoding="utf-8")
    assert "verify_environment.py" in text
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        assert "verify_model_manifest.py" not in line, line
        assert "verify_dataset_manifest.py" not in line, line


def test_model_release_ci_fetches_then_verifies_content_fingerprint():
    text = (WF / "model-release-ci.yml").read_text(encoding="utf-8")
    assert "verify_model_manifest.py" in text, "必须按内容指纹校验模型清单"
    # 只看真正会执行的命令行: 注释里可以(也应该)解释为什么忽略 mtime。
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("#")]
    commands = "\n".join(lines)
    order = [commands.index(token) for token in (
        "fetch_weights.py", "verify_model_manifest.py", "check_deps.py --ci",
        "check_deployment_config.py", "tests/test_vision.py")]
    assert order == sorted(order), order
    for line in lines:
        assert "mtime" not in line, line

# ---------- provenance 持久性 (审计风险: 重新生成会抹掉手填的 provenance) ----------


def _seed_weight_repo(tmp_path, payload=b"CANDIDATE-WEIGHT"):
    (tmp_path / "data" / "weights").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "weights" / "cand.pt").write_bytes(payload)
    return tmp_path / "data" / "model_manifest.json"


def _regen(tmp_path):
    return _run("make_manifest.py", "--repo-root", str(tmp_path),
                "--weights-dir", "data/weights")


def test_make_manifest_preserves_registered_provenance(tmp_path):
    """重新生成清单不得抹掉人工登记的 provenance, 否则"登记"毫无意义。"""
    man = _seed_weight_repo(tmp_path)
    assert _regen(tmp_path).returncode == 0
    data = json.loads(man.read_text(encoding="utf-8"))
    assert data["models"][0]["training"] is None      # 首次生成为空(未登记)

    data["models"][0]["training"] = {"dataset_version": "dv-x", "epochs": 200}
    data["models"][0]["eval"] = {"id_metric": "mAP50", "id_value": 0.58}
    data["models"][0]["release_candidate"] = True
    man.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    assert _regen(tmp_path).returncode == 0           # 重新生成(权重内容未变)
    kept = json.loads(man.read_text(encoding="utf-8"))["models"][0]
    assert kept["training"]["epochs"] == 200, "手填 provenance 被抹掉了"
    assert kept["release_candidate"] is True
    assert "继承" in kept["informational"].get("provenance", "")


def test_make_manifest_clears_provenance_when_weight_content_changes(tmp_path):
    """权重内容变了(sha256 不同)时**不得**继承旧 provenance —— 那等于伪造声明。"""
    man = _seed_weight_repo(tmp_path)
    assert _regen(tmp_path).returncode == 0
    data = json.loads(man.read_text(encoding="utf-8"))
    data["models"][0]["training"] = {"dataset_version": "dv-x", "epochs": 200}
    data["models"][0]["release_candidate"] = True
    sha_before = data["models"][0]["sha256"]
    man.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # 换掉权重内容 -> sha256 改变
    (tmp_path / "data" / "weights" / "cand.pt").write_bytes(b"DIFFERENT-WEIGHT-v2")
    assert _regen(tmp_path).returncode == 0
    changed = json.loads(man.read_text(encoding="utf-8"))["models"][0]
    assert changed["sha256"] != sha_before
    assert changed["training"] is None, "权重已变却继承了旧 provenance(伪造风险)"
    assert changed.get("release_candidate") is None
    assert "清空" in changed["informational"].get("provenance", "")
