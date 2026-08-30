"""Unit tests for OcrPostProcessor (P-033 #37: gettext + custom correction dict)."""

import pytest
from recognition.ocr.post_processor import OcrPostProcessor
from recognition.ocr.types import OCRResult

pytestmark = pytest.mark.unit


class TestCorrectionDict:
    """Custom correction dictionary tests."""

    def test_empty_dict_returns_original(self):
        """Empty correction dict returns text unchanged."""
        processor = OcrPostProcessor()
        assert processor.apply_correction_dict("hello") == "hello"

    def test_basic_correction(self):
        """Basic character-level correction works."""
        processor = OcrPostProcessor(correction_dict={'l': '1', 'O': '0'})
        assert processor.apply_correction_dict("lOOl") == "1001"

    def test_chinese_correction(self):
        """Chinese character correction works."""
        processor = OcrPostProcessor(correction_dict={'丨': '1', '〇': '0'})
        assert processor.apply_correction_dict("丨〇〇丨") == "1001"

    def test_partial_correction(self):
        """Only characters in dict are replaced, others unchanged."""
        processor = OcrPostProcessor(correction_dict={'l': '1'})
        assert processor.apply_correction_dict("hello") == "he11o"

    def test_update_correction_dict(self):
        """update_correction_dict adds new entries."""
        processor = OcrPostProcessor(correction_dict={'a': '1'})
        processor.update_correction_dict({'b': '2'})
        assert processor.apply_correction_dict("ab") == "12"

    def test_clear_correction_dict(self):
        """clear_correction_dict removes all entries."""
        processor = OcrPostProcessor(correction_dict={'a': '1'})
        processor.clear_correction_dict()
        assert processor.apply_correction_dict("a") == "a"
        assert processor.correction_dict == {}


class TestProcessText:
    """Full pipeline process_text tests."""

    def test_no_processors_returns_original(self):
        """No processors enabled returns original text."""
        processor = OcrPostProcessor()
        assert processor.process_text("hello") == "hello"

    def test_correction_only(self):
        """Only correction dict applied (no OpenCC, no gettext)."""
        processor = OcrPostProcessor(correction_dict={'l': '1'})
        assert processor.process_text("hello") == "he11o"

    def test_correction_dict_property(self):
        """correction_dict property returns a copy."""
        original = {'a': '1'}
        processor = OcrPostProcessor(correction_dict=original)
        d = processor.correction_dict
        d['b'] = '2'
        # Original should be unchanged
        assert processor.correction_dict == {'a': '1'}


class TestProcessResults:
    """process_results tests with OCRResult list."""

    def test_process_empty_list(self):
        """Empty list returns empty list."""
        processor = OcrPostProcessor(correction_dict={'l': '1'})
        assert processor.process_results([]) == []

    def test_process_preserves_confidence_and_box(self):
        """Confidence and box are preserved, only text is modified."""
        processor = OcrPostProcessor(correction_dict={'l': '1'})
        results = [
            OCRResult(text="hello", confidence=0.95, box=(10, 20, 100, 50)),
        ]
        processed = processor.process_results(results)
        assert len(processed) == 1
        assert processed[0].text == "he11o"
        assert processed[0].confidence == 0.95
        assert processed[0].box == (10, 20, 100, 50)

    def test_process_multiple_results(self):
        """Multiple results are all processed."""
        processor = OcrPostProcessor(correction_dict={'l': '1', 'O': '0'})
        results = [
            OCRResult(text="lOOl", confidence=0.9, box=(0, 0, 10, 10)),
            OCRResult(text="text", confidence=0.8, box=(0, 0, 20, 20)),
        ]
        processed = processor.process_results(results)
        assert processed[0].text == "1001"
        assert processed[1].text == "text"


class TestProperties:
    """Property tests."""

    def test_opencc_available_default_false(self):
        """OpenCC is not available by default (auto_simplify=False)."""
        processor = OcrPostProcessor()
        assert processor.opencc_available is False

    def test_translation_available_default_false(self):
        """gettext translation is not available by default."""
        processor = OcrPostProcessor()
        assert processor.translation_available is False

    def test_translation_available_with_invalid_path(self):
        """gettext with invalid path falls back to no translation."""
        processor = OcrPostProcessor(
            translation_domain='test',
            translation_path='/nonexistent/path',
        )
        # fallback=True means translator is set but returns original text
        # Actually, with fallback=True, translation() returns NullTranslations
        # so translation_available should be True
        assert processor.translation_available is True
        # Translation should return original text
        assert processor.apply_translation("hello") == "hello"
