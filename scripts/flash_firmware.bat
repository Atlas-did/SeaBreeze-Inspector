@echo off
chcp 65001 >nul
REM =============================================================================
REM 固件一键烧入脚本 (Windows)
REM 底层调用 flash_firmware.py，提供便捷入口
REM 用法: 双击运行 或 cmd中执行 scripts\flash_firmware.bat
REM =============================================================================

echo ========================================
echo   Arduino Nano CH340 — 一键烧入
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python。请安装Python 3.10+并添加到PATH。
    pause
    exit /b 1
)

REM 激活虚拟环境（如果存在）
if exist "%PROJECT_ROOT%\.venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%\.venv\Scripts\activate.bat"
)

REM 传递所有参数给Python脚本
cd /d "%PROJECT_ROOT%"
python "%SCRIPT_DIR%flash_firmware.py" %*
