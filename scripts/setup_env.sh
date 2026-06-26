#!/bin/bash
# =============================================================================
# 一键环境初始化脚本（Linux/macOS）
# 用法: bash scripts/setup_env.sh
# =============================================================================

set -e  # 遇到错误立即退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/.venv"

echo "=========================================="
echo "  海上风电运维无人机-机械臂协同系统"
echo "  开发环境一键初始化"
echo "=========================================="
echo ""

# 1. 检测Python版本
echo "[1/5] 检测Python环境..."
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
else
    echo "错误: 未找到Python。请安装Python 3.10或更高版本。"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo "      检测到Python: $PYTHON_VERSION"

# 检查Python版本 >= 3.10
$PYTHON_CMD -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" || {
    echo "错误: Python版本过低，需要 3.10+，当前 $PYTHON_VERSION"
    exit 1
}

# 2. 创建虚拟环境
echo "[2/5] 创建虚拟环境..."
if [ -d "$VENV_DIR" ]; then
    echo "      检测到已有虚拟环境，跳过创建"
else
    $PYTHON_CMD -m venv "$VENV_DIR"
    echo "      虚拟环境已创建: $VENV_DIR"
fi

# 3. 激活虚拟环境并升级pip
echo "[3/5] 升级pip..."
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    # Windows Git Bash
    source "$VENV_DIR/Scripts/activate"
else
    # Linux/macOS
    source "$VENV_DIR/bin/activate"
fi

python -m pip install --upgrade pip

# 4. 安装依赖
echo "[4/5] 安装项目依赖..."
pip install -r "$PROJECT_ROOT/requirements.txt"

# 5. 验证安装
echo "[5/5] 验证关键依赖..."
python -c "import djitellopy; print(f'      djitellopy: OK')"
python -c "import cv2; print(f'      opencv-python: OK')"
python -c "import yaml; print(f'      pyyaml: OK')"
python -c "import numpy; print(f'      numpy: OK')"
python -c "import pygame; print(f'      pygame: OK')"
python -c "import serial; print(f'      pyserial: OK')"
python -c "from ultralytics import YOLO; print(f'      ultralytics: OK')"

echo ""
echo "=========================================="
echo "  环境初始化完成！"
echo "=========================================="
echo ""
echo "激活虚拟环境命令:"
echo "  Linux/macOS: source .venv/bin/activate"
echo "  Windows:     .venv\\Scripts\\activate"
echo ""
echo "运行仿真模式:"
echo "  python -m backend.simulation.main"
echo ""
