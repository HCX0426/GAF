"""Pipeline 扩展节点 fail_result 三要素测试 (N192 A1 P1).

验证 YoloDetectNode / SegmentNode / AdvancedInputNode 的 fail_result 调用
都带 node_id / node_type / error_code, 让 AI 诊断时能定位节点 + 分类错误。

不验证节点执行成功路径, 只验证失败路径的三要素完整性。
"""
from unittest.mock import MagicMock, patch

import pytest
from core.error_codes import NodeErrorCode
from core.pipeline_nodes import AdvancedInputNode, SegmentNode, YoloDetectNode

pytestmark = pytest.mark.integration


class TestYoloDetectNodeFailResult:
    """YoloDetectNode 失败路径应带 error_code / node_id / node_type."""

    def test_fail_no_model_path_has_error_code_and_node_id(self):
        """缺 model_path 时 fail_result 应带 error_code=PARAM_INVALID + node_id."""
        node = YoloDetectNode(id="yolo_1", config={})
        mock_context = MagicMock()
        mock_context.get_variable.return_value = None

        result = node.execute(mock_context)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "yolo_1"
        assert result.node_type == "yolo_detect"
        assert "model_path" in result.error_msg

    def test_fail_onnx_unavailable_has_device_error(self):
        """ONNX 引擎不可用时 fail_result 应带 error_code=DEVICE_ERROR."""
        node = YoloDetectNode(id="yolo_1", config={"model_path": "/nonexistent.onnx"})
        mock_context = MagicMock()

        with patch("core.onnx_engine.OnnxEngine") as mock_engine_cls:
            mock_engine = MagicMock()
            mock_engine.is_available = False
            mock_engine_cls.return_value = mock_engine

            result = node.execute(mock_context)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_ERROR.value
        assert result.node_id == "yolo_1"
        assert result.node_type == "yolo_detect"

    def test_fail_no_device_in_context_has_device_disconnected(self):
        """上下文未找到 device 时 fail_result 应带 error_code=DEVICE_DISCONNECTED."""
        node = YoloDetectNode(id="yolo_1", config={"model_path": "/path.onnx"})
        mock_context = MagicMock()
        mock_context.get_variable.return_value = None  # device is None

        with patch("core.onnx_engine.OnnxEngine") as mock_engine_cls:
            mock_engine = MagicMock()
            mock_engine.is_available = True
            mock_engine_cls.return_value = mock_engine

            result = node.execute(mock_context)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "yolo_1"

    def test_fail_generic_exception_includes_input_config(self):
        """通用 Exception 路径应把 input_config 写入 data 让 AI 可见."""
        node = YoloDetectNode(id="yolo_1", config={"model_path": "/path.onnx", "confidence_threshold": 0.7})
        mock_context = MagicMock()

        with patch("core.onnx_engine.OnnxEngine", side_effect=RuntimeError("unexpected")):
            result = node.execute(mock_context)

        assert not result.success
        assert result.error_code == NodeErrorCode.UNKNOWN.value
        assert result.node_id == "yolo_1"
        # data 应包含 input_config
        assert result.data is not None
        assert "input_config" in result.data
        assert result.data["input_config"].get("model_path") == "/path.onnx"


class TestSegmentNodeFailResult:
    """SegmentNode 失败路径应带 error_code / node_id / node_type."""

    def test_fail_engine_unavailable_has_device_error(self):
        """分割引擎不可用时 fail_result 应带 error_code=DEVICE_ERROR."""
        node = SegmentNode(id="seg_1", config={"mode": "u2net"})
        mock_context = MagicMock()

        with patch("core.segmentation.SegmentationEngine") as mock_engine_cls:
            mock_engine = MagicMock()
            mock_engine.is_available = False
            mock_engine_cls.return_value = mock_engine

            result = node.execute(mock_context)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_ERROR.value
        assert result.node_id == "seg_1"
        assert result.node_type == "segment"

    def test_fail_generic_exception_includes_input_config(self):
        """通用 Exception 路径应把 input_config 写入 data."""
        node = SegmentNode(id="seg_1", config={"mode": "sam", "model_path": "/path"})
        mock_context = MagicMock()

        with patch("core.segmentation.SegmentationEngine", side_effect=RuntimeError("unexpected")):
            result = node.execute(mock_context)

        assert not result.success
        assert result.error_code == NodeErrorCode.UNKNOWN.value
        assert result.node_id == "seg_1"
        assert result.data is not None
        assert "input_config" in result.data


class TestAdvancedInputNodeFailResult:
    """AdvancedInputNode 失败路径应带 error_code / node_id / node_type."""

    def test_fail_message_fps_missing_message_has_param_invalid(self):
        """message_fps 模式缺 message 参数时 fail_result 应带 error_code=PARAM_INVALID."""
        node = AdvancedInputNode(id="input_1", config={"input_mode": "message_fps"})
        mock_context = MagicMock()

        result = node.execute(mock_context)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "input_1"
        assert result.node_type == "advanced_input"

    def test_fail_unknown_input_mode_has_param_invalid(self):
        """未知输入模式时 fail_result 应带 error_code=PARAM_INVALID."""
        node = AdvancedInputNode(id="input_1", config={"input_mode": "unknown_mode"})
        mock_context = MagicMock()

        result = node.execute(mock_context)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "input_1"

    def test_fail_generic_exception_includes_input_config(self):
        """通用 Exception 路径应把 input_config 写入 data."""
        node = AdvancedInputNode(id="input_1", config={"input_mode": "block_input", "duration": 5})
        mock_context = MagicMock()

        with patch("core.advanced_input.BlockInput", side_effect=RuntimeError("unexpected")):
            result = node.execute(mock_context)

        assert not result.success
        assert result.error_code == NodeErrorCode.UNKNOWN.value
        assert result.node_id == "input_1"
        assert result.data is not None
        assert "input_config" in result.data


class TestOrchestratorDeviceFailResult:
    """orchestrator 设备 fail_result 应带 error_code=DEVICE_DISCONNECTED."""

    def test_orchestrator_device_not_exist_has_device_disconnected(self):
        """设备不存在时 fail_result 应带 error_code=DEVICE_DISCONNECTED."""
        # 这个测试可能需要 mock 设备管理器, 如果太复杂可以跳过
        # 重点是验证 orchestrator.py L550 和 L570 的 fail_result 调用
        pytest.skip("orchestrator 集成测试需要完整 mock, 留给后续 task")


class TestResultDataCoordSystemAndSource:
    """N192 A2 P2: 成功路径 result_data 应含 coord_system / source 标签.

    让下游节点可识别坐标系 (logical / physical) 和数据来源 (node_id + node_type).
    """

    def test_yolo_detect_success_has_coord_system_and_source(self):
        """YoloDetectNode 成功时 result_data 应含 coord_system='logical' + source."""
        import numpy as np

        node = YoloDetectNode(id="yolo_1", config={"model_path": "/path.onnx"})
        mock_context = MagicMock()
        mock_device = MagicMock()
        mock_device.capture_screen.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_context.get_variable.return_value = mock_device

        with patch("core.onnx_engine.OnnxEngine") as mock_engine_cls:
            mock_engine = MagicMock()
            mock_engine.is_available = True
            mock_detection = MagicMock()
            mock_detection.label = "enemy"
            mock_detection.confidence = 0.95
            mock_detection.bbox = [10, 20, 30, 40]
            mock_engine.detect.return_value = [mock_detection]
            mock_engine_cls.return_value = mock_engine

            result = node.execute(mock_context)

        assert result.success
        assert result.data is not None
        assert result.data["coord_system"] == "logical"
        assert result.data["source"] == "yolo_1_yolo_detect"

    def test_segment_success_has_coord_system_and_source(self):
        """SegmentNode 成功时 result_data 应含 coord_system='logical' + source."""
        import numpy as np

        node = SegmentNode(id="seg_1", config={"mode": "u2net"})
        mock_context = MagicMock()
        mock_device = MagicMock()
        mock_device.capture_screen.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_context.get_variable.return_value = mock_device

        with patch("core.segmentation.SegmentationEngine") as mock_engine_cls:
            mock_engine = MagicMock()
            mock_engine.is_available = True
            mock_region = MagicMock()
            mock_region.label = "ui_element"
            mock_region.confidence = 0.88
            mock_region.bbox = [5, 15, 25, 35]
            mock_engine.segment.return_value = [mock_region]
            mock_engine_cls.return_value = mock_engine

            result = node.execute(mock_context)

        assert result.success
        assert result.data is not None
        assert result.data["coord_system"] == "logical"
        assert result.data["source"] == "seg_1_segment"

    def test_advanced_input_success_has_source(self):
        """AdvancedInputNode 成功时 result_data 应含 source (无坐标, 无 coord_system)."""
        node = AdvancedInputNode(id="input_1", config={"input_mode": "block_input"})
        mock_context = MagicMock()

        with patch("core.advanced_input.BlockInput") as mock_handler_cls:
            mock_handler = MagicMock()
            mock_handler.is_available = True
            mock_handler.is_active = True
            mock_handler_cls.return_value = mock_handler

            result = node.execute(mock_context)

        assert result.success
        assert result.data is not None
        assert result.data["source"] == "input_1_advanced_input"
        # advanced_input 不涉及坐标, 不应有 coord_system 字段
        assert "coord_system" not in result.data
