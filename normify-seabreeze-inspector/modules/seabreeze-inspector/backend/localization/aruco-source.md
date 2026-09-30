---
uid: c3d4e5f6
id: seabreeze-inspector.backend.localization.aruco-source
parent: seabreeze-inspector.backend.localization
tags: [localization, aruco, vision]
name: {zh: "ArUco 视觉定位源", en: "ArUco Vision Localization"}
description:
  zh: >
      真实 ArUco 定位：检测标记 → solvePnP 解位姿 → 世界坐标（cm，z-up），质量分 = exp(-重投影误差/3.0) × min(1, 标记数/2)，依据是实测残差而非估计。被动推帧式：由主循环每帧把视频帧推进来（read_frame），未检出/解算失败/内参未标定一律返回 None。实测单标记误差 1.867cm、双标记 1.478cm。
      
  en: >
      Real ArUco localization: detect markers, solvePnP, then world coordinates (cm, z-up) with quality = exp(-reprojection error/3.0) x min(1, markers/2), grounded in measured residuals. Passively frame-driven: the main loop pushes each frame via read_frame; no detection, failed solve or uncalibrated intrinsics all yield None. Measured error: 1.867 cm single marker, 1.478 cm two markers.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:32:18.249Z"
fingerprint: fe62a1f369823cf5ea0b56d36bd03b5a2075bfd4f40e754e9cfe0df18d695f09
source:
  - path: "backend/localization/aruco_source.py"
    line: 1
    end_line: 235
apis:
  - protocol: rpc
    path: "ArUcoLocalizationSource.read_frame"
    description:
      zh: >
          推入一帧并解算；成功则缓存一条带时间戳/质量的观测。
          
      en: >
          Pushes one frame and solves it, caching a timestamped, quality-scored observation.
          
  - protocol: rpc
    path: "ArUcoLocalizationSource.read"
    description:
      zh: >
          取最近一次观测并做可用性判定（过期/低质量即 None）。
          
      en: >
          Returns the latest observation after usability checks (None when stale or low quality).
          
  - protocol: rpc
    path: "ArUcoLocalizationSource.set_calibration"
    description:
      zh: >
          设置相机内参与畸变；未标定时定位不可用。
          
      en: >
          Sets camera intrinsics and distortion; without calibration localization stays unusable.
          
---
