"""Tests for OCR engines: ONNXPaddleOCR, DGOCR, OpenCC converter (N126-F6)"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from recognition.ocr.dgocr_engine import DGOCREngine
from recognition.ocr.onnx_paddle_engine import ONNXPaddleOCREngine
from recognition.ocr.opencc_converter import OpenCCConverter
from recognition.ocr.types import OCRResult

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# ONNXPaddleOCREngine tests
# ---------------------------------------------------------------------------


class TestONNXPaddleOCREngine:
    """Verify ONNXPaddleOCR engine wrapper"""

    def test_default_config(self):
        engine = ONNXPaddleOCREngine()
        assert engine._use_angle_cls is False
        assert engine._use_npu is False
        assert engine._use_openvino is False
        assert engine._engine is None

    def test_custom_config(self):
        engine = ONNXPaddleOCREngine(
            use_angle_cls=True,
            use_npu=True,
            use_openvino=True,
            det_model_dir="/path/to/det",
            rec_model_dir="/path/to/rec",
        )
        assert engine._use_angle_cls is True
        assert engine._use_npu is True
        assert engine._use_openvino is True
        assert engine._det_model_dir == "/path/to/det"

    def test_available_languages(self):
        engine = ONNXPaddleOCREngine()
        assert "ch" in engine.available_languages()
        assert "en" in engine.available_languages()

    def test_raises_import_error_when_not_installed(self):
        engine = ONNXPaddleOCREngine()
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        with (
            patch.dict("sys.modules", {"onnxocr": None, "onnxocr.onnx_paddleocr": None}),
            pytest.raises(ImportError, match="ONNXPaddleOCR"),
        ):
            engine.recognize(image)

    def test_parses_ocr_result_correctly(self):
        """Verify ONNXPaddleOCR result format is parsed correctly"""
        engine = ONNXPaddleOCREngine()
        mock_onnx = MagicMock()
        # Simulate ONNXPaddleOcr.ocr() return: [[box, (text, conf)], ...]
        mock_onnx.ocr.return_value = [[
            ([[10, 20], [110, 20], [110, 60], [10, 60]], ("hello", 0.95)),
            ([[200, 100], [300, 100], [300, 140], [200, 140]], ("world", 0.88)),
        ]]
        engine._engine = mock_onnx

        image = np.zeros((200, 400, 3), dtype=np.uint8)
        results = engine.recognize(image)

        assert len(results) == 2
        assert results[0].text == "hello"
        assert results[0].confidence == pytest.approx(0.95)
        assert results[0].box == (10, 20, 110, 60)
        assert results[1].text == "world"
        assert results[1].box == (200, 100, 300, 140)

    def test_handles_empty_result(self):
        engine = ONNXPaddleOCREngine()
        mock_onnx = MagicMock()
        mock_onnx.ocr.return_value = []
        engine._engine = mock_onnx

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        results = engine.recognize(image)
        assert results == []

    def test_handles_none_result(self):
        engine = ONNXPaddleOCREngine()
        mock_onnx = MagicMock()
        mock_onnx.ocr.return_value = None
        engine._engine = mock_onnx

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        results = engine.recognize(image)
        assert results == []

    def test_handles_malformed_item(self):
        """Items missing text_info should be skipped, not crash"""
        engine = ONNXPaddleOCREngine()
        mock_onnx = MagicMock()
        mock_onnx.ocr.return_value = [[
            ([[10, 20], [110, 20], [110, 60], [10, 60]], ("ok", 0.9)),
            [],  # malformed item
            None,  # another malformed
        ]]
        engine._engine = mock_onnx

        image = np.zeros((100, 200, 3), dtype=np.uint8)
        results = engine.recognize(image)
        assert len(results) == 1
        assert results[0].text == "ok"


# ---------------------------------------------------------------------------
# DGOCREngine tests
# ---------------------------------------------------------------------------


class TestDGOCREngine:
    """Verify DGOCR engine wrapper"""

    def test_default_config(self):
        engine = DGOCREngine()
        assert engine._use_dml is True
        assert engine._engine is None

    def test_custom_config(self):
        engine = DGOCREngine(use_dml=False)
        assert engine._use_dml is False

    def test_available_languages(self):
        engine = DGOCREngine()
        assert "ch" in engine.available_languages()

    def test_raises_import_error_when_not_installed(self):
        engine = DGOCREngine()
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        with patch.dict("sys.modules", {"dgocr": None}), pytest.raises(ImportError, match="DGOCR"):
            engine.recognize(image)

    def test_parses_batched_result(self):
        """DGOCR returns a list of per-image result lists (batched)"""
        engine = DGOCREngine()
        mock_dgocr = MagicMock()
        # Batched format: [[image1_detections], [image2_detections]]
        mock_dgocr.run.return_value = [
            [
                ([[10, 20], [110, 20], [110, 60], [10, 60]], ("text1", 0.9)),
            ],
            [
                ([[50, 50], [150, 50], [150, 90], [50, 90]], ("text2", 0.85)),
            ],
        ]
        engine._engine = mock_dgocr

        image = np.zeros((200, 200, 3), dtype=np.uint8)
        results = engine.recognize(image)
        assert len(results) == 2
        assert results[0].text == "text1"
        assert results[1].text == "text2"

    def test_parses_single_image_result(self):
        """DGOCR may also return a flat list (single image)"""
        engine = DGOCREngine()
        mock_dgocr = MagicMock()
        # Single-image format: flat list of detections
        mock_dgocr.run.return_value = [
            ([[10, 20], [110, 20], [110, 60], [10, 60]], ("hello", 0.92)),
        ]
        engine._engine = mock_dgocr

        image = np.zeros((100, 200, 3), dtype=np.uint8)
        results = engine.recognize(image)
        # Note: single-image flat list may be detected as "batched" with
        # one image containing one detection — both paths should work
        assert len(results) >= 1
        assert results[0].text == "hello"

    def test_handles_empty_result(self):
        engine = DGOCREngine()
        mock_dgocr = MagicMock()
        mock_dgocr.run.return_value = []
        engine._engine = mock_dgocr

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        results = engine.recognize(image)
        assert results == []

    def test_handles_none_result(self):
        engine = DGOCREngine()
        mock_dgocr = MagicMock()
        mock_dgocr.run.return_value = None
        engine._engine = mock_dgocr

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        results = engine.recognize(image)
        assert results == []


# ---------------------------------------------------------------------------
# OpenCCConverter tests
# ---------------------------------------------------------------------------


class TestOpenCCConverter:
    """Verify OpenCC simplified/traditional Chinese conversion"""

    def test_default_config(self):
        conv = OpenCCConverter()
        assert conv._auto_simplify is False
        assert conv._conversion == "t2s"
        assert conv._japanese_fallback is False

    def test_custom_config(self):
        conv = OpenCCConverter(
            auto_simplify=True,
            conversion="s2t",
            japanese_fallback=True,
        )
        assert conv._auto_simplify is True
        assert conv._conversion == "s2t"
        assert conv._japanese_fallback is True

    def test_convert_text_returns_original_when_disabled(self):
        """When auto_simplify=False, text is returned unchanged"""
        conv = OpenCCConverter(auto_simplify=False)
        assert conv.convert_text("測試文字") == "測試文字"

    def test_convert_text_returns_original_when_opencc_missing(self):
        """When opencc package is not installed, text is returned unchanged"""
        conv = OpenCCConverter(auto_simplify=True)
        with patch.dict("sys.modules", {"opencc": None}):
            result = conv.convert_text("測試")
        assert result == "測試"

    def test_convert_text_uses_opencc_when_available(self):
        """When opencc is installed, text is converted"""
        conv = OpenCCConverter(auto_simplify=True, conversion="t2s")
        mock_opencc = MagicMock()
        mock_converter = MagicMock()
        mock_converter.convert.return_value = "测试"
        mock_opencc.return_value = mock_converter

        with patch("builtins.__import__") as mock_import:
            mock_import.return_value = MagicMock(OpenCC=mock_opencc)
            conv.convert_text("測試")
        # Should have called convert
        assert mock_converter.convert.called

    def test_convert_results_preserves_box_and_confidence(self):
        """convert_results should only change text, not box/confidence"""
        conv = OpenCCConverter(auto_simplify=False)  # disabled = passthrough
        original = [
            OCRResult(text="測試", confidence=0.95, box=(10, 20, 100, 50)),
            OCRResult(text="文字", confidence=0.88, box=(200, 100, 300, 140)),
        ]
        converted = conv.convert_results(original)
        assert len(converted) == 2
        assert converted[0].text == "測試"
        assert converted[0].confidence == 0.95
        assert converted[0].box == (10, 20, 100, 50)

    def test_convert_results_empty_list(self):
        conv = OpenCCConverter(auto_simplify=True)
        assert conv.convert_results([]) == []

    def test_is_available_false_when_disabled(self):
        conv = OpenCCConverter(auto_simplify=False)
        assert conv.is_available is False

    def test_is_available_false_when_opencc_missing(self):
        conv = OpenCCConverter(auto_simplify=True)
        with patch.dict("sys.modules", {"opencc": None}):
            assert conv.is_available is False

    def test_japanese_fallback_initializes_jp2t_converter(self):
        """When japanese_fallback=True, both jp2t and main converters are loaded"""
        conv = OpenCCConverter(
            auto_simplify=True, conversion="t2s", japanese_fallback=True
        )
        mock_opencc = MagicMock()
        mock_converter = MagicMock()
        mock_converter.convert.return_value = "converted"
        mock_opencc.return_value = mock_converter

        with patch("builtins.__import__") as mock_import:
            mock_import.return_value = MagicMock(OpenCC=mock_opencc)
            conv.convert_text("test")

        # OpenCC should have been called twice: once for jp2t, once for t2s
        assert mock_opencc.call_count == 2

    def test_unsupported_conversion_logs_warning(self):
        conv = OpenCCConverter(auto_simplify=True, conversion="invalid")
        result = conv.convert_text("test")
        # Should return original text due to invalid conversion
        assert result == "test"

    def test_supported_conversions_includes_common_configs(self):
        assert "t2s" in OpenCCConverter.SUPPORTED_CONVERSIONS
        assert "s2t" in OpenCCConverter.SUPPORTED_CONVERSIONS
        assert "jp2t" in OpenCCConverter.SUPPORTED_CONVERSIONS
        assert "tw2s" in OpenCCConverter.SUPPORTED_CONVERSIONS

    def test_auto_simplify_property(self):
        conv = OpenCCConverter(auto_simplify=True)
        assert conv.auto_simplify is True
        conv2 = OpenCCConverter(auto_simplify=False)
        assert conv2.auto_simplify is False
