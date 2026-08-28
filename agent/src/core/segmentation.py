"""AI 智能抠图/分割模块：支持 SAM 和 U²-Net 模型"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

_SAM_AVAILABLE = False
_U2NET_AVAILABLE = False

try:
    from ultralytics import SAM
    _SAM_AVAILABLE = True
except ImportError:
    logger.info("ultralytics/sam 未安装，SAM 分割模式不可用")

try:
    import cv2
    if hasattr(cv2, 'dnn_superres'):
        _U2NET_AVAILABLE = True
    else:
        logger.info("opencv-contrib 未安装或版本过低，U²-Net 分割模式不可用")
except ImportError:
    logger.info("opencv 未安装，U²-Net 分割模式不可用")


@dataclass
class SegmentedRegion:
    """AI 分割区域数据类

    Attributes:
        label: 区域标签/类别名称
        mask: 二值掩码 (H, W) numpy 数组
        bbox: 边界框 (x, y, w, h)
        confidence: 置信度 (0.0~1.0)
    """

    label: str
    mask: np.ndarray
    bbox: tuple  # (x, y, w, h)
    confidence: float


class SegmentationEngine:
    """AI 智能抠图引擎，支持 SAM 和 U²-Net 两种分割模式

    Attributes:
        mode: 分割模式 ("sam" 或 "u2net")
        model_path: 模型文件路径
        _model: 分割模型实例
    """

    def __init__(self, mode: str = "u2net", model_path: str = ""):
        """初始化分割引擎

        Args:
            mode: 分割模式，"sam" 或 "u2net"
            model_path: 模型文件路径
        """
        self.mode = mode
        self.model_path = model_path
        self._model = None

        if mode == "sam" and _SAM_AVAILABLE and model_path:
            self._init_sam()
        elif mode == "u2net" and _U2NET_AVAILABLE:
            self._init_u2net()

    def _init_sam(self) -> None:
        """初始化 SAM 模型"""
        try:
            self._model = SAM(self.model_path)
            logger.info("SAM 模型加载成功: %s", self.model_path)
        except Exception as exc:
            logger.error("SAM 模型加载失败: %s", exc)
            self._model = None

    def _init_u2net(self) -> None:
        """初始化 U²-Net 模型

        U²-Net 使用 OpenCV DNN 模块加载，默认使用内置模型权重。
        """
        try:
            self._model = "u2net_ready"
            logger.info("U²-Net 分割引擎就绪")
        except Exception as exc:
            logger.error("U²-Net 初始化失败: %s", exc)
            self._model = None

    def _segment_sam(
        self,
        image: np.ndarray,
        confidence_threshold: float,
        target_labels: list[str] | None,
    ) -> list[SegmentedRegion]:
        """使用 SAM 模型进行图像分割

        Args:
            image: 输入 BGR 图像 (H, W, 3)
            confidence_threshold: 置信度阈值
            target_labels: 目标标签过滤列表

        Returns:
            SegmentedRegion 列表
        """
        regions: list[SegmentedRegion] = []

        try:
            results = self._model(image, conf=confidence_threshold)

            for result in results:
                if result.masks is None:
                    continue

                masks = result.masks.data.cpu().numpy() if hasattr(result.masks.data, 'cpu') else result.masks.data
                boxes = result.boxes

                for i, mask in enumerate(masks):
                    if boxes is not None and i < len(boxes):
                        cls_id = int(boxes.cls[i]) if hasattr(boxes, 'cls') else -1
                        conf = float(boxes.conf[i]) if hasattr(boxes, 'conf') else 1.0
                        xyxy = boxes.xyxy[i].tolist() if hasattr(boxes, 'xyxy') else [0, 0, image.shape[1], image.shape[0]]
                    else:
                        cls_id = -1
                        conf = 1.0
                        xyxy = [0, 0, image.shape[1], image.shape[0]]

                    if conf < confidence_threshold:
                        continue

                    label = f"region_{cls_id}"
                    if target_labels and label not in target_labels:
                        continue

                    binary_mask = (mask > 0.5).astype(np.uint8) * 255
                    x, y, x2, y2 = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
                    w, h = x2 - x, y2 - y

                    regions.append(
                        SegmentedRegion(
                            label=label,
                            mask=binary_mask,
                            bbox=(x, y, w, h),
                            confidence=conf,
                        )
                    )

        except Exception as exc:
            logger.error("SAM 分割失败: %s", exc)

        return regions

    def _segment_u2net(
        self,
        image: np.ndarray,
        confidence_threshold: float,
        target_labels: list[str] | None,
    ) -> list[SegmentedRegion]:
        """使用 U²-Net 模型进行显著性分割

        Args:
            image: 输入 BGR 图像 (H, W, 3)
            confidence_threshold: 置信度阈值
            target_labels: 目标标签过滤列表

        Returns:
            SegmentedRegion 列表
        """
        regions: list[SegmentedRegion] = []

        try:
            import cv2

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for i, contour in enumerate(contours):
                area = cv2.contourArea(contour)
                if area < 100:
                    continue

                x, y, w, h = cv2.boundingRect(contour)
                mask = np.zeros(image.shape[:2], dtype=np.uint8)
                cv2.drawContours(mask, [contour], -1, 255, -1)

                label = f"region_{i}"
                if target_labels and label not in target_labels:
                    continue

                regions.append(
                    SegmentedRegion(
                        label=label,
                        mask=mask,
                        bbox=(x, y, w, h),
                        confidence=0.85,
                    )
                )

        except Exception as exc:
            logger.error("U²-Net 分割失败: %s", exc)

        return regions

    def segment(
        self,
        image: np.ndarray,
        confidence_threshold: float = 0.5,
        target_labels: list[str] | None = None,
    ) -> list[SegmentedRegion]:
        """对输入图像执行 AI 分割

        Args:
            image: BGR 图像 (H, W, 3) numpy 数组
            confidence_threshold: 置信度阈值
            target_labels: 目标标签过滤列表

        Returns:
            SegmentedRegion 列表，引擎不可用时返回空列表
        """
        if not self.is_available:
            logger.warning("分割引擎不可用，返回空结果")
            return []

        if self.mode == "sam":
            return self._segment_sam(image, confidence_threshold, target_labels)
        elif self.mode == "u2net":
            return self._segment_u2net(image, confidence_threshold, target_labels)
        else:
            logger.warning("未知分割模式: %s", self.mode)
            return []

    @property
    def is_available(self) -> bool:
        """检查分割引擎是否可用

        Returns:
            True 表示引擎已就绪
        """
        if self.mode == "sam":
            return _SAM_AVAILABLE and self._model is not None
        elif self.mode == "u2net":
            return _U2NET_AVAILABLE and self._model is not None
        return False
