"""OCR 引擎注册表：管理多引擎注册与竞速基准测试"""

import logging
import time

import numpy as np
from recognition.ocr import BaseOCREngine

logger = logging.getLogger(__name__)


class OCREngineRegistry:
    """OCR 引擎注册表

    管理多个 OCR 引擎的注册、竞速基准测试和最优引擎选择。
    同一进程内基准测试结果会被缓存，避免重复测评。
    """

    def __init__(self):
        """初始化引擎注册表"""
        self._engines: dict[str, BaseOCREngine] = {}
        self._best_engine_name: str | None = None
        self._benchmarked: bool = False

    def register(self, engine: BaseOCREngine, name: str) -> None:
        """注册 OCR 引擎

        Args:
            engine: OCR 引擎实例
            name: 引擎名称标识
        """
        if name in self._engines:
            logger.warning("引擎 %s 已注册，将被覆盖", name)
        self._engines[name] = engine
        self._benchmarked = False
        logger.info("OCR 引擎已注册: %s", name)

    def benchmark(self, image: np.ndarray) -> str:
        """对所有已注册引擎执行竞速测试，返回最快的引擎名

        对各引擎依次执行 recognize，记录耗时，选取最快的。
        结果会被缓存，后续调用直接返回缓存的最优引擎名。

        Args:
            image: 用于基准测试的图像

        Returns:
            最快引擎的名称

        Raises:
            RuntimeError: 当没有注册任何引擎时抛出
        """
        if not self._engines:
            raise RuntimeError("没有注册任何 OCR 引擎，请先调用 register()")

        if self._benchmarked and self._best_engine_name is not None:
            logger.debug("使用缓存的基准测试结果: %s", self._best_engine_name)
            return self._best_engine_name

        best_name = ""
        best_time = float("inf")

        for name, engine in self._engines.items():
            try:
                start = time.perf_counter()
                engine.recognize(image)
                elapsed = time.perf_counter() - start

                logger.info("引擎 %s 耗时: %.4f 秒", name, elapsed)

                if elapsed < best_time:
                    best_time = elapsed
                    best_name = name
            except Exception as exc:
                logger.warning("引擎 %s 基准测试失败: %s", name, exc)

        if not best_name:
            raise RuntimeError("所有引擎基准测试均失败")

        self._best_engine_name = best_name
        self._benchmarked = True
        logger.info("基准测试完成，最优引擎: %s (%.4f 秒)", best_name, best_time)
        return best_name

    def get_best(self) -> BaseOCREngine:
        """获取最优 OCR 引擎

        必须在 benchmark() 之后调用，否则抛出异常。

        Returns:
            最优 OCR 引擎实例

        Raises:
            RuntimeError: 尚未执行基准测试时抛出
        """
        if self._best_engine_name is None:
            raise RuntimeError("尚未执行基准测试，请先调用 benchmark()")
        return self._engines[self._best_engine_name]

    def get_engine(self, name: str) -> BaseOCREngine:
        """按名称获取指定引擎

        Args:
            name: 引擎名称

        Returns:
            对应的 OCR 引擎实例

        Raises:
            KeyError: 引擎名称不存在时抛出
        """
        if name not in self._engines:
            raise KeyError(f"引擎 {name} 未注册")
        return self._engines[name]

    def reset(self) -> None:
        """重置基准测试缓存，下次 benchmark() 将重新测评"""
        self._best_engine_name = None
        self._benchmarked = False
        logger.info("基准测试缓存已重置")

    @property
    def engine_names(self):
        """返回所有已注册引擎名称"""
        return list(self._engines.keys())
