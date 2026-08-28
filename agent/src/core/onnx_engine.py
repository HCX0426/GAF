"""ONNX 推理引擎：使用 onnxruntime 加载 .onnx 模型进行目标检测"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

try:
    import onnxruntime as ort
    _ONNX_AVAILABLE = True
except ImportError:
    _ONNX_AVAILABLE = False
    ort = None
    logger.warning("onnxruntime 未安装，ONNX 推理引擎将返回空结果")


@dataclass
class OnnxDetection:
    """ONNX 检测结果数据类

    Attributes:
        label: 检测到的标签/类别名称
        confidence: 置信度 (0.0~1.0)
        bbox: 边界框 (x, y, w, h)
    """

    label: str
    confidence: float
    bbox: tuple  # (x, y, w, h)


class OnnxEngine:
    """ONNX 推理引擎，封装 onnxruntime 进行目标检测推理

    Attributes:
        model_path: .onnx 模型文件路径
        providers: ONNX Runtime 执行提供者列表
        _session: onnxruntime.InferenceSession 实例
    """

    def __init__(
        self,
        model_path: str,
        use_gpu: bool = True,
        confidence_threshold: float = 0.5,
    ):
        """初始化 ONNX 推理引擎

        Args:
            model_path: .onnx 模型文件路径
            use_gpu: 是否尝试使用 GPU 加速（CUDA/DirectML）
            confidence_threshold: 默认置信度阈值
        """
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self._session: ort.InferenceSession | None = None
        self._input_name: str | None = None
        self._output_names: list[str] | None = None
        self._providers: list[str] = []

        if not _ONNX_AVAILABLE:
            logger.warning("onnxruntime 未安装，OnnxEngine 初始化跳过模型加载")
            return

        self._init_session(use_gpu)

    def _get_available_providers(self, use_gpu: bool) -> list[str]:
        """获取可用的 ONNX 执行提供者列表

        Args:
            use_gpu: 是否尝试 GPU 加速

        Returns:
            提供者优先级列表
        """
        if not use_gpu:
            return ["CPUExecutionProvider"]

        providers = []
        available = ort.get_available_providers() if ort else []

        if "CUDAExecutionProvider" in available:
            providers.append("CUDAExecutionProvider")
            logger.info("检测到 CUDA，启用 GPU 加速")
        elif "DmlExecutionProvider" in available:
            providers.append("DmlExecutionProvider")
            logger.info("检测到 DirectML，启用 GPU 加速")
        else:
            logger.info("未检测到 GPU 提供者，回退到 CPU 推理")

        if "CPUExecutionProvider" in available:
            providers.append("CPUExecutionProvider")

        return providers if providers else ["CPUExecutionProvider"]

    def _init_session(self, use_gpu: bool) -> None:
        """初始化 onnxruntime 推理会话

        Args:
            use_gpu: 是否尝试 GPU 加速
        """
        try:
            self._providers = self._get_available_providers(use_gpu)
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )
            self._session = ort.InferenceSession(
                self.model_path,
                sess_options=sess_options,
                providers=self._providers,
            )
            self._input_name = self._session.get_inputs()[0].name
            self._output_names = [out.name for out in self._session.get_outputs()]
            logger.info(
                "ONNX 模型加载成功: %s, 提供者: %s",
                self.model_path,
                self._session.get_providers(),
            )
        except Exception as exc:
            logger.error("ONNX 模型加载失败: %s, 错误: %s", self.model_path, exc)
            self._session = None

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """图像预处理：缩放、归一化、转换为模型输入格式

        Args:
            image: 原始 BGR 图像 (H, W, 3) numpy 数组

        Returns:
            预处理后的模型输入张量 (1, 3, 640, 640)
        """
        import cv2

        input_size = 640
        img = cv2.resize(image, (input_size, input_size))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.transpose(2, 0, 1)
        img = img.astype(np.float32) / 255.0
        img = np.expand_dims(img, axis=0)
        return img

    def _postprocess(
        self,
        outputs: list[np.ndarray],
        original_shape: tuple,
        confidence_threshold: float,
        target_labels: list[str] | None = None,
    ) -> list[OnnxDetection]:
        """YOLO 输出后处理：解析检测结果、NMS、坐标缩放

        Args:
            outputs: 模型原始输出
            original_shape: 原始图像 (H, W)
            confidence_threshold: 置信度阈值
            target_labels: 目标标签过滤列表，为空则不过滤

        Returns:
            OnnxDetection 列表
        """
        detections: list[OnnxDetection] = []

        if not outputs:
            return detections

        output = outputs[0]
        if output is None or output.size == 0:
            return detections

        orig_h, orig_w = original_shape[:2]
        input_size = 640
        scale_x = orig_w / input_size
        scale_y = orig_h / input_size

        det_output = output[0] if output.ndim == 3 else output

        for row in det_output:
            if row.ndim == 0:
                continue
            class_id = int(row[5]) if len(row) > 5 else -1
            confidence = float(row[4]) if len(row) > 4 else 0.0

            if confidence < confidence_threshold:
                continue

            cx, cy, bw, bh = float(row[0]), float(row[1]), float(row[2]), float(row[3])
            x = int((cx - bw / 2) * scale_x)
            y = int((cy - bh / 2) * scale_y)
            w = int(bw * scale_x)
            h = int(bh * scale_y)

            x = max(0, min(x, orig_w - 1))
            y = max(0, min(y, orig_h - 1))
            w = max(1, min(w, orig_w - x))
            h = max(1, min(h, orig_h - y))

            label = f"class_{class_id}"
            if target_labels and label not in target_labels and str(class_id) not in target_labels:
                continue

            detections.append(
                OnnxDetection(
                    label=label,
                    confidence=confidence,
                    bbox=(x, y, w, h),
                )
            )

        return detections

    def detect(
        self,
        image: np.ndarray,
        confidence_threshold: float | None = None,
        target_labels: list[str] | None = None,
    ) -> list[OnnxDetection]:
        """对输入图像执行目标检测

        Args:
            image: BGR 图像 (H, W, 3) numpy 数组
            confidence_threshold: 置信度阈值，默认使用实例配置
            target_labels: 目标标签过滤列表

        Returns:
            OnnxDetection 检测结果列表，引擎不可用时返回空列表
        """
        if not _ONNX_AVAILABLE or self._session is None:
            logger.warning("ONNX 引擎不可用，返回空检测结果")
            return []

        threshold = confidence_threshold or self.confidence_threshold

        try:
            input_tensor = self._preprocess(image)
            outputs = self._session.run(self._output_names, {self._input_name: input_tensor})
            return self._postprocess(
                outputs,
                image.shape,
                threshold,
                target_labels,
            )
        except Exception as exc:
            logger.error("ONNX 推理失败: %s", exc)
            return []

    @property
    def is_available(self) -> bool:
        """检查 ONNX 引擎是否可用

        Returns:
            True 表示引擎已就绪可进行推理
        """
        return _ONNX_AVAILABLE and self._session is not None

    def close(self) -> None:
        """释放 ONNX 推理会话资源"""
        if self._session is not None:
            try:
                del self._session
                self._session = None
                logger.info("ONNX 会话已释放")
            except Exception:
                pass
