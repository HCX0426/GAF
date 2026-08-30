"""OpenCC simplified/traditional Chinese conversion for OCR post-processing.

Provides a post-processing hook that converts OCR-detected text between
simplified and traditional Chinese. The conversion is two-step:
    1. jp2t: Japanese kanji -> Traditional Chinese (handles Japanese games)
    2. t2s: Traditional Chinese -> Simplified Chinese

This is particularly useful for OCR on Japanese/Traditional Chinese game UIs
where the user expects Simplified Chinese output.

Reference: ok-script/ok/task/task.py:844-864 (fix_texts method)
"""

import logging

from recognition.ocr.types import OCRResult

logger = logging.getLogger(__name__)


class OpenCCConverter:
    """OpenCC-based text converter for OCR post-processing.

    Lazily initializes OpenCC converters on first use. If the `opencc`
    package is not installed, conversion is skipped with a warning.

    Supported conversion directions:
        - jp2t: Japanese kanji -> Traditional Chinese
        - t2s: Traditional Chinese -> Simplified Chinese
        - s2t: Simplified Chinese -> Traditional Chinese
        - tw2s: Taiwanese Traditional -> Simplified Chinese
        - hk2s: Hong Kong Traditional -> Simplified Chinese
    """

    # Supported OpenCC conversion configs
    SUPPORTED_CONVERSIONS = {
        "jp2t",  # Japanese -> Traditional Chinese
        "t2s",   # Traditional -> Simplified
        "s2t",   # Simplified -> Traditional
        "tw2s",  # Taiwanese Traditional -> Simplified
        "hk2s",  # Hong Kong Traditional -> Simplified
        "t2tw",  # Traditional -> Taiwanese
        "t2hk",  # Traditional -> Hong Kong
    }

    def __init__(
        self,
        auto_simplify: bool = False,
        conversion: str = "t2s",
        japanese_fallback: bool = False,
    ):
        """Initialize OpenCC converter configuration.

        Args:
            auto_simplify: If True, automatically convert all OCR text to
                Simplified Chinese. This is the main switch.
            conversion: OpenCC conversion config name (default "t2s" for
                Traditional -> Simplified).
            japanese_fallback: If True, apply jp2t (Japanese -> Traditional)
                before the main conversion. Useful for Japanese game OCR.
        """
        self._auto_simplify = auto_simplify
        self._conversion = conversion
        self._japanese_fallback = japanese_fallback
        self._cc_main: object | None = None
        self._cc_jp2t: object | None = None
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Lazy-load OpenCC converters.

        Returns:
            True if OpenCC is available and initialized, False otherwise.
        """
        if self._initialized:
            return self._cc_main is not None

        self._initialized = True

        if not self._auto_simplify:
            return False

        try:
            from opencc import OpenCC
        except ImportError:
            logger.warning(
                "opencc 未安装，繁简转换将被跳过。请执行: pip install opencc"
            )
            return False

        if self._conversion not in self.SUPPORTED_CONVERSIONS:
            logger.warning(
                "不支持的 OpenCC 转换: %s, 支持的转换: %s",
                self._conversion, self.SUPPORTED_CONVERSIONS,
            )
            return False

        try:
            self._cc_main = OpenCC(self._conversion)
            if self._japanese_fallback:
                self._cc_jp2t = OpenCC("jp2t")
            logger.info(
                "OpenCC 初始化完成 (conversion=%s, jp_fallback=%s)",
                self._conversion, self._japanese_fallback,
            )
            return True
        except Exception as exc:
            logger.error("OpenCC 初始化失败: %s", exc)
            return False

    def convert_text(self, text: str) -> str:
        """Convert a single text string using OpenCC.

        Args:
            text: Input text to convert.

        Returns:
            Converted text. If OpenCC is not available or auto_simplify is
            False, returns the original text unchanged.
        """
        if not self._ensure_initialized():
            return text

        result = text
        # Step 1: Japanese -> Traditional (if enabled)
        if self._cc_jp2t is not None:
            result = self._cc_jp2t.convert(result)
        # Step 2: Main conversion (e.g., Traditional -> Simplified)
        if self._cc_main is not None:
            result = self._cc_main.convert(result)
        return result

    def convert_results(self, results: list[OCRResult]) -> list[OCRResult]:
        """Apply OpenCC conversion to a list of OCR results.

        Args:
            results: List of OCRResult objects to convert.

        Returns:
            New list of OCRResult objects with converted text. If OpenCC is
            not available, returns the original list unchanged.
        """
        if not self._ensure_initialized():
            return results

        converted: list[OCRResult] = []
        for r in results:
            new_text = self.convert_text(r.text)
            converted.append(OCRResult(
                text=new_text,
                confidence=r.confidence,
                box=r.box,
            ))
        return converted

    @property
    def is_available(self) -> bool:
        """Check if OpenCC is available and enabled."""
        return self._ensure_initialized()

    @property
    def auto_simplify(self) -> bool:
        """Whether auto-simplification is enabled."""
        return self._auto_simplify
