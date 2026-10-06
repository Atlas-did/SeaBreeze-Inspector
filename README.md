# Offshore Wind Turbine UAV-Arm Cooperative Inspection System

> An open-source UAV + robotic arm cooperative system for offshore wind turbine inspection.
> Built with DJI Tello, Arduino, and Python.

[![Test Suite](https://github.com/Atlas-did/SeaBreeze-Inspector/actions/workflows/test.yml/badge.svg)](https://github.com/Atlas-did/SeaBreeze-Inspector/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Overview

This project proposes an intelligent inspection solution combining a UAV with a 3-DOF lightweight robotic arm. Using a DJI Tello drone, it achieves autonomous flight, stable hovering, and defect identification on wind turbine towers through:

- **Disturbance Observer (12-state EKF)** — estimates wind disturbances; innovation is χ²₆-consistent (D² test)
- **Feedforward PID Controller** — disturbance-aware position control. **The default demo path runs plain PID (no feedforward);** pass `cascade_feedforward=True` to get the PID+FF controller described in the paper (measured −80.6% wind-hover error). See the "default path has no feedforward" note below.
- **RRT\* Path Planning** — 3D obstacle-aware trajectory generation (wired into the demo mission key `M`)
- **Defect Detection (YOLO11s training line)** — real-time crack/corrosion/damage detection

## Tech Stack

| Component | Details |
|-----------|---------|
| UAV Platform | DJI Tello (via [DJITelloPy](https://github.com/damiafuentes/DJITelloPy)) |
| Robotic Arm | 3-DOF SG90 servos + 3D-printed structure |
| MCU | Arduino Nano (CH340) + PCA9685 servo driver |
| Algorithms | 12D-EKF, PID+Feedforward, RRT\*, YOLO11s (detector) |
| Simulation | Pygame + Three.js 3D visualization |
| Frontend | Web 3D (main demo) + Tkinter dashboard (legacy, monitor-only) |
| Language | Python 3.10+ |

> **模型状态（诚实标注，勿据此宣称可复现）**：训练线是 **YOLO11s**
> （`backend/vision/train.py` 的 `DEFAULT_MODEL`）；而 `config/yolo_config.yaml`
> 当前指向的是**历史权重** `seabreeze_v3.pt`，其训练/评估 provenance 尚未登记
> （`data/model_manifest.json` 的 `training` / `eval` 仍为 null）。
> 该配置已由 `scripts/check_deployment_config.py` 把关（权重必须存在且 SHA256 对得上），
> 但在 provenance 补齐前，**它不是一个可复现的发布候选**。

> **物理驱动模式（诚实披露，P1-12）**：`SimRuntime` 有两种驱动方式，**默认不是真机链路**。
> - `velocity_command_mode=False`（**默认**）：物理由 SimRuntime 自带级联环读 `mc.target_pos` 驱动；
>   **仓库已发表的高度/悬停数字均来自这一路径**（有 golden 测试锁定，见
>   `tests/test_transport_model.py::test_default_path_matches_pre_change_golden`）。
> - `velocity_command_mode=True`：物理由控制器输出 → `drone.set_velocity` → 机体速度环驱动，
>   即**真机同源链路**。
>
> 两种模式数值不可混用。对照实验见 `verify_scripts/compare_command_modes.py`，输出
> `command_mode_comparison.json`；在同一侧风（0.05/0.04 m/s + 阵风 0.02）与同种子下实测：
> cascade 悬停 XY 误差 **0.0952 m** / Z 误差 0.0040 m / 峰值速度 0.840 m/s；
> velocity 悬停 XY 误差 **0.0123 m** / Z 误差 0.0146 m / 峰值速度 1.000 m/s。
> 若要让演示路径等于真机链路，须显式打开该开关，**并接受已发表数值随之改变**。

> **⚠️ 默认演示路径不含前馈（必读）**：论文/README 宣称的是 **PID + Feedforward** 控制器，
> 但**默认配置下前馈对物理不起作用**：
> - 默认 `cascade_feedforward=False` ⇒ 级联环**不消费**扰动估计 `d̂`，物理上跑的是
>   **纯 PID**；`mc` 控制器算出的前馈项在仿真路径中被丢弃（历史行为，见 P0-1）。
> - 只有显式传 `cascade_feedforward=True` 时，级联环才会减去 `d̂`，此时才是**PID + FF**
>   —— 也才是论文所述系统。实测抗风悬停误差 0.0896 → 0.0174 m（**−80.6%**）。
> - 之所以默认关闭：仓库有一条硬要求"默认路径逐位不变"，**已发表的高度/悬停数字全部来自
>   无前馈的默认路径**（`tests/test_transport_model.py::test_default_path_matches_pre_change_golden`）。
>
> **引用口径**：凡引用"PID+前馈补偿"的结论，必须同时标注它是 `cascade_feedforward=True`
> 得到的；凡引用已发表的高度/悬停数字，必须标注它来自默认（**无前馈**）路径。两者不可互换。

## Quick Start

### 1. Environment Setup

```bash
# Windows
scripts\setup_env.bat

# Linux/macOS
bash scripts/setup_env.sh
```

### 2. Run Simulation

```bash
# Pygame desktop simulation
python -m backend.simulation.simulation

# Web 3D simulation (main demo)
python backend/simulation/http_bridge.py
# Then open: http://localhost:8811
```

### 3. Flash Arduino Firmware

```bash
python scripts/flash_firmware.py
```

### 4. Run Tests

```bash
# Run all test suites (427 tests in 46 files)
bash scripts/run_tests.sh      # Linux/macOS
scripts\run_tests.bat          # Windows

# Or run individually
python tests/test_ekf.py
python tests/test_integration.py
python tests/test_e2e_simulation.py  # End-to-end simulation
```

## Project Structure

```
offshore-wind-uav-arm/
|-- backend/
|   |-- core/              # Algorithms (EKF / PID+FF / RRT* / Filters)
|   |-- drone/             # Tello interface + RCManager
|   |-- arm/               # Robotic arm kinematics + controller
|   |-- vision/            # YOLO defect detection + training
|   |-- simulation/        # Pygame sim + HTTP bridge + models
|   |-- runtime/           # SimRuntime single control loop    [Phase 3]
|   |-- hal/               # Hardware abstraction layer        [Phase 4]
|   |-- mission/           # Mission states + FailsafeMonitor
|   |-- utils/             # Bus(pub-sub) / Config / Units / Logger
|   +-- main.py            # MissionController (8-state FSM)
|-- frontend/              # Tkinter dashboard (legacy monitor; Web 3D is the main demo)
|-- firmware/              # Arduino servo controller
|-- config/                # YAML configuration files
|-- data/                  # Flight logs + datasets
|-- tests/                 # Pytest suite (427 tests, 46 files)
|-- scripts/               # Setup / flash / verification tools
|-- docs/                  # Documentation + attic
+-- seabreeze-3d-sim/      # Web 3D sim (Three.js, main demo)
```

