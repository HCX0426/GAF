"""颜色处理器：HSV/RGB/BGR 颜色空间识别"""

from enum import Enum

import cv2
import numpy as np


class ColorSpace(Enum):
    """颜色空间枚举"""
    RGB = "rgb"
    BGR = "bgr"
    HSV = "hsv"


class ColorProcessor:
    """颜色处理器：支持 HSV/RGB/BGR 颜色空间识别"""

    @staticmethod
    def parse_color(color_str: str, space: ColorSpace = ColorSpace.RGB) -> tuple[int, ...]:
        """解析颜色字符串为元组

        Args:
            color_str: 颜色字符串，如 "#FF0000" 或 "255,0,0" 或 "0,100,100"(HSV)
            space: 颜色空间

        Returns:
            颜色元组
        """
        if color_str.startswith("#"):
            hex_color = color_str.lstrip("#")
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            if space == ColorSpace.BGR:
                return (b, g, r)
            return (r, g, b)

        parts = [int(x.strip()) for x in color_str.split(",")]
        return tuple(parts)

    @staticmethod
    def to_hsv(color: tuple[int, ...], space: ColorSpace = ColorSpace.RGB) -> tuple[int, int, int]:
        """将颜色转换为 HSV 空间

        Args:
            color: 颜色元组
            space: 输入颜色空间

        Returns:
            HSV 元组 (H: 0-180, S: 0-255, V: 0-255)
        """
        arr = np.array([[list(color)]], dtype=np.uint8)
        if space == ColorSpace.RGB:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
        elif space == ColorSpace.BGR:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2HSV)
        return tuple(arr[0][0].tolist())

    @staticmethod
    def create_hsv_range(
        hsv: tuple[int, int, int],
        h_range: int = 10,
        s_range: int = 50,
        v_range: int = 50,
    ) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        """创建 HSV 范围（lower, upper）

        Args:
            hsv: 中心 HSV 值
            h_range: H 容差
            s_range: S 容差
            v_range: V 容差

        Returns:
            (lower, upper) 范围元组
        """
        lower = (
            max(0, hsv[0] - h_range),
            max(0, hsv[1] - s_range),
            max(0, hsv[2] - v_range),
        )
        upper = (
            min(180, hsv[0] + h_range),
            min(255, hsv[1] + s_range),
            min(255, hsv[2] + v_range),
        )
        return lower, upper

    @staticmethod
    def find_color_in_image(
        image: np.ndarray,
        color: tuple[int, ...],
        space: ColorSpace = ColorSpace.RGB,
        h_range: int = 10,
        s_range: int = 50,
        v_range: int = 50,
    ) -> tuple[int, int] | None:
        """在图像中查找指定颜色的位置

        Args:
            image: BGR 格式图像
            color: 目标颜色
            space: 颜色空间
            h_range, s_range, v_range: HSV 容差

        Returns:
            匹配中心坐标 (x, y)，未找到返回 None
        """
        hsv = ColorProcessor.to_hsv(color, space)
        lower, upper = ColorProcessor.create_hsv_range(hsv, h_range, s_range, v_range)

        hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv_image, np.array(lower), np.array(upper))

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        moments = cv2.moments(largest)
        if moments["m00"] == 0:
            return None

        cx = int(moments["m10"] / moments["m00"])
        cy = int(moments["m01"] / moments["m00"])
        return (cx, cy)
