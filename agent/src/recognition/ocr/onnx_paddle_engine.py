"""ONNXPaddleOCR engine — direct ONNX runtime inference for PaddleOCR models.

This engine wraps the `onnxocr` package (or equivalent ONNX-based PaddleOCR
implementation) to provide OCR without requiring the full PaddlePaddle
framework. Models are loaded as .onnx files and inference runs via
onnxruntime, supporting CPU/CUDA/DirectML execution providers.

Reference: ok-script/ok/task/TaskExecutor.py:109-156 (ocr_lib initialization)
"""

import logging
from typing import Any

import numpy as np
from recognition.ocr import BaseOCREngine
from recognition.ocr.types import OCRResult

logger = logging.getLogger(__name__)


class ONNXPaddleOCREngine(BaseOCREngine):
    """ONNX-based PaddleOCR engine — lightweight, no PaddlePaddle dependency.

    Uses the `onnxocr` package which provides ONNX-converted PaddleOCR models
    (detection + recognition + classification). Falls back gracefully if
    the package or model files are not available.

    Lazy initialization: the ONNX inference session is created on first
    ``recognize()`` call, not at construction time.
    """

    def __init__(
        self,
        use_angle_cls: bool = False,
        use_npu: bool = False,
        use_openvino: bool = False,
        det_model_dir: str | None = None,
        rec_model_dir: str | None = None,
        cls_model_dir: str | None = None,
    ):
        """Initialize ONNX PaddleOCR engine configuration.

        Args:
            use_angle_cls: Whether to use angle classification (text orientation).
                Disabled by default for performance (most game UIs are horizontal).
            use_npu: Use Intel NPU acceleration (requires NPU runtime).
            use_openvino: Use OpenVINO backend instead of ONNX Runtime.
            det_model_dir: Custom detection model directory. If None, uses
                the default models bundled with onnxocr.
            rec_model_dir: Custom recognition model directory.
            cls_model_dir: Custom classification model directory.
        """
        self._use_angle_cls = use_angle_cls
        self._use_npu = use_npu
        self._use_openvino = use_openvino
        self._det_model_dir = det_model_dir
        self._rec_model_dir = rec_model_dir
        self._cls_model_dir = cls_model_dir
        self._engine: Any = None

    def _ensure_engine(self) -> None:
        """Lazy-load: ensure the ONNXPaddleOcr instance is initialized."""
        if self._engine is not None:
            return

        try:
            # onnxocr is the ok-script reference package
            from onnxocr.onnx_paddleocr import ONNXPaddleOcr
        except ImportError:
            try:
                # Alternative: onnxpaddleocr package
                from onnxpaddleocr import ONNXPaddleOcr
            except ImportError as exc:
                raise ImportError(
                    "ONNXPaddleOCR 未安装，请执行: pip install onnxocr "
                    "或 pip install onnxpaddleocr"
                ) from exc

        kwargs: dict[str, Any] = {
            "use_angle_cls": self._use_angle_cls,
            "use_npu": self._use_npu,
            "use_openvino": self._use_openvino,
        }
        # Only pass model dirs if explicitly set (otherwise use defaults)
        if self._det_model_dir:
            kwargs["det_model_dir"] = self._det_model_dir
        if self._rec_model_dir:
            kwargs["rec_model_dir"] = self._rec_model_dir
        if self._cls_model_dir:
            kwargs["cls_model_dir"] = self._cls_model_dir

        self._engine = ONNXPaddleOcr(**kwargs)
        logger.info(
            "ONNXPaddleOCR 引擎初始化完成 (angle_cls=%s, npu=%s, openvino=%s)",
            self._use_angle_cls, self._use_npu, self._use_openvino,
        )

    def recognize(self, image: np.ndarray, lang: str = "ch") -> list[OCRResult]:
        """Run OCR on the input image using ONNX-based PaddleOCR models.

        Args:
            image: Input image (BGR numpy array).
            lang: Language code (ignored by onnxocr — models are language-specific).

        Returns:
            List of OCRResult with text, confidence, and bounding box.
        """
        self._ensure_engine()

        results: list[OCRResult] = []
        # ONNXPaddleOcr.ocr() returns [[box, (text, confidence)], ...]
        raw_results = self._engine.ocr(image)

        if raw_results is None or len(raw_results) == 0:
            return results

        # Handle both single-image and batched result formats
        ocr_data = raw_results[0] if isinstance(raw_results[0], list) else raw_results
        if ocr_data is None:
            return results

        for item in ocr_data:
            if not item or len(item) < 2:
                continue
            box_points = item[0]
            text_info = item[1]

            # text_info may be (text, confidence) or just text
            if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                text = str(text_info[0])
                confidence = float(text_info[1])
            else:
                text = str(text_info)
                confidence = 1.0

            # box_points is a 4-point polygon [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
            x1 = int(min(p[0] for p in box_points))
            y1 = int(min(p[1] for p in box_points))
            x2 = int(max(p[0] for p in box_points))
            y2 = int(max(p[1] for p in box_points))

            results.append(OCRResult(
                text=text,
                confidence=confidence,
                box=(x1, y1, x2, y2),
            ))

        return results

    def available_languages(self) -> list[str]:
        """Return supported language codes.

        ONNXPaddleOCR models are language-specific (bundled in model dir).
        Default models support Chinese + English.
        """
        return ["ch", "en"]
