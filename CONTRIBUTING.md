# Contributing Guide

Thanks for your interest in contributing to the Offshore Wind UAV-Arm project!

## Getting Started

1. Fork the repo and clone locally
2. Set up the dev environment:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

3. Run tests to verify everything works:

```bash
python -m pytest tests/ -v
```

## Development Workflow

### Code Style

- Python code formatted with [Black](https://github.com/psf/black) (line length 88)
- Lint with [Flake8](https://flake8.pycqa.org/)
- YAML files: spaces only, 2-space indent (no tabs!)
- Follow the existing patterns in each module

### Testing

- All new features should include tests
- Run the full suite before submitting:

```bash
python -m pytest tests/ -v --tb=short
```

- Current test suites (14 total):

| Suite | Coverage |
|-------|----------|
| `test_ekf.py` | EKF observer — matrix dims, state transition, accuracy, performance, adaptive Q |
| `test_controller.py` | Feedforward PID — step response, disturbance rejection |
| `test_arm.py` | Arm kinematics — FK/IK roundtrip, joint limits, Jacobian, reachability |
| `test_trajectory.py` | RRT* — basic planning, multi-obstacle, performance, visualization |
| `test_vision.py` | Defect detector — output format, edge cases, resize, draw |
| `test_communication.py` | MessageBus — basic, callback, connector, thread safety, overflow |
| `test_config.py` | Config loader — YAML load, nested access, missing keys, types |
| `test_tello_mock.py` | Tello mock — basic, controller, emergency, battery |
| `test_integration.py` | Integration — EKF+controller, FK/IK, RRT*, safety guard |
| `test_simulation.py` | Simulation — physics, wind, sensors, turbine, arm model |
| `test_safety_guard.py` | Safety guard — battery, attitude, height, timeout, reset, boundaries |
| `test_arm_controller.py` | Arm controller — mock mode, IK, reset, duration |
| `test_main.py` | State machine — 8-state transitions, SafetyGuard, Logger, VideoStream |
| `test_e2e_simulation.py` | End-to-end — full mission flow, emergency interrupt, logging, shutdown |

### Commit Messages

Use conventional commits:

```
feat: add wind gust model to simulation
fix: correct Kff sign in feedforward controller
docs: update API_INTERFACE with new endpoints
test: add safety guard boundary tests
refactor: use cKDTree for RRT* nearest neighbor
```

### Pull Requests

1. Reference any related issues
2. Describe what changed and why
3. Ensure CI passes (tests run on push automatically)
4. Request review from a maintainer

## Project Architecture

See [ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md) for design rationale and [SOFTWARE.md](docs/SOFTWARE.md) for data flow diagrams.
