"""Unit tests for ``_serialize_for_json`` in ``src/client/connection.py``.

Covers TD-016 regression: numpy ``ndarray`` / scalar types must be converted
to native Python types so ``json.dumps`` does not fall back to ``default=str``
and emit multi-KB array repr strings into ``task.result`` payloads.
"""

import dataclasses
import json

import numpy as np
import pytest
from client.connection import _serialize_for_json

pytestmark = pytest.mark.unit


class TestNumpySerialization:
    """numpy ndarray / scalar handling (TD-016 fix)."""

    def test_serialize_ndarray_1d(self):
        """1-D ndarray converts to a plain Python list."""
        arr = np.array([1, 2, 3])
        result = _serialize_for_json(arr)
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    def test_serialize_ndarray_2d(self):
        """2-D ndarray converts to a nested list."""
        arr = np.array([[1, 2], [3, 4]])
        result = _serialize_for_json(arr)
        assert result == [[1, 2], [3, 4]]

    def test_serialize_ndarray_3d(self):
        """3-D ndarray (e.g. screenshot RGB pixels) converts to nested list."""
        arr = np.array([[[42, 38, 38], [43, 39, 38]], [[10, 11, 12], [13, 14, 15]]])
        result = _serialize_for_json(arr)
        assert result == [[[42, 38, 38], [43, 39, 38]], [[10, 11, 12], [13, 14, 15]]]

    def test_serialize_ndarray_float_dtype(self):
        """float-dtype ndarray values become Python floats, not numpy floats."""
        arr = np.array([1.5, 2.5, 3.5], dtype=np.float32)
        result = _serialize_for_json(arr)
        assert result == [1.5, 2.5, 3.5]

    def test_serialize_ndarray_empty(self):
        """Empty ndarray converts to an empty list."""
        arr = np.array([])
        result = _serialize_for_json(arr)
        assert result == []

    def test_serialize_numpy_integer_scalar(self):
        """``np.int64`` scalar converts to a Python int."""
        assert _serialize_for_json(np.int64(42)) == 42
        assert isinstance(_serialize_for_json(np.int64(42)), int)

    def test_serialize_numpy_floating_scalar(self):
        """``np.float64`` scalar converts to a Python float."""
        result = _serialize_for_json(np.float64(3.14))
        assert abs(result - 3.14) < 1e-6
        assert isinstance(result, float)

    def test_serialize_numpy_bool_scalar(self):
        """``np.bool_`` scalar converts to a Python bool."""
        assert _serialize_for_json(np.bool_(True)) is True
        assert _serialize_for_json(np.bool_(False)) is False
        assert isinstance(_serialize_for_json(np.bool_(True)), bool)


class TestNumpyInNestedStructures:
    """numpy values embedded in dicts / lists / dataclasses."""

    def test_serialize_ndarray_inside_dict(self):
        """ndarray value inside a dict is converted."""
        payload = {"roi": np.array([1, 2, 3]), "score": 0.95}
        result = _serialize_for_json(payload)
        assert result == {"roi": [1, 2, 3], "score": 0.95}

    def test_serialize_ndarray_inside_list(self):
        """ndarray element inside a list is converted."""
        payload = [np.array([1, 2]), "label"]
        result = _serialize_for_json(payload)
        assert result == [[1, 2], "label"]

    def test_serialize_numpy_scalar_inside_dict(self):
        """numpy scalars inside a dict are converted to native types."""
        payload = {"count": np.int32(10), "ratio": np.float64(0.5)}
        result = _serialize_for_json(payload)
        assert result == {"count": 10, "ratio": 0.5}

    def test_serialize_ndarray_inside_dataclass(self):
        """ndarray inside a dataclass field is converted."""

        @dataclasses.dataclass
        class MatchResult:
            score: float
            bbox: np.ndarray

        obj = MatchResult(score=0.92, bbox=np.array([10, 20, 30, 40]))
        result = _serialize_for_json(obj)
        assert result == {"score": 0.92, "bbox": [10, 20, 30, 40]}


class TestJsonDumpsIntegration:
    """End-to-end: ``json.dumps`` succeeds without ``default=str`` fallback."""

    def test_json_dumps_ndarray_without_default_str(self):
        """json.dumps on a payload with ndarray does not need default=str."""
        payload = {
            "pixels": np.array([[1, 2], [3, 4]]),
            "count": np.int64(4),
            "ratio": np.float64(0.5),
        }
        serialized = _serialize_for_json(payload)
        # Should not raise TypeError; no default= fallback needed.
        text = json.dumps(serialized, ensure_ascii=False)
        # Verify the round-trip preserves the converted values.
        restored = json.loads(text)
        assert restored == {
            "pixels": [[1, 2], [3, 4]],
            "count": 4,
            "ratio": 0.5,
        }

    def test_json_dumps_ndarray_repr_not_in_output(self):
        """The numpy array repr string must not leak into the JSON output.

        Regression guard for TD-016: previously the ``default=str`` fallback
        produced ``"array([[1, 2],\\n [3, 4]])`` strings. The serialized
        output must contain a proper JSON array instead.
        """
        payload = {"data": np.array([1, 2, 3])}
        text = json.dumps(_serialize_for_json(payload), ensure_ascii=False)
        assert "array(" not in text
        assert "[1, 2, 3]" in text


class TestPassthroughValues:
    """Non-numpy values pass through unchanged."""

    def test_serialize_string(self):
        assert _serialize_for_json("hello") == "hello"

    def test_serialize_int(self):
        assert _serialize_for_json(42) == 42

    def test_serialize_none(self):
        assert _serialize_for_json(None) is None

    def test_serialize_plain_dict(self):
        assert _serialize_for_json({"a": 1}) == {"a": 1}

    def test_serialize_nested_plain(self):
        assert _serialize_for_json({"a": [1, {"b": 2}]}) == {"a": [1, {"b": 2}]}

    def test_serialize_dataclass(self):
        """Plain dataclass (no numpy) still converts to dict."""

        @dataclasses.dataclass
        class Point:
            x: int
            y: int

        assert _serialize_for_json(Point(1, 2)) == {"x": 1, "y": 2}
