"""template_match 失败路径诊断字段测试 — N192 A2 P2.

验证 TemplateMatchNode 失败路径的 fail_result 调用都带:
- error_code / node_id / node_type 三要素 (Task 2.1 遗漏, Task 3.1 补齐)
- 诊断字段 threshold / confidence / coord_system / template / roi
  (可选 match_loc, 仅在到达匹配阶段时存在)

不验证成功路径, 只验证失败路径的诊断完整性, 让 AI 不必读 JSONL
就能从 result_data 拿到失败上下文 (N192 视角 A: AI 调试可观测性).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.error_codes import NodeErrorCode
from engine.context import PipelineContext
from engine.nodes.template_match import TemplateMatchNode

pytestmark = pytest.mark.unit


def _make_mock_device(screen=None):
    """Build mock device with optional screen (None = capture returns None)."""
    device = MagicMock()
    device.device_id = "mock"
    device.capture_screen.return_value = screen
    return device


def _make_context(device=None, debug_mode=False, transformer=None):
    """Build a real PipelineContext with given device / transformer.

    Using the real PipelineContext (vs bare MagicMock) makes sure attribute
    access patterns match production code (e.g. context.coord_transformer,
    context.debug_mode, context.emit_coord_trace).
    """
    ctx = PipelineContext()
    ctx.device = device
    ctx.debug_mode = debug_mode
    ctx.coord_transformer = transformer  # None → legacy raw-pixel path
    return ctx


class TestTemplateMatchFailDiagnostics:
    """N192 A2 P2: 失败路径 result_data 应含诊断字段 + 三要素."""

    def test_device_none_has_error_code_and_node_id(self):
        """device=None 时 fail_result 应带 error_code=DEVICE_DISCONNECTED + node_id."""
        node = TemplateMatchNode(
            id="tm_1",
            config={"template": "x.png", "threshold": 0.8},
        )
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "tm_1"
        assert result.node_type == "template_match"
        # 诊断字段
        assert result.data is not None
        assert result.data.get("threshold") == 0.8
        assert result.data.get("confidence") == 0.0
        assert result.data.get("coord_system") == "physical"
        assert result.data.get("template") == "x.png"

    def test_screen_none_has_error_code_and_node_id(self):
        """截图返回 None 时 fail_result 应带 error_code=DEVICE_ERROR + node_id."""
        node = TemplateMatchNode(
            id="tm_1",
            config={"template": "x.png", "threshold": 0.8},
        )
        device = _make_mock_device(screen=None)
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_ERROR.value
        assert result.node_id == "tm_1"
        assert result.node_type == "template_match"
        assert result.data is not None
        assert result.data.get("threshold") == 0.8

    def test_template_load_fail_includes_diagnostic_fields(self):
        """模板加载失败时 fail_data 应含 threshold/confidence/coord_system/template/roi.

        使用不存在的路径 → _load_template 返回 None → 走 legacy path 失败.
        """
        node = TemplateMatchNode(
            id="tm_1",
            config={
                "template": "/nonexistent/path/missing_template.png",
                "threshold": 0.85,
                "roi": {"x": 10, "y": 20, "w": 100, "h": 80},
            },
        )
        screen = np.zeros((200, 200, 3), dtype=np.uint8)
        device = _make_mock_device(screen=screen)
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "tm_1"
        assert result.node_type == "template_match"
        # 诊断字段
        assert result.data is not None
        assert result.data.get("threshold") == 0.85
        assert result.data.get("confidence") == 0.0  # 未到匹配阶段
        assert result.data.get("coord_system") == "physical"  # legacy path
        assert result.data.get("template") == "/nonexistent/path/missing_template.png"
        assert result.data.get("roi") == {"x": 10, "y": 20, "w": 100, "h": 80}

    def test_confidence_below_threshold_includes_diagnostic_fields(self):
        """置信度低于阈值时 fail_data 应含 threshold/confidence/match_loc/coord_system.

        用随机噪声 template + 全黑 screen (零方差) → CCOEFF_NORMED 分母含 0,
        confidence 极低, 低于阈值 0.99. 使用 20x20 template 避免 1x1 退化情况
        (1x1 template 在 OpenCV 中 CCOEFF_NORMED 恒返回 1.0, 是已知边界行为).
        """
        import base64

        import cv2

        # 20x20 随机噪声 template, base64 PNG 编码
        rng = np.random.RandomState(123)
        noise_template = rng.randint(0, 256, size=(20, 20, 3), dtype=np.uint8)
        ok, buf = cv2.imencode('.png', noise_template)
        assert ok
        noise_template_b64 = base64.b64encode(buf.tobytes()).decode('ascii')

        node = TemplateMatchNode(
            id="tm_2",
            config={
                "template": noise_template_b64,
                "threshold": 0.99,  # 高阈值, 必定失败
            },
        )
        screen = np.zeros((100, 100, 3), dtype=np.uint8)  # 全黑 (零方差)
        device = _make_mock_device(screen=screen)
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        # 应该是 LOW_CONFIDENCE (匹配跑完了, 但置信度低于阈值)
        assert result.error_code == NodeErrorCode.LOW_CONFIDENCE.value
        assert result.node_id == "tm_2"
        assert result.node_type == "template_match"
        # 诊断字段
        assert result.data is not None
        assert result.data.get("threshold") == 0.99
        assert "confidence" in result.data
        assert result.data.get("coord_system") == "physical"
        assert "template" in result.data
        assert "match_loc" in result.data  # 匹配阶段已跑完, 应有坐标

    def test_template_too_large_includes_diagnostic_fields(self):
        """模板尺寸大于搜索区域时 fail_data 应含诊断字段."""
        import base64

        import cv2

        # 200x200 template 比 100x100 screen 大
        big_template = np.zeros((200, 200, 3), dtype=np.uint8)
        ok, buf = cv2.imencode('.png', big_template)
        assert ok
        big_template_b64 = base64.b64encode(buf.tobytes()).decode('ascii')

        node = TemplateMatchNode(
            id="tm_1",
            config={
                "template": big_template_b64,
                "threshold": 0.8,
            },
        )
        screen = np.zeros((100, 100, 3), dtype=np.uint8)
        device = _make_mock_device(screen=screen)
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "tm_1"
        assert result.node_type == "template_match"
        assert result.data is not None
        assert result.data.get("threshold") == 0.8
        assert result.data.get("confidence") == 0.0
        assert result.data.get("coord_system") == "physical"

    def test_template_config_empty_includes_diagnostic_fields(self):
        """template 配置为空时 fail_data 应含诊断字段 (走 _load_template None 路径)."""
        node = TemplateMatchNode(
            id="tm_1",
            config={
                "template": "",  # 空字符串
                "threshold": 0.9,
            },
        )
        screen = np.zeros((100, 100, 3), dtype=np.uint8)
        device = _make_mock_device(screen=screen)
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "tm_1"
        assert result.node_type == "template_match"
        assert result.data is not None
        assert result.data.get("threshold") == 0.9
        assert result.data.get("confidence") == 0.0


class TestTemplateMatchFailResultContract:
    """所有 fail_result 调用必须带 error_code / node_id / node_type 三要素."""

    def test_all_fail_paths_have_node_id_and_node_type(self):
        """扫描性测试: 多种失败场景都应返回 node_id + node_type 非空."""
        screen = np.zeros((100, 100, 3), dtype=np.uint8)
        # Use a sentinel object (not a string) to avoid numpy array == str
        # comparison raising ValueError. Each scenario is a callable that
        # builds the appropriate context.
        screen_none = object()  # sentinel for "capture_screen returns None"
        device_none = object()  # sentinel for "device=None"

        def build_ctx(marker):
            if marker is device_none:
                return _make_context(device=None)
            if marker is screen_none:
                return _make_context(device=_make_mock_device(screen=None))
            # Otherwise treat as a numpy screen array
            return _make_context(device=_make_mock_device(screen=marker))

        scenarios = [
            ({"template": "x.png", "threshold": 0.8}, device_none, "device none"),
            ({"template": "x.png", "threshold": 0.8}, screen_none, "screen none"),
            ({"template": "/nonexistent.png", "threshold": 0.8}, screen, "template load fail"),
            ({"template": "", "threshold": 0.8}, screen, "template empty"),
        ]
        for config, marker, desc in scenarios:
            node = TemplateMatchNode(id="tm_x", config=config)
            ctx = build_ctx(marker)

            result = node.execute(ctx)
            assert not result.success, f"场景 {desc} 应失败"
            assert result.node_id == "tm_x", f"场景 {desc} 缺 node_id"
            assert result.node_type == "template_match", f"场景 {desc} 缺 node_type"
            assert result.error_code, f"场景 {desc} 缺 error_code"
            assert result.error_code != "", f"场景 {desc} error_code 为空"
