"""Adaptive JPEG compressor with purpose-based quality presets.

🔧 Status: helper implemented and unit-tested; not yet wired into the
agent's screenshot stream (currently the backend's
``device_bridge/platforms/windows/screenshot.py`` hardcodes quality=85).
Integration is tracked under screenshot-optimization.md §4.2.

Two compression modes
---------------------
1. **By purpose**: ``compress(image, purpose="recognition")`` picks a
   quality from ``QUALITY_PRESETS`` (95/80/70/50 for
   recognition/monitor/stream/thumbnail). The ``default_quality`` constructor
   arg is consumed when ``purpose`` is unknown — callers should pass
   ``config.jpeg_quality`` here to activate the previously-dead config field.

2. **By target size**: ``compress_for_stream(image, target_size_kb=50)``
   binary-searches the quality parameter to hit the size budget. Used for
   low-latency streaming where bandwidth is the constraint.

Network-aware adjustment
------------------------
``update_bandwidth(rtt_ms)`` records the latest network round-trip time;
when RTT is high, ``_get_quality`` downshifts by one preset to reduce
payload size. This is a coarse heuristic — a real implementation would
also consider loss rate and TCP window — but it preserves the API contract
from the design doc.
"""

from __future__ import annotations

import logging
import time

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class AdaptiveJPEGCompressor:
    """Adaptive JPEG compressor with purpose presets and target-size mode.

    Args:
        default_quality: JPEG quality [1, 100] used when ``purpose`` is
            unknown. Should be sourced from ``config.jpeg_quality`` (default
            80) so the previously-dead config field is activated.
        rtt_threshold_ms: RTT above which quality is downshifted by one
            preset. Default 300ms (cellular / congested wifi).
    """

    QUALITY_PRESETS: dict[str, int] = {
        "recognition": 95,
        "monitor": 80,
        "stream": 70,
        "thumbnail": 50,
    }

    def __init__(self, default_quality: int = 80, rtt_threshold_ms: float = 300.0):
        if not 1 <= default_quality <= 100:
            raise ValueError(
                f"default_quality must be in [1, 100], got {default_quality}",
            )
        self._default_quality = int(default_quality)
        self._rtt_threshold_ms = float(rtt_threshold_ms)
        self._rtt_ms: float = 0.0
        self._rtt_updated_at: float = 0.0
        # RTT readings decay after this many seconds (avoid acting on stale data)
        self._rtt_decay_seconds: float = 30.0

    # ── Public API ──────────────────────────────────────────────
    @property
    def default_quality(self) -> int:
        """Configured default quality."""
        return self._default_quality

    @property
    def current_rtt_ms(self) -> float:
        """Most recent RTT reading (0.0 if never updated)."""
        return self._rtt_ms

    def update_bandwidth(self, rtt_ms: float) -> None:
        """Record the latest network RTT (ms). Used for adaptive downshift."""
        if rtt_ms < 0:
            logger.warning("AdaptiveJPEGCompressor: negative RTT ignored: %s", rtt_ms)
            return
        self._rtt_ms = float(rtt_ms)
        self._rtt_updated_at = time.monotonic()

    def compress(self, image: np.ndarray, purpose: str = "monitor") -> bytes:
        """Compress BGR image to JPEG bytes, choosing quality by purpose.

        Args:
            image: BGR numpy array (H, W, 3).
            purpose: One of 'recognition' / 'monitor' / 'stream' /
                'thumbnail' (case-insensitive). Unknown purposes fall back
                to ``default_quality``.

        Returns:
            JPEG-encoded bytes.
        """
        if image is None or image.size == 0:
            raise ValueError("image is None or empty")

        quality = self._get_quality(purpose)
        return self._encode(image, quality)

    def compress_for_stream(
        self,
        image: np.ndarray,
        target_size_kb: int = 50,
        min_quality: int = 30,
        max_quality: int = 95,
    ) -> bytes:
        """Compress to a target byte size via binary search on quality.

        Args:
            image: BGR numpy array.
            target_size_kb: Maximum JPEG size in KB. Default 50.
            min_quality: Lower bound for binary search. Default 30.
            max_quality: Upper bound for binary search. Default 95.

        Returns:
            JPEG-encoded bytes ≤ target_size_kb when feasible. If even
            min_quality exceeds the budget, returns the min_quality encoding
            (best effort).
        """
        if image is None or image.size == 0:
            raise ValueError("image is None or empty")
        if not 1 <= min_quality <= max_quality <= 100:
            raise ValueError(
                f"quality bounds invalid: min={min_quality}, max={max_quality}",
            )

        low, high = min_quality, max_quality
        best_bytes: bytes | None = None

        while low <= high:
            mid = (low + high) // 2
            encoded = self._encode(image, mid)
            size_kb = len(encoded) / 1024

            if size_kb <= target_size_kb:
                best_bytes = encoded
                low = mid + 1  # try higher quality
            else:
                high = mid - 1  # too big, lower quality

        if best_bytes is not None:
            return best_bytes

        # Even min_quality exceeds budget — return min_quality encoding.
        logger.warning(
            "compress_for_stream: target %d KB unachievable, returning min_quality=%d",
            target_size_kb, min_quality,
        )
        return self._encode(image, min_quality)

    # ── Internal helpers ───────────────────────────────────────
    def _get_quality(self, purpose: str) -> int:
        """Resolve quality for a purpose, applying RTT-based downshift."""
        purpose_lower = purpose.lower() if isinstance(purpose, str) else ""
        quality = self.QUALITY_PRESETS.get(purpose_lower, self._default_quality)

        # RTT-aware downshift: if RTT is high and recently updated, drop one
        # preset level to reduce payload size.
        if self._rtt_is_high():
            downshifted = max(1, quality - 10)
            logger.debug(
                "AdaptiveJPEGCompressor: high RTT %.0fms, downshift %d→%d",
                self._rtt_ms, quality, downshifted,
            )
            quality = downshifted

        return quality

    def _rtt_is_high(self) -> bool:
        """True if RTT reading is recent and exceeds threshold."""
        if self._rtt_ms <= 0:
            return False
        age = time.monotonic() - self._rtt_updated_at
        if age > self._rtt_decay_seconds:
            return False  # stale reading
        return self._rtt_ms > self._rtt_threshold_ms

    @staticmethod
    def _encode(image: np.ndarray, quality: int) -> bytes:
        """Encode image to JPEG bytes at the given quality."""
        encode_param = [cv2.IMWRITE_JPEG_QUALITY, int(quality)]
        ok, buf = cv2.imencode(".jpg", image, encode_param)
        if not ok:
            raise RuntimeError(f"cv2.imencode failed at quality={quality}")
        return buf.tobytes()
