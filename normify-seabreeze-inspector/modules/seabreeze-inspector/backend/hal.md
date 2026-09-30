---
uid: 5e1c93b4
id: seabreeze-inspector.backend.hal
parent: seabreeze-inspector.backend
tags: [hal, interface, abc]
name: {zh: "硬件抽象层接口", en: "HAL Interfaces"}
description:
  zh: >
      硬件抽象层的抽象基类契约：DroneInterface（连接/起飞/降落/受控紧急下降/kill 近地硬停桨/相对移动/悬停/电量/高度/姿态/状态字典/是否在飞）、ArmInterface（关节角与末端位姿）、VisionInterface（检测）。仿真与真机实现同一组接口，任务层只依赖抽象。
      
  en: >
      The HAL abstract contracts: DroneInterface (connect/takeoff/land/controlled emergency/kill hard-cut near ground/relative move/hover/battery/height/attitude/state dict/is-flying), ArmInterface (joint angles and end-effector pose) and VisionInterface (detect). Simulation and real hardware implement the same interfaces; the mission layer depends only on abstractions.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.800Z"
fingerprint: 4a22f40a759afd5b729939120bc56f0fd196468ca24dbef6270271fbacab8a40
source:
  - path: "backend/hal/interfaces.py"
    line: 13
    end_line: 135
apis:
  - protocol: rpc
    path: "DroneInterface.connect"
    description:
      zh: >
          建立与无人机的连接，返回是否成功。
          
      en: >
          Establishes the drone connection and returns success.
          
  - protocol: rpc
    path: "DroneInterface.emergency"
    description:
      zh: >
          受控紧急下降（非立即停桨）：高空快速但可控下降，近地才允许升级硬停。
          
      en: >
          Controlled emergency descent, not an immediate motor stop: a fast but controlled descent at altitude, escalating only near the ground.
          
  - protocol: rpc
    path: "DroneInterface.kill"
    description:
      zh: >
          立即停桨（硬杀），仅限近地 (<3m) 使用，禁止高空调用。
          
      en: >
          Immediate motor stop (hard kill), allowed only near the ground (<3 m) and never at altitude.
          
  - protocol: rpc
    path: "ArmInterface.set_angles"
    description:
      zh: >
          设置 [base, shoulder, elbow] 关节角（度）。
          
      en: >
          Sets the [base, shoulder, elbow] joint angles in degrees.
          
  - protocol: rpc
    path: "VisionInterface.detect"
    description:
      zh: >
          对一帧图像执行缺陷检测，返回 class_name/confidence/bbox 列表。
          
      en: >
          Runs defect detection on a frame, returning class_name/confidence/bbox records.
          
---
