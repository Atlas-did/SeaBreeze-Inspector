# Offshore Wind Turbine UAV-Arm Cooperative Inspection System

> An open-source UAV + robotic arm cooperative system for offshore wind turbine inspection.
> Built with DJI Tello, Arduino, and Python.

[![Test Suite](https://github.com/Atlas-did/SeaBreeze-Inspector/actions/workflows/test.yml/badge.svg)](https://github.com/Atlas-did/SeaBreeze-Inspector/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Overview

This project proposes an intelligent inspection solution combining a UAV with a 3-DOF lightweight robotic arm. Using a DJI Tello drone, it achieves autonomous flight, stable hovering, and defect identification on wind turbine towers through:

- **Disturbance Observer (12-state EKF)** — estimates and compensates for wind disturbances
- **Feedforward PID Controller** — disturbance-aware position control
- **RRT\* Path Planning** — 3D obstacle-aware trajectory generation
- **Defect Detection (YOLO11s training line)** — real-time crack/corrosion/damage detection

## Tech Stack

| Component | Details |
|-----------|---------|
| UAV Platform | DJI Tello (via [DJITelloPy](https://github.com/damiafuentes/DJITelloPy)) |
| Robotic Arm | 3-DOF SG90 servos + 3D-printed structure |
| MCU | Arduino Nano (CH340) + PCA9685 servo driver |
| Algorithms | 12D-EKF, PID+Feedforward, RRT\*, YOLO11s (detector) |
| Simulation | Pygame + Three.js 3D visualization |
| Frontend | Tkinter dashboard (monitor-only) + Web 3D (main demo) |
| Language | Python 3.10+ |

> **模型状态（诚实标注，勿据此宣称可复现）**：训练线是 **YOLO11s**
> （`backend/vision/train.py` 的 `DEFAULT_MODEL`）；而 `config/yolo_config.yaml`
> 当前指向的是**历史权重** `seabreeze_v3.pt`，其训练/评估 provenance 尚未登记
> （`data/model_manifest.json` 的 `training` / `eval` 仍为 null）。
> 该配置已由 `scripts/check_deployment_config.py` 把关（权重必须存在且 SHA256 对得上），
> 但在 provenance 补齐前，**它不是一个可复现的发布候选**。

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
# Run all test suites (134 tests in 20 files)
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
|-- frontend/              # Tkinter dashboard (monitor)
|-- firmware/              # Arduino servo controller
|-- config/                # YAML configuration files
|-- data/                  # Flight logs + datasets
|-- tests/                 # Pytest suite (134 tests, 20 files)
|-- scripts/               # Setup / flash / verification tools
|-- docs/                  # Documentation + attic
+-- seabreeze-3d-sim/      # Web 3D sim (Three.js, main demo)
```

