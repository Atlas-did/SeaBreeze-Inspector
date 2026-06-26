@echo off
chcp 65001 >nul
REM =============================================================================
REM 一键运行全部测试（Windows）
REM 用法: 双击运行 或 cmd中执行 scripts\run_tests.bat
REM =============================================================================

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

echo ==========================================
echo   海上风电巡检无人机-机械臂协同系统
echo   全部测试套件（Windows）
echo ==========================================
echo.

cd /d "%PROJECT_ROOT%"

set PASS=0
set FAIL=0

REM 运行每个测试套件
for %%t in (
    test_ekf
    test_controller
    test_arm
    test_trajectory
    test_vision
    test_communication
    test_config
    test_tello_mock
    test_integration
) do (
    echo.
    echo --- %%t ---
    python tests/%%t.py
    if errorlevel 1 (
        echo [FAIL] %%t
        set /a FAIL+=1
    ) else (
        echo [PASS] %%t
        set /a PASS+=1
    )
)

echo.
echo ==========================================
echo   测试完成: PASS=%PASS%, FAIL=%FAIL%
echo ==========================================
pause
