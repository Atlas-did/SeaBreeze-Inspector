---
uid: 5f7a3c98
id: seabreeze-inspector.backend.simulation.models.arm-and-turbine
parent: seabreeze-inspector.backend.simulation.models
tags: [arm, geometry]
name: {zh: "机械臂与风机几何模型", en: "Arm & Turbine Geometry"}
description:
  zh: >
      仿真用 3-DOF 机械臂（实现 ArmInterface）与风机圆柱体几何体：关节角读写、末端定位与碰撞/表面点计算。
      
  en: >
      Simulation-side 3-DOF arm (implementing ArmInterface) and the wind-turbine cylinder geometry: joint angle access, end-point pose, collision and surface-point computation.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.808Z"
fingerprint: ce32ed8a7bada782ae8d16b707a8b42692c87b33f5e71d299304766a744293ab
source:
  - path: "backend/simulation/models.py"
    line: 237
    end_line: 355
apis:
  - protocol: rpc
    path: "RobotArm3DOF.set_angles"
    description:
      zh: >
          设置关节角。
          
      en: >
          Sets joint angles.
          
  - protocol: rpc
    path: "RobotArm3DOF.get_endpoint"
    description:
      zh: >
          读末端位置。
          
      en: >
          Reads the end-effector position.
          
  - protocol: rpc
    path: "WindTurbine.check_collision"
    description:
      zh: >
          碰撞检测。
          
      en: >
          Collision check.
          
  - protocol: rpc
    path: "WindTurbine.get_surface_point"
    description:
      zh: >
          取叶片表面巡检点。
          
      en: >
          Returns a blade surface inspection point.
          
---
