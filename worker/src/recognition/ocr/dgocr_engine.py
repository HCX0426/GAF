"""DGOCR (DuGuang OCR) engine — Windows-friendly OCR with DirectML support.

DGOCR is a lightweight OCR engine optimized for Windows DirectML acceleration.
It is particularly effective for game UIs due to its high accuracy on stylized
text. The engine returns batched results (list of per-image detections).

Reference: ok-script/ok/task/task.py:951-981 (duguang_ocr method)
"""

import logging
from typing import Any

import numpy as np
from recognition.ocr import BaseOCREngine
from recognition.ocr.types import OCRResult

logger = logging.getLogger(__name__)


class DGOCREngine(BaseOCREngine):
    """DuGuang OCR engine wrapper with DirectML acceleration support.

    Uses the `dgocr` package which provides Windows-optimized OCR with
    optional DirectML GPU acceleration. Falls back gracefully if the
    package is not installed.

    Note: DGOCR is Windows-only due to DirectML dependency. On macOS/Linux,
    construction will succeed but ``recognize()`` will raise ImportError.

    Lazy initialization: the DGOCR instance is created on first
    ``recognize()`` call.
    """

    def __init__(self, use_dml: bool = True):
        """Initialize DGOCR engine configuration.

        Args:
            use_dml: Whether to use DirectML GPU acceleration (Windows only).
                Set to False to force CPU inference.
        """
        self._use_dml = use_dml
        self._engine: Any = None

    def _ensure_engine(self) -> None:
        """Lazy-load: ensure the DGOCR instance is initialized."""
        if self._engine is not None:
            return

        try:
            from dgocr import DGOCR
        except ImportError as exc:
            raise ImportError(
                "DGOCR 未安装，请执行: pip install dgocr "
                "(仅 Windows 支持 DirectML)"
            ) from exc

        self._engine = DGOCR(use_dml=self._use_dml)
        logger.info("DGOCR 引擎初始化完成 (DirectML=%s)", self._use_dml)

    def recognize(self, image: np.ndarray, lang: str = "ch") -> list[OCRResult]:
        """Run OCR on the input image using DGOCR.

        Args:
            image: Input image (BGR numpy array).
            lang: Language code (DGOCR supports Chinese primarily).

        Returns:
            List of OCRResult with text, confidence, and bounding box.
        """
        self._ensure_engine()

        results: list[OCRResult] = []
        # DGOCR.run() returns a list of per-image results (batch-friendly)
        # Each element is a list of [pos, (text, confidence)] detections
        raw_results = self._engine.run(image)

        if raw_results is None:
            return results

        # Handle both batched and single-image result formats
        if raw_results and isinstance(raw_results[0], list):
            # Batched: list of per-image result lists
            for image_results in raw_results:
                if not image_results:
                    continue
                results.extend(self._parse_detections(image_results))
        else:
            # Single image: flat list of detections
            results.extend(self._parse_detections(raw_results))

        return results

    @staticmethod
    def _parse_detections(detections: list) -> list[OCRResult]:
        """Parse a list of [pos, (text, confidence)] detections into OCRResult.

        Args:
            detections: List of detection tuples from DGOCR.

        Returns:
            List of OCRResult objects.
        """
        parsed: list[OCRResult] = []
        for det in detections:
            if not det or len(det) < 2:
                continue
            box_points = det[0]
            text_info = det[1]

            if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                text = str(text_info[0])
                confidence = float(text_info[1])
            else:
                text = str(text_info)
                confidence = 1.0

            # box_points is a 4-point polygon
            x1 = int(min(p[0] for p in box_points))
            y1 = int(min(p[1] for p in box_points))
            x2 = int(max(p[0] for p in box_points))
            y2 = int(max(p[1] for p in box_points))

            parsed.append(OCRResult(
                text=text,
                confidence=confidence,
                box=(x1, y1, x2, y2),
            ))
        return parsed

    def available_languages(self) -> list[str]:
        """Return supported language codes.

        DGOCR primarily supports Chinese (Simplified and Traditional).
        """
        return ["ch", "en"]
