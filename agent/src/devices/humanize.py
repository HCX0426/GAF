"""拟人化操作：添加随机延迟和偏移使操作更自然"""

import logging
import random
import time
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)


def _random_range(
    value: float | tuple[float, float],
    default: tuple[float, float],
) -> float:
    """从范围或固定值中生成随机数

    Args:
        value: 固定值或 (min, max) 范围元组
        default: 默认范围

    Returns:
        随机生成的数值
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return random.uniform(value[0], value[1])
    return random.uniform(default[0], default[1])


def _bezier_curve(
    points: Sequence[tuple[float, float]],
    num_samples: int = 20,
) -> list:
    """生成贝塞尔曲线上的点

    Supports arbitrary order via Bernstein polynomials. With 4 control
    points this is a cubic (4-point) Bézier curve — the recommended
    trajectory shape for human-like swipes (Alas minitouch.py reference).
    With 3 control points it falls back to quadratic.

    Args:
        points: Control points (typically 3 quadratic or 4 cubic).
        num_samples: Number of samples along the curve.

    Returns:
        Curve points [(x, y), ...] with len == num_samples + 1.
    """
    n = len(points) - 1
    curve_points = []

    for t_idx in range(num_samples + 1):
        t = t_idx / num_samples
        x = 0.0
        y = 0.0
        for i, (px, py) in enumerate(points):
            bernstein = (
                _combination(n, i)
                * (t ** i)
                * ((1 - t) ** (n - i))
            )
            x += px * bernstein
            y += py * bernstein
        curve_points.append((x, y))

    return curve_points


def _cubic_bezier_4p(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    num_samples: int = 20,
) -> list:
    """Compute a 4-point cubic Bézier curve directly.

    B(t) = (1-t)^3*P0 + 3*(1-t)^2*t*P1 + 3*(1-t)*t^2*P2 + t^3*P3
    for t in [0, 1].

    Reference: Alas minitouch.py 4-point cubic swipe trajectory.

    Args:
        p0, p1, p2, p3: Four control points.
        num_samples: Number of samples along the curve.

    Returns:
        Curve points [(x, y), ...] with len == num_samples + 1.
    """
    # Guard against division by zero when num_samples == 0; return just P0.
    if num_samples <= 0:
        return [(float(p0[0]), float(p0[1]))]
    curve_points = []
    for t_idx in range(num_samples + 1):
        t = t_idx / num_samples
        u = 1.0 - t
        # Cubic Bernstein coefficients.
        b0 = u * u * u
        b1 = 3 * u * u * t
        b2 = 3 * u * t * t
        b3 = t * t * t
        x = b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0]
        y = b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]
        curve_points.append((x, y))
    return curve_points


def _combination(n: int, k: int) -> float:
    """计算组合数 C(n, k)

    Args:
        n: 总数
        k: 选取数

    Returns:
        组合数
    """
    if k < 0 or k > n:
        return 0.0
    if k == 0 or k == n:
        return 1.0
    result = 1.0
    for i in range(min(k, n - k)):
        result = result * (n - i) / (i + 1)
    return result


class HumanizedInput:
    """拟人化操作，添加随机延迟和偏移使操作更自然"""

    def __init__(self, input_controller: Any, config: dict | None = None):
        """初始化拟人化输入控制器

        Args:
            input_controller: 底层输入控制器（需实现 click/swipe/key_press/text_input）
            config: 可选配置字典
        """
        self._controller = input_controller
        self._config = config or {}

    def click(
        self,
        x: int,
        y: int,
        random_offset: int = 3,
        pre_delay: float | tuple[float, float] = (0.05, 0.15),
        post_delay: float | tuple[float, float] = (0.1, 0.3),
    ) -> None:
        """拟人化点击：添加随机偏移+前后延迟

        Args:
            x: 目标 X 坐标
            y: 目标 Y 坐标
            random_offset: 随机偏移范围（像素）
            pre_delay: 点击前延迟（秒），支持范围元组
            post_delay: 点击后延迟（秒），支持范围元组
        """
        actual_x = x + int(random.gauss(0, random_offset * 0.4))
        actual_y = y + int(random.gauss(0, random_offset * 0.4))

        pre = _random_range(pre_delay, (0.05, 0.15))
        time.sleep(pre)

        self._controller.click(actual_x, actual_y)
        logger.debug("拟人化点击: (%d,%d)->(%d,%d), pre_delay=%.3fs", x, y, actual_x, actual_y, pre)

        post = _random_range(post_delay, (0.1, 0.3))
        time.sleep(post)

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float | tuple[float, float] = (0.3, 0.8),
        steps: int | None = None,
        cubic: bool = True,
    ) -> None:
        """拟人化滑动：添加贝塞尔曲线+随机速度

        P2-2: Defaults to 4-point cubic Bézier (cubic=True). Pass cubic=False
        to use the legacy 3-point quadratic curve. The cubic curve uses two
        intermediate control points at 1/3 and 2/3 of the trajectory, each
        offset by random jitter, producing a more natural S-shape swipe.

        Args:
            x1: 起始 X 坐标
            y1: 起始 Y 坐标
            x2: 终止 X 坐标
            y2: 终止 Y 坐标
            duration: 滑动时长（秒），支持范围元组
            steps: 滑动步数，None 则自动计算
            cubic: True=4-point cubic Bézier (default, P2-2);
                   False=legacy 3-point quadratic.
        """
        actual_duration = _random_range(duration, (0.3, 0.8))

        if cubic:
            # P2-2: 4-point cubic Bézier with two random control points.
            # Place control points at t=1/3 and t=2/3 along the line,
            # then add per-axis jitter to produce natural S-curves.
            p1_x = x1 + (x2 - x1) / 3.0 + random.randint(-30, 30)
            p1_y = y1 + (y2 - y1) / 3.0 + random.randint(-30, 30)
            p2_x = x1 + 2 * (x2 - x1) / 3.0 + random.randint(-30, 30)
            p2_y = y1 + 2 * (y2 - y1) / 3.0 + random.randint(-30, 30)
            num_steps = steps or max(5, int(actual_duration * 20))
            curve = _cubic_bezier_4p(
                (x1, y1), (p1_x, p1_y), (p2_x, p2_y), (x2, y2),
                num_samples=num_steps,
            )
        else:
            mid_x = (x1 + x2) / 2 + random.randint(-30, 30)
            mid_y = (y1 + y2) / 2 + random.randint(-30, 30)
            control_points = [(x1, y1), (mid_x, mid_y), (x2, y2)]
            num_steps = steps or max(5, int(actual_duration * 20))
            curve = _bezier_curve(control_points, num_samples=num_steps)

        step_delay = actual_duration / num_steps if num_steps > 0 else 0.01

        for i in range(len(curve) - 1):
            cx, cy = curve[i]
            nx, ny = curve[i + 1]
            jitter_x = random.uniform(-1, 1)
            jitter_y = random.uniform(-1, 1)
            self._controller.swipe(
                int(cx + jitter_x), int(cy + jitter_y),
                int(nx + jitter_x), int(ny + jitter_y),
            )
            time.sleep(step_delay)

        logger.debug(
            "拟人化滑动: (%d,%d)->(%d,%d), duration=%.3fs, steps=%d, cubic=%s",
            x1, y1, x2, y2, actual_duration, num_steps, cubic,
        )

    def key_press(
        self,
        key: str,
        pre_delay: float | tuple[float, float] = (0.05, 0.1),
    ) -> None:
        """拟人化按键

        Args:
            key: 按键名称
            pre_delay: 按键前延迟（秒），支持范围元组
        """
        pre = _random_range(pre_delay, (0.05, 0.1))
        time.sleep(pre)

        self._controller.key_press(key)
        logger.debug("拟人化按键: %s, pre_delay=%.3fs", key, pre)

        post = _random_range((0.05, 0.15), (0.05, 0.15))
        time.sleep(post)

    def text_input(
        self,
        text: str,
        interval: float | tuple[float, float] = (0.03, 0.08),
    ) -> None:
        """拟人化文本输入：逐字符+随机间隔

        Args:
            text: 输入的文本内容
            interval: 字符间间隔（秒），支持范围元组
        """
        for char in text:
            self._controller.text_input(char)
            delay = _random_range(interval, (0.03, 0.08))
            time.sleep(delay)

        logger.debug("拟人化文本输入: %s (长度=%d)", text[:20], len(text))
