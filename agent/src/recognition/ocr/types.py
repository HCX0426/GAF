"""OCR 相关数据类型定义"""

from dataclasses import dataclass


@dataclass
class OCRResult:
    """OCR 识别结果

    Attributes:
        text: 识别出的文本内容
        confidence: 识别置信度 (0.0 ~ 1.0)
        box: 文本框坐标 (x1, y1, x2, y2)
    """

    text: str
    confidence: float
    box: tuple
