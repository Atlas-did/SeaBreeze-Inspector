"""
飞行日志记录器 — 支持CSV格式记录飞行数据、扰动估计、检测框。

用法:
    from backend.utils.logger import FlightLogger

    logger = FlightLogger()
    logger.start_session()  # 开始新的记录会话

    # 在每次传感器更新后记录
    logger.log_frame(
        position=(x, y, z),
        disturbance=(dx, dy, dz),
        detections=[{"class": "crack", "conf": 0.92, "bbox": [x1, y1, x2, y2]}],
    )

    logger.save()  # 保存到CSV文件
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# 默认日志输出目录（相对项目根目录）
try:
    from backend.utils.config import PROJECT_ROOT
    DEFAULT_LOG_DIR: Path = PROJECT_ROOT / "data" / "processed" / "logs"
except ImportError:
    DEFAULT_LOG_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "processed" / "logs"


@dataclass
class LogFrame:
    """单帧日志数据结构"""
    timestamp: float               # 时间戳（秒，time.time()）
    datetime_str: str              # 人类可读时间字符串
    pos_x: float                   # 位置 X (cm)
    pos_y: float                   # 位置 Y (cm)
    pos_z: float                   # 位置 Z (cm)
    dist_dx: float                 # 扰动估计 X (cm/s²)
    dist_dy: float                 # 扰动估计 Y (cm/s²)
    dist_dz: float                 # 扰动估计 Z (cm/s²)
    detection_count: int           # 检测框数量
    detections_json: str           # 检测框详情（JSON字符串）
    extra: str = ""                # 额外信息（JSON字符串，可选）


class FlightLogger:
    """
    飞行日志记录器。

    每帧记录以下信息:
        - 时间戳（精确到微秒）
        - 无人机位置 (x, y, z) cm
        - 扰动估计值 (dx, dy, dz) cm/s²
        - YOLO检测框（类别、置信度、坐标）

    输出格式: CSV（可直接用Excel打开分析）
    """

    # CSV列头定义
    # P2-E: 扰动列标单位修正 N→cm/s²
    CSV_HEADERS = [
        "timestamp",
        "datetime",
        "pos_x_cm",
        "pos_y_cm",
        "pos_z_cm",
        "disturbance_x_cmps2",
        "disturbance_y_cmps2",
        "disturbance_z_cmps2",
        "detection_count",
        "detections_json",
        "extra",
    ]

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        session_name: Optional[str] = None,
    ) -> None:
        """
        初始化日志记录器。

        参数:
            log_dir: 日志存储目录，默认 data/processed/logs/
            session_name: 会话名称，默认使用当前时间
        """
        self.log_dir: Path = log_dir or DEFAULT_LOG_DIR
        self.session_name: str = session_name or datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        self.log_file: Path = self.log_dir / f"{self.session_name}.csv"

        # 内存缓冲区，减少频繁IO
        self._buffer: List[LogFrame] = []
        self._buffer_size: int = 10  # 每10帧刷盘一次
        self._total_frames: int = 0
        self._is_recording: bool = False

        # 确保日志目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def start_session(self) -> None:
        """开始新的记录会话，写入CSV头部"""
        with open(self.log_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self.CSV_HEADERS)
        self._is_recording = True
        self._total_frames = 0
        print(f"[Logger] 会话已启动，日志文件: {self.log_file}")

    def log_frame(
        self,
        position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        disturbance: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        detections: Optional[List[Dict[str, Any]]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        记录一帧数据。

        参数:
            position: 无人机位置 (x, y, z)，单位 cm
            disturbance: 扰动估计 (dx, dy, dz)，单位 cm/s²
            detections: YOLO检测结果列表，每项为字典
            extra: 任意额外数据字典（会被序列化为JSON）
        """
        if not self._is_recording:
            raise RuntimeError("日志记录器未启动，请先调用 start_session()")

        detections = detections or []
        frame = LogFrame(
            timestamp=time.time(),
            datetime_str=datetime.now().isoformat(),
            pos_x=position[0],
            pos_y=position[1],
            pos_z=position[2],
            dist_dx=disturbance[0],
            dist_dy=disturbance[1],
            dist_dz=disturbance[2],
            detection_count=len(detections),
            detections_json=json.dumps(detections, ensure_ascii=False),
            extra=json.dumps(extra, ensure_ascii=False) if extra else "",
        )

        self._buffer.append(frame)
        self._total_frames += 1

        # 缓冲区满时刷盘
        if len(self._buffer) >= self._buffer_size:
            self._flush()

    def _flush(self) -> None:
        """将缓冲区数据写入CSV文件"""
        if not self._buffer:
            return

        with open(self.log_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for frame in self._buffer:
                writer.writerow([
                    f"{frame.timestamp:.6f}",
                    frame.datetime_str,
                    f"{frame.pos_x:.2f}",
                    f"{frame.pos_y:.2f}",
                    f"{frame.pos_z:.2f}",
                    f"{frame.dist_dx:.4f}",
                    f"{frame.dist_dy:.4f}",
                    f"{frame.dist_dz:.4f}",
                    frame.detection_count,
                    frame.detections_json,
                    frame.extra,
                ])

        self._buffer.clear()

    def save(self) -> Path:
        """保存所有剩余数据到文件，返回文件路径"""
        self._flush()
        print(
            f"[Logger] 会话已保存: {self.log_file} "
            f"(共 {self._total_frames} 帧)"
        )
        return self.log_file

    def stop(self) -> Path:
        """停止记录并保存"""
        self._is_recording = False
        return self.save()

    def __enter__(self) -> FlightLogger:
        """支持 with 语句"""
        self.start_session()
        return self

    def __exit__(self, *args: Any) -> None:
        """退出 with 时自动保存"""
        self.stop()

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def total_frames(self) -> int:
        return self._total_frames
