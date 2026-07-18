# Contributing to SeaBreeze Inspector

## Five Iron Rules (2026-07 Refactor)

These rules were established during the Phase 1-6 refactor.
Violating any of them will be flagged in code review.

### Rule 1: Single MissionState Enum

The entire system has exactly one task state enumeration:
`backend/mission/states.py:MissionState`.

- NO module may define custom task state strings
- Use `normalize_state_name()` to convert legacy aliases
- Historical aliases (TAKING_OFF, RETURNING, LANDING) are rejected at import time

### Rule 2: Single Message Bus

The entire system has exactly one message bus:
`backend/utils/bus.py:MessageBus` (pub-sub model).

- NO new Queue, dispatch thread, or second Message class
- Each subscriber gets an independent queue (no consumer contention)
- Use `bus.publish(topic, data)` to send, `sub.read_latest()` to receive
- Legacy `bus.get()` is removed (raises NotImplementedError)

### Rule 3: Unified Units and Coordinate System

All modules must use consistent units. Conversions go through `backend/utils/units.py`.

| Layer | Length | Velocity | Coordinate | Height axis |
|-------|--------|----------|------------|-------------|
| Backend (mission/core/EKF) | cm | cm/s | z-up | pos[2] |
| Simulation physics | m | m/s | z-up | pos[2] |
| Robotic arm | mm | - | z-up | pos[2] |
| Web frontend boundary | m | m/s | y-up | pos[1] |

- Cross-boundary conversions MUST use `units.py` functions
- NO manual multiply/divide by 100, 1000, etc.
- Web boundary conversion: `zup_cm_to_yup_m()` / `yup_m_to_zup_cm()`

### Rule 4: Single Control Loop

The simulation has exactly one control loop: `backend/runtime/loop.py:SimRuntime`.

- All simulations (Pygame, HTTP bridge, tests) share the same loop
- `MissionController.update_with_external_data()` is the common interface
- Frontends are data sources or observers, never control loop owners

### Rule 5: YAML-First Configuration

Hardware parameters must live in `config/*.yaml`.

- NO bare physical constants as fallbacks in code
- Arm link lengths: read from `arm_config.yaml`, not hardcoded defaults
- New parameters: add to schema + YAML, never only in code

## Development Workflow

1. Create branch: `feature/name-task`
2. Write code + tests
3. Run `pytest tests/ -q` -- must be all green
4. Run direct smoke tests: `python tests/test_bus_pubsub.py`
5. Submit PR with description of changes

## Code Review Checklist

- [ ] No custom state strings (Rule 1)
- [ ] No new Queue/dispatch/bus (Rule 2)
- [ ] Unit conversions use `units.py` (Rule 3)
- [ ] Simulations use `SimRuntime` (Rule 4)
- [ ] Hardware params from YAML, not code (Rule 5)
- [ ] `pytest tests/ -q` passes

## Test Conventions

- Each test file must support both `pytest` and direct `python tests/xxx.py`
- Add `if __name__ == '__main__':` block for direct execution
- Use `@pytest.fixture` for shared setup
- Use `@pytest.mark.hardware` for tests requiring real drone/arm