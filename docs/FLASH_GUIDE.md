# Arduino Nano CH340 固件烧入指南

> 本文档提供完整的固件烧入流程，涵盖驱动安装、工具配置、一键烧入和故障排查。
>
> 烧入工具选型：
> - **主方案：arduino-cli**（推荐）— 命令行工具，已封装在 `scripts/flash_firmware.py` 中
> - **备用方案：Arduino IDE** — 图形界面，当主方案因网络问题无法使用时兜底

---

## 一、准备工作

### 1.1 硬件清单

| 物品 | 数量 | 说明 |
|------|------|------|
| Arduino Nano (CH340芯片) | 1 | 主控板 |
| USB-A to Mini-USB数据线 | 1 | **必须是数据线**（能传数据），不是纯充电线 |
| PCA9685舵机驱动板 | 1 | I2C接口 |
| 电脑 (Windows/Mac/Linux) | 1 | 已安装Python 3.10+ |

### 1.2 软件清单

| 软件 | 用途 | 安装方式 |
|------|------|---------|
| Python 3.10+ | 运行一键烧入脚本 | [python.org](https://python.org) 下载安装 |
| pyserial | 串口通信库 | `pip install pyserial` |
| arduino-cli | 主烧入工具 | 见下方"安装arduino-cli" |
| CH340驱动 | USB转串口驱动 | 见下方"安装CH340驱动" |

---

## 二、安装CH340驱动

Nano CH340的USB芯片需要专门的驱动程序。

### Windows

1. 将Nano通过USB线连接到电脑
2. 打开"设备管理器"（右键开始菜单 → 设备管理器）
3. 查看"端口(COM和LPT)"下是否有 **"USB-SERIAL CH340(COMx)"**
   - 如果有 → 驱动已安装，记下COM口号（如COM3）
   - 如果有黄色感叹号 → 驱动未安装，继续步骤4
4. 下载CH340驱动：
   - 淘宝/京东Arduino卖家通常会提供驱动文件
   - 或搜索 "CH340驱动下载" 从WCH官网下载
5. 解压驱动包，右键 `CH341SER.EXE` → 以管理员身份运行 → 安装
6. 重新插拔USB线，再次检查设备管理器

### macOS

macOS 10.15+ 通常自带CH340驱动。连接Nano后打开终端：

```bash
ls /dev/cu.*
```

如果能看到类似 `/dev/cu.wchusbserial*` 或 `/dev/cu.usbserial*` 的设备，说明驱动已就绪。

如果看不到，安装驱动：

```bash
# 使用 Homebrew 安装
brew tap adrianmihalko/ch340g-ch34g-ch34x-mac-os-x-driver
brew install wch-ch34x-usb-serial-driver
```

### Linux

Linux内核通常自带CH340驱动。连接Nano后：

```bash
# 查看设备
ls /dev/ttyUSB*
# 或
ls /dev/ttyACM*
```

如果看不到设备，尝试加载驱动：

```bash
sudo modprobe ch341
```

权限问题（上传时提示 Permission denied）：

```bash
# 临时方案
sudo chmod 666 /dev/ttyUSB0

# 永久方案（推荐）：将用户加入dialout组
sudo usermod -a -G dialout $USER
# 然后注销并重新登录
```

---

## 三、安装arduino-cli（主方案）

### 自动安装（推荐）

运行项目环境初始化脚本（会自动安装arduino-cli）：

```bash
# Windows
scripts\setup_env.bat

# Linux/macOS
bash scripts/setup_env.sh
```

### 手动安装

#### Windows

1. 打开浏览器，访问 https://github.com/arduino/arduino-cli/releases/latest
2. 下载文件名类似 `arduino-cli_1.0.4_Windows_64bit.zip`
3. 解压到 `C:\arduino-cli\`
4. 将该文件夹添加到系统PATH：
   - 右键"此电脑" → 属性 → 高级系统设置 → 环境变量
   - 编辑"Path" → 新建 → 输入 `C:\arduino-cli`
   - 确定 → 确定
5. 打开新的命令提示符，验证：
   ```cmd
   arduino-cli version
   ```

#### macOS

```bash
brew install arduino-cli
```

#### Linux

```bash
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
sudo mv bin/arduino-cli /usr/local/bin/
arduino-cli version
```

---

## 四、一键烧入（主方案）

### 4.1 全自动模式

```bash
# 进入项目根目录
cd offshore-wind-uav-arm

# Windows
python scripts\flash_firmware.py

# Linux/macOS
python3 scripts/flash_firmware.py
```

脚本会自动执行：
1. 扫描并识别CH340串口
2. 检查arduino-cli安装
3. 安装Arduino AVR Board Core（首次需下载约100MB）
4. 安装Adafruit PWM Servo Driver库
5. 编译 `firmware/servo_controller/servo_controller.ino`
6. 上传到Nano
7. 串口验证（发送查询指令，检查角度回显）

### 4.2 手动指定参数

```bash
# 指定串口
python scripts/flash_firmware.py --port COM3

# 指定新Bootloader（如果旧Bootloader上传失败）
python scripts/flash_firmware.py --bootloader new

# 跳过验证
python scripts/flash_firmware.py --skip-verify

# 指定arduino-cli路径（如果不在PATH中）
python scripts/flash_firmware.py --cli-path "C:\arduino-cli\arduino-cli.exe"
```

### 4.3 预期输出

```
============================================================
  Arduino Nano CH340 — 一键烧入工具
  主方案: arduino-cli  |  备用: Arduino IDE
============================================================

=== 步骤 1: 检测Nano/CH340串口 ===
[INFO] 正在扫描可用串口...
[ OK ] 检测到CH340设备: COM3 (USB-SERIAL CH340)

=== 步骤 2: 检查 arduino-cli ===
[ OK ] arduino-cli: C:\arduino-cli\arduino-cli.exe
[ OK ] arduino-cli  Version: 1.0.4 Commit: xxx Date: xxx

=== 步骤 3: 安装依赖 ===
[INFO] 检查 Arduino AVR Board Core...
[ OK ] Arduino AVR Core 已安装
[INFO] 检查 Adafruit PWM Servo Driver 库...
[ OK ] Adafruit PWM Servo Driver 库已安装

=== 步骤 4: 编译固件 ===
[INFO] Board: arduino:avr:nano:cpu=atmega328old
[INFO] 源码: ...\servo_controller.ino
[INFO] 开始编译...
[ OK ] Sketch uses 12345 bytes (40%) of 30720 bytes
[ OK ] Global variables use 987 bytes (48%) of 2048 bytes
[ OK ] 编译成功

=== 步骤 5: 上传固件到Nano ===
[INFO] 串口: COM3
[INFO] Bootloader: 旧(57600)
[INFO] 正在上传 (请保持USB连接)...
[ OK ] 上传成功!

=== 步骤 6: 验证固件 (串口通信测试) ===
[INFO] 打开串口 COM3 @ 115200bps...
[INFO] 等待Nano启动完成 (3秒)...
[INFO] 发送验证指令: "Q"
[INFO] 收到响应: "A:90,S:90,E:90"
[ OK ] 验证通过! 固件运行正常
[ OK ] 当前角度: A:90,S:90,E:90

============================================================
  烧入完成!
============================================================
  串口: COM3
  Bootloader: 旧(57600)
  固件: servo_controller.ino

  下一步:
    1. 打开串口监视器 (115200波特率)
    2. 发送 Q 查询角度
    3. 发送 A90,45,30 控制机械臂
============================================================
```

---

## 五、手动烧入（备用方案：Arduino IDE）

当arduino-cli因网络问题无法安装时，使用Arduino IDE手动烧入。

### 5.1 安装Arduino IDE

1. 访问 https://www.arduino.cc/en/software
2. 下载对应系统的安装包
3. 安装并启动

### 5.2 安装Adafruit库

1. Arduino IDE → 工具 → 管理库
2. 搜索 "Adafruit PWM Servo Driver"
3. 安装 "Adafruit PCA9685 PWM Servo Driver Library"
4. 会自动安装依赖 "Adafruit BusIO"

### 5.3 选择开发板

1. 工具 → 开发板 → Arduino AVR Boards → Arduino Nano
2. 工具 → 处理器 → ATmega328P **(Old Bootloader)**
   - ⚠️ CH340克隆版必须选Old Bootloader！
3. 工具 → 端口 → 选择CH340对应的COM口

### 5.4 打开并上传固件

1. 文件 → 打开 → 选择 `firmware/servo_controller/servo_controller.ino`
2. 点击 "✓" 按钮编译
3. 点击 "→" 按钮上传
4. 等待显示 "上传完成"

### 5.5 验证

1. 工具 → 串口监视器
2. 波特率选择 115200
3. 输入 `Q`，点击发送
4. 期待回显：`A:90,S:90,E:90`

---

## 六、常见问题排查

### 问题1：找不到串口

**现象：** 设备管理器中没有"USB-SERIAL CH340"

| 排查步骤 | 操作 |
|---------|------|
| 1. 换USB口 | 尝试电脑上的其他USB接口（优先USB 2.0） |
| 2. 换数据线 | **必须**使用能传输数据的USB线，充电线不行 |
| 3. 检查驱动 | 设备管理器中是否有黄色感叹号 → 安装CH340驱动 |
| 4. 换电脑测试 | 排除电脑USB控制器问题 |
| 5. 检查Nano | Nano上的电源指示灯(PWR)是否亮起 |

### 问题2：上传超时 / "not in sync"

**现象：** 上传过程中卡住，最后报 timeout 或 not in sync

| 原因 | 解决方案 |
|------|---------|
| Bootloader不匹配 | 尝试切换Bootloader类型：`--bootloader new` |
| 串口被占用 | 关闭Arduino IDE串口监视器、其他串口工具 |
| USB线质量问题 | 更换数据线，尽量用短一点（<1m）的线 |
| 手动复位时机 | 在点击上传后、看到"Uploading..."瞬间按RESET键 |
| CH340驱动问题 | 卸载驱动后重新安装最新版 |

### 问题3：波特率错误

**现象：** 上传成功但串口验证收不到数据，或收到乱码

| 可能原因 | 解决方案 |
|---------|---------|
| 串口监视器波特率不对 | 必须是 **115200**（不是9600） |
| Bootloader波特率选错 | 旧Bootloader用57600上传，但固件内用115200通信 |
| 串口被其他程序占用 | 关闭所有串口监视器后再验证 |

### 问题4：Bootloader损坏

**现象：** 任何上传方式都失败，Nano完全不响应

**修复方法（需要另一块Arduino或USBasp编程器）：**

1. 用另一块Arduino作为ISP编程器
2. 连接：编程器D10→Nano RESET, D11→D11, D12→D12, D13→D13, 5V→5V, GND→GND
3. 编程器运行 ArduinoISP 示例 sketch
4. 工具 → 烧录引导程序

**如果没有第二块Arduino：**
- 购买USBasp编程器（约10元）
- 或请其他有经验的团队成员协助

### 问题5：Windows路径含空格

**现象：** 脚本报错说找不到文件

**解决方案：**
- 本脚本已使用 `pathlib.Path` 处理所有路径，自动兼容空格
- 如果手动运行arduino-cli，路径用双引号包裹：
  ```cmd
  arduino-cli compile --fqbn arduino:avr:nano "C:\My Projects\firmware"
  ```

### 问题6：Linux权限不足

**现象：** 报错 `Permission denied: /dev/ttyUSB0`

```bash
# 临时方案
sudo chmod 666 /dev/ttyUSB0

# 永久方案
sudo usermod -a -G dialout $USER
# 注销并重新登录生效
```

---

## 七、通信指令速查表

烧入完成后，用串口监视器（115200波特率）发送以下指令测试：

| 指令 | 功能 | 示例响应 |
|------|------|---------|
| `Q` | 查询当前角度 | `A:90,S:90,E:30` |
| `A90,45,30` | 绝对角度模式 | `[ABS] 目标角度 → Base:90 ...` |
| `R10,0,-5` | 相对增量模式 | `[REL] 增量 (10,0,-5) → ...` |
| `H` | 归位到90,90,90 | `[HOME] 正在归位...` |
| `S` | 紧急停止 | `[STOP] 紧急停止...` |
| `?` | 帮助信息 | 打印指令列表 |

---

*文档版本: v1.0 | 2026年6月*
