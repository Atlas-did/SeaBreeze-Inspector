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
- **YOLOv8-Nano Defect Detection** — real-time crack/corrosion/damage detection

## Tech Stack

| Component | Details |
|-----------|---------|
| UAV Platform | DJI Tello (via [DJITelloPy](https://github.com/damiafuentes/DJITelloPy)) |
| Robotic Arm | 3-DOF SG90 servos + 3D-printed structure |
| MCU | Arduino Nano (CH340) + PCA9685 servo driver |
| Algorithms | 12D-EKF, PID+Feedforward, RRT\*, YOLOv8-Nano |
| Simulation | Pygame 3D visualization |
| Frontend | Tkinter monitoring dashboard |
| Language | Python 3.10+ |

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
python -m backend.simulation.simulation
```

### 3. Flash Arduino Firmware

```bash
python scripts/flash_firmware.py
```

### 4. Run Tests

```bash
# Run all 14 test suites
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
├── backend/
│   ├── core/              # Algorithms (EKF / Controller / Path Planning)
│   ├── drone/             # Tello interface (state machine / video stream)
│   ├── arm/               # Robotic arm control (kinematics / controller)
│   ├── vision/            # YOLO defect detection (detector / training / datasets)
│   ├── simulation/        # Pygame simulation (models / renderer)
│   ├── utils/             # Config / logging / communication utilities
│   ├── main.py            # Main scheduler (8-state FSM + SafetyGuard)
│   └── safety_guard.py    # Safety monitor (battery / attitude / height / timeout)
├── firmware/              # Arduino firmware (servo controller)
├── frontend/              # Tkinter monitoring dashboard
├── config/                # YAML configuration templates (with schema validation)
├── docs/                  # Technical documentation
├── scripts/               # One-click setup & flash scripts
├── tests/                 # 14 test suites (unit / integration / E2E)
├── .github/workflows/     # CI configuration (test.yml)
├── requirements.txt       # Production dependencies
├── requirements-dev.txt   # Development dependencies
└── pytest.ini             # pytest configuration
```

## Documentation

| Document | Description |
|----------|-------------|
| [API_INTERFACE.md](docs/API_INTERFACE.md) | Full module API reference |
| [ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md) | Architecture Decision Records (ADRs) |
| [EKF_DERIVATION.md](docs/EKF_DERIVATION.md) | EKF mathematical derivation |
| [KINEMATICS_DERIVATION.md](docs/KINEMATICS_DERIVATION.md) | Arm kinematics derivation |
| [TRAJECTORY_ALGORITHM.md](docs/TRAJECTORY_ALGORITHM.md) | RRT\* path planning algorithm |
| [FLASH_GUIDE.md](docs/FLASH_GUIDE.md) | Arduino flashing guide |
| [PINOUT.md](docs/PINOUT.md) | Pin definitions & wiring |
| [SERVO_PROTOCOL.md](docs/SERVO_PROTOCOL.md) | Serial communication protocol |
| [TUNING_GUIDE.md](docs/TUNING_GUIDE.md) | PID & EKF parameter tuning |
| [HARDWARE.md](docs/HARDWARE.md) | Hardware BOM & assembly |
| [SOFTWARE.md](docs/SOFTWARE.md) | Software architecture |
| [SIM_GUIDE.md](docs/SIM_GUIDE.md) | Simulation user guide |
| [TESTING.md](docs/TESTING.md) | Testing strategy & coverage |

## State Machine

```
IDLE → TAKEOFF → HOVERING → NAVIGATE(RRT*) → INSPECT(YOLO) → RETURN → LAND
  ↑                                                                      ↓
  └────────────────────── EMERGENCY (any state) ─────────────────────────┘
```

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Run tests (`python -m pytest tests/ -v`)
4. Commit your changes
5. Open a Pull Request

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

## References

- [DJITelloPy](https://github.com/damiafuentes/DJITelloPy) — DJI Tello Python SDK
- [PX4-Autopilot](https://github.com/PX4/PX4-Autopilot) — Industrial-grade EKF & sensor fusion
- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) — YOLO training best practices
- [Betaflight](https://github.com/betaflight/betaflight) — IMU filtering & PID tuning
