"""Pipeline 扩展节点：YOLO 检测、AI 抠图、高级输入"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


@register_node("yolo_detect")
@dataclass
class YoloDetectNode(PipelineNode):
    """YOLOv8 ONNX 目标检测 Pipeline 节点

    截图 → ONNX 推理 → 返回检测结果列表。

    config 参数：
    - model_path: ONNX 模型文件路径
    - confidence_threshold: 置信度阈值 (0.0~1.0)，默认 0.5
    - target_labels: 目标标签过滤列表，默认不过滤
    """

    node_type: str = "yolo_detect"

    def execute(self, context: PipelineContext) -> AutoResult:
        """执行 YOLO 目标检测

        Args:
            context: Pipeline 执行上下文

        Returns:
            AutoResult，data 包含检测结果列表
        """
        import time

        start = time.monotonic()
        model_path = self.config.get("model_path", "")
        confidence_threshold = self.config.get("confidence_threshold", 0.5)
        target_labels = self.config.get("target_labels", None)

        if not model_path:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="YoloDetectNode: 未配置 model_path",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
            )

        try:
            from core.onnx_engine import OnnxEngine

            engine = OnnxEngine(
                model_path=model_path,
                use_gpu=self.config.get("use_gpu", True),
                confidence_threshold=confidence_threshold,
            )

            if not engine.is_available:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg="ONNX 引擎不可用",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.DEVICE_ERROR,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            device = context.get_variable("device")
            if device is None:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg="上下文中未找到 device",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            screenshot = device.capture_screen()
            if screenshot is None:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg="截图失败",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.DEVICE_ERROR,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            screen_array = np.array(screenshot) if not isinstance(screenshot, np.ndarray) else screenshot
            detections = engine.detect(
                screen_array,
                confidence_threshold=confidence_threshold,
                target_labels=target_labels,
            )

            result_data = {
                "detections": [
                    {
                        "label": d.label,
                        "confidence": d.confidence,
                        "bbox": list(d.bbox),
                    }
                    for d in detections
                ],
                "count": len(detections),
                # N192 A2 P2: 补 coord_system / source 标签, 让下游节点可识别坐标系
                "coord_system": "logical",  # bbox 与截图同坐标系 (设备客户端逻辑坐标)
                "source": f"{self.id}_yolo_detect",
            }

            context.set_variable(f"{self.id}_detect_result", result_data)
            engine.close()
            elapsed = time.monotonic() - start
            return success_result(data=result_data, elapsed_time=elapsed)

        except ImportError as exc:
            elapsed = time.monotonic() - start
            logger.warning("ONNX 依赖未安装: %s", exc)
            return fail_result(
                error_msg=f"ONNX 依赖未安装: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error("YoloDetectNode 执行失败: %s", exc)
            return fail_result(
                error_msg=str(exc),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data={"input_config": self.config},
            )


@register_node("segment")
@dataclass
class SegmentNode(PipelineNode):
    """AI 智能抠图 Pipeline 节点

    截图 → AI 分割模型推理 → 返回分割区域列表。

    config 参数：
    - mode: 分割模式，"sam" 或 "u2net"，默认 "u2net"
    - model_path: 模型文件路径
    - target_labels: 目标标签过滤列表，默认不过滤
    - confidence_threshold: 置信度阈值，默认 0.5
    """

    node_type: str = "segment"

    def execute(self, context: PipelineContext) -> AutoResult:
        """执行 AI 智能抠图

        Args:
            context: Pipeline 执行上下文

        Returns:
            AutoResult，data 包含分割区域列表
        """
        import time

        start = time.monotonic()
        mode = self.config.get("mode", "u2net")
        model_path = self.config.get("model_path", "")
        target_labels = self.config.get("target_labels", None)
        confidence_threshold = self.config.get("confidence_threshold", 0.5)

        try:
            from core.segmentation import SegmentationEngine

            engine = SegmentationEngine(
                mode=mode,
                model_path=model_path,
            )

            if not engine.is_available:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg="分割引擎不可用：依赖未安装",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.DEVICE_ERROR,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            device = context.get_variable("device")
            if device is None:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg="上下文中未找到 device",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            screenshot = device.capture_screen()
            if screenshot is None:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg="截图失败",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.DEVICE_ERROR,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            screen_array = np.array(screenshot) if not isinstance(screenshot, np.ndarray) else screenshot
            regions = engine.segment(
                screen_array,
                confidence_threshold=confidence_threshold,
                target_labels=target_labels,
            )

            result_data = {
                "regions": [
                    {
                        "label": r.label,
                        "confidence": r.confidence,
                        "bbox": list(r.bbox),
                    }
                    for r in regions
                ],
                "count": len(regions),
                # N192 A2 P2: 补 coord_system / source 标签, 让下游节点可识别坐标系
                "coord_system": "logical",  # bbox 与截图同坐标系 (设备客户端逻辑坐标)
                "source": f"{self.id}_segment",
            }

            context.set_variable(f"{self.id}_segment_result", result_data)
            elapsed = time.monotonic() - start
            return success_result(data=result_data, elapsed_time=elapsed)

        except ImportError as exc:
            elapsed = time.monotonic() - start
            logger.warning("分割依赖未安装: %s", exc)
            return fail_result(
                error_msg=f"分割依赖未安装: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error("SegmentNode 执行失败: %s", exc)
            return fail_result(
                error_msg=str(exc),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data={"input_config": self.config},
            )


@register_node("advanced_input")
@dataclass
class AdvancedInputNode(PipelineNode):
    """高级输入 Pipeline 节点

    支持多种高级输入模式：message_fps / mouse_lock / block_input。

    config 参数：
    - input_mode: 输入模式，"message_fps" / "mouse_lock" / "block_input"
    - message: 消息内容（message_fps 模式使用）
    - window_title: 目标窗口标题
    - duration: 持续时长（秒），0 表示手动 stop
    """

    node_type: str = "advanced_input"

    def execute(self, context: PipelineContext) -> AutoResult:
        """执行高级输入操作

        Args:
            context: Pipeline 执行上下文

        Returns:
            AutoResult
        """
        import time

        start = time.monotonic()
        input_mode = self.config.get("input_mode", "block_input")
        message = self.config.get("message", "")
        window_title = self.config.get("window_title", "")
        duration = self.config.get("duration", 0)

        try:
            from core.advanced_input import BlockInput, MessageInputFPS, MouseLockFollow

            handler = None

            if input_mode == "message_fps":
                if not message:
                    elapsed = time.monotonic() - start
                    return fail_result(
                        error_msg="message_fps 模式需要提供 message 参数",
                        elapsed_time=elapsed,
                        error_code=NodeErrorCode.PARAM_INVALID,
                        node_id=self.id,
                        node_type=self.node_type,
                    )
                handler = MessageInputFPS(window_title=window_title, message=message)

            elif input_mode == "mouse_lock":
                handler = MouseLockFollow(window_title=window_title)

            elif input_mode == "block_input":
                handler = BlockInput()

            else:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"未知的输入模式: {input_mode}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            if not handler.is_available:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"输入模式 {input_mode} 不可用",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.DEVICE_ERROR,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            handler.start()

            if duration > 0:
                time.sleep(duration)
                handler.stop()

            context.set_variable(f"{self.id}_input_handler", handler)
            elapsed = time.monotonic() - start
            return success_result(
                data={
                    "input_mode": input_mode,
                    "active": handler.is_active,
                    # N192 A2 P2: 补 source 标签 (无坐标, 不补 coord_system)
                    "source": f"{self.id}_advanced_input",
                },
                elapsed_time=elapsed,
            )

        except ImportError as exc:
            elapsed = time.monotonic() - start
            logger.warning("高级输入依赖未安装: %s", exc)
            return fail_result(
                error_msg=f"高级输入依赖未安装: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error("AdvancedInputNode 执行失败: %s", exc)
            return fail_result(
                error_msg=str(exc),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data={"input_config": self.config},
            )
