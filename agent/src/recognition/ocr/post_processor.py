"""OCR post-processing pipeline: OpenCC + gettext + custom correction dictionary.

Combines three post-processing steps:
1. OpenCC simplified/traditional Chinese conversion (delegated to OpenCCConverter)
2. gettext-based translation (for game-specific text mapping)
3. Custom correction dictionary (for common OCR misrecognition fixes)

Reference: ok-script/ok/task/task.py:844-864 (fix_texts method)

Usage:
    processor = OcrPostProcessor(
        auto_simplify=True,
        translation_domain='game_x',
        translation_path='/path/to/locales',
        correction_dict={'l': '1', 'O': '0', '丨': '1'},
    )
    corrected = processor.process_text("lOOl")
    # -> "1001" (after correction dict applied)
"""

import gettext
import logging
from pathlib import Path
from typing import Any

from recognition.ocr.opencc_converter import OpenCCConverter
from recognition.ocr.types import OCRResult

logger = logging.getLogger(__name__)


class OcrPostProcessor:
    """OCR post-processing pipeline combining OpenCC + gettext + custom dictionary.

    Steps applied in order:
        1. Custom correction dictionary (character-level fixes)
        2. OpenCC conversion (simplified/traditional Chinese)
        3. gettext translation (phrase-level mapping)

    The order ensures that OCR misrecognition is fixed first, then language
    conversion is applied, finally domain-specific translation.
    """

    def __init__(
        self,
        auto_simplify: bool = False,
        opencc_conversion: str = "t2s",
        japanese_fallback: bool = False,
        translation_domain: str | None = None,
        translation_path: str | Path | None = None,
        translation_lang: str = "zh_CN",
        correction_dict: dict[str, str] | None = None,
    ):
        """Initialize OCR post-processor.

        Args:
            auto_simplify: If True, enable OpenCC simplified Chinese conversion.
            opencc_conversion: OpenCC conversion config name (default "t2s").
            japanese_fallback: If True, apply jp2t before main conversion.
            translation_domain: gettext domain name (e.g., "game_x"). If None,
                gettext translation is disabled.
            translation_path: Path to directory containing locale folders.
                Required if translation_domain is set.
            translation_lang: Language code for gettext (default "zh_CN").
            correction_dict: Custom correction mapping (e.g., {'l': '1'}).
                Applied character-by-character before OpenCC and gettext.
        """
        self._opencc = OpenCCConverter(
            auto_simplify=auto_simplify,
            conversion=opencc_conversion,
            japanese_fallback=japanese_fallback,
        )
        self._translation_domain = translation_domain
        self._translation_path = Path(translation_path) if translation_path else None
        self._translation_lang = translation_lang
        self._correction_dict = correction_dict or {}
        self._translator: Any | None = None
        self._init_translator()

    def _init_translator(self) -> None:
        """Initialize gettext translator if domain and path are provided."""
        if not self._translation_domain or not self._translation_path:
            return

        try:
            localedir = str(self._translation_path)
            self._translator = gettext.translation(
                self._translation_domain,
                localedir=localedir,
                languages=[self._translation_lang],
                fallback=True,
            )
            logger.info(
                "gettext translator loaded (domain=%s, lang=%s, path=%s)",
                self._translation_domain, self._translation_lang, localedir,
            )
        except Exception as exc:
            logger.warning("gettext translator init failed: %s", exc)
            self._translator = None

    def apply_correction_dict(self, text: str) -> str:
        """Apply custom correction dictionary to text.

        Replaces each character found in the correction dict with its mapping.
        This handles common OCR misrecognition (e.g., 'l' -> '1', 'O' -> '0').

        Args:
            text: Input text.

        Returns:
            Text with corrections applied.
        """
        if not self._correction_dict:
            return text
        return ''.join(self._correction_dict.get(ch, ch) for ch in text)

    def apply_translation(self, text: str) -> str:
        """Apply gettext translation to text.

        Uses gettext to translate the entire text string. If no translation
        is found, returns the original text unchanged.

        Args:
            text: Input text.

        Returns:
            Translated text, or original if no translation available.
        """
        if self._translator is None:
            return text
        translated = self._translator.gettext(text)
        return translated

    def process_text(self, text: str) -> str:
        """Apply full post-processing pipeline to a text string.

        Order: correction dict -> OpenCC -> gettext

        Args:
            text: Input text from OCR.

        Returns:
            Post-processed text.
        """
        # Step 1: Custom correction dictionary (character-level)
        result = self.apply_correction_dict(text)
        # Step 2: OpenCC conversion (language-level)
        result = self._opencc.convert_text(result)
        # Step 3: gettext translation (phrase-level)
        result = self.apply_translation(result)
        return result

    def process_results(self, results: list[OCRResult]) -> list[OCRResult]:
        """Apply full post-processing pipeline to OCR results.

        Args:
            results: List of OCRResult objects.

        Returns:
            New list of OCRResult objects with post-processed text.
        """
        processed: list[OCRResult] = []
        for r in results:
            new_text = self.process_text(r.text)
            processed.append(OCRResult(
                text=new_text,
                confidence=r.confidence,
                box=r.box,
            ))
        return processed

    @property
    def opencc_available(self) -> bool:
        """Whether OpenCC conversion is available."""
        return self._opencc.is_available

    @property
    def translation_available(self) -> bool:
        """Whether gettext translation is available."""
        return self._translator is not None

    @property
    def correction_dict(self) -> dict[str, str]:
        """The custom correction dictionary."""
        return dict(self._correction_dict)

    def update_correction_dict(self, updates: dict[str, str]) -> None:
        """Update the correction dictionary with new entries.

        Args:
            updates: New correction mappings to add/override.
        """
        self._correction_dict.update(updates)

    def clear_correction_dict(self) -> None:
        """Clear all entries from the correction dictionary."""
        self._correction_dict.clear()
