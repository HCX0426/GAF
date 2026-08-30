"""OCR 引擎模块：BaseOCREngine 抽象基类 + 引擎注册与导出"""

from abc import ABC, abstractmethod

import numpy as np
from recognition.ocr.types import OCRResult


class BaseOCREngine(ABC):
    """OCR 引擎抽象基类，定义统一的识别接口"""

    @abstractmethod
    def recognize(self, image: np.ndarray, lang: str = 'ch') -> list[OCRResult]:
        """对图像执行 OCR 识别

        Args:
            image: 输入图像 (BGR 格式 numpy 数组)
            lang: 识别语言代码，默认 'ch' (中文)

        Returns:
            OCRResult 列表，每个元素包含识别文本、置信度和坐标框
        """
        ...

    @abstractmethod
    def available_languages(self) -> list[str]:
        """返回引擎支持的语言代码列表

        Returns:
            语言代码列表，如 ['ch', 'en', 'fr']
        """
        ...
