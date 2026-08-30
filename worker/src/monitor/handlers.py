"""弹窗处理器和剧情跳过器：自动检测并处理游戏中的弹窗和剧情对话"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.constants import EventType

if TYPE_CHECKING:
    from devices.manager import DeviceManager
    from image.processor import ImageProcessor

logger = logging.getLogger(__name__)


@dataclass
class PopupTemplate:
    """弹窗模板定义"""
    name: str
    detect_template: str
    detect_roi: dict[str, int] | None = None
    detect_threshold: float = 0.8
    action_type: str = "click"
    action_target: str | None = None
    action_coordinates: tuple[int, int] | None = None
    action_roi: dict[str, int] | None = None
    priority: int = 0
    cooldown: float = 1.0
    last_triggered: float = 0.0

    def __post_init__(self):
        """校验模板参数"""
        if not self.name:
            raise ValueError("弹窗模板名称不能为空")
        if self.action_type == EventType.CLICK and not self.action_target and not self.action_coordinates:
            raise ValueError(f"弹窗模板 {self.name} 的 click 操作必须指定 action_target 或 action_coordinates")


@dataclass
class StorySkipTemplate:
    """剧情跳过模板定义"""
    name: str
    detect_template: str
    detect_roi: dict[str, int] | None = None
    detect_threshold: float = 0.85
    skip_button_template: str | None = None
    skip_button_coordinates: tuple[int, int] | None = None
    confirm_template: str | None = None
    confirm_coordinates: tuple[int, int] | None = None
    skip_delay: float = 0.5

    def __post_init__(self):
        """校验模板参数"""
        if not self.name:
            raise ValueError("剧情跳过模板名称不能为空")
        if not self.skip_button_template and not self.skip_button_coordinates:
            raise ValueError(f"剧情跳过模板 {self.name} 必须指定 skip_button_template 或 skip_button_coordinates")


class PopupHandler:
    """弹窗处理器：自动检测并关闭游戏中的各类弹窗

    支持多种弹窗类型：
    - 系统公告弹窗
    - 活动推荐弹窗
    - 奖励领取弹窗
    - 网络异常弹窗
    - 更新提示弹窗
    """

    def __init__(
        self,
        device_manager: DeviceManager,
        image_processor: ImageProcessor,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self._device_manager = device_manager
        self._image_processor = image_processor
        self._event_callback = event_callback or self._default_event_callback
        self._templates: dict[str, PopupTemplate] = {}

    def add_template(self, template: PopupTemplate) -> None:
        """添加弹窗模板

        Args:
            template: 弹窗模板实例
        """
        self._templates[template.name] = template
        logger.info("已添加弹窗模板: %s (priority=%d)", template.name, template.priority)

    def remove_template(self, name: str) -> None:
        """移除弹窗模板

        Args:
            name: 模板名称
        """
        if name in self._templates:
            del self._templates[name]
            logger.info("已移除弹窗模板: %s", name)

    def check_and_handle(self, screenshot: Any | None = None) -> bool:
        """检查并处理弹窗

        按优先级遍历所有弹窗模板，检测是否存在匹配的弹窗，
        如果存在则执行对应的关闭操作

        Args:
            screenshot: 当前截图，为 None 时自动截图

        Returns:
            是否处理了弹窗
        """
        if screenshot is None:
            screenshot = self._take_screenshot()
        if screenshot is None:
            return False

        sorted_templates = sorted(self._templates.values(), key=lambda t: t.priority, reverse=True)

        for template in sorted_templates:
            now = time.monotonic()
            if now - template.last_triggered < template.cooldown:
                continue

            match = self._image_processor.find_template(
                screenshot,
                template.detect_template,
                roi=template.detect_roi,
                threshold=template.detect_threshold,
            )
            if match is None:
                continue

            logger.info("检测到弹窗: %s (confidence=%.2f)", template.name, match.get("confidence", 0))
            self._execute_action(template)
            template.last_triggered = now

            self._event_callback(template.name, {
                "type": "popup_handled",
                "template_name": template.name,
                "match": match,
                "timestamp": time.time(),
            })
            return True

        return False

    def _execute_action(self, template: PopupTemplate) -> None:
        """执行弹窗关闭操作

        Args:
            template: 匹配到的弹窗模板
        """
        device = self._device_manager.get_active_device()
        if device is None:
            logger.warning("无活跃设备，无法执行弹窗操作")
            return

        if template.action_type == EventType.CLICK:
            if template.action_target:
                screenshot = self._take_screenshot()
                if screenshot is not None:
                    match = self._image_processor.find_template(
                        screenshot,
                        template.action_target,
                        roi=template.action_roi,
                    )
                    if match:
                        center_x = match["x"] + match["w"] // 2
                        center_y = match["y"] + match["h"] // 2
                        device.emit_coord_trace(
                            step="monitor_click",
                            raw=(center_x, center_y),
                            converted=(center_x, center_y),
                            formula=f"popup_handler click template target of {template.name} at ({center_x},{center_y})",
                            coord_system_in="physical",
                            coord_system_out="physical",
                            extra={"source": "popup_handler", "template_name": template.name, "action_target": template.action_target},
                        )
                        device.click(center_x, center_y)
                        logger.debug("弹窗 %s: 点击模板目标 (%d, %d)", template.name, center_x, center_y)
                        return

            if template.action_coordinates:
                device.emit_coord_trace(
                    step="monitor_click",
                    raw=template.action_coordinates,
                    converted=template.action_coordinates,
                    formula=f"popup_handler click coordinates of {template.name} at {template.action_coordinates}",
                    coord_system_in="physical",
                    coord_system_out="physical",
                    extra={"source": "popup_handler", "template_name": template.name, "action_coordinates": template.action_coordinates},
                )
                device.click(*template.action_coordinates)
                logger.debug("弹窗 %s: 点击坐标 %s", template.name, template.action_coordinates)

    def _take_screenshot(self) -> Any | None:
        """截取当前屏幕画面"""
        try:
            device = self._device_manager.get_active_device()
            if device:
                return device.capture_screen()
        except Exception as exc:
            logger.warning("弹窗处理器截图失败: %s", exc)
        return None

    @staticmethod
    def _default_event_callback(rule_name: str, data: dict[str, Any]) -> None:
        """默认事件回调"""
        logger.info("弹窗事件: %s, data=%s", rule_name, data)


class StorySkipper:
    """剧情跳过器：自动检测并跳过游戏中的剧情对话

    支持两种跳过方式：
    1. 直接点击跳过按钮
    2. 点击跳过按钮后确认（二次确认弹窗）
    """

    def __init__(
        self,
        device_manager: DeviceManager,
        image_processor: ImageProcessor,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self._device_manager = device_manager
        self._image_processor = image_processor
        self._event_callback = event_callback or self._default_event_callback
        self._templates: dict[str, StorySkipTemplate] = {}

    def add_template(self, template: StorySkipTemplate) -> None:
        """添加剧情跳过模板

        Args:
            template: 剧情跳过模板实例
        """
        self._templates[template.name] = template
        logger.info("已添加剧情跳过模板: %s", template.name)

    def remove_template(self, name: str) -> None:
        """移除剧情跳过模板

        Args:
            name: 模板名称
        """
        if name in self._templates:
            del self._templates[name]
            logger.info("已移除剧情跳过模板: %s", name)

    def check_and_skip(self, screenshot: Any | None = None) -> bool:
        """检查并跳过剧情

        遍历所有剧情跳过模板，检测是否存在剧情对话界面，
        如果存在则执行跳过操作

        Args:
            screenshot: 当前截图，为 None 时自动截图

        Returns:
            是否跳过了剧情
        """
        if screenshot is None:
            screenshot = self._take_screenshot()
        if screenshot is None:
            return False

        for template in self._templates.values():
            match = self._image_processor.find_template(
                screenshot,
                template.detect_template,
                roi=template.detect_roi,
                threshold=template.detect_threshold,
            )
            if match is None:
                continue

            logger.info("检测到剧情对话: %s (confidence=%.2f)", template.name, match.get("confidence", 0))
            self._skip_story(template)

            self._event_callback(template.name, {
                "type": "story_skipped",
                "template_name": template.name,
                "match": match,
                "timestamp": time.time(),
            })
            return True

        return False

    def _skip_story(self, template: StorySkipTemplate) -> None:
        """执行剧情跳过操作

        Args:
            template: 匹配到的剧情跳过模板
        """
        device = self._device_manager.get_active_device()
        if device is None:
            logger.warning("无活跃设备，无法跳过剧情")
            return

        if template.skip_button_template:
            screenshot = self._take_screenshot()
            if screenshot is not None:
                match = self._image_processor.find_template(screenshot, template.skip_button_template)
                if match:
                    center_x = match["x"] + match["w"] // 2
                    center_y = match["y"] + match["h"] // 2
                    device.emit_coord_trace(
                        step="monitor_click",
                        raw=(center_x, center_y),
                        converted=(center_x, center_y),
                        formula=f"story_skipper click skip button of {template.name} at ({center_x},{center_y})",
                        coord_system_in="physical",
                        coord_system_out="physical",
                        extra={"source": "story_skipper_skip", "template_name": template.name, "skip_button_template": template.skip_button_template},
                    )
                    device.click(center_x, center_y)
                    logger.debug("剧情 %s: 点击跳过按钮 (%d, %d)", template.name, center_x, center_y)
                    self._handle_confirm(template)
                    return

        if template.skip_button_coordinates:
            device.emit_coord_trace(
                step="monitor_click",
                raw=template.skip_button_coordinates,
                converted=template.skip_button_coordinates,
                formula=f"story_skipper click skip coordinates of {template.name} at {template.skip_button_coordinates}",
                coord_system_in="physical",
                coord_system_out="physical",
                extra={"source": "story_skipper_skip", "template_name": template.name, "skip_button_coordinates": template.skip_button_coordinates},
            )
            device.click(*template.skip_button_coordinates)
            logger.debug("剧情 %s: 点击跳过坐标 %s", template.name, template.skip_button_coordinates)
            self._handle_confirm(template)

    def _handle_confirm(self, template: StorySkipTemplate) -> None:
        """处理跳过后的确认弹窗

        Args:
            template: 剧情跳过模板
        """
        time.sleep(template.skip_delay)

        device = self._device_manager.get_active_device()
        if device is None:
            return

        if template.confirm_template:
            screenshot = self._take_screenshot()
            if screenshot is not None:
                match = self._image_processor.find_template(screenshot, template.confirm_template)
                if match:
                    center_x = match["x"] + match["w"] // 2
                    center_y = match["y"] + match["h"] // 2
                    device.emit_coord_trace(
                        step="monitor_click",
                        raw=(center_x, center_y),
                        converted=(center_x, center_y),
                        formula=f"story_skipper click confirm button of {template.name} at ({center_x},{center_y})",
                        coord_system_in="physical",
                        coord_system_out="physical",
                        extra={"source": "story_skipper_confirm", "template_name": template.name, "confirm_template": template.confirm_template},
                    )
                    device.click(center_x, center_y)
                    logger.debug("剧情 %s: 点击确认按钮 (%d, %d)", template.name, center_x, center_y)
                    return

        if template.confirm_coordinates:
            device.emit_coord_trace(
                step="monitor_click",
                raw=template.confirm_coordinates,
                converted=template.confirm_coordinates,
                formula=f"story_skipper click confirm coordinates of {template.name} at {template.confirm_coordinates}",
                coord_system_in="physical",
                coord_system_out="physical",
                extra={"source": "story_skipper_confirm", "template_name": template.name, "confirm_coordinates": template.confirm_coordinates},
            )
            device.click(*template.confirm_coordinates)
            logger.debug("剧情 %s: 点击确认坐标 %s", template.name, template.confirm_coordinates)

    def _take_screenshot(self) -> Any | None:
        """截取当前屏幕画面"""
        try:
            device = self._device_manager.get_active_device()
            if device:
                return device.capture_screen()
        except Exception as exc:
            logger.warning("剧情跳过器截图失败: %s", exc)
        return None

    @staticmethod
    def _default_event_callback(rule_name: str, data: dict[str, Any]) -> None:
        """默认事件回调"""
        logger.info("剧情跳过事件: %s, data=%s", rule_name, data)
