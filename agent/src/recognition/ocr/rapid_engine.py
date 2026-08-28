"""RapidOCR 引擎实现"""

import logging

import numpy as np
from recognition.ocr import BaseOCREngine
from recognition.ocr.types import OCRResult

logger = logging.getLogger(__name__)


class RapidOCREngine(BaseOCREngine):
    """RapidOCR 引擎封装，提供轻量级 OCR 识别能力

    基于 ONNX Runtime，无需 PaddlePaddle 框架，部署更轻量。
    采用懒加载策略，首次调用 recognize 时才初始化 RapidOCR 实例。
    """

    def __init__(self):
        """初始化 RapidOCR 引擎"""
        self._engine = None

    def _ensure_engine(self):
        """懒加载：确保 RapidOCR 实例已初始化"""
        if self._engine is not None:
            return

        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise ImportError(
                "RapidOCR 未安装，请执行: pip install rapidocr-onnxruntime"
            ) from exc

        self._engine = RapidOCR()
        logger.info("RapidOCR 引擎初始化完成")

    def recognize(self, image: np.ndarray, lang: str = 'ch') -> list[OCRResult]:
        """对图像执行 OCR 识别

        Args:
            image: 输入图像 (BGR 或 RGB 格式 numpy 数组)
            lang: 识别语言代码（RapidOCR 主要支持中文/英文）

        Returns:
            OCRResult 列表
        """
        self._ensure_engine()

        results: list[OCRResult] = []
        raw_results, _ = self._engine(image)

        if raw_results is None:
            return results

        for item in raw_results:
            box_points = item[0]
            text = item[1] if len(item) > 1 else ""
            confidence = item[2] if len(item) > 2 else 0.0

            x1 = int(min(p[0] for p in box_points))
            y1 = int(min(p[1] for p in box_points))
            x2 = int(max(p[0] for p in box_points))
            y2 = int(max(p[1] for p in box_points))

            results.append(OCRResult(
                text=str(text),
                confidence=float(confidence),
                box=(x1, y1, x2, y2),
            ))

        return results

    def available_languages(self) -> list[str]:
        """返回支持的语言代码列表

        Returns:
            RapidOCR 当前主要支持中文和英文
        """
        return ['ch', 'en']
