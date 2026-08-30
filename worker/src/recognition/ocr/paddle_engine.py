"""PaddleOCR 引擎实现"""

import logging

import numpy as np
from recognition.ocr import BaseOCREngine
from recognition.ocr.types import OCRResult

logger = logging.getLogger(__name__)


class PaddleOCREngine(BaseOCREngine):
    """PaddleOCR 引擎封装，提供中文/英文 OCR 识别能力

    采用懒加载策略，首次调用 recognize 时才初始化 PaddleOCR 实例，
    避免导入时就加载模型导致的启动延迟。
    """

    def __init__(self, use_gpu: bool = False, show_log: bool = False):
        """初始化 PaddleOCR 引擎

        Args:
            use_gpu: 是否启用 GPU 推理（默认 False，使用 CPU）
            show_log: 是否输出 PaddleOCR 内部调试日志
        """
        self._use_gpu = use_gpu
        self._show_log = show_log
        self._engine = None

    def _ensure_engine(self):
        """懒加载：确保 PaddleOCR 实例已初始化"""
        if self._engine is not None:
            return

        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise ImportError(
                "PaddleOCR 未安装，请执行: pip install paddleocr"
            ) from exc

        self._engine = PaddleOCR(
            use_angle_cls=True,
            lang='ch',
            use_gpu=self._use_gpu,
            show_log=self._show_log,
        )
        logger.info("PaddleOCR 引擎初始化完成 (GPU=%s)", self._use_gpu)

    def recognize(self, image: np.ndarray, lang: str = 'ch') -> list[OCRResult]:
        """对图像执行 OCR 识别

        Args:
            image: 输入图像 (BGR 或 RGB 格式 numpy 数组)
            lang: 识别语言代码

        Returns:
            OCRResult 列表
        """
        self._ensure_engine()

        results: list[OCRResult] = []
        raw_results = self._engine.ocr(image, cls=True)

        if raw_results is None or len(raw_results) == 0:
            return results

        ocr_data = raw_results[0]
        if ocr_data is None:
            return results

        for item in ocr_data:
            box_points = item[0]
            text_info = item[1]
            text = text_info[0] if text_info else ""
            confidence = text_info[1] if text_info else 0.0

            x1 = int(min(p[0] for p in box_points))
            y1 = int(min(p[1] for p in box_points))
            x2 = int(max(p[0] for p in box_points))
            y2 = int(max(p[1] for p in box_points))

            results.append(OCRResult(
                text=text,
                confidence=float(confidence),
                box=(x1, y1, x2, y2),
            ))

        return results

    def available_languages(self) -> list[str]:
        """返回支持的语言代码列表

        Returns:
            PaddleOCR 内置支持的语言列表
        """
        return ['ch', 'en', 'fr', 'german', 'korean', 'japan']
