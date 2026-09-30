---
uid: 4d2b7f18
id: seabreeze-inspector.tests.simulation
parent: seabreeze-inspector.tests
tags: [pytest, simulation]
name: {zh: "仿真测试", en: "Simulation Tests"}
description:
  zh: >
      Pygame 仿真、高度驱动器与端到端仿真流水线的测试。
      
  en: >
      Tests for the Pygame simulation, the altitude driver and the end-to-end simulation pipeline.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.851Z"
fingerprint: 20a2b9a709398a851cdb68e783042f5b374069cfe43c14959f6db49274d28c5f
source:
  - path: "tests/test_simulation.py"
  - path: "tests/test_simulation_altitude.py"
  - path: "tests/test_e2e_simulation.py"
apis:
  - protocol: rpc
    path: "pytest:tests/test_e2e_simulation.py"
    description:
      zh: >
          端到端仿真用例（4 条）。
          
      en: >
          End-to-end cases (4).
          
  - protocol: rpc
    path: "pytest:tests/test_simulation.py"
    description:
      zh: >
          仿真用例（6 条）。
          
      en: >
          Simulation cases (6).
          
  - protocol: rpc
    path: "pytest:tests/test_simulation_altitude.py"
    description:
      zh: >
          高度驱动器用例（3 条）。
          
      en: >
          Altitude-driver cases (3).
          
---
