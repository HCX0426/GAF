"""图像识别：模板匹配 + 颜色识别 + 识别结果缓存"""

import hashlib
import logging
import os
from collections import OrderedDict
from typing import Any

import cv2
import numpy as np
from image.color import ColorProcessor, ColorSpace

logger = logging.getLogger(__name__)

DEFAULT_CACHE_SIZE = 32
DEFAULT_RESULT_CACHE_SIZE = 64


class _LRUCache(OrderedDict):
    """LRU 缓存：用于模板图像缓存"""

    def __init__(self, maxsize: int = DEFAULT_CACHE_SIZE):
        super().__init__()
        self._maxsize = maxsize

    def get_or_load(self, key: str, loader) -> Any:
        """获取缓存或加载模板

        Args:
            key: 缓存键（模板路径）
            loader: 加载函数

        Returns:
            模板图像
        """
        if key in self:
            self.move_to_end(key)
            return self[key]

        value = loader()
        self[key] = value
        if len(self) > self._maxsize:
            oldest = next(iter(self))
            del self[oldest]
        return value


class ImageProcessor:
    """图像识别处理器：模板匹配 + 颜色识别，支持 LRU 模板缓存和识别结果缓存"""

    def __init__(
        self,
        cache_size: int = DEFAULT_CACHE_SIZE,
        result_cache_size: int = DEFAULT_RESULT_CACHE_SIZE,
    ):
        self._template_cache = _LRUCache(maxsize=cache_size)
        self._color_processor = ColorProcessor()
        self._result_cache: OrderedDict = OrderedDict()
        self._result_cache_size = result_cache_size

    def find_template(
        self,
        screenshot: np.ndarray,
        template: str,
        roi: dict[str, int] | None = None,
        threshold: float = 0.8,
    ) -> dict[str, Any] | None:
        """模板匹配（带识别结果缓存）

        Args:
            screenshot: BGR 格式截图
            template: 模板图片路径
            roi: 感兴趣区域 {"x": , "y": , "w": , "h": }
            threshold: 匹配阈值

        Returns:
            匹配结果 {"x", "y", "w", "h", "confidence"}，未找到返回 None
        """
        if screenshot is None or (hasattr(screenshot, 'size') and screenshot.size == 0):
            logger.warning("截图为空，无法执行模板匹配")
            return None

        cache_key = self._make_result_cache_key(screenshot, f"tmpl:{template}:{roi}:{threshold}")
        cached = self._get_result_cache(cache_key)
        if cached is not _CACHE_MISS:
            return cached

        tmpl_img = self._load_template(template)
        if tmpl_img is None:
            return None

        search_area = screenshot
        offset_x, offset_y = 0, 0

        if roi:
            x, y = roi.get("x", 0), roi.get("y", 0)
            w, h = roi.get("w", 0), roi.get("h", 0)
            if w > 0 and h > 0:
                search_area = screenshot[y:y + h, x:x + w]
                offset_x, offset_y = x, y

        if search_area.shape[0] < tmpl_img.shape[0] or search_area.shape[1] < tmpl_img.shape[1]:
            logger.warning("搜索区域小于模板尺寸")
            return None

        result = cv2.matchTemplate(search_area, tmpl_img, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val < threshold:
            logger.debug("模板匹配未达阈值: %.3f < %.3f", max_val, threshold)
            self._set_result_cache(cache_key, None)
            return None

        th, tw = tmpl_img.shape[:2]
        match_result = {
            "x": int(max_loc[0] + offset_x),
            "y": int(max_loc[1] + offset_y),
            "w": tw,
            "h": th,
            "confidence": float(max_val),
        }
        self._set_result_cache(cache_key, match_result)
        return match_result

    def find_color(
        self,
        screenshot: np.ndarray,
        color: str,
        roi: dict[str, int] | None = None,
        space: ColorSpace = ColorSpace.RGB,
        h_range: int = 10,
        s_range: int = 50,
        v_range: int = 50,
    ) -> dict[str, Any] | None:
        """颜色识别

        Args:
            screenshot: BGR 格式截图
            color: 颜色字符串
            roi: 感兴趣区域
            space: 颜色空间
            h_range, s_range, v_range: HSV 容差

        Returns:
            匹配结果 {"x", "y"}，未找到返回 None
        """
        if screenshot is None or (hasattr(screenshot, 'size') and screenshot.size == 0):
            logger.warning("截图为空，无法执行颜色识别")
            return None

        search_area = screenshot
        offset_x, offset_y = 0, 0

        if roi:
            x, y = roi.get("x", 0), roi.get("y", 0)
            w, h = roi.get("w", 0), roi.get("h", 0)
            if w > 0 and h > 0:
                search_area = screenshot[y:y + h, x:x + w]
                offset_x, offset_y = x, y

        color_tuple = ColorProcessor.parse_color(color, space)
        pos = ColorProcessor.find_color_in_image(
            search_area, color_tuple, space, h_range, s_range, v_range
        )

        if pos is None:
            return None

        return {
            "x": pos[0] + offset_x,
            "y": pos[1] + offset_y,
        }

    def _load_template(self, path: str) -> np.ndarray | None:
        """加载模板图片（带 LRU 缓存）"""
        def _loader():
            if not os.path.isfile(path):
                logger.warning("模板文件不存在: %s", path)
                return None
            img = cv2.imread(path, cv2.IMREAD_COLOR)
            if img is None:
                logger.warning("无法读取模板: %s", path)
            return img

        return self._template_cache.get_or_load(path, _loader)

    def _make_result_cache_key(self, screenshot: np.ndarray, params: str) -> str:
        """生成识别结果缓存键

        基于截图内容的哈希和识别参数生成唯一键，
        同一截图 + 同一参数不会重复识别

        Args:
            screenshot: 截图数据
            params: 识别参数字符串

        Returns:
            缓存键字符串
        """
        img_hash = hashlib.md5(screenshot.tobytes()).hexdigest()[:16]
        return f"{img_hash}:{params}"

    def _get_result_cache(self, key: str) -> Any | None:
        """从识别结果缓存中获取结果

        Args:
            key: 缓存键

        Returns:
            缓存的识别结果，未命中返回 None（但用哨兵区分"未缓存"和"缓存了None"）
        """
        if key in self._result_cache:
            self._result_cache.move_to_end(key)
            return self._result_cache[key]
        return _CACHE_MISS

    def _set_result_cache(self, key: str, value: Any) -> None:
        """设置识别结果缓存

        Args:
            key: 缓存键
            value: 识别结果
        """
        self._result_cache[key] = value
        if len(self._result_cache) > self._result_cache_size:
            oldest = next(iter(self._result_cache))
            del self._result_cache[oldest]

    def clear_result_cache(self) -> None:
        """清空识别结果缓存"""
        self._result_cache.clear()
        logger.debug("识别结果缓存已清空")


_CACHE_MISS = object()
