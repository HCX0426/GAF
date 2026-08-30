"""click 节点：鼠标点击 — 调用真实 Device.click() 发送点击事件"""

from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.exceptions import DeviceError
from core.result import AutoResult, fail_result, success_result
from core.wait_freezes import ScreenChangeOutcome, WaitFreezes
from engine.node import PipelineNode, register_node
from engine.target import resolve_target

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


@register_node(
    "click",
    display_name="鼠标点击",
    category="action",
    description="在指定坐标或匹配区域执行点击操作",
    params_schema={
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X 坐标", "default": 0},
            "y": {"type": "integer", "description": "Y 坐标", "default": 0},
            "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left", "description": "鼠标按钮"},
            "clicks": {"type": "integer", "minimum": 1, "default": 1, "description": "点击次数"},
            "interval": {"type": "number", "minimum": 0, "default": 0.1, "description": "点击间隔（秒）"},
            "target": {"type": ["string", "object", "null"], "description": "P0-6 target spec，设置后覆盖 x/y"},
            "target_offset": {"type": ["object", "array", "null"], "description": "P0-6 target offset"},
            "activate_window": {"type": "boolean", "default": True, "description": "点击前是否激活窗口"},
            "expect_screen_change": {"type": "boolean", "default": True, "description": "点击后是否预期画面变化"},
            "screen_change_timeout": {"type": "number", "minimum": 0.1, "default": 2.0, "description": "画面变化检测超时（秒）"},
            "screen_change_threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.01, "description": "画面变化检测阈值"},
        },
    },
)
@dataclass
class ClickNode(PipelineNode):
    """Mouse click node that sends real click events via Device

    Config parameters:
    - x: Click X coordinate (int), can reference variables like "${prev_node_x}"
    - y: Click Y coordinate (int)
    - target: P0-6 target spec — auto-resolve (x, y) from a recognition result
        or context variable. May be "_last_match_pos" (default when present),
        "_anchor_pos", "${var_name}", or a dict {"x": int, "y": int}.
        When set, overrides x/y.
    - target_offset: P0-6 offset applied to the resolved target. Dict
        {"x": int, "y": int} or list [x, y].
    - button: Mouse button "left" / "right" / "middle", default "left"
    - clicks: Number of clicks, default 1
    - interval: Interval between clicks (seconds), default 0.1
    - activate_window: Whether to activate target window before clicking (bool), default True
    """

    node_type: str = "click"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """Task 4.28 (P1-17): 构建失败诊断 data, 统一注入 node_id/node_type/error_code/coord_system + 节点特有配置字段。"""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "button": self.config.get("button", "left"),
            "clicks": self.config.get("clicks", 1),
            "interval": self.config.get("interval", 0.1),
            "target": self.config.get("target"),
        }
        data.update(kwargs)
        return data

    def _resolve_coordinate(self, raw_value: Any, context: PipelineContext, axis: str) -> int:
        """Resolve coordinate value from literal int or variable reference

        Supports:
        - Literal integer: 100
        - Variable reference: "${template_match_1_match_result.x}"

        Args:
            raw_value: Raw config value (int, float, or string)
            context: Pipeline context for variable lookup
            axis: Axis name for error messages ("x" or "y")

        Returns:
            Resolved integer coordinate

        Raises:
            ValueError: When the value cannot be resolved to an int (variable
                missing, dict missing axis, unparseable string, unsupported
                type). Callers must surface this as a pipeline failure rather
                than silently clicking (0, 0).
        """
        if isinstance(raw_value, (int, float)):
            return int(raw_value)

        if isinstance(raw_value, str):
            # Check for variable reference syntax ${...}
            if raw_value.startswith("${") and raw_value.endswith("}"):
                var_name = raw_value[2:-1]
                var_value = context.get_variable(var_name)
                if var_value is None:
                    raise ValueError(
                        f"变量 {var_name!r} 未找到，无法解析 {axis} 坐标"
                    )
                if isinstance(var_value, dict):
                    # Support nested access like "result.x"
                    if axis not in var_value:
                        raise ValueError(
                            f"变量 {var_name!r} 中缺少 {axis!r} 字段: {var_value!r}"
                        )
                    try:
                        return int(var_value[axis])
                    except (ValueError, TypeError) as exc:
                        raise ValueError(
                            f"变量 {var_name!r}[{axis!r}]={var_value[axis]!r} 无法转为 int"
                        ) from exc
                try:
                    return int(var_value)
                except (ValueError, TypeError) as exc:
                    raise ValueError(
                        f"变量 {var_name!r}={var_value!r} 无法转为 int"
                    ) from exc
            try:
                return int(float(raw_value))
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"无法解析 {axis} 坐标值: {raw_value!r}"
                ) from exc

        raise ValueError(
            f"不支持的 {axis} 坐标类型: {type(raw_value).__name__}={raw_value!r}"
        )

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute real mouse click via Device.click()

        Args:
            context: Pipeline execution context (must have device set)

        Returns:
            AutoResult with click result data
        """
        start = time.monotonic()

        device = context.device
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="PipelineContext 中未设置设备实例(device=None)，无法执行点击",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_DISCONNECTED,
                    x=self.config.get("x"), y=self.config.get("y"),
                ),
            )

        try:
            # P0-6: target / target_offset takes precedence over x/y when set.
            target = self.config.get("target")
            target_offset = self.config.get("target_offset")
            if target is not None:
                x, y = resolve_target(context, target, target_offset)
            else:
                x = self._resolve_coordinate(self.config.get("x", 0), context, "x")
                y = self._resolve_coordinate(self.config.get("y", 0), context, "y")
                # N191 P0-1 (架构层归一化修复, 2026-07-27):
                # config x/y 是 BASE 坐标系 (用户在 original_base_res 下定义),
                # 需转 LOGICAL 才能传给 WindowsDevice.click (期望 logical)。
                # ADB 无 transformer, _resolve_coordinate 返回的就是 physical, 一致。
                # 不转会导致 DPI>100% 或非 1920x1080 客户区下点击偏移。
                transformer = getattr(context, 'coord_transformer', None)
                if transformer is not None:
                    x, y = transformer.convert_original_to_current_client(x, y)
        except ValueError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"坐标解析失败: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.COORD_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.COORD_INVALID,
                    x=self.config.get("x"), y=self.config.get("y"),
                    resolve_error=str(exc),
                ),
            )
        button = self.config.get("button", "left")
        clicks = self.config.get("clicks", 1)
        interval = self.config.get("interval", 0.1)
        activate_window = self.config.get("activate_window", True)

        if not isinstance(clicks, int) or clicks < 1:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="点击次数必须 >= 1",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    x=x, y=y, clicks=clicks,
                ),
            )

        # Optionally activate/bring window to foreground before clicking
        if activate_window and hasattr(device, 'activate_window'):
            try:
                device.activate_window()
                time.sleep(0.05)  # Brief pause after activation
            except Exception as exc:
                logger.warning("窗口激活失败（继续执行点击）: %s", exc)

        # Execute click(s) with real device call
        actual_clicks = 0
        # N191 §10.10 决策点 2 A+ (AI 可调试性, 2026-07-27):
        # 记录 click 节点传入 device.click 的坐标 + 坐标系, 让 AI 能
        # 从日志反推点击位置 (D4 bug 现场重建) + 跨设备对比 (D3)。
        # device_type + transformer_id 由 context.emit_coord_trace 自动带。
        click_coord_system = getattr(context, "coord_system", "") or "legacy"
        with contextlib.suppress(Exception):
            context.emit_coord_trace(
                node_id=self.id,
                step="device_click",
                raw=(x, y),
                converted=(x, y),
                formula=f"device.click({x}, {y}) | coord_system={click_coord_system} | button={button} clicks={clicks}",
                coord_system_in=click_coord_system,
                coord_system_out=click_coord_system,
                extra={"button": button, "clicks": clicks, "interval": interval},
            )
        try:
            for i in range(clicks):
                device.click(x, y)
                actual_clicks += 1
                if i < clicks - 1 and interval > 0:
                    time.sleep(interval)

        except DeviceError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"设备点击失败(已执行{actual_clicks}/{clicks}次): {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_ERROR,
                    x=x, y=y, actual_clicks=actual_clicks, expected_clicks=clicks,
                    device_error=str(exc),
                ),
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"点击过程异常(已执行{actual_clicks}/{clicks}次): {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_ERROR,
                    x=x, y=y, actual_clicks=actual_clicks, expected_clicks=clicks,
                    exception_type=type(exc).__name__,
                ),
            )

        # 读取竞态防护配置（spec 阶段 4.2.2 — 任务 1.6）
        # 默认 True：点击-导航竞态是高频问题，默认开启轻量防护
        expect_screen_change = self.config.get("expect_screen_change", True)

        result_data = {
            "x": x,
            "y": y,
            "button": button,
            "clicks": actual_clicks,
            "interval": interval,
            "expect_screen_change": expect_screen_change,
            # Task 4.33 (P1-22): success path 补 coord_system, 与 fail path 诊断字段对齐
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }

        context.set_variable(f"{self.id}_click_result", result_data)
        elapsed = time.monotonic() - start
        logger.info(
            "点击完成: (%d, %d), button=%s, clicks=%d/%d, 耗时=%.3fs",
            x, y, button, actual_clicks, clicks, elapsed,
        )
        # Save debug image when debug_mode is enabled; capture paths for
        # structured_logger correlation (spec 阶段 6.5 — screenshot_path
        # for annotated + raw_screenshot_path for raw).
        click_screenshot = self._save_debug(context, x, y, actual_clicks == clicks)
        if click_screenshot.get("annotated"):
            result_data["screenshot_path"] = click_screenshot["annotated"]
        if click_screenshot.get("raw"):
            result_data["raw_screenshot_path"] = click_screenshot["raw"]

        # 默认轻量竞态防护：检测点击后画面是否变化（spec 阶段 4.2.2 — 任务 1.6）
        # 设计原则（spec 4.1）：
        # - UNCHANGED 不 fail，仅记 warning 供 AI 诊断（兼容"点击选中"等正常无变化场景）
        # - 配合 post_verify 强验证：关键节点可额外配置 post_verify 失败则 fail
        if expect_screen_change:
            screen_change_outcome = self._detect_screen_change(context)
            if screen_change_outcome is not None:
                result_data["screen_change_outcome"] = screen_change_outcome
                if screen_change_outcome == ScreenChangeOutcome.UNCHANGED.value:
                    logger.warning(
                        "点击 (%d, %d) 后画面未变化（UNCHANGED），可能存在竞态",
                        x, y,
                    )

        return success_result(data=result_data, elapsed_time=elapsed)

    def _save_debug(
        self,
        context: PipelineContext,
        x: int,
        y: int,
        is_success: bool,
    ) -> dict[str, str | None]:
        """Save an annotated debug image when context.debug_mode is True.

        Returns dict {annotated, raw} (spec 阶段 6.5 — for structured_logger
        screenshot_path + raw_screenshot_path fields), or {None, None} when
        debug_mode is off / save failed / no device available.
        """
        if not getattr(context, "debug_mode", False):
            return {"annotated": None, "raw": None}
        try:
            from utils.debug_image_saver import DebugImageSaver

            # N194 归一化 (2026-07-28): context.debug_dir 已是完整 exec_dir,
            # 不再拼 "action" 子目录. 见 template_match._save_debug 注释.
            debug_dir = getattr(context, "debug_dir", "./debug")
            saver = DebugImageSaver(debug_dir=debug_dir)
            device = getattr(context, "device", None)
            screen = None
            if device is not None and hasattr(device, "capture_screen"):
                try:
                    screen = device.capture_screen()
                except Exception as exc:
                    logger.debug("click debug capture error: %s", exc)
            if screen is None or screen.size == 0:
                return {"annotated": None, "raw": None}
            return saver.save_action_debug(
                screen=screen,
                node_id=self.id,
                node_type="click",
                is_success=is_success,
                action_info={"x": x, "y": y, "button": self.config.get("button", "left")},
            )
        except Exception as exc:
            logger.warning("click debug save failed: %s", exc, exc_info=True)
            return {"annotated": None, "raw": None}

    def _detect_screen_change(self, context: PipelineContext) -> str | None:
        """点击后轻量竞态防护：检测画面是否变化（spec 阶段 4.2.2 — 任务 1.6）。

        优先使用 context.wait_freezes + context.capture_fn (spec §4.2.3 依赖注入,
        由 engine.load() 注入共享 WaitFreezes 实例); 若未注入则回退到 per-call
        新建 WaitFreezes + device.capture_screen (向后兼容单测/旧调用方).

        timeout/threshold/poll_interval 通过 node.config 可配:
        - screen_change_timeout: 默认 2.0s (spec §4.2.2)
        - screen_change_threshold: 默认 0.01 (1% 像素变化)
        - screen_change_poll_interval: 默认 0.1s

        捕获所有异常并降级为 SKIPPED，不影响点击主流程。

        设计原则（spec 4.1）：
        - CHANGED: 画面变化，正常路径，AI 可放心继续
        - UNCHANGED: 2s 内无变化，疑似竞态，仅 warning 不 fail（兼容点击选中场景）
        - TIMEOUT: 设备异常或响应过慢，AI 应警觉
        - SKIPPED: device 无 capture_screen 或 baseline 捕获失败，跳过检测

        Args:
            context: PipelineContext 实例 (用 context.wait_freezes /
                     context.capture_fn / context.device)

        Returns:
            ScreenChangeOutcome 枚举值字符串，或 None（理论上不会返回 None）
        """
        # 优先用注入的 wait_freezes / capture_fn (spec §4.2.3)
        wait_freezes = getattr(context, "wait_freezes", None)
        capture_fn = getattr(context, "capture_fn", None)
        device = getattr(context, "device", None)

        # 回退路径: 未注入 wait_freezes 但 device 有 capture_screen
        # (向后兼容单测/旧调用方, spec §4.2.3 注入是阶段 1 任务 1.6 的一部分)
        if wait_freezes is None:
            if device is None or not hasattr(device, "capture_screen"):
                return ScreenChangeOutcome.SKIPPED.value
            wait_freezes = WaitFreezes()
            capture_fn = device.capture_screen
        elif capture_fn is None:
            # wait_freezes 已注入但 capture_fn 未注入, 尝试 device.capture_screen
            if device is None or not hasattr(device, "capture_screen"):
                return ScreenChangeOutcome.SKIPPED.value
            capture_fn = device.capture_screen

        # 可配参数 (spec §4.2.2: timeout 通过 node.config 可配)
        timeout = self.config.get("screen_change_timeout", 2.0)
        change_threshold = self.config.get("screen_change_threshold", 0.01)
        poll_interval = self.config.get("screen_change_poll_interval", 0.1)

        try:
            outcome = wait_freezes.wait_for_change_lightweight(
                capture_fn=capture_fn,
                timeout=timeout,
                change_threshold=change_threshold,
                poll_interval=poll_interval,
            )
            return outcome.value
        except Exception as exc:
            # 兜底：wait_for_change_lightweight 内部已捕获 capture_fn 异常，
            # 这里仅防止 WaitFreezes 调用本身出问题。
            logger.warning(
                "点击后画面变化检测异常（降级为 SKIPPED）: %s", exc,
                exc_info=True,
            )
            return ScreenChangeOutcome.SKIPPED.value
