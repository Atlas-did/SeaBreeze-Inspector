#!/bin/bash
# =============================================================================
# 固件一键烧入脚本 (Linux/macOS)
# 底层调用 flash_firmware.py，提供便捷入口
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 颜色
GREEN="\033[92m"
CYAN="\033[96m"
RESET="\033[0m"

echo -e "${CYAN}========================================${RESET}"
echo -e "${CYAN}  Arduino Nano CH340 — 一键烧入${RESET}"
echo -e "${CYAN}========================================${RESET}"
echo ""

# 检查Python
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "错误: 未找到Python。请安装Python 3.10+"
    exit 1
fi

# 激活虚拟环境（如果存在）
if [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate" 2>/dev/null || true
fi

# 传递所有参数给Python脚本
cd "$PROJECT_ROOT"
$PYTHON "$SCRIPT_DIR/flash_firmware.py" "$@"
