@echo off
chcp 65001 >nul
REM =============================================================================
REM 一键环境初始化脚本（Windows）
REM 用法: 双击运行 或 cmd中执行 scripts\setup_env.bat
REM =============================================================================

echo ==========================================
echo   海上风电运维无人机-机械臂协同系统
echo   开发环境一键初始化（Windows）
echo ==========================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "VENV_DIR=%PROJECT_ROOT%\.venv"

REM 1. 检测Python
echo [1/5] 检测Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python。请安装Python 3.10+并添加到PATH。
    pause
    exit /b 1
)

for /f "tokens=2" %%a in ('python --version 2^>^&1') do set PYTHON_VERSION=%%a
echo       检测到Python: %PYTHON_VERSION%

REM 2. 创建虚拟环境
echo [2/5] 创建虚拟环境...
if exist "%VENV_DIR%" (
    echo       检测到已有虚拟环境，跳过创建
) else (
    python -m venv "%VENV_DIR%"
    echo       虚拟环境已创建
)

REM 3. 激活虚拟环境并升级pip
echo [3/5] 升级pip...
call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --upgrade pip

REM 4. 安装依赖
echo [4/5] 安装项目依赖...
pip install -r "%PROJECT_ROOT%\requirements.txt"

REM 5. 验证安装
echo [5/5] 验证关键依赖...
python -c "import djitellopy; print('      djitellopy: OK')"
python -c "import cv2; print('      opencv-python: OK')"
python -c "import yaml; print('      pyyaml: OK')"
python -c "import numpy; print('      numpy: OK')"
python -c "import pygame; print('      pygame: OK')"
python -c "import serial; print('      pyserial: OK')"
python -c "from ultralytics import YOLO; print('      ultralytics: OK')"

echo.
echo ==========================================
echo   环境初始化完成！
echo ==========================================
echo.
echo 激活虚拟环境命令:
echo   .venv\Scripts\activate
echo.
pause
