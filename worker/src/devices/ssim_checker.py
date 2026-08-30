"""SSIM-based duplicate frame detector for screenshot dedup.

🔧 Status: helper implemented and unit-tested; not yet wired into the
ScreenshotManager.capture() hot path (integration tracked under
screenshot-optimization.md §3.3 as a future P2 task).

Algorithm
---------
Primary: ``skimage.metrics.structural_similarity`` (multi-channel SSIM).
Fallback (when scikit-image is not installed): a PSNR-based proxy via
``cv2.PSNR`` mapped to a [0, 1] similarity score. The proxy is less
perceptually accurate but preserves the API contract so callers do not
need to know which backend is active.

Usage
-----
::

    checker = SSIMChecker(threshold=0.95, downsample=4)
    if checker.is_same_scene(current_frame):
        # Skip recognition — last frame is still valid.
        ...
    score = checker.compute(img_a, img_b)  # stateless, returns float

The stateful ``is_same_scene`` API mirrors the design in
``screenshot-optimization.md`` §3.2; the stateless ``compute`` API is
exposed for ad-hoc comparisons (e.g. benchmark / debug).
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Lazy-import scikit-image once. ``_SKIMAGE_AVAILABLE`` records whether the
# import succeeded so we don't retry on every call.
_SKIMAGE_AVAILABLE: bool | None = None
_STRUCTURAL_SIMILARITY = None  # type: ignore[type-arg]


def _load_skimage():
    """Try to import skimage.metrics.structural_similarity; cache the result."""
    global _SKIMAGE_AVAILABLE, _STRUCTURAL_SIMILARITY
    if _SKIMAGE_AVAILABLE is not None:
        return _SKIMAGE_AVAILABLE
    try:
        from skimage.metrics import structural_similarity as ssim_fn
        _STRUCTURAL_SIMILARITY = ssim_fn
        _SKIMAGE_AVAILABLE = True
        logger.info("SSIMChecker: using scikit-image backend")
    except ImportError:
        _SKIMAGE_AVAILABLE = False
        logger.warning(
            "SSIMChecker: scikit-image not installed, falling back to "
            "cv2.PSNR-based similarity proxy (less perceptually accurate)",
        )
    return _SKIMAGE_AVAILABLE


class SSIMChecker:
    """Stateful + stateless SSIM-based duplicate frame detector.

    Args:
        threshold: Similarity score in [0, 1] above which two frames are
            considered the same scene. Default 0.95.
        downsample: Integer factor used to shrink frames before comparison
            (computing SSIM on full-res frames is expensive). Default 4.
            Set to 1 to disable downsampling.
    """

    def __init__(self, threshold: float = 0.95, downsample: int = 4):
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold must be in [0, 1], got {threshold}")
        if downsample < 1:
            raise ValueError(f"downsample must be >= 1, got {downsample}")
        self._threshold = float(threshold)
        self._downsample = int(downsample)
        self._last_screenshot: np.ndarray | None = None
        self._last_score: float = 1.0
        _load_skimage()

    # ── Public API ──────────────────────────────────────────────
    @property
    def threshold(self) -> float:
        """Configured similarity threshold."""
        return self._threshold

    @property
    def last_score(self) -> float:
        """Most recent similarity score (1.0 if no comparison yet)."""
        return self._last_score

    @property
    def backend(self) -> str:
        """Active backend name: 'skimage' or 'cv2_psnr'."""
        return "skimage" if _SKIMAGE_AVAILABLE else "cv2_psnr"

    def compute(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """Compute similarity between two BGR images. Stateless.

        Args:
            img1: BGR numpy array (H, W, 3).
            img2: BGR numpy array (H, W, 3).

        Returns:
            Similarity score in [0, 1]. 1.0 = identical.
        """
        if img1 is None or img2 is None:
            return 0.0
        if img1.shape != img2.shape:
            # Resize img2 to match img1 to allow comparison of different sizes.
            try:
                img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
            except Exception as exc:
                logger.warning("SSIMChecker.compute: resize failed: %s", exc)
                return 0.0

        small1 = self._downsample_image(img1)
        small2 = self._downsample_image(img2)

        if _SKIMAGE_AVAILABLE and _STRUCTURAL_SIMILARITY is not None:
            try:
                # channel_axis=2 → multichannel (BGR) SSIM
                score = float(_STRUCTURAL_SIMILARITY(small1, small2, channel_axis=2))
                return max(0.0, min(1.0, score))
            except Exception as exc:
                logger.warning("SSIMChecker.compute: skimage failed (%s), falling back to PSNR", exc)

        return self._psnr_similarity(small1, small2)

    def is_same_scene(self, current: np.ndarray) -> bool:
        """Stateful: compare ``current`` against the previously seen frame.

        Updates internal state (last_screenshot + last_score). The first
        call always returns False (no baseline yet) and stores ``current``
        as the new baseline.

        Args:
            current: BGR numpy array.

        Returns:
            True if similarity >= threshold (scene unchanged).
        """
        if current is None:
            return False
        if self._last_screenshot is None:
            self._last_screenshot = current
            self._last_score = 1.0
            return False

        if self._last_screenshot.shape != current.shape:
            # Resolution changed — definitely a new scene.
            self._last_screenshot = current
            self._last_score = 0.0
            return False

        score = self.compute(self._last_screenshot, current)
        self._last_score = score
        self._last_screenshot = current
        return score >= self._threshold

    def reset(self) -> None:
        """Clear internal state (e.g. on device switch / pipeline reset)."""
        self._last_screenshot = None
        self._last_score = 1.0

    # ── Internal helpers ───────────────────────────────────────
    def _downsample_image(self, image: np.ndarray) -> np.ndarray:
        """Shrink image by ``downsample`` factor on each axis."""
        if self._downsample <= 1:
            return image
        h, w = image.shape[:2]
        new_w = max(1, w // self._downsample)
        new_h = max(1, h // self._downsample)
        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

    @staticmethod
    def _psnr_similarity(img1: np.ndarray, img2: np.ndarray) -> float:
        """Map cv2.PSNR output to a [0, 1] similarity score.

        PSNR returns dB: 100 dB ≈ identical, 0-30 dB ≈ very different.
        We use ``score = 1 - exp(-psnr/20)`` which gives:
          - psnr=50  → score ≈ 0.918
          - psnr=30  → score ≈ 0.777
          - psnr=10  → score ≈ 0.393
          - psnr=0   → score = 0
        This is a coarse proxy, not a true SSIM replacement.
        """
        if img1.shape != img2.shape:
            try:
                img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
            except Exception:
                return 0.0
        # cv2.PSNR returns inf when images are identical; cap to 100 dB.
        try:
            psnr = float(cv2.PSNR(img1, img2))
        except Exception:
            return 0.0
        if psnr == float("inf") or psnr > 100.0:
            return 1.0
        score = 1.0 - float(np.exp(-psnr / 20.0))
        return max(0.0, min(1.0, score))
