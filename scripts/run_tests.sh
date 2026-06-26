#!/bin/bash
# 一键运行全部测试并生成覆盖率报告

set -e

echo "=========================================="
echo "  海上风电巡检系统 — 测试套件"
echo "=========================================="

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# 检查 pytest
if ! command -v pytest &> /dev/null; then
    echo "[INFO] pytest 未安装, 使用 python -m pytest"
    PYTEST="python -m pytest"
else
    PYTEST="pytest"
fi

# 安装依赖
echo "[1/4] 检查依赖..."
pip install -q pytest pytest-cov matplotlib scipy numpy pygame 2>/dev/null || true

# 运行测试
echo ""
echo "[2/4] 运行单元测试..."
$PYTEST tests/ -v --tb=short \
    --ignore=tests/test_integration.py \
    -q 2>&1 | tail -20

echo ""
echo "[3/4] 运行集成测试..."
python tests/test_integration.py

# 生成覆盖率报告
echo ""
echo "[4/4] 生成覆盖率报告..."
$PYTEST tests/ --cov=backend --cov-report=html --cov-report=term-missing -q 2>/dev/null || echo "[INFO] 覆盖率报告需安装 pytest-cov"

if [ -d "htmlcov" ]; then
    echo "[OK] 覆盖率报告: htmlcov/index.html"
fi

echo ""
echo "=========================================="
echo "  全部测试完成!"
echo "=========================================="
