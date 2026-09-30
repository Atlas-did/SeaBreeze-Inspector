---
uid: 9f2b7d05
id: seabreeze-inspector.backend.utils.flight-logger
parent: seabreeze-inspector.backend.utils
tags: [logging, csv, telemetry]
name: {zh: "飞行日志记录器", en: "Flight Logger"}
description:
  zh: >
      把每帧时间戳（微秒级）、位置(cm)、扰动估计(cm/s²)与 YOLO 检测框写成 CSV：10 帧内存缓冲刷盘、支持 with 语法与显式 save/stop，默认落盘 data/processed/logs/<会话名>.csv，可直接用 Excel/pandas 分析。
      
  en: >
      Writes per-frame timestamp, position (cm), disturbance estimate (cm/s²) and YOLO detections to CSV: a 10-frame memory buffer, with-statement support and explicit save/stop, defaulting to data/processed/logs/<session>.csv for Excel or pandas analysis.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.813Z"
fingerprint: 3aef48462d4b5f54675d496bbb88ea486661b80ccb9bdede91842ce28db637a2
source:
  - path: "backend/utils/logger.py"
    line: 31
    end_line: 214
apis:
  - protocol: rpc
    path: "FlightLogger.start_session"
    description:
      zh: >
          开始记录会话并写入 CSV 表头。
          
      en: >
          Starts a recording session and writes the CSV header.
          
  - protocol: rpc
    path: "FlightLogger.log_frame"
    description:
      zh: >
          记录一帧位置/扰动/检测框，缓冲满 10 帧自动刷盘。
          
      en: >
          Records one frame of position, disturbance and detections; flushes every ten buffered frames.
          
  - protocol: rpc
    path: "FlightLogger.save"
    description:
      zh: >
          把剩余缓冲写入 CSV，返回日志文件路径。
          
      en: >
          Flushes the remaining buffer to CSV and returns the log path.
          
  - protocol: rpc
    path: "FlightLogger.stop"
    description:
      zh: >
          停止记录并保存，用于 with 退出与优雅关闭。
          
      en: >
          Stops recording and saves, used on with-exit and graceful shutdown.
          
  - protocol: file
    path: "data/processed/logs/<session>.csv"
    description:
      zh: >
          默认日志输出文件：每会话一个 CSV。
          
      en: >
          Default log output: one CSV file per session.
          
deps:
  - kind: reference
    to: seabreeze-inspector.backend.utils.config-loader.loader-core
    from_api: "rpc:FlightLogger.start_session"
    to_api: "rpc:ConfigLoader.load"
    label: {zh: "复用 PROJECT_ROOT 定位日志目录", en: "Reuses PROJECT_ROOT for logs"}
---
