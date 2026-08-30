"""FramePool — 内存中缓存最近 N 帧截图，支持时间戳检索"""

import threading

import numpy as np


class FramePool:
    """按时间戳索引的帧缓存池

    在内存中缓存最近 N 帧截图，支持获取最新帧和按时间戳查找。
    线程安全。
    """

    def __init__(self, max_frames: int = 30):
        """初始化帧池

        Args:
            max_frames: 最大缓存帧数，默认 30
        """
        self._max_frames = max_frames
        self._frames: list[tuple[float, np.ndarray]] = []
        self._lock = threading.Lock()

    def add(self, frame: np.ndarray, timestamp: float) -> None:
        """添加一帧到缓存池

        Args:
            frame: 截图帧数据（numpy 数组）
            timestamp: 帧时间戳（秒，如 time.time()）

        TD-359: 校验帧有效性，无效帧（None/空/全黑）跳过不缓存。
        """
        if frame is None:
            return
        if frame.size == 0:
            return
        # 全黑帧检查: 所有像素值之和为 0
        if np.sum(frame) == 0:
            return

        with self._lock:
            self._frames.append((timestamp, frame.copy()))
            if len(self._frames) > self._max_frames:
                self._frames = self._frames[-self._max_frames:]

    def get_latest(self) -> np.ndarray | None:
        """获取最新缓存帧

        Returns:
            最新帧的 numpy 数组，缓存为空时返回 None
        """
        with self._lock:
            if not self._frames:
                return None
            return self._frames[-1][1].copy()

    def get_by_timestamp(self, ts: float) -> np.ndarray | None:
        """按时间戳查找最接近的缓存帧

        Args:
            ts: 目标时间戳（秒）

        Returns:
            最接近时间戳的帧的 numpy 数组，缓存为空时返回 None
        """
        with self._lock:
            if not self._frames:
                return None
            closest = min(self._frames, key=lambda item: abs(item[0] - ts))
            return closest[1].copy()

    def clear(self) -> None:
        """清空所有缓存帧"""
        with self._lock:
            self._frames.clear()

    @property
    def size(self) -> int:
        """当前缓存帧数"""
        with self._lock:
            return len(self._frames)

    @property
    def max_frames(self) -> int:
        """最大缓存帧数"""
        return self._max_frames
