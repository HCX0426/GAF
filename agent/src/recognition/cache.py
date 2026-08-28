"""OCR 结果缓存：基于图像哈希的结果复用"""

import logging
from collections import OrderedDict

import numpy as np
from recognition.ocr.types import OCRResult

logger = logging.getLogger(__name__)

try:
    import cv2

    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    logger.warning("cv2 未安装，OCR 缓存将使用简化的哈希算法")


class OCRResultCache:
    """OCR 结果缓存

    基于感知哈希（phash）的图像去重缓存，相同或高度相似的图像
    可直接复用 OCR 结果，避免重复识别。
    """

    def __init__(self, max_size: int = 500):
        """初始化 OCR 结果缓存

        Args:
            max_size: 最大缓存条目数，默认 500
        """
        self._max_size = max_size
        self._cache: OrderedDict = OrderedDict()

    @staticmethod
    def compute_image_hash(image: np.ndarray) -> str:
        """计算图像的感知哈希值

        优先使用 OpenCV 的 pHash，若不可用则退化为简化的均值哈希。

        Args:
            image: 输入图像 (numpy 数组)

        Returns:
            十六进制哈希字符串
        """
        if HAS_CV2:
            import cv2

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
            resized = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
            dct = cv2.dct(np.float32(resized))
            dct_low = dct[:8, :8]
            mean_val = dct_low.mean()
            hash_bits = (dct_low > mean_val).flatten()
            hash_bytes = np.packbits(hash_bits.astype(np.uint8))
            return hash_bytes.tobytes().hex()

        gray = np.mean(image, axis=2).astype(np.uint8) if len(image.shape) == 3 else image
        # Avoid slice step=0 (ValueError) when image dimensions < 8
        step_y = max(1, gray.shape[0] // 8)
        step_x = max(1, gray.shape[1] // 8)
        resized = gray[::step_y, ::step_x][:8, :8]
        mean_val = resized.mean()
        hash_bits = (resized > mean_val).flatten()
        hash_val = int("".join(str(int(b)) for b in hash_bits), 2)
        return hex(hash_val)

    def get(self, image_hash: str) -> list[OCRResult] | None:
        """根据图像哈希获取缓存的 OCR 结果

        Args:
            image_hash: 图像感知哈希值

        Returns:
            缓存的 OCRResult 列表，未命中返回 None
        """
        if image_hash in self._cache:
            self._cache.move_to_end(image_hash)
            logger.debug("OCR 缓存命中: %s", image_hash[:16])
            return self._cache[image_hash]
        return None

    def set(self, image_hash: str, results: list[OCRResult]) -> None:
        """将 OCR 结果存入缓存

        Args:
            image_hash: 图像感知哈希值
            results: OCR 识别结果列表
        """
        if image_hash in self._cache:
            self._cache.move_to_end(image_hash)

        self._cache[image_hash] = results

        if len(self._cache) > self._max_size:
            oldest_key, _ = self._cache.popitem(last=False)
            logger.debug("OCR 缓存淘汰: %s", oldest_key[:16])

    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()
        logger.info("OCR 结果缓存已清空")

    @property
    def size(self) -> int:
        """当前缓存条目数"""
        return len(self._cache)
