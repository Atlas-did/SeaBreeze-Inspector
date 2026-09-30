---
uid: c5a1d863
id: seabreeze-inspector.backend.arm
parent: seabreeze-inspector.backend
tags: [python, arm, kinematics]
name: {zh: "机械臂控制", en: "Robotic Arm"}
description:
  zh: >
      3DOF 机械臂：底座/大臂/小臂的正逆运动学（数值 IK + 多初始猜测 + 雅可比）与串口控制器（Arduino Nano，A<base>,<shoulder>,<elbow> 指令，角度可查询与归位）。连杆长度与串口参数由 arm_config.yaml 提供。
  en: >
      3-DOF arm: forward/inverse kinematics for base, shoulder and elbow (numerical IK with multi-start guesses plus a Jacobian) and a serial controller for the Arduino Nano (A<base>,<shoulder>,<elbow> commands, angle query and homing). Link lengths and serial parameters come from arm_config.yaml.
revision: 87c9ca9d3bdad6782b1b05816e2dab9be91c40d9
updated_at: "2026-09-30T04:50:00Z"
fingerprint: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
source: []
---
