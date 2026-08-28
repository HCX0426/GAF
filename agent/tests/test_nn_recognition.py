"""P2-3 NN Classifier / Regressor node tests.

Mocks onnxruntime.InferenceSession so tests run without a real .onnx
model file. Verifies preprocessing, softmax, top-K selection,
confidence threshold, and error paths.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Register nodes.
import engine.nodes.nn_recognition  # noqa: F401
from engine.context import PipelineContext
from engine.node import PipelineNode
from engine.nodes.nn_recognition import (
    _preprocess,
    _softmax,
)

pytestmark = pytest.mark.unit

# ============================================================
# Helpers
# ============================================================

class _FakeInput:
    def __init__(self, name="input"):
        self.name = name


class _FakeOutput:
    def __init__(self, name="output"):
        self.name = name


class _FakeSession:
    """Minimal InferenceSession stand-in."""

    def __init__(self, output_values, input_name="input", output_name="output"):
        self._output_values = output_values
        self._input_name = input_name
        self._output_name = output_name

    def get_inputs(self):
        return [_FakeInput(self._input_name)]

    def get_outputs(self):
        return [_FakeOutput(self._output_name)]

    def run(self, output_names, input_feed):
        # Return list of arrays matching output_names.
        return [self._output_values]


def _make_ort_patch(output_values, input_name="input", output_name="output"):
    """Build a patch context that swaps onnxruntime.InferenceSession."""
    def _factory(model_path):
        return _FakeSession(output_values, input_name, output_name)

    fake_ort = MagicMock()
    fake_ort.InferenceSession = _factory
    return patch("engine.nodes.nn_recognition._lazy_import_onnxruntime",
                 return_value=fake_ort)


# ============================================================
# Test: _softmax helper
# ============================================================

class TestSoftmax:
    def test_softmax_sums_to_one(self):
        x = np.array([1.0, 2.0, 3.0])
        s = _softmax(x)
        assert abs(sum(s) - 1.0) < 1e-9

    def test_softmax_all_equal(self):
        x = np.array([5.0, 5.0, 5.0])
        s = _softmax(x)
        assert np.allclose(s, [1 / 3, 1 / 3, 1 / 3])

    def test_softmax_numerical_stability(self):
        # Large values should not overflow.
        x = np.array([1000.0, 1001.0, 1002.0])
        s = _softmax(x)
        assert np.all(np.isfinite(s))
        assert abs(sum(s) - 1.0) < 1e-9

    def test_softmax_ordering_preserved(self):
        x = np.array([1.0, 5.0, 3.0])
        s = _softmax(x)
        # Highest logit -> highest probability.
        assert s[1] > s[2] > s[0]


# ============================================================
# Test: _preprocess helper
# ============================================================

class TestPreprocess:
    def test_preprocess_default_shape(self):
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        out = _preprocess(img, target_size=None, normalize=True,
                          channel_first=True, dtype="float32")
        # batch=1, channel=3, h=10, w=10
        assert out.shape == (1, 3, 10, 10)
        assert out.dtype == np.float32

    def test_preprocess_resize(self):
        img = np.zeros((20, 30, 3), dtype=np.uint8)
        out = _preprocess(img, target_size=(64, 32), normalize=False,
                          channel_first=True, dtype="float32")
        # After resize: 32x64 (tw, th) → shape (1, 3, 32, 64)
        assert out.shape == (1, 3, 32, 64)

    def test_preprocess_normalize_divides_by_255(self):
        img = np.full((4, 4, 3), 255, dtype=np.uint8)
        out = _preprocess(img, target_size=None, normalize=True,
                          channel_first=False, dtype="float32")
        assert np.allclose(out, 1.0)

    def test_preprocess_no_normalize(self):
        img = np.full((4, 4, 3), 100, dtype=np.uint8)
        out = _preprocess(img, target_size=None, normalize=False,
                          channel_first=False, dtype="float32")
        assert np.allclose(out, 100.0)

    def test_preprocess_dtype_uint8(self):
        img = np.zeros((4, 4, 3), dtype=np.uint8)
        out = _preprocess(img, target_size=None, normalize=False,
                          channel_first=False, dtype="uint8")
        assert out.dtype == np.uint8

    def test_preprocess_channel_last(self):
        img = np.zeros((8, 6, 3), dtype=np.uint8)
        out = _preprocess(img, target_size=None, normalize=False,
                          channel_first=False, dtype="float32")
        assert out.shape == (1, 8, 6, 3)


# ============================================================
# Test: NNClassifierNode
# ============================================================

class TestNNClassifierNode:
    def test_missing_model_path_returns_fail(self):
        node = PipelineNode.create({
            "id": "n1", "node_type": "nn_classifier", "config": {},
        })
        ctx = PipelineContext()
        result = node.execute(ctx)
        assert not result.success
        assert "model_path" in result.error_msg

    def test_missing_image_returns_fail(self):
        node = PipelineNode.create({
            "id": "n2", "node_type": "nn_classifier",
            "config": {"model_path": "/fake/model.onnx"},
        })
        ctx = PipelineContext()
        result = node.execute(ctx)
        assert not result.success
        assert "no image" in result.error_msg

    def test_no_onnxruntime_returns_fail(self):
        node = PipelineNode.create({
            "id": "n3", "node_type": "nn_classifier",
            "config": {"model_path": "/fake/model.onnx"},
        })
        ctx = PipelineContext()
        ctx.set_variable("image", np.zeros((10, 10, 3), dtype=np.uint8))
        with patch("engine.nodes.nn_recognition._lazy_import_onnxruntime",
                   return_value=None):
            result = node.execute(ctx)
        assert not result.success
        assert "onnxruntime" in result.error_msg

    def test_classifier_success_top1(self):
        """Mock ORT returns 3-class logits; verify top-1 selection."""
        # logits where class 1 has the highest value.
        logits = np.array([[0.1, 5.0, 2.0]])
        node = PipelineNode.create({
            "id": "n4", "node_type": "nn_classifier",
            "config": {
                "model_path": "/fake/model.onnx",
                "labels": ["cat", "dog", "bird"],
                "target_size": [10, 10],
            },
        })
        ctx = PipelineContext()
        ctx.set_variable("image", np.zeros((20, 20, 3), dtype=np.uint8))
        with _make_ort_patch(logits):
            result = node.execute(ctx)
        assert result.success
        assert result.data["label"] == "dog"
        assert result.data["class_id"] == 1
        assert result.data["confidence"] > 0.5
        # context variable set
        assert ctx.get_variable("n4_nn_result") is not None

    def test_classifier_no_labels_returns_index_string(self):
        logits = np.array([[0.0, 0.0, 9.0]])
        node = PipelineNode.create({
            "id": "n5", "node_type": "nn_classifier",
            "config": {"model_path": "/fake/model.onnx", "target_size": [4, 4]},
        })
        ctx = PipelineContext()
        ctx.set_variable("image", np.zeros((8, 8, 3), dtype=np.uint8))
        with _make_ort_patch(logits):
            result = node.execute(ctx)
        assert result.success
        assert result.data["label"] == "2"  # No labels -> str(index)
        assert result.data["class_id"] == 2

    def test_classifier_top_k(self):
        logits = np.array([[1.0, 3.0, 2.0]])
        node = PipelineNode.create({
            "id": "n6", "node_type": "nn_classifier",
            "config": {
                "model_path": "/fake/model.onnx",
                "labels": ["a", "b", "c"],
                "top_k": 3,
                "target_size": [4, 4],
            },
        })
        ctx = PipelineContext()
        ctx.set_variable("image", np.zeros((4, 4, 3), dtype=np.uint8))
        with _make_ort_patch(logits):
            result = node.execute(ctx)
        assert result.success
        assert len(result.data["predictions"]) == 3
        # Top-1 should still be class 1.
        assert result.data["predictions"][0]["class_id"] == 1

    def test_classifier_confidence_below_min(self):
        # Evenly matched logits → low confidence on each class.
        logits = np.array([[1.0, 1.0, 1.0]])
        node = PipelineNode.create({
            "id": "n7", "node_type": "nn_classifier",
            "config": {
                "model_path": "/fake/model.onnx",
                "labels": ["a", "b", "c"],
                "confidence_min": 0.5,
                "target_size": [4, 4],
            },
        })
        ctx = PipelineContext()
        ctx.set_variable("image", np.zeros((4, 4, 3), dtype=np.uint8))
        with _make_ort_patch(logits):
            result = node.execute(ctx)
        assert not result.success
        assert "confidence" in result.error_msg
        # Predictions should still be in data.
        assert "predictions" in result.data

    def test_classifier_uses_screenshot_var(self):
        """_load_image also checks 'screenshot' variable."""
        logits = np.array([[5.0, 0.0]])
        node = PipelineNode.create({
            "id": "n8", "node_type": "nn_classifier",
            "config": {
                "model_path": "/fake/model.onnx",
                "labels": ["x", "y"],
                "target_size": [4, 4],
            },
        })
        ctx = PipelineContext()
        ctx.set_variable("screenshot", np.zeros((4, 4, 3), dtype=np.uint8))
        with _make_ort_patch(logits):
            result = node.execute(ctx)
        assert result.success
        assert result.data["label"] == "x"

    def test_classifier_uses_last_frame_var(self):
        """_load_image also checks 'last_frame' variable."""
        logits = np.array([[0.0, 9.0]])
        node = PipelineNode.create({
            "id": "n9", "node_type": "nn_classifier",
            "config": {
                "model_path": "/fake/model.onnx",
                "labels": ["x", "y"],
                "target_size": [4, 4],
            },
        })
        ctx = PipelineContext()
        ctx.set_variable("last_frame", np.zeros((4, 4, 3), dtype=np.uint8))
        with _make_ort_patch(logits):
            result = node.execute(ctx)
        assert result.success
        assert result.data["label"] == "y"

    def test_classifier_roi_crops_image(self):
        """ROI should crop the image before inference."""
        logits = np.array([[5.0]])
        node = PipelineNode.create({
            "id": "n10", "node_type": "nn_classifier",
            "config": {
                "model_path": "/fake/model.onnx",
                "labels": ["only"],
                "roi": {"x": 2, "y": 2, "w": 4, "h": 4},
                "target_size": [4, 4],
            },
        })
        ctx = PipelineContext()
        ctx.set_variable("image", np.zeros((10, 10, 3), dtype=np.uint8))
        with _make_ort_patch(logits):
            result = node.execute(ctx)
        assert result.success

    def test_classifier_exception_returns_fail(self):
        """If session.run raises, node returns fail_result gracefully."""
        class _BoomSession(_FakeSession):
            def run(self, output_names, input_feed):
                raise RuntimeError("inference blew up")

        def _factory(model_path):
            return _BoomSession(np.array([[0.0]]))

        fake_ort = MagicMock()
        fake_ort.InferenceSession = _factory

        node = PipelineNode.create({
            "id": "n11", "node_type": "nn_classifier",
            "config": {"model_path": "/fake/model.onnx", "target_size": [4, 4]},
        })
        ctx = PipelineContext()
        ctx.set_variable("image", np.zeros((4, 4, 3), dtype=np.uint8))
        with patch("engine.nodes.nn_recognition._lazy_import_onnxruntime",
                   return_value=fake_ort):
            result = node.execute(ctx)
        assert not result.success
        assert "nn_classifier error" in result.error_msg


# ============================================================
# Test: NNRegressorNode
# ============================================================

class TestNNRegressorNode:
    def test_regressor_missing_model_path(self):
        node = PipelineNode.create({
            "id": "r1", "node_type": "nn_regressor", "config": {},
        })
        ctx = PipelineContext()
        result = node.execute(ctx)
        assert not result.success
        assert "model_path" in result.error_msg

    def test_regressor_missing_image(self):
        node = PipelineNode.create({
            "id": "r2", "node_type": "nn_regressor",
            "config": {"model_path": "/fake/model.onnx"},
        })
        ctx = PipelineContext()
        result = node.execute(ctx)
        assert not result.success
        assert "no image" in result.error_msg

    def test_regressor_success_single_output(self):
        out = np.array([[42.5]])
        node = PipelineNode.create({
            "id": "r3", "node_type": "nn_regressor",
            "config": {"model_path": "/fake/model.onnx", "target_size": [4, 4]},
        })
        ctx = PipelineContext()
        ctx.set_variable("image", np.zeros((4, 4, 3), dtype=np.uint8))
        with _make_ort_patch(out):
            result = node.execute(ctx)
        assert result.success
        assert result.data["raw"] == [42.5]
        # Default output key when no output_names given.
        assert result.data["outputs"]["output_0"] == 42.5

    def test_regressor_success_named_outputs(self):
        out = np.array([[1.0, 2.0, 3.0]])
        node = PipelineNode.create({
            "id": "r4", "node_type": "nn_regressor",
            "config": {
                "model_path": "/fake/model.onnx",
                "output_names": ["x", "y", "angle"],
                "target_size": [4, 4],
            },
        })
        ctx = PipelineContext()
        ctx.set_variable("image", np.zeros((4, 4, 3), dtype=np.uint8))
        with _make_ort_patch(out):
            result = node.execute(ctx)
        assert result.success
        assert result.data["outputs"]["x"] == 1.0
        assert result.data["outputs"]["y"] == 2.0
        assert result.data["outputs"]["angle"] == 3.0

    def test_regressor_no_onnxruntime_returns_fail(self):
        node = PipelineNode.create({
            "id": "r5", "node_type": "nn_regressor",
            "config": {"model_path": "/fake/model.onnx"},
        })
        ctx = PipelineContext()
        ctx.set_variable("image", np.zeros((4, 4, 3), dtype=np.uint8))
        with patch("engine.nodes.nn_recognition._lazy_import_onnxruntime",
                   return_value=None):
            result = node.execute(ctx)
        assert not result.success
        assert "onnxruntime" in result.error_msg

    def test_regressor_exception_returns_fail(self):
        class _BoomSession(_FakeSession):
            def run(self, output_names, input_feed):
                raise RuntimeError("regressor blew up")

        def _factory(model_path):
            return _BoomSession(np.array([[0.0]]))

        fake_ort = MagicMock()
        fake_ort.InferenceSession = _factory

        node = PipelineNode.create({
            "id": "r6", "node_type": "nn_regressor",
            "config": {"model_path": "/fake/model.onnx", "target_size": [4, 4]},
        })
        ctx = PipelineContext()
        ctx.set_variable("image", np.zeros((4, 4, 3), dtype=np.uint8))
        with patch("engine.nodes.nn_recognition._lazy_import_onnxruntime",
                   return_value=fake_ort):
            result = node.execute(ctx)
        assert not result.success
        assert "nn_regressor error" in result.error_msg


# ============================================================
# Test: node registration
# ============================================================

class TestRegistration:
    def test_nn_classifier_registered(self):
        from engine.node import PIPELINE_NODE_REGISTRY
        assert "nn_classifier" in PIPELINE_NODE_REGISTRY

    def test_nn_regressor_registered(self):
        from engine.node import PIPELINE_NODE_REGISTRY
        assert "nn_regressor" in PIPELINE_NODE_REGISTRY
