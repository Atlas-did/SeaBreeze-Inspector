---
uid: 3d8f1c65
id: seabreeze-inspector.backend.arm.kinematics
parent: seabreeze-inspector.backend.arm
tags: [arm, kinematics, ik]
name: {zh: "3DOF 机械臂运动学", en: "3-DOF Arm Kinematics"}
description:
  zh: >
      底座/大臂/小臂三关节运动学：FK 由 θ1..θ3 求末端 (x,y,z)，其中小臂与末端共线（L23=L2+L3）；IK 用 L-BFGS-B 数值优化加 5×5×4 初始猜测网格搜索，保证与 FK 一致，无 scipy 时退化为解析解并处理 r≈0 与超出工作空间两种退化情形；Jacobian 给出 3×3 雅可比供速度控制。连杆长度优先从 arm_config.yaml 读取。
      
  en: >
      Kinematics for the base/shoulder/elbow joints: FK maps theta1..theta3 to the end-effector (x,y,z) with the forearm and tip collinear (L23=L2+L3); IK runs L-BFGS-B over a 5x5x4 multi-start grid to stay consistent with FK, degrading to an analytic solution without scipy while handling the r~0 and out-of-workspace degeneracies; Jacobian returns the 3x3 Jacobian for velocity control. Link lengths are read from arm_config.yaml first.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.794Z"
fingerprint: 034a4d9a047d174048a902b0aeff4585f9d649f5214492aec9510c8673d452e9
source:
  - path: "backend/arm/arm_kinematics.py"
    line: 24
    end_line: 182
apis:
  - protocol: rpc
    path: "FK"
    description:
      zh: >
          正运动学：三关节角度（度）→ 末端位置 (x,y,z) mm。
          
      en: >
          Forward kinematics: joint angles in degrees to end-effector (x,y,z) in mm.
          
  - protocol: rpc
    path: "IK"
    description:
      zh: >
          逆运动学：末端 (x,y,z) mm → [θ1,θ2,θ3] 度，数值优化 + 多初始猜测，失败回退解析解与默认姿态。
          
      en: >
          Inverse kinematics: end-effector (x,y,z) in mm to [theta1,theta2,theta3] in degrees via numerical optimisation with multi-start guesses, falling back to the analytic solution and a default pose.
          
  - protocol: rpc
    path: "Jacobian"
    description:
      zh: >
          计算 3×3 雅可比矩阵，用于关节速度到末端速度的映射。
          
      en: >
          Computes the 3x3 Jacobian mapping joint rates to end-effector velocity.
          
  - protocol: rpc
    path: "deg2rad"
    description:
      zh: >
          角度转弧度的薄封装。
          
      en: >
          Thin degrees-to-radians helper.
          
  - protocol: rpc
    path: "rad2deg"
    description:
      zh: >
          弧度转角度的薄封装，IK 解析分支使用。
          
      en: >
          Thin radians-to-degrees helper used by the analytic IK branch.
          
---
