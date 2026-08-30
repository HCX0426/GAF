"""截图竞速测试 — 对比 WGC/DXGI/GDI/PrintWindow 各方法延迟 + 可靠性

TD-006 修复 (N141): 旧版 benchmark 只测速度，导致 _detect_best_method 选了
最快的 GDI (13ms)，但 GDI BitBlt 截不到被遮挡窗口。新版增加"可靠性"维度：
对比每种方法的截图与 PrintWindow ground-truth 的像素差，差异大的方法标记为
is_reliable=False，不参与速度排名 (排在可靠方法之后)。

排序规则: reliable 方法按速度升序 → unreliable 方法按速度升序 (供 debug)。
screenshot.py 的 _detect_best_method 取 [0][0] 仍是最快且可靠的方法。
"""

import logging
import time
from typing import NamedTuple

import numpy as np

logger = logging.getLogger(__name__)

# Methods with reliability score below this threshold are excluded from the
# top of the speed ranking. 0.95 means avg pixel diff < 12.75/255 (≈5% per
# channel). Tuned to catch GDI-vs-PrintWindow divergence on occluded windows
# (typical diff > 0.3 → score < 0.7) while tolerating minor codec noise.
RELIABILITY_THRESHOLD = 0.95


class BenchmarkResult(NamedTuple):
    """Result of benchmarking a single capture method.

    Fields:
        method: Method name (wgc/dxgi/gdi/printwindow)
        latency_ms: Average capture latency in milliseconds (lower = faster)
        reliability: Similarity score vs PrintWindow ground truth
                     (1.0 = identical, 0.0 = totally different).
                     1.0 when ground truth is unavailable or reliability
                     check is skipped (e.g., DXGI desktop capture).
        is_reliable: True if reliability >= RELIABILITY_THRESHOLD.
                     Reliable methods participate in the speed ranking;
                     unreliable methods are sorted after reliable ones.
        frame_shape: Shape of the captured frame (height, width, channels),
                     or None on failure. Used for debugging dimension
                     mismatches that can cause reliability=0.
    """
    method: str
    latency_ms: float
    reliability: float
    is_reliable: bool
    frame_shape: tuple | None = None


def benchmark_capture_methods(hwnd: int) -> list[BenchmarkResult]:
    """依次测试各截图方法的平均延迟 + 可靠性，返回排序结果

    每种方法截图 10 帧取平均延迟，并捕获一帧与 PrintWindow ground-truth 对比
    计算可靠性分数。不可靠的方法 (reliability < RELIABILITY_THRESHOLD) 排在
    可靠方法之后，避免 _detect_best_method 选中"快但截不到内容"的方法。

    Args:
        hwnd: 目标窗口句柄

    Returns:
        [BenchmarkResult, ...] 排序结果：
        - 可靠方法按 latency_ms 升序在前
        - 不可靠方法按 latency_ms 升序在后 (供 debug)
        取 [0][0] 即为最快且可靠的方法名。
    """
    test_frames = 10
    ground_truth = _capture_ground_truth(hwnd)
    if ground_truth is not None:
        logger.info(
            "Ground truth captured via PrintWindow: shape=%s",
            ground_truth.shape,
        )
    else:
        logger.warning(
            "Ground truth 捕获失败，跳过可靠性检查 (仅按速度排名)"
        )

    raw_results: list[BenchmarkResult] = []

    # --- 测试 WGC ---
    try:
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        if wgc.initialize(hwnd):
            latency, frame = _measure_with_frame(wgc, test_frames)
            if latency is not None:
                reliability, is_reliable = _compute_reliability(frame, ground_truth)
                raw_results.append(BenchmarkResult(
                    method="wgc",
                    latency_ms=latency,
                    reliability=reliability,
                    is_reliable=is_reliable,
                    frame_shape=tuple(frame.shape) if frame is not None else None,
                ))
                logger.info(
                    "WGC: %.1fms, reliability=%.4f (%s)",
                    latency, reliability, "OK" if is_reliable else "UNRELIABLE",
                )
            else:
                logger.info("WGC 初始化成功但截图失败")
            wgc.release()
        else:
            logger.info("WGC 初始化失败，跳过测试")
    except Exception as exc:
        logger.info("WGC 测试异常: %s", exc)

    # --- 测试 DXGI (Desktop Duplication) ---
    # DXGI captures the entire desktop, not a specific window. Pixel-by-pixel
    # comparison with PrintWindow (window-only) would always fail, so we skip
    # reliability for DXGI and assume reliable (it's reliable when available).
    try:
        latency, frame = _measure_dxgi_with_frame(hwnd, test_frames)
        if latency is not None:
            raw_results.append(BenchmarkResult(
                method="dxgi",
                latency_ms=latency,
                reliability=1.0,  # skipped — different capture region
                is_reliable=True,
                frame_shape=tuple(frame.shape) if frame is not None else None,
            ))
            logger.info(
                "DXGI: %.1fms, reliability=skipped (desktop capture)",
                latency,
            )
    except Exception as exc:
        logger.info("DXGI 测试异常: %s", exc)

    # --- 测试 GDI ---
    try:
        latency, frame = _measure_gdi_with_frame(hwnd, test_frames)
        if latency is not None:
            reliability, is_reliable = _compute_reliability(frame, ground_truth)
            raw_results.append(BenchmarkResult(
                method="gdi",
                latency_ms=latency,
                reliability=reliability,
                is_reliable=is_reliable,
                frame_shape=tuple(frame.shape) if frame is not None else None,
            ))
            logger.info(
                "GDI: %.1fms, reliability=%.4f (%s)",
                latency, reliability, "OK" if is_reliable else "UNRELIABLE",
            )
    except Exception as exc:
        logger.info("GDI 测试异常: %s", exc)

    # --- 测试 PrintWindow ---
    try:
        latency, frame = _measure_printwindow_with_frame(hwnd, test_frames)
        if latency is not None:
            # PrintWindow IS the ground truth source, so reliability is 1.0
            # by definition (compared to itself). Still measure to log latency.
            reliability, is_reliable = _compute_reliability(frame, ground_truth)
            raw_results.append(BenchmarkResult(
                method="printwindow",
                latency_ms=latency,
                reliability=reliability,
                is_reliable=is_reliable,
                frame_shape=tuple(frame.shape) if frame is not None else None,
            ))
            logger.info(
                "PrintWindow: %.1fms, reliability=%.4f (%s)",
                latency, reliability, "OK" if is_reliable else "UNRELIABLE",
            )
    except Exception as exc:
        logger.info("PrintWindow 测试异常: %s", exc)

    # Sort: reliable methods first (by speed), unreliable last (by speed).
    # This ensures _detect_best_method picks the fastest RELIABLE method.
    reliable = [r for r in raw_results if r.is_reliable]
    unreliable = [r for r in raw_results if not r.is_reliable]
    reliable.sort(key=lambda r: r.latency_ms)
    unreliable.sort(key=lambda r: r.latency_ms)
    sorted_results = reliable + unreliable

    logger.info(
        "竞速结果 (可靠→不可靠, 各组按速度升序): %s",
        [(r.method, f"{r.latency_ms:.1f}ms", f"rel={r.reliability:.3f}")
         for r in sorted_results],
    )
    return sorted_results


def _capture_ground_truth(hwnd: int) -> np.ndarray | None:
    """Capture a ground-truth frame using PrintWindow for reliability comparison.

    PrintWindow is the most reliable method for capturing occluded windows —
    it sends WM_PRINT directly to the target window, which renders its own
    content regardless of what's on top. Other methods (GDI BitBlt) capture
    what's visible on screen, which may be a different window's pixels if the
    target is occluded. Comparing each method's capture to this ground truth
    catches the GDI-can't-capture-occluded bug (TD-003 / N141) at benchmark
    time instead of at template_match time.

    Falls back to GDI if PrintWindow is unavailable. Returns None if both fail
    (benchmark then degrades to speed-only ranking).

    Args:
        hwnd: Target window handle

    Returns:
        BGR numpy array, or None on failure
    """
    from platforms.windows.screenshot import ScreenshotManager

    if not hwnd:
        # No hwnd — desktop capture. Use GDI as ground truth (PrintWindow
        # requires a window handle).
        mgr = ScreenshotManager(hwnd=None, method=ScreenshotManager.GDI)
        return mgr.capture()

    # Try PrintWindow first (most reliable for occluded windows).
    mgr = ScreenshotManager(
        hwnd=hwnd,
        method=ScreenshotManager.PRINTWINDOW,
        client_only=True,
    )
    frame = mgr.capture()
    if frame is not None:
        return frame

    # Fallback to GDI (works when window is not occluded, which is the
    # expected case during benchmark — if the window IS occluded at
    # benchmark time, GDI will produce wrong pixels, but then PrintWindow
    # above should have succeeded).
    mgr = ScreenshotManager(
        hwnd=hwnd,
        method=ScreenshotManager.GDI,
        client_only=True,
    )
    return mgr.capture()


def _compute_reliability(
    frame: np.ndarray | None,
    ground_truth: np.ndarray | None,
) -> tuple[float, bool]:
    """Compute reliability score of a captured frame vs ground truth.

    Uses mean absolute difference (MAD) normalized to [0, 1]:
        score = 1.0 - mean(|frame - ground_truth|) / 255.0

    Args:
        frame: The captured frame to evaluate (BGR numpy array)
        ground_truth: The reference frame (from PrintWindow)

    Returns:
        (score, is_reliable) where:
        - score: 1.0 = identical, 0.0 = totally different
        - is_reliable: True if score >= RELIABILITY_THRESHOLD

    Edge cases:
        - ground_truth is None → (1.0, True) — assume reliable, speed-only
        - frame is None → (0.0, False)
        - shape mismatch → (0.0, False) — different dimensions = unreliable
    """
    if ground_truth is None:
        # Can't compute reliability — assume reliable (speed-only ranking).
        return 1.0, True
    if frame is None:
        return 0.0, False
    if frame.shape != ground_truth.shape:
        # Different dimensions = definitively unreliable. Common causes:
        # - DPI virtualization (1024x576 vs 1536x864) — see N141
        # - client_only mismatch (window rect vs client rect)
        logger.debug(
            "Reliability shape mismatch: frame=%s vs ground_truth=%s",
            frame.shape, ground_truth.shape,
        )
        return 0.0, False

    diff = np.mean(np.abs(
        frame.astype(np.float32) - ground_truth.astype(np.float32)
    )) / 255.0
    score = 1.0 - float(diff)
    return score, score >= RELIABILITY_THRESHOLD


def _measure_with_frame(
    capture_obj, frames: int,
) -> tuple[float | None, np.ndarray | None]:
    """Measure avg latency of a capture object and return one sample frame.

    Args:
        capture_obj: Object with capture() method returning np.ndarray or None
        frames: Number of successful captures to average

    Returns:
        (avg_latency_ms, sample_frame) — either may be None on failure.
        sample_frame is the first successful capture (cheapest to obtain).
    """
    times: list[float] = []
    sample_frame: np.ndarray | None = None
    for _ in range(frames + 2):
        start = time.perf_counter()
        result = capture_obj.capture()
        elapsed = (time.perf_counter() - start) * 1000.0
        if result is not None:
            times.append(elapsed)
            if sample_frame is None:
                sample_frame = result
        if len(times) >= frames:
            break

    if not times:
        return None, None
    return sum(times) / len(times), sample_frame


def _measure_method(capture_obj, frames: int) -> float | None:
    """测量通用截图对象的平均延迟 (向后兼容 wrapper)

    旧版 API，仅返回延迟。新版 _measure_with_frame 同时返回样本帧用于
    可靠性对比。新代码应直接调用 _measure_with_frame。

    Args:
        capture_obj: 截图对象，需有 capture() 方法返回 np.ndarray
        frames: 测试帧数

    Returns:
        平均延迟（毫秒），失败返回 None
    """
    latency, _ = _measure_with_frame(capture_obj, frames)
    return latency


def _measure_dxgi_with_frame(
    hwnd: int, frames: int,
) -> tuple[float | None, np.ndarray | None]:
    """测试 DXGI 桌面复制延迟 + 返回样本帧

    Note: DXGI captures the entire desktop, not a specific window. The
    returned frame will have desktop dimensions, not window dimensions.
    Reliability comparison is skipped for DXGI in benchmark_capture_methods.
    """
    from platforms.windows.screenshot import ScreenshotManager

    # hwnd intentionally None — DXGI is desktop duplication, not window-scoped.
    mgr = ScreenshotManager(hwnd=None, method=ScreenshotManager.DXGI)
    return _measure_with_frame(mgr, frames)


def _measure_gdi_with_frame(
    hwnd: int, frames: int,
) -> tuple[float | None, np.ndarray | None]:
    """测试 GDI 截图延迟 + 返回样本帧"""
    from platforms.windows.screenshot import ScreenshotManager

    mgr = ScreenshotManager(
        hwnd=hwnd, method=ScreenshotManager.GDI, client_only=True,
    )
    return _measure_with_frame(mgr, frames)


def _measure_printwindow_with_frame(
    hwnd: int, frames: int,
) -> tuple[float | None, np.ndarray | None]:
    """测试 PrintWindow 截图延迟 + 返回样本帧"""
    from platforms.windows.screenshot import ScreenshotManager

    mgr = ScreenshotManager(
        hwnd=hwnd, method=ScreenshotManager.PRINTWINDOW, client_only=True,
    )
    return _measure_with_frame(mgr, frames)
