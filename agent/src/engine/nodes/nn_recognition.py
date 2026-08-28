"""P2-3 NN Classifier / Regressor nodes — ONNX Runtime inference.

MaaFramework Pipeline Protocol defines NeuralNetworkClassifier and
NeuralNetworkRegressor recognition types. These nodes load an ONNX model
and run inference on the current screen (or a cropped ROI), returning
the predicted label (classifier) or numeric output (regressor).

ONNX Runtime is already a transitive dependency via rapidocr-onnxruntime.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


def _lazy_import_onnxruntime():
    """Import onnxruntime lazily so the module loads even when ORT is missing."""
    try:
        import onnxruntime as ort  # type: ignore[import-not-found]
        return ort
    except ImportError:
        logger.warning("onnxruntime not available; NN nodes will degrade")
        return None


def _load_image(context: PipelineContext, roi: dict[str, int] | None) -> np.ndarray | None:
    """Acquire an image from context, optionally cropped to roi."""
    for var_name in ("image", "screenshot", "last_frame"):
        img = context.get_variable(var_name)
        if img is not None and isinstance(img, np.ndarray):
            if roi:
                x = max(0, int(roi.get("x", 0)))
                y = max(0, int(roi.get("y", 0)))
                w = int(roi.get("w", img.shape[1]))
                h = int(roi.get("h", img.shape[0]))
                x2 = min(x + w, img.shape[1])
                y2 = min(y + h, img.shape[0])
                return img[y:y2, x:x2]
            return img
    return None


def _preprocess(image: np.ndarray, *, target_size, normalize: bool, channel_first: bool,
                dtype: str) -> np.ndarray:
    """Resize + normalize + transpose to model input layout."""
    import cv2

    if target_size:
        tw, th = int(target_size[0]), int(target_size[1])
        image = cv2.resize(image, (tw, th))

    arr = image.astype(np.float32)
    if normalize:
        arr = arr / 255.0

    if channel_first:
        # HWC -> CHW
        arr = np.transpose(arr, (2, 0, 1))

    # Add batch dim.
    arr = np.expand_dims(arr, axis=0)

    if dtype == "float64":
        arr = arr.astype(np.float64)
    elif dtype == "int32":
        arr = arr.astype(np.int32)
    elif dtype == "uint8":
        arr = arr.astype(np.uint8)
    else:
        arr = arr.astype(np.float32)
    return arr


@register_node("nn_classifier")
@dataclass
class NNClassifierNode(PipelineNode):
    """P2-3 Neural network classifier node (ONNX Runtime).

    Runs an ONNX classification model on the current screen frame (or ROI)
    and returns the top-1 label + confidence.

    Config parameters:
    - model_path: Path to the .onnx model file (required).
    - input_name: Model input tensor name (default: auto-detect first input).
    - output_name: Model output tensor name (default: auto-detect first output).
    - labels: List[str] mapping class index to label name (optional).
        If omitted, returns raw class index as int.
    - target_size: [width, height] for input resize (default: no resize).
    - normalize: Divide pixel values by 255 (default True).
    - channel_first: Transpose HWC -> CHW (default True).
    - dtype: Input dtype ("float32"/"float64"/"int32"/"uint8", default "float32").
    - roi: {"x", "y", "w", "h"} crop region (default: full image).
    - top_k: Return top-K predictions (default 1).
    - confidence_min: Minimum confidence to consider a match (default 0.0).
    """

    node_type: str = "nn_classifier"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — N192 A1+A2: 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "model_path": self.config.get("model_path", ""),
            "roi": self.config.get("roi"),
            "top_k": self.config.get("top_k", 1),
            "confidence_min": self.config.get("confidence_min", 0.0),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()

        ort = _lazy_import_onnxruntime()
        if ort is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="onnxruntime not installed; cannot run nn_classifier",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.DEVICE_ERROR),
            )

        model_path = self.config.get("model_path")
        if not model_path:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="model_path is required",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.PARAM_INVALID),
            )

        image = _load_image(context, self.config.get("roi"))
        if image is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="no image available in context",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_ERROR,
                    image_var_checked=["image", "screenshot", "last_frame"],
                ),
            )

        try:
            session = ort.InferenceSession(model_path)
            input_name = self.config.get("input_name") or session.get_inputs()[0].name
            output_name = self.config.get("output_name") or session.get_outputs()[0].name

            input_arr = _preprocess(
                image,
                target_size=self.config.get("target_size"),
                normalize=self.config.get("normalize", True),
                channel_first=self.config.get("channel_first", True),
                dtype=self.config.get("dtype", "float32"),
            )

            outputs = session.run([output_name], {input_name: input_arr})
            logits = outputs[0]

            # Softmax + top-k.
            probs = _softmax(logits[0])
            top_k = int(self.config.get("top_k", 1))
            top_k = max(1, min(top_k, len(probs)))
            top_indices = np.argsort(probs)[::-1][:top_k]

            labels: list[str] = self.config.get("labels", [])
            results = []
            for idx in top_indices:
                label = labels[int(idx)] if int(idx) < len(labels) else str(int(idx))
                results.append({"label": label, "class_id": int(idx), "confidence": float(probs[int(idx)])})

            top = results[0]
            conf_min = float(self.config.get("confidence_min", 0.0))
            if top["confidence"] < conf_min:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"top-1 confidence {top['confidence']:.4f} < {conf_min}",
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.LOW_CONFIDENCE,
                        predictions=results,
                        top_confidence=top["confidence"],
                        confidence_min=conf_min,
                    ),
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.LOW_CONFIDENCE,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            result_data = {
                "label": top["label"],
                "class_id": top["class_id"],
                "confidence": top["confidence"],
                "predictions": results,
                "model_path": model_path,
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            }
            context.set_variable(f"{self.id}_nn_result", result_data)
            # P0-6: NN doesn't produce a 2D match position; skip publish_match_pos.
            elapsed = time.monotonic() - start
            logger.info(
                "nn_classifier: label=%s conf=%.4f elapsed=%.3fs",
                top["label"], top["confidence"], elapsed,
            )
            return success_result(data=result_data, elapsed_time=elapsed)
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error("nn_classifier failed: %s", exc, exc_info=True)
            return fail_result(
                error_msg=f"nn_classifier error: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN,
                    model_path=model_path,
                    exception_type=type(exc).__name__,
                ),
            )


@register_node("nn_regressor")
@dataclass
class NNRegressorNode(PipelineNode):
    """P2-3 Neural network regressor node (ONNX Runtime).

    Runs an ONNX regression model and returns the numeric output(s).

    Config parameters:
    - model_path: Path to the .onnx model file (required).
    - input_name / output_name: Tensor names (default: auto-detect).
    - target_size / normalize / channel_first / dtype: Same as classifier.
    - roi: Crop region (default: full image).
    - output_names: List[str] naming each output dimension (optional).
    """

    node_type: str = "nn_regressor"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — N192 A1+A2: 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "model_path": self.config.get("model_path", ""),
            "roi": self.config.get("roi"),
            "output_names": self.config.get("output_names", []),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()

        ort = _lazy_import_onnxruntime()
        if ort is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="onnxruntime not installed; cannot run nn_regressor",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.DEVICE_ERROR),
            )

        model_path = self.config.get("model_path")
        if not model_path:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="model_path is required",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.PARAM_INVALID),
            )

        image = _load_image(context, self.config.get("roi"))
        if image is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="no image available in context",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_ERROR,
                    image_var_checked=["image", "screenshot", "last_frame"],
                ),
            )

        try:
            session = ort.InferenceSession(model_path)
            input_name = self.config.get("input_name") or session.get_inputs()[0].name
            output_name = self.config.get("output_name") or session.get_outputs()[0].name

            input_arr = _preprocess(
                image,
                target_size=self.config.get("target_size"),
                normalize=self.config.get("normalize", True),
                channel_first=self.config.get("channel_first", True),
                dtype=self.config.get("dtype", "float32"),
            )

            outputs = session.run([output_name], {input_name: input_arr})
            raw = outputs[0].flatten().tolist()

            output_names: list[str] = self.config.get("output_names", [])
            values: dict[str, float] = {}
            for i, v in enumerate(raw):
                key = output_names[i] if i < len(output_names) else f"output_{i}"
                values[key] = float(v)

            result_data = {
                "outputs": values,
                "raw": raw,
                "model_path": model_path,
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            }
            context.set_variable(f"{self.id}_nn_result", result_data)
            elapsed = time.monotonic() - start
            logger.info("nn_regressor: outputs=%s elapsed=%.3fs", values, elapsed)
            return success_result(data=result_data, elapsed_time=elapsed)
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error("nn_regressor failed: %s", exc, exc_info=True)
            return fail_result(
                error_msg=f"nn_regressor error: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN,
                    model_path=model_path,
                    exception_type=type(exc).__name__,
                ),
            )


def _softmax(x: np.ndarray) -> np.ndarray:
    """Numerically stable softmax over a 1D array."""
    x = np.asarray(x, dtype=np.float64)
    z = x - np.max(x)
    e = np.exp(z)
    return e / np.sum(e)
