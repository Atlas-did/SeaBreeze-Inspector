"""
Tello视频流 — 独立线程获取帧, 通过Queue解耦生产者-消费者
"""

import queue
import threading
import time

import numpy as np


class TelloVideoStream:
    """Tello视频流, 生产者(抓帧线程) → Queue → 消费者(get_frame)"""

    def __init__(self, tello_controller=None, mock: bool = False):
        self.tello = tello_controller
        self.mock = mock
        self._running = False
        self._thread: threading.Thread | None = None
        self._fps = 0.0
        self._frame_count = 0
        self._last_time = time.time()
        # Queue用于生产者-消费者解耦 (P0-6: 正确使用队列)
        self._frame_queue = queue.Queue(maxsize=2)
        # 最新帧缓存 (线程安全读取)
        self._latest_frame: np.ndarray | None = None
        self._frame_lock = threading.Lock()

    def start(self) -> bool:
        """启动视频采集线程"""
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        return True

    def _capture_loop(self):
        """生产者: 持续抓帧, 放入队列"""
        while self._running:
            if self.mock:
                # 模拟帧: 640x480 随机色块
                frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
                self._enqueue_frame(frame)
                time.sleep(1 / 30)
            elif self.tello and self.tello._tello:
                try:
                    frame_reader = self.tello._tello.get_frame_read()
                    frame = frame_reader.frame
                    if frame is not None:
                        self._enqueue_frame(frame)
                except Exception:
                    time.sleep(0.05)
            else:
                time.sleep(0.1)

    def _enqueue_frame(self, frame: np.ndarray):
        """将帧放入队列 (丢弃旧帧以保持低延迟)"""
        # 如果队列满了, 丢弃最旧的帧
        try:
            self._frame_queue.put_nowait(frame)
        except queue.Full:
            try:
                self._frame_queue.get_nowait()  # 丢弃旧帧
                self._frame_queue.put_nowait(frame)  # 放入新帧
            except queue.Empty:
                pass

        # 更新最新帧缓存 (线程安全)
        with self._frame_lock:
            self._latest_frame = frame

        # FPS统计
        self._frame_count += 1
        now = time.time()
        if now - self._last_time >= 1.0:
            self._fps = self._frame_count / (now - self._last_time)
            self._frame_count = 0
            self._last_time = now

    def get_frame(self) -> np.ndarray | None:
        """消费者: 获取最新帧 (非阻塞, 线程安全)"""
        # 尝试从队列获取最新帧
        try:
            frame = self._frame_queue.get_nowait()
            # 清空队列中所有旧帧, 只保留最新
            while not self._frame_queue.empty():
                try:
                    frame = self._frame_queue.get_nowait()
                except queue.Empty:
                    break
            with self._frame_lock:
                self._latest_frame = frame
            return frame
        except queue.Empty:
            # 队列为空, 返回缓存的最新帧
            with self._frame_lock:
                return self._latest_frame

    def stop(self):
        """停止视频采集"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    @property
    def fps(self) -> float:
        return self._fps
