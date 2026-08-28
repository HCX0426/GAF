"""Task 1.2 + 1.3: 6 个节点 fail_result 诊断字段测试 (N192 A2 P2).

验证 ocr / feature_match / color_detect / click / branch / app_control 6 个节点的
fail_result 调用都带:
- error_code / node_id / node_type 三要素 (Task 1.2)
- ocr/feature_match/color_detect 失败路径含 result_data 诊断字段 (Task 1.3):
  - coord_system / 节点配置关键字段 / 失败时的中间值

参考 test_template_match_failure.py 的测试模式, 走早期失败分支 (避免构造真实图像).

扩展段: 14 个动作类节点的 fail_result 三要素 + data.coord_system 测试
(long_press / swipe / key_press / text_input / wheel / multi_swipe /
 multi_touch / multi_scroll / wait / monitor / device_control / goto /
 direct_hit / nn_recognition)。
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import to register nodes.
import engine.nodes.app_control  # noqa: F401
import engine.nodes.branch  # noqa: F401
import engine.nodes.click  # noqa: F401  # noqa: F401
import engine.nodes.color_detect  # noqa: F401
import engine.nodes.device_control  # noqa: F401
import engine.nodes.feature_match  # noqa: F401
import engine.nodes.goto  # noqa: F401
import engine.nodes.key_press  # noqa: F401
import engine.nodes.long_press  # noqa: F401
import engine.nodes.monitor  # noqa: F401
import engine.nodes.multi_scroll  # noqa: F401
import engine.nodes.multi_swipe  # noqa: F401
import engine.nodes.multi_touch  # noqa: F401
import engine.nodes.neural_network  # noqa: F401
import engine.nodes.nn_recognition  # noqa: F401
import engine.nodes.ocr  # noqa: F401
import engine.nodes.random_delay  # noqa: F401
import engine.nodes.roi_resolver  # noqa: F401
import engine.nodes.swipe  # noqa: F401
import engine.nodes.template_match_any  # noqa: F401
import engine.nodes.text_input  # noqa: F401
import engine.nodes.wait  # noqa: F401
import engine.nodes.wheel  # noqa: F401
from core.error_codes import NodeErrorCode
from core.result import fail_result
from engine.context import PipelineContext
from engine.node import PIPELINE_NODE_REGISTRY
from engine.nodes._child_runner import run_child

pytestmark = pytest.mark.unit


def _make_node(node_type, node_id="test_node", config=None):
    """通过工厂创建节点实例."""
    return PIPELINE_NODE_REGISTRY[node_type].from_dict({
        "id": node_id,
        "node_type": node_type,
        "config": config or {},
    })


def _make_capture_device(screen=None, raise_exc=None):
    """Build mock device whose capture_screen returns screen / raises raise_exc."""
    dev = MagicMock()
    dev.device_id = "mock"
    if raise_exc is not None:
        dev.capture_screen.side_effect = raise_exc
    else:
        dev.capture_screen.return_value = screen
    return dev


def _make_context(device=None, debug_mode=False, transformer=None):
    """Build a real PipelineContext with given device / transformer."""
    ctx = PipelineContext()
    ctx.device = device
    ctx.debug_mode = debug_mode
    ctx.coord_transformer = transformer  # None → legacy raw-pixel path
    return ctx


# ============================================================
# OCRNode
# ============================================================

class TestOCRFailDiagnostics:
    """Task 1.2 + 1.3: ocr 节点 fail_result 诊断字段测试."""

    def test_no_image_device_error(self):
        """无图像 + 无设备 → DEVICE_ERROR + 诊断字段 (coord_system/region/expected_text/engine)."""
        node = _make_node("ocr", node_id="ocr_1", config={
            "region": {"x": 0, "y": 0, "w": 100, "h": 50},
            "expected_text": "hello",
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_ERROR.value
        assert result.node_id == "ocr_1"
        assert result.node_type == "ocr"
        # 诊断字段 (Task 1.3)
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("region") == {"x": 0, "y": 0, "w": 100, "h": 50}
        assert result.data.get("expected_text") == "hello"
        # engine 字段存在 (可能为 None / 'unavailable' / 引擎名)
        assert "engine" in result.data

    def test_mock_expected_text_mismatch_ocr_empty(self):
        """mock 路径 expected_text 不匹配 → OCR_EMPTY + 诊断字段."""
        node = _make_node("ocr", node_id="ocr_2", config={
            "mock_text": "actual text",
            "expected_text": "expected different",
            "region": {"x": 10, "y": 20, "w": 100, "h": 80},
        })
        ctx = _make_context(device=None)
        with patch.object(type(node), "_get_ocr_engine", return_value=(None, None)):
            result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.OCR_EMPTY.value
        assert result.node_id == "ocr_2"
        assert result.node_type == "ocr"
        # 诊断字段 + result_data 合并
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("region") == {"x": 10, "y": 20, "w": 100, "h": 80}
        assert result.data.get("expected_text") == "expected different"
        # mock 路径合并的 result_data 字段
        assert result.data.get("text") == "actual text"


# ============================================================
# FeatureMatchNode
# ============================================================

class TestFeatureMatchFailDiagnostics:
    """Task 1.2 + 1.3: feature_match 节点 fail_result 诊断字段测试."""

    def test_device_none_device_disconnected(self):
        """device=None → DEVICE_DISCONNECTED + 诊断字段 (method/min_matches/ratio_threshold)."""
        node = _make_node("feature_match", node_id="fm_1", config={
            "template": "x.png",
            "method": "sift",
            "min_matches": 15,
            "ratio_threshold": 0.7,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "fm_1"
        assert result.node_type == "feature_match"
        # 诊断字段
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("method") == "sift"
        assert result.data.get("min_matches") == 15
        assert result.data.get("ratio_threshold") == 0.7

    def test_invalid_method_param_invalid(self):
        """不支持的方法 → PARAM_INVALID + 诊断字段."""
        node = _make_node("feature_match", node_id="fm_2", config={
            "template": "x.png",
            "method": "invalid_detector",
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "fm_2"
        assert result.node_type == "feature_match"
        assert result.data is not None
        # method 字段保留原配置值, 让 AI 看到出错时的参数
        assert result.data.get("method") == "invalid_detector"

    def test_template_load_fail_param_invalid(self):
        """模板加载失败 → PARAM_INVALID + 诊断字段."""
        node = _make_node("feature_match", node_id="fm_3", config={
            "template": "/nonexistent/path/missing.png",
            "method": "orb",
        })
        screen = np.zeros((100, 100, 3), dtype=np.uint8)
        device = _make_capture_device(screen=screen)
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "fm_3"
        assert result.node_type == "feature_match"
        # 诊断字段
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("method") == "orb"

    def test_screen_none_device_error(self):
        """截图返回 None → DEVICE_ERROR + 诊断字段."""
        node = _make_node("feature_match", node_id="fm_4", config={
            "template": "x.png",
        })
        device = _make_capture_device(screen=None)
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_ERROR.value
        assert result.node_id == "fm_4"
        assert result.node_type == "feature_match"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"

    def test_solid_image_no_match(self):
        """纯色图像 → detectAndCompute 返回 None → NO_MATCH + 诊断字段.

        纯色图像没有特征点, ORB/SIFT 都返回 desc=None, 走"特征点提取失败"路径.
        """
        node = _make_node("feature_match", node_id="fm_5", config={
            "template": "x.png",  # 会 fallback 到全黑 screen 一起失败
            "method": "orb",
            "min_matches": 5,
        })
        # 全黑 screen + 全黑 template (template 加载失败先触发, 这里走 PARAM_INVALID)
        # 改用真实小图像让 template 加载成功, 但 screen 是纯色 → 特征点提取失败
        # 直接用 base64 编码一个噪声 template
        import base64

        import cv2
        rng = np.random.RandomState(42)
        noise_template = rng.randint(0, 256, size=(30, 30, 3), dtype=np.uint8)
        ok, buf = cv2.imencode('.png', noise_template)
        assert ok
        template_b64 = base64.b64encode(buf.tobytes()).decode('ascii')

        node = _make_node("feature_match", node_id="fm_5", config={
            "template": template_b64,
            "method": "orb",
            "min_matches": 5,
        })
        # screen 是纯色 (零方差), ORB 检测不到特征点
        screen = np.zeros((100, 100, 3), dtype=np.uint8)
        device = _make_capture_device(screen=screen)
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        # 纯色 screen → desc_screen=None → NO_MATCH (特征点提取失败)
        # 也可能 template 自身有特征点但 screen 没有, 走 NO_MATCH
        assert result.error_code in (
            NodeErrorCode.NO_MATCH.value,
            NodeErrorCode.LOW_CONFIDENCE.value,
        )
        assert result.node_id == "fm_5"
        assert result.node_type == "feature_match"
        # 诊断字段
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("method") == "orb"


# ============================================================
# ColorDetectNode
# ============================================================

class TestColorDetectFailDiagnostics:
    """Task 1.2 + 1.3: color_detect 节点 fail_result 诊断字段测试."""

    def test_device_none_device_disconnected(self):
        """device=None → DEVICE_DISCONNECTED + 诊断字段 (lower/upper/min_area)."""
        node = _make_node("color_detect", node_id="cd_1", config={
            "lower": [0, 50, 50],
            "upper": [10, 255, 255],
            "min_area": 50,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "cd_1"
        assert result.node_type == "color_detect"
        # 诊断字段
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("lower") == [0, 50, 50]
        assert result.data.get("upper") == [10, 255, 255]
        assert result.data.get("min_area") == 50

    def test_screen_none_device_error(self):
        """截图返回 None → DEVICE_ERROR + 诊断字段."""
        node = _make_node("color_detect", node_id="cd_2")
        device = _make_capture_device(screen=None)
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_ERROR.value
        assert result.node_id == "cd_2"
        assert result.node_type == "color_detect"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"

    def test_color_not_found_includes_mask_pixels(self):
        """颜色不匹配 → COLOR_NOT_FOUND + mask_nonzero_pixels 诊断字段.

        用全黑 screen + 蓝色 HSV 阈值 → mask 全零 → 无轮廓 → COLOR_NOT_FOUND.
        """
        node = _make_node("color_detect", node_id="cd_3", config={
            "lower": [100, 50, 50],   # 蓝色 HSV
            "upper": [130, 255, 255],
            "min_area": 10,
        })
        # 全黑 screen (BGR), HSV 阈值为蓝色 → mask 全零
        screen = np.zeros((100, 100, 3), dtype=np.uint8)
        device = _make_capture_device(screen=screen)
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.COLOR_NOT_FOUND.value
        assert result.node_id == "cd_3"
        assert result.node_type == "color_detect"
        # 诊断字段 + mask_nonzero_pixels (中间值)
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("lower") == [100, 50, 50]
        assert result.data.get("upper") == [130, 255, 255]
        assert result.data.get("min_area") == 10
        # mask 非零像素应为 0 (全黑 screen 不匹配蓝色阈值)
        assert "mask_nonzero_pixels" in result.data
        assert result.data.get("mask_nonzero_pixels") == 0


# ============================================================
# ClickNode
# ============================================================

class TestClickFailErrorCodes:
    """Task 1.2: click 节点 fail_result error_code 测试 (无 Task 1.3 诊断字段要求)."""

    def test_device_none_device_disconnected(self):
        """device=None → DEVICE_DISCONNECTED."""
        node = _make_node("click", node_id="clk_1", config={"x": 10, "y": 20})
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "clk_1"
        assert result.node_type == "click"

    def test_coord_invalid_for_unsupported_type(self):
        """坐标解析失败 (list 类型) → COORD_INVALID."""
        # list 类型不在 _resolve_coordinate 支持范围 → ValueError → COORD_INVALID
        node = _make_node("click", node_id="clk_2", config={"x": [1, 2, 3], "y": 20})
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.COORD_INVALID.value
        assert result.node_id == "clk_2"
        assert result.node_type == "click"

    def test_param_invalid_for_zero_clicks(self):
        """clicks < 1 → PARAM_INVALID."""
        node = _make_node("click", node_id="clk_3", config={
            "x": 10, "y": 20, "clicks": 0,
        })
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "clk_3"
        assert result.node_type == "click"


# ============================================================
# BranchNode
# ============================================================

class TestBranchFailErrorCodes:
    """Task 1.2: branch 节点 fail_result error_code 测试."""

    def test_empty_var_name_param_invalid(self):
        """condition_variable 为空 → PARAM_INVALID."""
        node = _make_node("branch", node_id="br_1", config={})
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "br_1"
        assert result.node_type == "branch"


# ============================================================
# StartAppNode / StopAppNode
# ============================================================

class TestAppControlFailErrorCodes:
    """Task 1.2: start_app / stop_app 节点 fail_result error_code 测试."""

    def test_start_app_no_device_device_disconnected(self):
        """start_app device=None → DEVICE_DISCONNECTED."""
        node = _make_node("start_app", node_id="sa_1", config={"package": "com.x"})
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "sa_1"
        assert result.node_type == "start_app"

    def test_start_app_android_no_package_param_invalid(self):
        """start_app Android + 空 package → PARAM_INVALID."""
        device = MagicMock()
        device.device_type = "emulator"
        node = _make_node("start_app", node_id="sa_2", config={})
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "sa_2"
        assert result.node_type == "start_app"

    def test_start_app_windows_no_command_param_invalid(self):
        """start_app Windows + 空 command → PARAM_INVALID."""
        device = MagicMock()
        device.device_type = "windows"
        node = _make_node("start_app", node_id="sa_3", config={})
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "sa_3"
        assert result.node_type == "start_app"

    def test_stop_app_no_device_device_disconnected(self):
        """stop_app device=None → DEVICE_DISCONNECTED."""
        node = _make_node("stop_app", node_id="sp_1", config={"package": "com.x"})
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "sp_1"
        assert result.node_type == "stop_app"

    def test_stop_app_android_no_package_param_invalid(self):
        """stop_app Android + 空 package → PARAM_INVALID."""
        device = MagicMock()
        device.device_type = "emulator"
        node = _make_node("stop_app", node_id="sp_2", config={})
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "sp_2"
        assert result.node_type == "stop_app"


# ============================================================
# 扫描性测试: 所有失败场景都应返回非空 error_code + node_id + node_type
# ============================================================

class TestAllNodesFailResultContract:
    """Task 1.2 contract: 所有 fail_result 调用必须带 error_code / node_id / node_type 三要素."""

    def test_all_fail_paths_have_three_element_metadata(self):
        """扫描性测试: 多种失败场景都应返回 node_id + node_type + 非空 error_code."""
        screen_none = object()  # sentinel for capture_screen returns None
        device_none = object()  # sentinel for device=None

        def build_ctx(marker):
            if marker is device_none:
                return _make_context(device=None)
            if marker is screen_none:
                return _make_context(device=_make_capture_device(screen=None))
            return _make_context(device=_make_capture_device(screen=marker))

        scenarios = [
            # (node_type, config, marker, description)
            ("ocr", {"region": {"x": 0, "y": 0, "w": 10, "h": 10}}, device_none, "ocr device none"),
            ("ocr", {"expected_text": "x"}, device_none, "ocr no image"),
            ("feature_match", {"template": "x.png"}, device_none, "fm device none"),
            ("feature_match", {"template": "x.png", "method": "bad"}, device_none, "fm bad method"),
            ("feature_match", {"template": "/missing.png"}, np.zeros((50, 50, 3), dtype=np.uint8), "fm template fail"),
            ("color_detect", {}, device_none, "cd device none"),
            ("color_detect", {}, screen_none, "cd screen none"),
            ("color_detect", {"lower": [100, 50, 50], "upper": [130, 255, 255]},
             np.zeros((50, 50, 3), dtype=np.uint8), "cd no match"),
            ("click", {"x": 0, "y": 0}, device_none, "click device none"),
            ("click", {"x": 0, "y": 0, "clicks": 0}, device_none, "click zero clicks"),
            ("branch", {}, device_none, "branch empty var"),
            ("start_app", {}, device_none, "start_app no device"),
            ("stop_app", {}, device_none, "stop_app no device"),
        ]
        for node_type, config, marker, desc in scenarios:
            node = _make_node(node_type, node_id=f"test_{desc.replace(' ', '_')}", config=config)
            ctx = build_ctx(marker)
            result = node.execute(ctx)
            assert not result.success, f"场景 {desc} 应失败"
            assert result.node_id, f"场景 {desc} 缺 node_id"
            assert result.node_type == node_type, f"场景 {desc} node_type 不匹配"
            assert result.error_code, f"场景 {desc} 缺 error_code"
            assert result.error_code != "", f"场景 {desc} error_code 为空"
            assert result.error_code != NodeErrorCode.UNKNOWN.value or "unknown" in desc.lower(), (
                f"场景 {desc} 不应默认 UNKNOWN (应分类到具体错误码)"
            )


# ============================================================
# 扩展段: 14 个动作类节点 fail_result 三要素 + data.coord_system 测试
# ============================================================

class TestLongPressFailDiagnostics:
    """long_press 节点 fail_result 诊断字段测试."""

    def test_device_none_device_disconnected(self):
        """device=None → DEVICE_DISCONNECTED + 诊断字段 (button/duration_ms)."""
        node = _make_node("long_press", node_id="lp_1", config={
            "x": 10, "y": 20, "button": "right", "duration_ms": 500,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "lp_1"
        assert result.node_type == "long_press"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("button") == "right"
        assert result.data.get("duration_ms") == 500

    def test_coord_invalid_for_unsupported_type(self):
        """坐标解析失败 (list 类型) → COORD_INVALID + 诊断字段."""
        node = _make_node("long_press", node_id="lp_2", config={
            "x": [1, 2], "y": 20,
        })
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.COORD_INVALID.value
        assert result.node_id == "lp_2"
        assert result.node_type == "long_press"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"


class TestSwipeFailDiagnostics:
    """swipe 节点 fail_result 诊断字段测试."""

    def test_device_none_device_disconnected(self):
        """device=None → DEVICE_DISCONNECTED + 诊断字段 (duration)."""
        node = _make_node("swipe", node_id="sw_1", config={
            "x1": 0, "y1": 0, "x2": 100, "y2": 100, "duration": 500,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "sw_1"
        assert result.node_type == "swipe"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("duration") == 500


class TestKeyPressFailDiagnostics:
    """key_press 节点 fail_result 诊断字段测试."""

    def test_device_none_device_disconnected(self):
        """device=None → DEVICE_DISCONNECTED + 诊断字段 (key/modifiers)."""
        node = _make_node("key_press", node_id="kp_1", config={
            "key": "enter", "modifiers": ["ctrl"],
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "kp_1"
        assert result.node_type == "key_press"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("key") == "enter"
        assert result.data.get("modifiers") == ["ctrl"]

    def test_empty_key_param_invalid(self):
        """空 key → PARAM_INVALID + 诊断字段."""
        node = _make_node("key_press", node_id="kp_2", config={"key": ""})
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "kp_2"
        assert result.node_type == "key_press"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"


class TestTextInputFailDiagnostics:
    """text_input 节点 fail_result 诊断字段测试."""

    def test_device_none_device_disconnected(self):
        """device=None → DEVICE_DISCONNECTED + 诊断字段 (text/clear_before)."""
        node = _make_node("text_input", node_id="ti_1", config={
            "text": "hello", "clear_before": True,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "ti_1"
        assert result.node_type == "text_input"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("text") == "hello"
        assert result.data.get("clear_before") is True

    def test_empty_text_param_invalid(self):
        """空 text → PARAM_INVALID + 诊断字段."""
        node = _make_node("text_input", node_id="ti_2", config={"text": ""})
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "ti_2"
        assert result.node_type == "text_input"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"


class TestWheelFailDiagnostics:
    """wheel 节点 fail_result 诊断字段测试."""

    def test_device_none_device_disconnected(self):
        """device=None → DEVICE_DISCONNECTED + 诊断字段 (delta)."""
        node = _make_node("wheel", node_id="wh_1", config={
            "x": 10, "y": 20, "delta": 240,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "wh_1"
        assert result.node_type == "wheel"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("delta") == 240

    def test_coord_invalid_for_unsupported_type(self):
        """坐标解析失败 (list 类型) → COORD_INVALID + 诊断字段."""
        node = _make_node("wheel", node_id="wh_2", config={
            "x": [1, 2], "y": 20,
        })
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.COORD_INVALID.value
        assert result.node_id == "wh_2"
        assert result.node_type == "wheel"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"


class TestMultiSwipeFailDiagnostics:
    """multi_swipe 节点 fail_result 诊断字段测试."""

    def test_device_none_device_disconnected(self):
        """device=None → DEVICE_DISCONNECTED + 诊断字段 (parallel/swipes_count)."""
        node = _make_node("multi_swipe", node_id="ms_1", config={
            "swipes": [{"x1": 0, "y1": 0, "x2": 100, "y2": 100}],
            "parallel": True,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "ms_1"
        assert result.node_type == "multi_swipe"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("parallel") is True
        assert result.data.get("swipes_count") == 1

    def test_empty_swipes_param_invalid(self):
        """空 swipes 列表 → PARAM_INVALID + 诊断字段."""
        node = _make_node("multi_swipe", node_id="ms_2", config={"swipes": []})
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "ms_2"
        assert result.node_type == "multi_swipe"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("swipes_count") == 0


class TestMultiTouchFailDiagnostics:
    """multi_touch 节点 fail_result 诊断字段测试."""

    def test_device_none_device_disconnected(self):
        """device=None → DEVICE_DISCONNECTED + 诊断字段 (parallel/touches_count)."""
        node = _make_node("multi_touch", node_id="mt_1", config={
            "touches": [{"action": "down", "x": 0, "y": 0}],
            "parallel": False,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "mt_1"
        assert result.node_type == "multi_touch"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("parallel") is False
        assert result.data.get("touches_count") == 1

    def test_empty_touches_param_invalid(self):
        """空 touches 列表 → PARAM_INVALID + 诊断字段."""
        node = _make_node("multi_touch", node_id="mt_2", config={"touches": []})
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "mt_2"
        assert result.node_type == "multi_touch"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"

    def test_invalid_action_param_invalid(self):
        """非法 action → PARAM_INVALID + 诊断字段 (touch_index/action)."""
        node = _make_node("multi_touch", node_id="mt_3", config={
            "touches": [{"action": "invalid_action", "x": 0, "y": 0}],
        })
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "mt_3"
        assert result.node_type == "multi_touch"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("touch_index") == 0
        assert result.data.get("action") == "invalid_action"


class TestMultiScrollFailDiagnostics:
    """multi_scroll 节点 fail_result 诊断字段测试."""

    def test_device_none_device_disconnected(self):
        """device=None → DEVICE_DISCONNECTED + 诊断字段 (parallel/scrolls_count)."""
        node = _make_node("multi_scroll", node_id="msc_1", config={
            "scrolls": [{"x": 0, "y": 0, "delta": 120}],
            "parallel": True,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "msc_1"
        assert result.node_type == "multi_scroll"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("parallel") is True
        assert result.data.get("scrolls_count") == 1

    def test_empty_scrolls_param_invalid(self):
        """空 scrolls 列表 → PARAM_INVALID + 诊断字段."""
        node = _make_node("multi_scroll", node_id="msc_2", config={"scrolls": []})
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "msc_2"
        assert result.node_type == "multi_scroll"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"


class TestWaitFailDiagnostics:
    """wait 节点 fail_result 诊断字段测试."""

    def test_unknown_mode_param_invalid(self):
        """未知 mode → PARAM_INVALID + 诊断字段 (mode)."""
        node = _make_node("wait", node_id="wt_1", config={"mode": "invalid_mode"})
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "wt_1"
        assert result.node_type == "wait"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("mode") == "invalid_mode"

    def test_stable_no_device_device_disconnected(self):
        """stable 模式 device=None → DEVICE_DISCONNECTED + 诊断字段."""
        node = _make_node("wait", node_id="wt_2", config={
            "mode": "stable", "max_wait": 1.0,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "wt_2"
        assert result.node_type == "wait"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("mode") == "stable"

    def test_template_no_device_device_disconnected(self):
        """template 模式 device=None → DEVICE_DISCONNECTED + 诊断字段."""
        node = _make_node("wait", node_id="wt_3", config={
            "mode": "template", "template": "x.png", "max_wait": 1.0,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "wt_3"
        assert result.node_type == "wait"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"

    def test_ocr_no_text_param_invalid(self):
        """ocr 模式无 text → PARAM_INVALID + 诊断字段."""
        node = _make_node("wait", node_id="wt_4", config={
            "mode": "ocr", "max_wait": 1.0,
        })
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "wt_4"
        assert result.node_type == "wait"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"


class TestMonitorFailDiagnostics:
    """monitor 节点 fail_result 诊断字段测试."""

    def test_unknown_action_param_invalid(self):
        """未知 action → PARAM_INVALID + 诊断字段 (action)."""
        node = _make_node("monitor", node_id="mn_1", config={"action": "invalid_action"})
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "mn_1"
        assert result.node_type == "monitor"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("action") == "invalid_action"


class TestDeviceControlFailDiagnostics:
    """device_control 节点 fail_result 诊断字段测试."""

    def test_unknown_action_param_invalid(self):
        """未知 action → PARAM_INVALID + 诊断字段 (action)."""
        node = _make_node("device_control", node_id="dc_1", config={"action": "invalid_action"})
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "dc_1"
        assert result.node_type == "device_control"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("action") == "invalid_action"


class TestGotoFailDiagnostics:
    """goto 节点 fail_result 诊断字段测试."""

    def test_empty_target_param_invalid(self):
        """空 target_node_id + label → PARAM_INVALID + 诊断字段 (target_node_id/label)."""
        node = _make_node("goto", node_id="gt_1", config={})
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "gt_1"
        assert result.node_type == "goto"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("target_node_id") == ""
        assert result.data.get("label") == ""


class TestDirectHitFailDiagnostics:
    """direct_hit 节点 fail_result 诊断字段测试."""

    def test_device_none_device_disconnected(self):
        """device=None → DEVICE_DISCONNECTED + 诊断字段 (button/clicks)."""
        node = _make_node("direct_hit", node_id="dh_1", config={
            "x": 10, "y": 20, "button": "right", "clicks": 2,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "dh_1"
        assert result.node_type == "direct_hit"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("button") == "right"
        assert result.data.get("clicks") == 2

    def test_coord_invalid_for_unsupported_type(self):
        """坐标解析失败 (list 类型) → COORD_INVALID + 诊断字段."""
        node = _make_node("direct_hit", node_id="dh_2", config={
            "x": [1, 2], "y": 20,
        })
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.COORD_INVALID.value
        assert result.node_id == "dh_2"
        assert result.node_type == "direct_hit"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"

    def test_zero_clicks_param_invalid(self):
        """clicks < 1 → PARAM_INVALID + 诊断字段 (clicks)."""
        node = _make_node("direct_hit", node_id="dh_3", config={
            "x": 10, "y": 20, "clicks": 0,
        })
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "dh_3"
        assert result.node_type == "direct_hit"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("clicks") == 0


class TestNNClassifierFailDiagnostics:
    """nn_classifier 节点 fail_result 诊断字段测试."""

    def test_no_model_path_param_invalid(self):
        """空 model_path → PARAM_INVALID + 诊断字段 (model_path/roi/top_k)."""
        node = _make_node("nn_classifier", node_id="nnc_1", config={
            "roi": {"x": 0, "y": 0, "w": 100, "h": 100},
            "top_k": 3,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "nnc_1"
        assert result.node_type == "nn_classifier"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("model_path") == ""
        assert result.data.get("roi") == {"x": 0, "y": 0, "w": 100, "h": 100}
        assert result.data.get("top_k") == 3

    def test_no_image_device_error(self):
        """有 model_path 但无图像 → DEVICE_ERROR + 诊断字段 (image_var_checked)."""
        node = _make_node("nn_classifier", node_id="nnc_2", config={
            "model_path": "/fake/path.onnx",
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_ERROR.value
        assert result.node_id == "nnc_2"
        assert result.node_type == "nn_classifier"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("model_path") == "/fake/path.onnx"
        assert result.data.get("image_var_checked") == ["image", "screenshot", "last_frame"]


class TestNNRegressorFailDiagnostics:
    """nn_regressor 节点 fail_result 诊断字段测试."""

    def test_no_model_path_param_invalid(self):
        """空 model_path → PARAM_INVALID + 诊断字段 (model_path/roi/output_names)."""
        node = _make_node("nn_regressor", node_id="nnr_1", config={
            "roi": {"x": 0, "y": 0, "w": 100, "h": 100},
            "output_names": ["score"],
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "nnr_1"
        assert result.node_type == "nn_regressor"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("model_path") == ""
        assert result.data.get("roi") == {"x": 0, "y": 0, "w": 100, "h": 100}
        assert result.data.get("output_names") == ["score"]

    def test_no_image_device_error(self):
        """有 model_path 但无图像 → DEVICE_ERROR + 诊断字段 (image_var_checked)."""
        node = _make_node("nn_regressor", node_id="nnr_2", config={
            "model_path": "/fake/path.onnx",
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_ERROR.value
        assert result.node_id == "nnr_2"
        assert result.node_type == "nn_regressor"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("model_path") == "/fake/path.onnx"
        assert result.data.get("image_var_checked") == ["image", "screenshot", "last_frame"]


# ============================================================
# 扩展扫描性测试: 14 个动作类节点失败场景都返回三要素 + data.coord_system
# ============================================================

class TestAllActionNodesFailResultContract:
    """14 个动作类节点 fail_result 契约: 三要素 + data.coord_system."""

    def test_all_action_node_fail_paths_have_full_metadata(self):
        """扫描性测试: 14 个动作类节点失败场景都返回 node_id + node_type +
        非空 error_code + data.coord_system."""
        screen_none = object()
        device_none = object()

        def build_ctx(marker):
            if marker is device_none:
                return _make_context(device=None)
            if marker is screen_none:
                return _make_context(device=_make_capture_device(screen=None))
            return _make_context(device=_make_capture_device(screen=marker))

        scenarios = [
            # (node_type, config, marker, description)
            ("long_press", {"x": 0, "y": 0}, device_none, "long_press device none"),
            ("long_press", {"x": [1], "y": 0}, MagicMock(), "long_press bad coord"),
            ("swipe", {"x1": 0, "y1": 0, "x2": 1, "y2": 1}, device_none, "swipe device none"),
            ("key_press", {"key": "enter"}, device_none, "key_press device none"),
            ("key_press", {"key": ""}, MagicMock(), "key_press empty key"),
            ("text_input", {"text": "x"}, device_none, "text_input device none"),
            ("text_input", {"text": ""}, MagicMock(), "text_input empty text"),
            ("wheel", {"x": 0, "y": 0}, device_none, "wheel device none"),
            ("wheel", {"x": [1], "y": 0}, MagicMock(), "wheel bad coord"),
            ("multi_swipe", {"swipes": [{"x1": 0, "y1": 0, "x2": 1, "y2": 1}]}, device_none, "multi_swipe device none"),
            ("multi_swipe", {"swipes": []}, MagicMock(), "multi_swipe empty"),
            ("multi_touch", {"touches": [{"action": "down", "x": 0, "y": 0}]}, device_none, "multi_touch device none"),
            ("multi_touch", {"touches": []}, MagicMock(), "multi_touch empty"),
            ("multi_touch", {"touches": [{"action": "bad", "x": 0, "y": 0}]}, MagicMock(), "multi_touch bad action"),
            ("multi_scroll", {"scrolls": [{"x": 0, "y": 0, "delta": 120}]}, device_none, "multi_scroll device none"),
            ("multi_scroll", {"scrolls": []}, MagicMock(), "multi_scroll empty"),
            ("wait", {"mode": "bad_mode"}, device_none, "wait bad mode"),
            ("wait", {"mode": "stable", "max_wait": 0.5}, device_none, "wait stable no device"),
            ("wait", {"mode": "template", "max_wait": 0.5}, device_none, "wait template no device"),
            ("wait", {"mode": "ocr", "max_wait": 0.5}, MagicMock(), "wait ocr no text"),
            ("wait", {"mode": "disappear", "max_wait": 0.5}, device_none, "wait disappear no device"),
            ("monitor", {"action": "bad_action"}, device_none, "monitor bad action"),
            ("device_control", {"action": "bad_action"}, device_none, "device_control bad action"),
            ("goto", {}, device_none, "goto empty target"),
            ("direct_hit", {"x": 0, "y": 0}, device_none, "direct_hit device none"),
            ("direct_hit", {"x": [1], "y": 0}, MagicMock(), "direct_hit bad coord"),
            ("direct_hit", {"x": 0, "y": 0, "clicks": 0}, MagicMock(), "direct_hit zero clicks"),
            ("nn_classifier", {}, device_none, "nn_classifier no model"),
            ("nn_classifier", {"model_path": "/fake.onnx"}, device_none, "nn_classifier no image"),
            ("nn_regressor", {}, device_none, "nn_regressor no model"),
            ("nn_regressor", {"model_path": "/fake.onnx"}, device_none, "nn_regressor no image"),
        ]
        for node_type, config, marker, desc in scenarios:
            node = _make_node(node_type, node_id=f"test_{desc.replace(' ', '_')}", config=config)
            ctx = build_ctx(marker)
            result = node.execute(ctx)
            assert not result.success, f"场景 {desc} 应失败"
            assert result.node_id, f"场景 {desc} 缺 node_id"
            assert result.node_type == node_type, f"场景 {desc} node_type 不匹配"
            assert result.error_code, f"场景 {desc} 缺 error_code"
            assert result.error_code != "", f"场景 {desc} error_code 为空"
            # data 必须含 coord_system (N191 schema 归一化 + N192 A2 诊断字段)
            assert result.data is not None, f"场景 {desc} 缺 data (诊断字段)"
            assert result.data.get("coord_system") == "legacy", (
                f"场景 {desc} data.coord_system 应为 'legacy'"
            )


# ============================================================
# Task 4.28 (P1-17): 7 个节点 fail_result 诊断字段测试
# branch / click / template_match_any / random_delay /
# roi_resolver / neural_network / _child_runner
# ============================================================

class TestBranchFailDiagnosticsData:
    """Task 4.28: branch 节点 fail_result data 诊断字段测试."""

    def test_empty_var_param_invalid_with_data(self):
        """condition_variable 为空 → PARAM_INVALID + data 含 coord_system/condition_variable/expected_value."""
        node = _make_node("branch", node_id="br_d1", config={
            "condition_operator": "eq",
            "condition_value": "expected",
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "br_d1"
        assert result.node_type == "branch"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("condition_variable") == ""
        assert result.data.get("expected_value") == "expected"


class TestClickFailDiagnosticsData:
    """Task 4.28: click 节点 fail_result data 诊断字段测试."""

    def test_device_none_with_data(self):
        """device=None → DEVICE_DISCONNECTED + data 含 coord_system/x/y."""
        node = _make_node("click", node_id="clk_d1", config={
            "x": 10, "y": 20, "button": "right",
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value
        assert result.node_id == "clk_d1"
        assert result.node_type == "click"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("x") == 10
        assert result.data.get("y") == 20
        assert result.data.get("button") == "right"

    def test_coord_invalid_with_data(self):
        """坐标解析失败 → COORD_INVALID + data 含 coord_system/x/y/resolve_error."""
        node = _make_node("click", node_id="clk_d2", config={
            "x": [1, 2, 3], "y": 20,
        })
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.COORD_INVALID.value
        assert result.node_id == "clk_d2"
        assert result.node_type == "click"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert "resolve_error" in result.data

    def test_zero_clicks_with_data(self):
        """clicks < 1 → PARAM_INVALID + data 含 coord_system/x/y/clicks."""
        node = _make_node("click", node_id="clk_d3", config={
            "x": 10, "y": 20, "clicks": 0,
        })
        device = MagicMock()
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "clk_d3"
        assert result.node_type == "click"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("x") == 10
        assert result.data.get("y") == 20
        assert result.data.get("clicks") == 0

    def test_success_path_has_coord_system(self):
        """Task 4.33 (P1-22): click 成功路径 result_data 含 coord_system 字段."""
        device = MagicMock()
        device.capture_screen.return_value = None  # 避免 debug 截图
        node = _make_node("click", node_id="clk_s1", config={
            "x": 10, "y": 20, "clicks": 1, "expect_screen_change": False,
        })
        ctx = _make_context(device=device)
        result = node.execute(ctx)

        assert result.success
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"


class TestTemplateMatchAnyFailDiagnosticsData:
    """Task 4.28: template_match_any 节点 fail_result data 诊断字段测试."""

    def test_empty_templates_param_invalid_with_data(self):
        """templates 为空 → PARAM_INVALID + data 含 coord_system/templates_count/threshold."""
        node = _make_node("template_match_any", node_id="tma_d1", config={
            "threshold": 0.9,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "tma_d1"
        assert result.node_type == "template_match_any"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("templates_count") == 0
        assert result.data.get("threshold") == 0.9

    def test_all_templates_fail_with_data(self):
        """全部模板失败 → NO_MATCH + data 含 coord_system/failed_templates_count."""
        node = _make_node("template_match_any", node_id="tma_d2", config={
            "templates": ["a.png", "b.png"],
            "threshold": 0.8,
        })
        ctx = _make_context(device=None)
        # mock run_child 返回失败, 模拟全部模板未命中
        with patch("engine.nodes.template_match_any.run_child") as mock_rc:
            mock_rc.return_value = fail_result(error_msg="mock fail")
            result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.NO_MATCH.value
        assert result.node_id == "tma_d2"
        assert result.node_type == "template_match_any"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("failed_templates_count") == 2
        assert result.data.get("successful_templates_count") == 0


class TestRandomDelayFailDiagnosticsData:
    """Task 4.28: random_delay 节点 fail_result data 诊断字段测试."""

    def test_invalid_min_max_with_data(self):
        """min/max 非法 (字符串) → PARAM_INVALID + data 含 coord_system/min/max."""
        node = _make_node("random_delay", node_id="rd_d1", config={
            "min": "abc", "max": "def",
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "rd_d1"
        assert result.node_type == "random_delay"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("min") == "abc"
        assert result.data.get("max") == "def"

    def test_invalid_range_with_data(self):
        """min < 0 → PARAM_INVALID + data 含 coord_system/min/max."""
        node = _make_node("random_delay", node_id="rd_d2", config={
            "min": -1.0, "max": 2.0,
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "rd_d2"
        assert result.node_type == "random_delay"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("min") == -1.0
        assert result.data.get("max") == 2.0


class TestROIResolverFailDiagnosticsData:
    """Task 4.28: roi_resolver 节点 fail_result data 诊断字段测试."""

    def test_missing_roi_param_invalid_with_data(self):
        """roi 缺失 → PARAM_INVALID + data 含 coord_system/roi/variable_name."""
        node = _make_node("roi_resolver", node_id="rr_d1", config={})
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "rr_d1"
        assert result.node_type == "roi_resolver"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("variable_name") == "rr_d1_roi"
        assert result.data.get("resolved_value") is None

    def test_invalid_roi_param_invalid_with_data(self):
        """roi 为非法 dict → PARAM_INVALID + data 含 coord_system/roi."""
        node = _make_node("roi_resolver", node_id="rr_d2", config={
            "roi": {"x": "abc", "y": 0, "w": 100, "h": 100},
        })
        ctx = _make_context(device=None)
        result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "rr_d2"
        assert result.node_type == "roi_resolver"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"


class TestNeuralNetworkFailDiagnosticsData:
    """Task 4.28: neural_network 节点 fail_result data 诊断字段测试."""

    def test_import_error_with_data(self):
        """ImportError → PARAM_INVALID + data 含 coord_system/model_path/framework/mode."""
        node = _make_node("neural_network", node_id="nn_d1", config={
            "mode": "classifier",
            "model_path": "/fake/path.onnx",
            "framework": "onnx",
        })
        ctx = _make_context(device=None)
        # mock nn_recognition 模块导入失败
        with patch.dict("sys.modules", {"engine.nodes.nn_recognition": None}):
            result = node.execute(ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.node_id == "nn_d1"
        assert result.node_type == "neural_network"
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("model_path") == "/fake/path.onnx"
        assert result.data.get("framework") == "onnx"
        assert result.data.get("mode") == "classifier"


class TestChildRunnerFailDiagnosticsData:
    """Task 4.28: _child_runner.run_child fail_result data 诊断字段测试."""

    def test_non_dict_spec_with_data(self):
        """非 dict spec → PARAM_INVALID + data 含 coord_system/spec_type."""
        ctx = _make_context(device=None)
        result = run_child("not_a_dict", ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("spec_type") == "str"
        assert result.data.get("child_pipeline_id") == ""

    def test_missing_node_type_with_data(self):
        """缺 node_type → PARAM_INVALID + data 含 coord_system/missing_key."""
        ctx = _make_context(device=None)
        result = run_child({"id": "child_1"}, ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.PARAM_INVALID.value
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert result.data.get("missing_key") == "node_type"
        assert result.data.get("child_pipeline_id") == "child_1"

    def test_child_create_exception_with_data(self):
        """child 创建异常 → UNKNOWN + data 含 coord_system/exception_type."""
        ctx = _make_context(device=None)
        # 用一个不存在的 node_type 触发 PipelineNode.create 异常
        result = run_child({
            "id": "child_2",
            "node_type": "nonexistent_node_type_xyz",
            "config": {},
        }, ctx)

        assert not result.success
        assert result.error_code == NodeErrorCode.UNKNOWN.value
        assert result.data is not None
        assert result.data.get("coord_system") == "legacy"
        assert "exception_type" in result.data
        assert result.data.get("child_pipeline_id") == "child_2"
        assert result.data.get("parent_node_id") == ""
        assert result.data.get("depth") == 0
