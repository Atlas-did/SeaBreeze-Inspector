#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
Arduino Nano CH340 一键烧入脚本
=============================================================================
功能:
  1. 自动检测 Nano/CH340 所在串口 (Win/Linux/Mac)
  2. 检查并指引安装 arduino-cli (主方案) / Arduino IDE (备用方案)
  3. 自动编译 firmware/servo_controller/servo_controller.ino
  4. 自动上传 (57600波特率, 旧Bootloader)
  5. 上传后验证: 打开串口115200, 发 Q\n, 期待角度回显
  6. 失败自动重试3次, 最后输出详细诊断

技术选型说明(烧入工具):
  主方案: arduino-cli — 命令行工具, 轻量(30MB), 跨平台,
          本脚本已封装所有调用细节, 用户无需手动敲命令。
  备用:   Arduino IDE — 图形界面, 当arduino-cli因网络问题
          无法安装时, 提供手动烧入步骤(见 docs/FLASH_GUIDE.md)。

用法:
  python scripts/flash_firmware.py
  python scripts/flash_firmware.py --port COM3          # 指定串口
  python scripts/flash_firmware.py --bootloader old     # 旧bootloader(默认)
  python scripts/flash_firmware.py --bootloader new     # 新bootloader
  python scripts/flash_firmware.py --skip-verify        # 跳过验证
=============================================================================
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

# =============================================================================
# 依赖检查: pyserial (用于串口检测和验证)
# =============================================================================
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[ERROR] 缺少 pyserial 依赖。请运行: pip install pyserial")
    sys.exit(1)

# =============================================================================
# 常量定义
# =============================================================================

# 项目根目录: 从 scripts/ 向上1层
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 固件路径
FIRMWARE_DIR = PROJECT_ROOT / "firmware" / "servo_controller"
INO_FILE = FIRMWARE_DIR / "servo_controller.ino"

# Board FQBN (Fully Qualified Board Name)
# Nano CH340 克隆版通常使用旧Bootloader, 上传波特率57600
BOARD_FQBN_OLD = "arduino:avr:nano:cpu=atmega328old"   # 旧Bootloader (默认)
BOARD_FQBN_NEW = "arduino:avr:nano:cpu=atmega328"       # 新Bootloader

# 上传波特率
UPLOAD_BAUD_OLD = 57600
UPLOAD_BAUD_NEW = 115200

# 验证串口参数
VERIFY_BAUDRATE = 115200      # 固件内Serial.begin(115200)
VERIFY_TIMEOUT = 3.0          # 串口读取超时(秒)
VERIFY_COMMAND = b"Q\n"       # 发送查询指令
VERIFY_EXPECTED = "A:"         # 期待回显中包含角度前缀

# 重试次数
MAX_RETRIES = 3

# arduino-cli 可执行文件名 (跨平台)
SYSTEM = platform.system()
if SYSTEM == "Windows":
    CLI_EXE = "arduino-cli.exe"
else:
    CLI_EXE = "arduino-cli"

# CH340设备描述关键词 (用于串口自动检测)
CH340_KEYWORDS = ["CH340", "CH340G", "USB-SERIAL CH340", "wch.cn"]


# =============================================================================
# 颜色输出 (跨平台)
# =============================================================================

class Color:
    """ANSI颜色码, Windows下自动启用虚拟终端处理"""

    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    @classmethod
    def init_windows(cls) -> None:
        """Windows下启用ANSI颜色支持"""
        if SYSTEM == "Windows":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except Exception:
                # 不支持颜色时清空所有颜色码
                for attr in dir(cls):
                    if not attr.startswith("_"):
                        setattr(cls, attr, "")


def info(msg: str) -> None:
    print(f"{Color.CYAN}[INFO]{Color.RESET} {msg}")


def ok(msg: str) -> None:
    print(f"{Color.GREEN}[ OK ]{Color.RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{Color.YELLOW}[WARN]{Color.RESET} {msg}")


def error(msg: str) -> None:
    print(f"{Color.RED}[FAIL]{Color.RESET} {msg}")


def step(num: int, title: str) -> None:
    print(f"\n{Color.BOLD}=== 步骤 {num}: {title} ==={Color.RESET}")


# =============================================================================
# 步骤 1: 检测串口
# =============================================================================

def detect_port(preferred: str | None = None) -> str | None:
    """
    自动检测CH340/Nano所在串口。

    参数:
        preferred: 用户指定的串口, 如 "COM3" 或 "/dev/ttyUSB0"

    返回:
        串口设备路径, 未找到返回 None
    """
    if preferred:
        info(f"使用用户指定串口: {preferred}")
        return preferred

    info("正在扫描可用串口...")
    ports = list(serial.tools.list_ports.comports())

    if not ports:
        error("未找到任何串口设备!")
        return None

    # 先尝试匹配CH340关键词
    candidates = []
    for p in ports:
        desc = f"{p.description} {p.manufacturer or ''} {p.hwid}".upper()
        if any(kw.upper() in desc for kw in CH340_KEYWORDS):
            candidates.append(p)

    if candidates:
        if len(candidates) == 1:
            port = candidates[0].device
            ok(f"检测到CH340设备: {port} ({candidates[0].description})")
            return port
        else:
            warn(f"检测到 {len(candidates)} 个CH340设备, 请手动选择:")
            for i, p in enumerate(candidates, 1):
                print(f"  {i}. {p.device} — {p.description}")
            choice = input("请输入序号 (或按Enter使用第一个): ").strip()
            idx = int(choice) - 1 if choice.isdigit() else 0
            port = candidates[idx].device
            ok(f"选择串口: {port}")
            return port

    # 未匹配到CH340, 列出所有可用串口让用户选择
    warn("未自动识别到CH340设备, 可用串口列表:")
    for i, p in enumerate(ports, 1):
        print(f"  {i}. {p.device} — {p.description}")

    choice = input("请输入序号选择串口 (或输入完整路径如 COM3): ").strip()

    # 用户输入了完整路径
    if choice.startswith("/") or choice.startswith("COM") or choice.startswith("/dev/"):
        return choice

    # 用户输入了序号
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(ports):
            return ports[idx].device

    error("无效选择")
    return None


# =============================================================================
# 步骤 2: 检查 arduino-cli
# =============================================================================

def find_arduino_cli() -> Path | None:
    """在PATH中查找arduino-cli可执行文件"""
    cli_path = shutil.which(CLI_EXE)
    if cli_path:
        return Path(cli_path)

    # 额外检查常见安装路径
    extra_paths = []
    if SYSTEM == "Windows":
        extra_paths = [
            Path.home() / "AppData" / "Local" / "Arduino15" / CLI_EXE,
            Path("C:/") / "Program Files" / "Arduino-cli" / CLI_EXE,
        ]
    elif SYSTEM == "Darwin":  # macOS
        extra_paths = [
            Path.home() / "Downloads" / CLI_EXE,
            Path("/usr/local/bin") / CLI_EXE,
        ]
    else:  # Linux
        extra_paths = [
            Path.home() / ".local" / "bin" / CLI_EXE,
            Path("/usr/local/bin") / CLI_EXE,
            Path("/usr/bin") / CLI_EXE,
        ]

    for p in extra_paths:
        if p.exists():
            return p

    return None


def print_cli_install_guide() -> None:
    """输出arduino-cli安装指引"""
    print(f"\n{Color.YELLOW}{'='*60}{Color.RESET}")
    print(f"{Color.BOLD}arduino-cli 未安装 — 安装指引{Color.RESET}")
    print(f"{Color.YELLOW}{'='*60}{Color.RESET}")

    if SYSTEM == "Windows":
        print("""
【Windows 安装方法】

方法1 (推荐) — 手动下载:
  1. 打开浏览器, 访问: https://github.com/arduino/arduino-cli/releases/latest
  2. 下载文件名类似: arduino-cli_1.0.4_Windows_64bit.zip
  3. 解压到任意文件夹 (建议 C:\\arduino-cli\\)
  4. 将该文件夹添加到系统PATH环境变量
  5. 重启命令提示符, 输入 arduino-cli version 验证

方法2 — 用 Scoop 安装 (需先安装Scoop):
  scoop install arduino-cli
""")
    elif SYSTEM == "Darwin":
        print("""
【macOS 安装方法】

方法1 (推荐) — Homebrew:
  brew install arduino-cli

方法2 — 手动下载:
  1. 访问: https://github.com/arduino/arduino-cli/releases/latest
  2. 下载: arduino-cli_1.0.4_macOS_64bit.tar.gz
  3. 解压: tar -xzf arduino-cli_*.tar.gz
  4. 移动: sudo mv arduino-cli /usr/local/bin/
  5. 验证: arduino-cli version
""")
    else:
        print("""
【Linux 安装方法】

方法1 (推荐) — 官方脚本:
  curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
  sudo mv bin/arduino-cli /usr/local/bin/

方法2 — 手动下载:
  1. 访问: https://github.com/arduino/arduino-cli/releases/latest
  2. 下载对应架构的tar.gz (amd64/arm64)
  3. tar -xzf arduino-cli_*.tar.gz
  4. sudo mv arduino-cli /usr/local/bin/

方法3 — Snap:
  sudo snap install arduino-cli
""")

    print("""
安装完成后, 重新运行本脚本:
  python scripts/flash_firmware.py

或者使用备用方案 — Arduino IDE 手动烧入:
  详见 docs/FLASH_GUIDE.md 的"备用方案"章节
""")
    print(f"{Color.YELLOW}{'='*60}{Color.RESET}\n")


# =============================================================================
# 步骤 3: 安装Board Core和库
# =============================================================================

def ensure_board_core(cli: Path) -> bool:
    """确保Arduino AVR核心已安装"""
    info("检查 Arduino AVR Board Core...")

    result = subprocess.run(
        [str(cli), "core", "list"],
        capture_output=True, text=True
    )

    if "arduino:avr" in result.stdout:
        ok("Arduino AVR Core 已安装")
        return True

    warn("Arduino AVR Core 未安装, 正在下载安装...")
    warn("首次安装需要下载约100MB数据, 请耐心等待...")

    # 添加board manager index (包含AVR核心)
    subprocess.run(
        [str(cli), "core", "update-index"],
        capture_output=True
    )

    # 安装AVR核心
    result = subprocess.run(
        [str(cli), "core", "install", "arduino:avr"],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        error(f"AVR Core 安装失败:\n{result.stderr}")
        return False

    ok("Arduino AVR Core 安装完成")
    return True


def ensure_libraries(cli: Path) -> bool:
    """确保所需库已安装"""
    info("检查 Adafruit PWM Servo Driver 库...")

    result = subprocess.run(
        [str(cli), "lib", "list"],
        capture_output=True, text=True
    )

    if "Adafruit PWM Servo Driver" in result.stdout:
        ok("Adafruit PWM Servo Driver 库已安装")
        return True

    warn("库未安装, 正在下载...")

    # 安装Adafruit PWM Servo Driver库
    result = subprocess.run(
        [str(cli), "lib", "install", "Adafruit PWM Servo Driver Library"],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        error(f"库安装失败:\n{result.stderr}")
        return False

    ok("Adafruit PWM Servo Driver 库安装完成")
    return True


# =============================================================================
# 步骤 4: 编译
# =============================================================================

def compile_firmware(cli: Path, fqbn: str) -> bool:
    """
    编译.ino文件。

    参数:
        cli: arduino-cli 路径
        fqbn: Board FQBN (如 arduino:avr:nano:cpu=atmega328old)

    返回:
        编译成功返回True
    """
    step(4, "编译固件")
    info(f"Board: {fqbn}")
    info(f"源码: {INO_FILE}")

    if not INO_FILE.exists():
        error(f"固件文件不存在: {INO_FILE}")
        return False

    # 编译命令
    cmd = [
        str(cli),
        "compile",
        "--fqbn", fqbn,
        "--warnings", "all",
        str(FIRMWARE_DIR)
    ]

    info("开始编译...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        error("编译失败!")
        print(f"\n{Color.RED}--- 编译输出 ---{Color.RESET}")
        print(result.stderr or result.stdout)
        print(f"{Color.RED}----------------{Color.RESET}\n")
        return False

    # 提取二进制大小信息
    for line in result.stdout.split("\n"):
        if "Sketch uses" in line or "Global variables" in line:
            ok(line.strip())

    ok("编译成功")
    return True


# =============================================================================
# 步骤 5: 上传
# =============================================================================

def upload_firmware(cli: Path, fqbn: str, port: str) -> bool:
    """
    上传编译好的固件到Arduino Nano。

    参数:
        cli: arduino-cli 路径
        fqbn: Board FQBN
        port: 串口设备路径

    返回:
        上传成功返回True
    """
    step(5, "上传固件到Nano")
    info(f"串口: {port}")
    info(f"Bootloader: {'旧(57600)' if 'old' in fqbn else '新(115200)'}")

    # 上传命令
    cmd = [
        str(cli),
        "upload",
        "--fqbn", fqbn,
        "--port", port,
        "--verify",            # 上传后回读验证
        str(FIRMWARE_DIR)
    ]

    info("正在上传 (请保持USB连接)...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        error("上传失败!")
        print(f"\n{Color.RED}--- 上传输出 ---{Color.RESET}")
        print(result.stderr or result.stdout)
        print(f"{Color.RED}----------------{Color.RESET}\n")

        # 上传失败的常见原因诊断
        diagnose_upload_failure(result.stderr or "", port, fqbn)
        return False

    ok("上传成功!")
    return True


def diagnose_upload_failure(output: str, port: str, fqbn: str) -> None:
    """对上传失败进行诊断并给出建议"""
    print(f"\n{Color.BOLD}--- 错误诊断 ---{Color.RESET}")

    if "not in sync" in output.lower() or "resp" in output.lower():
        warn("检测到Bootloader不匹配!")
        print("""
  Nano CH340克隆版通常使用旧Bootloader (57600波特率),
  但你的板子可能刷了新的Bootloader。

  解决方案:
    1. 尝试新Bootloader模式:
       python scripts/flash_firmware.py --port {port} --bootloader new

    2. 如果还是失败, 尝试手动按复位按钮:
       - 在上传开始瞬间(看到"Uploading..."时)按Nano上的RESET按钮
""")
    elif "timeout" in output.lower() or "couldn" in output.lower():
        warn("串口连接超时!")
        print(f"""
  可能原因:
    1. 串口 {port} 被其他程序占用 (如Arduino IDE串口监视器)
    2. USB线松动或损坏
    3. CH340驱动未安装

  解决方案:
    1. 关闭所有占用该串口的程序
    2. 重新插拔USB线
    3. 安装CH340驱动 (见 docs/FLASH_GUIDE.md)
""")
    elif "permission" in output.lower():
        warn("串口权限不足!")
        print(f"""
  Linux/macOS下需要串口权限:
    sudo chmod 666 {port}
  或永久添加用户到dialout组:
    sudo usermod -a -G dialout $USER
    (然后注销并重新登录)
""")

    print(f"{Color.BOLD}------------------{Color.RESET}\n")


# =============================================================================
# 步骤 6: 验证 (串口通信测试)
# =============================================================================

def verify_upload(port: str) -> bool:
    """
    上传后验证: 打开串口, 发送查询指令, 检查回显。

    验证流程:
        1. 打开串口 (115200波特率, 等待Nano复位完成)
        2. 发送 "Q\n" (查询角度)
        3. 期待收到包含 "A:" 的回显 (如 "A:90,S:90,E:90")
        4. 收到有效回显即验证通过

    参数:
        port: 串口设备路径

    返回:
        验证通过返回True
    """
    step(6, "验证固件 (串口通信测试)")
    info(f"打开串口 {port} @ {VERIFY_BAUDRATE}bps...")

    try:
        # 打开串口
        ser = serial.Serial(
            port=port,
            baudrate=VERIFY_BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=VERIFY_TIMEOUT,
        )
    except serial.SerialException as e:
        error(f"无法打开串口: {e}")
        return False

    # Nano复位后Bootloader会占用几秒, 等待其进入主程序
    info("等待Nano启动完成 (3秒)...")
    time.sleep(3.0)

    # 清空串口缓冲区
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    # 发送验证指令并读取回显
    info(f'发送验证指令: "{VERIFY_COMMAND.decode().strip()}"')
    ser.write(VERIFY_COMMAND)
    ser.flush()

    # 等待并读取响应
    time.sleep(0.5)
    response = ""
    deadline = time.time() + VERIFY_TIMEOUT
    while time.time() < deadline:
        if ser.in_waiting > 0:
            try:
                chunk = ser.read(ser.in_waiting).decode("utf-8", errors="replace")
                response += chunk
            except Exception:
                pass
        time.sleep(0.05)

    ser.close()

    # 检查响应
    info(f"收到响应: {repr(response.strip())}")

    if VERIFY_EXPECTED in response:
        ok("验证通过! 固件运行正常")
        # 提取角度信息
        lines = [l for l in response.split("\n") if VERIFY_EXPECTED in l]
        if lines:
            ok(f"当前角度: {lines[-1].strip()}")
        return True
    else:
        warn("验证未通过: 未收到预期回显")
        return False


def verify_with_retry(port: str, max_retries: int = MAX_RETRIES) -> bool:
    """
    带重试的验证。

    参数:
        port: 串口设备路径
        max_retries: 最大重试次数

    返回:
        最终验证结果
    """
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            warn(f"第 {attempt}/{max_retries} 次验证尝试...")
            time.sleep(2.0)

        if verify_upload(port):
            return True

    error(f"验证失败 (已重试 {max_retries} 次)")
    print(f"""
{Color.YELLOW}可能原因:{Color.RESET}
  1. Bootloader不匹配 (旧 vs 新) — 尝试: --bootloader new
  2. 串口被占用 — 关闭Arduino IDE串口监视器
  3. USB线仅供电无数据 — 更换数据线
  4. 固件编译错误 — 检查编译输出

{Color.YELLOW}手动验证方法:{Color.RESET}
  1. 打开Arduino IDE串口监视器 (115200波特率)
  2. 输入 Q 并发送
  3. 期待回显: A:90,S:90,E:90
""")
    return False


# =============================================================================
# 主流程
# =============================================================================

def main() -> int:
    """主函数, 返回exit code (0=成功, 1=失败)"""
    Color.init_windows()

    parser = argparse.ArgumentParser(
        description="Arduino Nano CH340 一键烧入脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/flash_firmware.py                    # 全自动
  python scripts/flash_firmware.py --port COM3        # 指定串口
  python scripts/flash_firmware.py --bootloader new   # 新Bootloader
  python scripts/flash_firmware.py --skip-verify      # 跳过验证
        """
    )
    parser.add_argument(
        "--port", "-p",
        default=None,
        help="指定串口 (如 COM3, /dev/ttyUSB0)"
    )
    parser.add_argument(
        "--bootloader", "-b",
        choices=["old", "new", "auto"],
        default="old",
        help="Bootloader类型 (默认: old, CH340克隆版通常用旧Bootloader)"
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="跳过上传后的串口验证"
    )
    parser.add_argument(
        "--cli-path",
        default=None,
        help="指定arduino-cli路径 (如未在PATH中)"
    )
    args = parser.parse_args()

    # 打印Banner
    print(f"""
{Color.BOLD}{'='*60}{Color.RESET}
{Color.BOLD}  Arduino Nano CH340 — 一键烧入工具{Color.RESET}
{Color.BOLD}  主方案: arduino-cli  |  备用: Arduino IDE{Color.RESET}
{Color.BOLD}{'='*60}{Color.RESET}
""")

    # 根据Bootloader类型选择FQBN
    if args.bootloader == "old":
        fqbn = BOARD_FQBN_OLD
    elif args.bootloader == "new":
        fqbn = BOARD_FQBN_NEW
    else:
        # auto: 先尝试old, 上传失败时提示尝试new
        fqbn = BOARD_FQBN_OLD

    # =====================================================================
    # 步骤 1: 检测串口
    # =====================================================================
    step(1, "检测Nano/CH340串口")
    port = detect_port(args.port)
    if not port:
        error("未找到可用串口, 烧入中止")
        print(f"\n提示: 用 --port 参数手动指定, 如 --port COM3")
        return 1

    # =====================================================================
    # 步骤 2: 检查 arduino-cli
    # =====================================================================
    step(2, "检查 arduino-cli")
    if args.cli_path:
        cli = Path(args.cli_path)
        if not cli.exists():
            error(f"指定的arduino-cli不存在: {cli}")
            return 1
    else:
        cli = find_arduino_cli()

    if not cli:
        error("未找到 arduino-cli!")
        print_cli_install_guide()
        return 1

    ok(f"arduino-cli: {cli}")
    version_result = subprocess.run(
        [str(cli), "version"],
        capture_output=True, text=True
    )
    if version_result.returncode == 0:
        ok(version_result.stdout.strip())

    # =====================================================================
    # 步骤 3: 安装依赖 (Board Core + 库)
    # =====================================================================
    step(3, "安装依赖")
    if not ensure_board_core(cli):
        error("Board Core 安装失败")
        return 1
    if not ensure_libraries(cli):
        warn("库安装失败, 但编译时可能自动处理")

    # =====================================================================
    # 步骤 4: 编译
    # =====================================================================
    if not compile_firmware(cli, fqbn):
        return 1

    # =====================================================================
    # 步骤 5: 上传
    # =====================================================================
    if not upload_firmware(cli, fqbn, port):
        # 如果旧bootloader失败, 提示尝试新的
        if args.bootloader == "old":
            warn("尝试用旧Bootloader上传失败")
            print(f"\n{Color.CYAN}提示: 你的Nano可能是新Bootloader,{Color.RESET}")
            print(f"{Color.CYAN}      请重新运行:{Color.RESET}")
            print(f"  python scripts/flash_firmware.py --port {port} --bootloader new\n")
        return 1

    # =====================================================================
    # 步骤 6: 验证
    # =====================================================================
    if not args.skip_verify:
        if not verify_with_retry(port):
            warn("串口验证未通过, 但固件可能已正确上传")
            warn("建议手动打开串口监视器测试")
    else:
        warn("已跳过验证 (--skip-verify)")

    # =====================================================================
    # 完成
    # =====================================================================
    print(f"\n{Color.GREEN}{'='*60}{Color.RESET}")
    print(f"{Color.GREEN}{Color.BOLD}  烧入完成!{Color.RESET}")
    print(f"{Color.GREEN}{'='*60}{Color.RESET}")
    print(f"""
  串口: {port}
  Bootloader: {'旧(57600)' if 'old' in fqbn else '新(115200)'}
  固件: {INO_FILE.name}

  下一步:
    1. 打开串口监视器 (115200波特率)
    2. 发送 Q 查询角度
    3. 发送 A90,45,30 控制机械臂

  详见: docs/FLASH_GUIDE.md
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
