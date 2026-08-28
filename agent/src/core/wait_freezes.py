"""WaitFreezes: frame comparison based freeze detection.

Detects when screen content has stabilized (no longer changing) by comparing
consecutive frames. Useful for replacing fixed sleep/delay waits with adaptive
waiting that proceeds as soon as the screen becomes stable.

Reference: MaaFramework's TemplateComparator / WaitFreezes strategy.
"""

import contextlib
import logging
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class ScreenChangeOutcome(StrEnum):
    """轻量竞态防护结果（spec 阶段 4.2.1 — 任务 1.7）。

    与 bool 不同，让 ClickNode 能区分多种"画面没变"的原因：
    - CHANGED: 画面变化，可继续下一步（正常路径）
    - UNCHANGED: 2s 内画面无变化（疑似竞态，但可能是"点击选中"等正常场景）
    - TIMEOUT: 等待超时（设备异常或响应过慢，需告警）
    - SKIPPED: 跳过检测（配置关闭或无 capture_fn）
    """

    CHANGED = "CHANGED"
    UNCHANGED = "UNCHANGED"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"


class WaitFreezes:
    """Wait until screen content stabilizes by comparing consecutive frames.

    Instead of using fixed delays (e.g., sleep(2000)), this class captures
    frames at intervals and compares them pixel-by-pixel. When consecutive
    frames are similar enough (below threshold), the screen is considered
    stable and waiting ends.

    Usage:
        wf = WaitFreezes()
        capture_func = lambda: device.capture_screen()
        stable = wf.wait(capture_func, timeout=5.0, similarity=0.99)
        if stable:
            print("Screen stabilized")
        else:
            print("Timeout - screen still changing")
    """

    def __init__(
        self,
        interval_ms: float = 50.0,
        stable_frames: int = 3,
        default_similarity: float = 0.99,
        diff_region: tuple[int, int, int, int] | None = None,
    ):
        """Initialize WaitFreezes detector

        Args:
            interval_ms: Milliseconds between frame captures (default 50ms)
            stable_frames: Number of consecutive similar frames required (default 3)
            default_similarity: Minimum similarity ratio to consider frames equal (0-1)
            diff_region: Optional (x, y, w, h) ROI to compare instead of full image
        """
        self._interval = interval_ms / 1000.0
        self._stable_frames = stable_frames
        self._default_similarity = default_similarity
        self._diff_region = diff_region
        self._prev_frame: np.ndarray | None = None
        self._stable_count = 0

    def wait(
        self,
        capture_fn: Callable[[], Any],
        timeout: float = 10.0,
        similarity: float | None = None,
        on_frame: Callable[[np.ndarray], None] | None = None,
    ) -> bool:
        """Wait until screen content stabilizes

        Repeatedly calls capture_fn and compares consecutive frames.
        Returns True when the screen is stable, or False on timeout.

        Args:
            capture_fn: Callable that returns BGR numpy array (or None)
            timeout: Maximum seconds to wait (default 10.0)
            similarity: Override default minimum similarity (0-1)
            on_frame: Optional callback called with each captured frame

        Returns:
            True if screen stabilized within timeout, False otherwise
        """
        sim_threshold = similarity if similarity is not None else self._default_similarity
        self._prev_frame = None
        self._stable_count = 0

        start_time = time.monotonic()
        iteration = 0

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                logger.info(
                    "WaitFreezes timeout after %.1fs (%d iterations, stable_count=%d)",
                    elapsed, iteration, self._stable_count,
                )
                return False

            frame = capture_fn()
            if frame is None:
                time.sleep(self._interval)
                continue

            if callable(on_frame):
                with contextlib.suppress(Exception):
                    on_frame(frame)

            if self._prev_frame is not None:
                sim = self._compare_frames(self._prev_frame, frame)

                if sim >= sim_threshold:
                    self._stable_count += 1
                    if self._stable_count >= self._stable_frames:
                        logger.info(
                            "Screen stable after %.1fs (%d iterations, sim=%.4f)",
                            elapsed, iteration, sim,
                        )
                        return True
                else:
                    self._stable_count = 0

            self._prev_frame = frame.copy()
            iteration += 1
            time.sleep(self._interval)

    def wait_for_change(
        self,
        capture_fn: Callable[[], Any],
        timeout: float = 30.0,
        change_threshold: float = 0.01,
    ) -> bool:
        """Wait until screen content changes (inverse of wait)

        Useful for detecting when a loading screen disappears or when
        an animation completes. Returns True when change is detected.

        Args:
            capture_fn: Callable returning BGR numpy array
            timeout: Maximum seconds to wait
            change_threshold: Minimum difference ratio to count as changed (0-1)

        Returns:
            True if change detected, False on timeout
        """
        baseline = capture_fn()
        if baseline is None:
            return False

        start_time = time.monotonic()
        iteration = 0

        while True:
            if time.monotonic() - start_time >= timeout:
                logger.info("waitForChange timeout after %d iterations", iteration)
                return False

            time.sleep(self._interval)
            frame = capture_fn()
            if frame is None:
                continue

            sim = self._compare_frames(baseline, frame)
            diff = 1.0 - sim

            if diff >= change_threshold:
                logger.info(
                    "Screen changed after %d iterations (diff=%.4f)", iteration, diff
                )
                return True

            iteration += 1

    def wait_for_change_lightweight(
        self,
        capture_fn: Callable[[], Any],
        timeout: float = 2.0,
        change_threshold: float = 0.01,
        poll_interval: float = 0.1,
    ) -> ScreenChangeOutcome:
        """轻量竞态防护：检测点击后画面是否变化（spec 阶段 4.2.1 — 任务 1.7）。

        与 ``wait_for_change`` 的区别：
        - 默认 2s 超时（不是 30s），适应点击-导航竞态的快速判断
        - 返回 ``ScreenChangeOutcome`` 枚举（CHANGED/UNCHANGED/TIMEOUT/SKIPPED），
          不是 bool，让 ClickNode 能区分"画面没变"与"设备异常"
        - 画面变化立即返回（不等稳定），未变化只记 warning 不 fail
        - 捕获 capture_fn 异常并降级为 TIMEOUT，不向上传播

        设计原则（spec 4.1）：
        - 默认轻量防护：ClickNode 默认调用此方法，2s 内画面变化则立即继续
        - UNCHANGED 只记 warning 不 fail（兼容"点击选中"等正常无变化场景）
        - 配合 post_verify 强验证：关键节点可额外配置 post_verify 失败则 fail

        Args:
            capture_fn: 设备截图函数，返回 BGR numpy 数组或 None
            timeout: 最长等待秒数（默认 2.0）
            change_threshold: 判定变化的最小差异比例（0-1，默认 0.01 = 1%）
            poll_interval: 轮询间隔秒数（默认 0.1）

        Returns:
            ScreenChangeOutcome 枚举值
        """
        # 捕获 baseline，异常降级为 SKIPPED（无法检测变化）
        try:
            baseline = capture_fn()
        except Exception as exc:
            logger.warning(
                "wait_for_change_lightweight: baseline capture failed: %s", exc,
            )
            return ScreenChangeOutcome.SKIPPED

        if baseline is None:
            # 首帧就 None（设备未就绪或无截图函数），跳过检测
            return ScreenChangeOutcome.SKIPPED

        start_time = time.monotonic()
        iteration = 0
        none_count = 0

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                logger.info(
                    "wait_for_change_lightweight: UNCHANGED after %.1fs (%d polls)",
                    elapsed, iteration,
                )
                return ScreenChangeOutcome.UNCHANGED

            time.sleep(poll_interval)
            iteration += 1

            # 捕获异常：单次失败不立即降级，连续 None 才判 TIMEOUT
            try:
                frame = capture_fn()
            except Exception as exc:
                logger.warning(
                    "wait_for_change_lightweight: capture failed (iter %d): %s",
                    iteration, exc,
                )
                none_count += 1
                if none_count >= 3:
                    return ScreenChangeOutcome.TIMEOUT
                continue

            if frame is None:
                none_count += 1
                if none_count >= 3:
                    logger.warning(
                        "wait_for_change_lightweight: TIMEOUT after %d None polls",
                        none_count,
                    )
                    return ScreenChangeOutcome.TIMEOUT
                continue

            # 重置 none_count：成功捕获到帧
            none_count = 0

            sim = self._compare_frames(baseline, frame)
            diff = 1.0 - sim

            if diff >= change_threshold:
                logger.info(
                    "wait_for_change_lightweight: CHANGED after %d polls (diff=%.4f)",
                    iteration, diff,
                )
                return ScreenChangeOutcome.CHANGED

    def _compare_frames(self, frame_a: np.ndarray, frame_b: np.ndarray) -> float:
        """Compute similarity ratio between two frames

        Compares pixel values in the configured region of interest.
        Returns value between 0.0 (completely different) and 1.0 (identical).

        Args:
            frame_a: First BGR frame
            frame_b: Second BGR frame

        Returns:
            Similarity ratio (0-1)
        """
        try:
            a = self._roi(frame_a).astype(np.float32)
            b = self._roi(frame_b).astype(np.float32)

            if a.shape != b.shape:
                min_h = min(a.shape[0], b.shape[0])
                min_w = min(a.shape[1], b.shape[1])
                a = a[:min_h, :min_w]
                b = b[:min_h, :min_w]

            total_pixels = a.shape[0] * a.shape[1]
            if total_pixels == 0:
                return 0.0

            diff = np.abs(a - b)
            max_diff = np.maximum(diff.max(), 1.0)
            normalized_diff = diff / max_diff
            matching_pixels = np.sum(normalized_diff < 0.05)
            similarity = matching_pixels / total_pixels

            return float(similarity)

        except Exception as exc:
            logger.debug("Frame comparison error: %s", exc)
            return 0.0

    def _roi(self, frame: np.ndarray) -> np.ndarray:
        """Extract region of interest from frame

        If diff_region is set, crops to that rectangle.
        Otherwise returns the full frame.

        Args:
            frame: BGR numpy array

        Returns:
            Cropped or original frame
        """
        if self._diff_region is None:
            return frame

        x, y, w, h = self._diff_region
        fh, fw = frame.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(fw, x + w)
        y2 = min(fh, y + h)
        return frame[y1:y2, x1:x2]

    def reset(self) -> None:
        """Reset internal state (previous frame, stable counter)"""
        self._prev_frame = None
        self._stable_count = 0

    @property
    def config(self) -> dict:
        """Current configuration"""
        return {
            "interval_ms": self._interval * 1000,
            "stable_frames": self._stable_frames,
            "similarity": self._default_similarity,
            "diff_region": self._diff_region,
        }
