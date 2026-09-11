# Offshore Wind Turbine UAV-Arm Cooperative Inspection System

> An open-source UAV + robotic arm cooperative system for offshore wind turbine inspection.
> Built with DJI Tello, Arduino, and Python.

[![Test Suite](https://github.com/offshore-wind-uav-arm/offshore-wind-uav-arm/actions/workflows/test.yml/badge.svg)](https://github.com/offshore-wind-uav-arm/offshore-wind-uav-arm/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Overview

This project proposes an intelligent inspection solution combining a UAV with a 3-DOF lightweight robotic arm. Using a DJI Tello drone, it achieves autonomous flight, stable hovering, and defect identification on wind turbine towers through:

- **Disturbance Observer (12-state EKF)** — estimates and compensates for wind disturbances
- **Feedforward PID Controller** — disturbance-aware position control
- **RRT\* Path Planning** — 3D obstacle-aware trajectory generation
- **Defect Detection (YOLO family)** — binary defect/clean detector on 1024px tiles;
  weights in `data/weights/` were trained with YOLO11s (see *Detection status* below)

## Tech Stack

| Component | Details |
|-----------|---------|
| UAV Platform | DJI Tello (via [DJITelloPy](https://github.com/damiafuentes/DJITelloPy)) |
| Robotic Arm | 3-DOF SG90 servos + 3D-printed structure |
| MCU | Arduino Nano (CH340) + PCA9685 servo driver |
| Algorithms | 12D-EKF, PID+Feedforward, RRT\*, YOLO11s detector |
| Simulation | Pygame + Three.js 3D visualization |
| Frontend | Tkinter dashboard (monitor-only) + Web 3D (main demo) |
| Language | Python 3.10+ |

## Detection status

The detection pipeline is under active re-evaluation; **do not cite a mAP
number from this repository or its docs** without checking
[`docs/research/`](docs/research/README.md) first. Summary:

- The model that produced the current `data/weights/` artifacts is **YOLO11s**
  (binary nc=1, 1024px tiles). `backend/vision/train.py` / `detect.py` still
  default to `yolov8n.pt` as a fallback path — swap in the trained weights
  explicitly.
- Earlier figures (~0.577 mAP@0.5, 3-class, "YOLOv8-Nano") came from a v3 run
  later found to have **83% validation/training overlap** and are invalid.
- Current best (v4) is provisional: adjacent-parent frames cross splits, so it
  measures same-scene generalization; a scene-isolated v5 failed (OOD), v5.1
  improved but is not yet usable. The next step is a frozen v5.2 dual-protocol
  evaluation (in-distribution validation + out-of-distribution test).

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
# Then open: http://localhost:8800
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

