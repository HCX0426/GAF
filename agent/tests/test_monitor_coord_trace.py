"""E2 (spec 2026-07-30-debug-directory-restructure) — monitor 路径 coord_trace.

验证 PopupHandler._handle_popup 和 StorySkipper._skip_story/_handle_confirm
在调用 device.click 前通过 device.emit_coord_trace(step="monitor_click", ...)
记录 trace, 让 AI 调试时能看到 monitor 触发的点击来源 (popup/skip/confirm) 和坐标.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure src on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from monitor.handlers import PopupHandler, PopupTemplate, StorySkipper, StorySkipTemplate

pytestmark = pytest.mark.unit


def _make_device_mock() -> MagicMock:
    """Create a mock device with emit_coord_trace + click."""
    device = MagicMock()
    device.emit_coord_trace = MagicMock()
    return device


def _make_device_manager_mock(device: MagicMock) -> MagicMock:
    """Create a mock DeviceManager returning the given device."""
    mgr = MagicMock()
    mgr.get_active_device.return_value = device
    return mgr


def _make_image_processor_mock(match: dict | None = None) -> MagicMock:
    """Create a mock ImageProcessor returning the given match or None."""
    ip = MagicMock()
    ip.find_template.return_value = match
    return ip


# ── PopupHandler tests ────────────────────────────────────────────────


class TestPopupHandlerCoordTrace:
    """PopupHandler._handle_popup 调用 device.click 前必须记 trace."""

    def test_popup_template_target_emits_coord_trace_before_click(self):
        """action_target 匹配后, emit_coord_trace 在 click 前被调用."""
        device = _make_device_mock()
        device_mgr = _make_device_manager_mock(device)
        image_processor = _make_image_processor_mock(
            match={"x": 100, "y": 50, "w": 40, "h": 30}
        )
        handler = PopupHandler(device_mgr, image_processor)

        template = PopupTemplate(
            name="test_popup",
            detect_template="detect.png",
            action_type="click",
            action_target="target.png",
        )

        handler._execute_action(template)

        # 验证 emit_coord_trace 被调用
        device.emit_coord_trace.assert_called_once()
        call_kwargs = device.emit_coord_trace.call_args.kwargs
        assert call_kwargs["step"] == "monitor_click", (
            f"Expected step=monitor_click, got {call_kwargs.get('step')}"
        )
        # center = (100 + 40//2, 50 + 30//2) = (120, 65)
        assert call_kwargs["raw"] == (120, 65), (
            f"Expected raw=(120, 65), got {call_kwargs['raw']}"
        )
        assert call_kwargs["extra"]["source"] == "popup_handler"
        assert call_kwargs["extra"]["template_name"] == "test_popup"
        # 验证 click 在 emit_coord_trace 之后被调用
        device.click.assert_called_once_with(120, 65)

    def test_popup_coordinates_emits_coord_trace_before_click(self):
        """action_coordinates 直接点击时, emit_coord_trace 在 click 前被调用."""
        device = _make_device_mock()
        device_mgr = _make_device_manager_mock(device)
        image_processor = _make_image_processor_mock()  # no match needed
        handler = PopupHandler(device_mgr, image_processor)

        template = PopupTemplate(
            name="coord_popup",
            detect_template="detect.png",
            action_type="click",
            action_coordinates=(500, 300),
        )

        handler._execute_action(template)

        device.emit_coord_trace.assert_called_once()
        call_kwargs = device.emit_coord_trace.call_args.kwargs
        assert call_kwargs["step"] == "monitor_click"
        assert call_kwargs["raw"] == (500, 300)
        assert call_kwargs["extra"]["source"] == "popup_handler"
        device.click.assert_called_once_with(500, 300)

    def test_popup_no_device_skips_emit(self):
        """无活跃设备时, 不报错."""
        device_mgr = MagicMock()
        device_mgr.get_active_device.return_value = None
        image_processor = _make_image_processor_mock()
        handler = PopupHandler(device_mgr, image_processor)

        template = PopupTemplate(
            name="no_device",
            detect_template="detect.png",
            action_type="click",
            action_coordinates=(100, 100),
        )

        # 不应抛异常
        handler._execute_action(template)


# ── StorySkipper tests ────────────────────────────────────────────────


class TestStorySkipperCoordTrace:
    """StorySkipper._skip_story 和 _handle_confirm 调用 device.click 前必须记 trace."""

    def test_skip_button_template_emits_coord_trace_before_click(self):
        """skip_button_template 匹配后, emit_coord_trace 在 click 前被调用."""
        device = _make_device_mock()
        device_mgr = _make_device_manager_mock(device)
        image_processor = _make_image_processor_mock(
            match={"x": 200, "y": 100, "w": 50, "h": 40}
        )
        skipper = StorySkipper(device_mgr, image_processor)

        template = StorySkipTemplate(
            name="test_skip",
            detect_template="detect.png",
            skip_button_template="skip_btn.png",
            skip_delay=0,
        )

        skipper._skip_story(template)

        # 验证 emit_coord_trace 被调用 (skip 阶段)
        device.emit_coord_trace.assert_called_once()
        call_kwargs = device.emit_coord_trace.call_args.kwargs
        assert call_kwargs["step"] == "monitor_click"
        # center = (200 + 50//2, 100 + 40//2) = (225, 120)
        assert call_kwargs["raw"] == (225, 120), (
            f"Expected raw=(225, 120), got {call_kwargs['raw']}"
        )
        assert call_kwargs["extra"]["source"] == "story_skipper_skip"
        assert call_kwargs["extra"]["template_name"] == "test_skip"
        device.click.assert_called_once_with(225, 120)

    def test_skip_coordinates_emits_coord_trace_before_click(self):
        """skip_button_coordinates 直接点击时, emit_coord_trace 在 click 前被调用."""
        device = _make_device_mock()
        device_mgr = _make_device_manager_mock(device)
        image_processor = _make_image_processor_mock()
        skipper = StorySkipper(device_mgr, image_processor)

        template = StorySkipTemplate(
            name="coord_skip",
            detect_template="detect.png",
            skip_button_coordinates=(800, 600),
            skip_delay=0,
        )

        skipper._skip_story(template)

        device.emit_coord_trace.assert_called_once()
        call_kwargs = device.emit_coord_trace.call_args.kwargs
        assert call_kwargs["step"] == "monitor_click"
        assert call_kwargs["raw"] == (800, 600)
        assert call_kwargs["extra"]["source"] == "story_skipper_skip"
        device.click.assert_called_once_with(800, 600)

    def test_confirm_template_emits_coord_trace_before_click(self):
        """confirm_template 匹配后, emit_coord_trace 在 click 前被调用."""
        device = _make_device_mock()
        device_mgr = _make_device_manager_mock(device)
        image_processor = _make_image_processor_mock(
            match={"x": 50, "y": 50, "w": 30, "h": 20}
        )
        skipper = StorySkipper(device_mgr, image_processor)

        template = StorySkipTemplate(
            name="test_confirm",
            detect_template="detect.png",
            skip_button_coordinates=(100, 100),
            confirm_template="confirm.png",
            confirm_coordinates=None,
            skip_delay=0,
        )

        skipper._handle_confirm(template)

        device.emit_coord_trace.assert_called_once()
        call_kwargs = device.emit_coord_trace.call_args.kwargs
        assert call_kwargs["step"] == "monitor_click"
        # center = (50 + 30//2, 50 + 20//2) = (65, 60)
        assert call_kwargs["raw"] == (65, 60), (
            f"Expected raw=(65, 60), got {call_kwargs['raw']}"
        )
        assert call_kwargs["extra"]["source"] == "story_skipper_confirm"
        assert call_kwargs["extra"]["template_name"] == "test_confirm"
        device.click.assert_called_once_with(65, 60)

    def test_confirm_coordinates_emits_coord_trace_before_click(self):
        """confirm_coordinates 直接点击时, emit_coord_trace 在 click 前被调用."""
        device = _make_device_mock()
        device_mgr = _make_device_manager_mock(device)
        image_processor = _make_image_processor_mock()
        skipper = StorySkipper(device_mgr, image_processor)

        template = StorySkipTemplate(
            name="coord_confirm",
            detect_template="detect.png",
            skip_button_coordinates=(100, 100),
            confirm_coordinates=(400, 250),
            skip_delay=0,
        )

        skipper._handle_confirm(template)

        device.emit_coord_trace.assert_called_once()
        call_kwargs = device.emit_coord_trace.call_args.kwargs
        assert call_kwargs["step"] == "monitor_click"
        assert call_kwargs["raw"] == (400, 250)
        assert call_kwargs["extra"]["source"] == "story_skipper_confirm"
        device.click.assert_called_once_with(400, 250)

    def test_skip_no_device_skips_emit(self):
        """无活跃设备时, 不报错."""
        device_mgr = MagicMock()
        device_mgr.get_active_device.return_value = None
        image_processor = _make_image_processor_mock()
        skipper = StorySkipper(device_mgr, image_processor)

        template = StorySkipTemplate(
            name="no_device",
            detect_template="detect.png",
            skip_button_coordinates=(100, 100),
            skip_delay=0,
        )

        # 不应抛异常
        skipper._skip_story(template)
        skipper._handle_confirm(template)
