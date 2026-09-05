"""Windows device controller: integrates WindowManager, ScreenshotManager,
and WindowsInputHandler (unified input with PostMessage support).

This is the concrete Windows implementation of BaseDevice abstract interface.
All Win32 API calls are encapsulated behind this class — business logic
must never call Win32 directly.
"""

import logging
from typing import Any

import numpy as np
from core.exceptions import DeviceError
from devices.base import BaseDevice, DeviceStatus, require_operable
from monitor.resources import record_screenshot
from platforms.windows.input import WindowsInputHandler
from platforms.windows.screenshot import ScreenshotManager
from platforms.windows.window import WindowManager

logger = logging.getLogger(__name__)


class WindowsDevice(BaseDevice):
    """Windows device controller with full platform abstraction.

    Combines window management, multi-strategy screenshot (WGC/DXGI/GDI/PrintWindow),
    dual-mode input (SendInput foreground / PostMessage background),
    DC/Bitmap cache for high-performance BitBlt screenshots,
    and multi-child-window compositing.

    All components are lazily initialized on first use or during connect().
    """

    def __init__(
        self,
        device_id: str = "windows-0",
        name: str = "Windows Device",
        window_title: str | None = None,
        window_handle: int | None = None,
        screenshot_method: str = "auto",
        input_method: str = "SendInput",
        control_mode: str = "pseudo_background",
        background: bool = False,
        use_dc_cache: bool = True,
    ):
        """Initialize Windows device controller

        Args:
            device_id: Unique device identifier
            name: Human-readable device name
            window_title: Target window title to find and bind (None for desktop)
            window_handle: Known-valid hwnd hint (from backend device_info).
                When set and still valid (``is_window``), connect() binds it
                directly instead of searching by title — this survives window
                title drift (browser page navigation) that breaks title search.
            screenshot_method: Screenshot strategy — "auto"/"wgc"/"dxgi"/"gdi"/"printwindow"
            input_method: Concrete input method — "SendInput"/"PostMessage"/"PseudoBackground"
            control_mode: High-level control mode — "foreground"/"background"/"pseudo_background".
                When input_method is "auto" or empty, control_mode derives the
                concrete input method and screenshot method.
            background: Legacy flag; True selects "PostMessage" input.
                Ignored when input_method or control_mode is explicitly set.
            use_dc_cache: Enable DC/Bitmap caching for GDI screenshots
        """
        super().__init__(device_id=device_id, name=name)
        self._window_mgr = WindowManager()

        # Derive concrete methods from control_mode when no explicit override.
        derived_screenshot, derived_input = self._derive_methods_from_control_mode(
            control_mode, screenshot_method, input_method
        )

        # client_only=True: capture only the client area (exclude title bar /
        # borders). Critical for coord_transformer correctness — ROI/template
        # scaling is computed against client_physical_res, so the screenshot
        # must also be client-only. Otherwise the ROI blue box lands on the
        # title bar and template_match confidence collapses (TD-003).
        self._screenshot_mgr = ScreenshotManager(method=derived_screenshot, client_only=True)

        # Resolve final input method: explicit > control_mode > legacy background flag.
        final_input_method = derived_input
        # Track whether the user originally requested "auto" so connect()
        # can re-resolve based on the bound window's class (some classes
        # block PostMessage/SendMessage — see input_variants.py).
        self._input_method_auto = (
            not input_method or input_method.lower() == "auto"
        )
        if not final_input_method or final_input_method == "auto":
            final_input_method = 'PostMessage' if background else 'SendInput'
        self._input_handler = WindowsInputHandler(method=final_input_method)

        self._window_title = window_title
        self._window_handle = window_handle
        self._screenshot_method = derived_screenshot
        self._input_method = final_input_method
        self._control_mode = control_mode
        self._use_dc_cache = use_dc_cache

        # Lazy-initialized advanced components
        self._dc_cache: Any | None = None
        self._subwindow_compositor: Any | None = None

    # ── Control-mode derivation ──────────────────────────────────────────

    @staticmethod
    def _derive_methods_from_control_mode(
        control_mode: str,
        screenshot_method: str,
        input_method: str,
    ) -> tuple[str, str]:
        """Derive concrete screenshot/input methods from control mode.

        Args:
            control_mode: "foreground" / "background" / "pseudo_background"
            screenshot_method: Explicit screenshot method override (e.g. "auto")
            input_method: Explicit input method override (e.g. "SendInput")

        Returns:
            (final_screenshot_method, final_input_method)

        Explicit non-auto concrete methods take precedence over control-mode
        defaults so users can override per device.
        """
        defaults = {
            "foreground": ("auto", "SendInput"),
            "background": ("auto", "PostMessage"),
            "pseudo_background": ("printwindow", "PseudoBackground"),
        }
        derived_screenshot, derived_input = defaults.get(control_mode, defaults["pseudo_background"])

        final_screenshot = screenshot_method if screenshot_method and screenshot_method != "auto" else derived_screenshot
        final_input = input_method if input_method and input_method not in ("", "auto") else derived_input
        return final_screenshot, final_input

    # ── BaseDevice abstract methods ──────────────────────────────────────

    def connect(self) -> None:
        """Initialize window binding and all subsystems

        Finds target window by title, binds hwnd to screenshot/input managers,
        and pre-initializes optional components (DC cache, PostMessage input).

        When a backend-provided ``window_handle`` hint is present and still
        valid (``is_window``), it is bound directly — browser window titles
        drift per page (e.g. ``about:blank`` → ``新标签页 - Google Chrome``),
        so title search can fail even though the hwnd is unchanged and usable.
        Title search is only attempted when there is no valid hwnd hint.

        When input_method was originally "auto", re-resolves the input
        method based on the bound window's class (some game windows block
        PostMessage/SendMessage — see input_variants.INPUT_COMPATIBILITY_TABLE).
        """
        try:
            bound = False
            if self._window_handle:
                from platforms.windows.window import is_window

                if is_window(self._window_handle):
                    self._window_mgr.set_hwnd(self._window_handle)
                    self._bind_hwnd(self._window_handle)
                    bound = True
                else:
                    logger.warning(
                        "backend 提供的窗口句柄已失效 (hwnd=%s), 回退到标题搜索",
                        hex(self._window_handle),
                    )
            if not bound and self._window_title:
                hwnd = self._window_mgr.find_window(title=self._window_title)
                if hwnd is None:
                    logger.warning("Window not found: %s, falling back to desktop", self._window_title)
                else:
                    self._bind_hwnd(hwnd)

            # Re-resolve input method based on the bound window's class.
            # No-op when the user explicitly chose a method (non-auto).
            self._resolve_auto_input_method()

            self._status = DeviceStatus.CONNECTED
            logger.info("Windows device connected: id=%s", self._device_id)
        except Exception as exc:
            self._status = DeviceStatus.ERROR
            raise DeviceError(f"Windows device connection failed: {exc}") from exc

    def disconnect(self) -> None:
        """Release all resources and disconnect"""
        self._release_advanced_components()
        self._screenshot_mgr.release()
        self._status = DeviceStatus.DISCONNECTED
        logger.info("Windows device disconnected: id=%s", self._device_id)

    @require_operable
    def capture_screen(self) -> np.ndarray | None:
        """Capture screen using the configured screenshot strategy

        Returns:
            BGR format numpy array (height, width, 3), or None on failure
        """
        result = self._screenshot_mgr.capture()
        if result is not None:
            record_screenshot()
        return result

    @require_operable
    def click(self, x: int, y: int) -> None:
        """Click at coordinates using current input mode (foreground/background).

        坐标系契约 (N191): 期望 **logical** (client) 坐标。
        `set_dpi_ratio()` 必须在调用前由 orchestrator 注入 (DPI=100% 时 ratio=1.0,
        logical == physical)。内部 `_input_handler.click` 会调
        `_logical_to_physical()` 转 physical 后传给 ClientToScreen/SendInput。
        """
        target = self._get_target()
        result = self._input_handler.click(target, x, y)
        if not result.success:
            logger.warning("Click failed: %s", result.error)

    @require_operable
    def key_press(self, key: str) -> None:
        """Press a key using current input mode"""
        target = self._get_target()
        result = self._input_handler.key_press(target, key)
        if not result.success:
            logger.warning("Key press failed: %s", result.error)

    @require_operable
    def key_combo(self, modifiers: list[str], key: str) -> None:
        """Press a real modifier+key combo (TD-398)."""
        target = self._get_target()
        result = self._input_handler.key_combo(target, modifiers, key)
        if not result.success:
            logger.warning("Key combo failed: %s", result.error)

    def set_dpi_ratio(self, ratio: float) -> None:
        """Set the logical-to-physical DPI scale ratio on the input handler.

        Called by the orchestrator after building RuntimeDisplayContext.
        SendInput/PseudoBackground modes need this to convert logical coords
        (from template_match) to physical coords (for ClientToScreen).

        Args:
            ratio: logical_to_physical_ratio (1.0 = 100%, 1.5 = 150%).
        """
        self._input_handler.set_dpi_ratio(ratio)

    def set_coord_trace_callback(self, callback: Any) -> None:
        """Inject a coord_trace callback into the input handler (N191 §10.10).

        Called by PipelineEngine.load to forward context.emit_coord_trace
        so that device-internal coordinate conversions (logical→physical,
        client_to_screen) emit traces for AI debuggability.
        """
        self._input_handler.set_coord_trace_callback(callback)

    def emit_coord_trace(
        self, *, step: str, raw: Any, converted: Any,
        formula: str, coord_system_in: str = "",
        coord_system_out: str = "", extra: dict[str, Any] | None = None,
    ) -> None:
        """Emit a coordinate transform trace via the input handler.

        Forwards to the input handler's best-effort trace emitter.
        No-op when coord_trace_callback is not set (monitor standalone path).
        """
        self._input_handler._emit_coord_trace_safe(
            step=step, raw=raw, converted=converted,
            formula=formula, coord_system_in=coord_system_in,
            coord_system_out=coord_system_out, extra=extra,
        )

    @require_operable
    def text_input(self, text: str) -> None:
        """Input text using current input mode (Unicode supported in SendInput mode)"""
        target = self._get_target()
        result = self._input_handler.text_input(target, text)
        if not result.success:
            logger.warning("Text input failed: %s", result.error)

    @require_operable
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> None:
        """Swipe from (x1,y1) to (x2,y2)

        坐标系契约 (N191): 期望 **logical** (client) 坐标, 同 ``click()``。
        ``set_dpi_ratio()`` 必须在调用前由 orchestrator 注入 (DPI=100% 时
        ratio=1.0, logical == physical)。内部 ``_input_handler.swipe`` 会调
        ``_logical_to_physical()`` 转 physical 后传给 ClientToScreen/SendInput。

        Args:
            x1, y1: Start coordinates (logical / client pixel)
            x2, y2: End coordinates (logical / client pixel)
            duration: Swipe duration in milliseconds (default 300ms)
        """
        target = self._get_target()
        result = self._input_handler.swipe(target, x1, y1, x2, y2, duration_ms=duration)
        if not result.success:
            logger.warning("Swipe failed: %s", result.error)

    @require_operable
    def get_resolution(self) -> tuple[int, int]:
        """Get screen/window resolution

        Returns:
            (width, height) tuple
        """
        rect = self._window_mgr.get_rect()
        if rect:
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            return (width, height)
        import ctypes
        user32 = ctypes.windll.user32
        return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))

    # ── Extended capabilities beyond BaseDevice ──────────────────────────

    def _bind_hwnd(self, hwnd: int) -> None:
        """Bind window handle to all subsystems

        Args:
            hwnd: Window handle to bind
        """
        self._screenshot_mgr.set_hwnd(hwnd)
        logger.debug("Bound hwnd=%s to all subsystems", hwnd)

    def get_window_class(self) -> str:
        """Return the class name of the bound window, or empty string.

        Public accessor used by auto-mode input-method resolution and
        debug logging. Delegates to ScreenshotManager's class-name query.
        """
        return self._screenshot_mgr._get_window_class_name()

    def _resolve_auto_input_method(self) -> None:
        """Re-resolve input method based on bound window's class.

        Called from connect() after hwnd binding. When the user originally
        requested input_method="auto", queries the bound window's class and
        picks the best legacy method ("SendInput"/"PostMessage") via
        input_variants.recommend_legacy_input_method().

        No-op when:
          - input_method was explicitly set (non-auto)
          - window class is empty (window not bound / query failed)
          - recommended method equals current method

        Logs the decision for debuggability.
        """
        if not getattr(self, "_input_method_auto", False):
            return
        try:
            window_class = self.get_window_class()
            if not window_class:
                # No window bound or query failed; keep current method
                return

            from platforms.windows.input_variants import (
                get_blocked_input_methods,
                get_compatibility_reason,
                recommend_legacy_input_method,
            )

            recommended = recommend_legacy_input_method(window_class)
            if recommended == self._input_method:
                # Already using the recommended method; nothing to do
                return

            # Log the switch with reason for debuggability
            reason = get_compatibility_reason(window_class)
            blocked = get_blocked_input_methods(window_class)
            blocked_str = ", ".join(m.value for m in blocked) if blocked else "none"
            old_method = self._input_method
            logger.info(
                "auto input-method resolution: window_class='%s' "
                "switching %s → %s (blocked: %s; reason: %s)",
                window_class, old_method, recommended, blocked_str, reason,
            )
            self._input_method = recommended
            self._input_handler = WindowsInputHandler(method=recommended)
        except Exception as exc:
            # Non-fatal: keep existing input method if resolution fails
            logger.warning("auto input-method resolution failed: %s", exc)

    def _get_target(self) -> str:
        """Get current target window handle as string

        Returns:
            Hex string of hwnd, or '0' for desktop
        """
        hwnd = self._window_mgr.hwnd
        if hwnd is None:
            return '0'
        return hex(hwnd)

    @property
    def dc_cache(self):
        """Get or lazy-create DCCache instance for high-performance BitBlt"""
        if self._dc_cache is None and self._use_dc_cache:
            from platforms.windows.dccache import DCCache
            self._dc_cache = DCCache()
            logger.debug("DCCache initialized")
        return self._dc_cache

    @property
    def input_handler(self) -> WindowsInputHandler:
        """Get the unified WindowsInputHandler instance

        Provides access to advanced features like find_target_child(),
        text_input() with Unicode support, and multi-button clicks.
        """
        return self._input_handler

    @property
    def subwindow_compositor(self):
        """Get or lazy-create SubWindowCompositor for multi-window screenshots"""
        if self._subwindow_compositor is None:
            from platforms.windows.subwindow import SubWindowCompositor
            self._subwindow_compositor = SubWindowCompositor()
            logger.debug("SubWindowCompositor initialized")
        return self._subwindow_compositor

    @require_operable
    def capture_screen_fast(self) -> np.ndarray | None:
        """Capture screenshot using DC/Bitmap cache (faster for repeated captures)

        Uses cached GDI objects to avoid repeated CreateCompatibleDC/Bitmap calls.
        Falls back to standard ScreenshotManager if DC cache is disabled.

        Returns:
            BGR numpy array, or None on failure
        """
        dc = self.dc_cache
        if dc is None:
            return self.capture_screen()

        hwnd = self._window_mgr.hwnd
        if hwnd is None:
            hwnd = 0
        result = dc.capture(hwnd)
        if result is not None:
            record_screenshot()
        return result

    @require_operable
    def capture_multi_window(
        self,
        layout: str = "overlay",
        padding: int = 0,
        class_filter: str | None = None,
        title_filter: str | None = None,
    ) -> np.ndarray | None:
        """Capture and composite multiple child windows into one image

        Finds child windows of the bound parent window, captures each one,
        and composites them according to the specified layout mode.

        Args:
            layout: Layout mode — "grid"/"vertical"/"horizontal"/"overlay"
            padding: Pixel gap between captured regions
            class_filter: Filter child windows by class name (substring match)
            title_filter: Filter child windows by title (substring match)

        Returns:
            Composite BGR numpy array, or None on failure
        """
        parent_hwnd = self._window_mgr.hwnd
        if parent_hwnd is None:
            logger.warning("No parent hwnd bound, cannot capture child windows")
            return None

        compositor = self.subwindow_compositor
        children = compositor.find_child_windows(
            parent_hwnd, class_filter=class_filter, title_filter=title_filter
        )
        if not children:
            logger.info("No child windows found for parent=%s", parent_hwnd)
            return self.capture_screen()

        hwnds = [c["hwnd"] for c in children]
        return compositor.composite(hwnds, layout=layout, padding=padding)

    @require_operable
    def click_background(self, x: int, y: int, button: str = "left") -> bool:
        """Click via PostMessage (works even when window is not foreground)

        Args:
            x: Client X coordinate
            y: Client Y coordinate
            button: Mouse button ("left"/"right"/"middle")

        Returns:
            True if message was sent successfully
        """
        target = self._get_target()
        result = self._input_handler.click(target, x, y, method='PostMessage', button=button)
        return result.success

    @require_operable
    def key_press_background(self, key: str) -> bool:
        """Press a key via PostMessage (works in background)

        Args:
            key: Key name (e.g., "enter", "a", "f1")

        Returns:
            True if messages were sent successfully
        """
        target = self._get_target()
        result = self._input_handler.key_press(target, key, method='PostMessage')
        return result.success

    @require_operable
    def text_input_background(self, text: str) -> bool:
        """Input text via PostMessage (works in background)

        Note: PostMessage mode only supports BMP characters via WM_CHAR.
        For Unicode/emoji, use foreground text_input() with SendInput mode.

        Args:
            text: Text to send

        Returns:
            True if messages were sent successfully
        """
        target = self._get_target()
        result = self._input_handler.text_input(target, text, method='PostMessage')
        return result.success

    def switch_input_mode(self, background: bool) -> None:
        """Switch between foreground (SendInput) and background (PostMessage) input

        Args:
            background: True to use PostMessage, False to use SendInput
        """
        self._input_handler.method = 'PostMessage' if background else 'SendInput'
        logger.debug("Input mode switched to: %s", "background" if background else "foreground")

    def reconfigure(
        self,
        *,
        input_method: str | None = None,
        screenshot_method: str | None = None,
        control_mode: str | None = None,
    ) -> None:
        """Apply updated config from backend on an existing matched device.

        When the backend updates device settings (e.g. switching input_method
        from "SendInput" to "PseudoBackground"), the agent's matched existing
        device must apply the new value. Without this, config changes only
        take effect after an agent restart.

        Args:
            input_method: New input method ("SendInput"/"PostMessage"/"PseudoBackground").
                None = keep current.
            screenshot_method: New screenshot method. None = keep current.
            control_mode: New control mode. None = keep current.
        """
        if input_method and input_method not in ("", "auto") and input_method != self._input_method:
            self._input_handler.method = input_method
            self._input_method = input_method
            logger.info(
                "Device %s reconfigured: input_method=%s",
                self._device_id,
                input_method,
            )
        if screenshot_method and screenshot_method not in ("", "auto") and screenshot_method != self._screenshot_method:
            self._screenshot_mgr.set_method(screenshot_method)
            self._screenshot_method = screenshot_method
            logger.info(
                "Device %s reconfigured: screenshot_method=%s",
                self._device_id,
                screenshot_method,
            )
        if control_mode and control_mode != self._control_mode:
            self._control_mode = control_mode
            logger.info(
                "Device %s reconfigured: control_mode=%s",
                self._device_id,
                control_mode,
            )

    def find_child_windows(
        self,
        class_filter: str | None = None,
        title_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find visible child windows of the bound parent window

        Args:
            class_filter: Class name substring filter
            title_filter: Title substring filter

        Returns:
            List of dicts with keys: hwnd, title, class, rect, width, height
        """
        parent_hwnd = self._window_mgr.hwnd
        if parent_hwnd is None:
            return []
        return self.subwindow_compositor.find_child_windows(
            parent_hwnd, class_filter=class_filter, title_filter=title_filter
        )

    def activate_window(self) -> bool:
        """Activate (bring to foreground) the target window"""
        return self._window_mgr.activate()

    def bring_to_foreground(self) -> bool:
        """Reliably bring window to foreground (bypasses foreground lock)

        Uses Alt-key trick to work around SetForegroundWindow restrictions
        in cross-process scenarios.
        """
        return self._window_mgr.bring_to_foreground()

    def get_window_rect(self) -> tuple[int, int, int, int] | None:
        """Get window rectangle (left, top, right, bottom)"""
        return self._window_mgr.get_rect()

    def get_client_rect(self) -> tuple[int, int, int, int] | None:
        """Get client area rectangle (0, 0, width, height).

        The client area excludes title bar and borders — what game UI
        renders into. Used by display_builder for DPI-aware scaling.
        """
        return self._window_mgr.get_client_rect()

    @property
    def hwnd(self) -> int | None:
        """Bound window handle (proxies to WindowManager.hwnd).

        Exposed so display_builder can query DPI / client rect without
        reaching into private _window_mgr.
        """
        return self._window_mgr.hwnd

    def is_foreground(self) -> bool:
        """Check if the target window is currently in the foreground"""
        return self._window_mgr.is_foreground()

    def find_window(
        self,
        title: str | None = None,
        exact: bool = False,
        regex: bool = False,
        class_name: str | None = None,
        process_name: str | None = None,
    ) -> int | None:
        """Find a window by various criteria

        Args:
            title: Window title (supports fuzzy/exact/regex matching)
            exact: Use exact title match
            regex: Use regex title match
            class_name: Window class name filter
            process_name: Process name filter

        Returns:
            Window handle, or None if not found
        """
        return self._window_mgr.find_window(
            title=title, exact=exact, regex=regex,
            class_name=class_name, process_name=process_name,
        )

    def set_target_window(self, hwnd: int) -> None:
        """Change the target window handle at runtime

        Args:
            hwnd: New window handle to bind
        """
        self._bind_hwnd(hwnd)
        logger.info("Target window changed to hwnd=%s", hwnd)

    def get_device_info(self) -> dict[str, Any]:
        """Get comprehensive device metadata including all subsystem info

        Returns:
            Dict with device identity, status, window info, and component states
        """
        info = super().get_device_info()
        info.update({
            "window_title": self._window_title,
            "screenshot_method": self._screenshot_method,
            "background_mode": self._input_handler.method == 'PostMessage',
            "dc_cache_enabled": self._use_dc_cache,
            "dc_cache_stats": self.dc_cache.stats if self._dc_cache else None,
        })
        rect = self._window_mgr.get_rect()
        if rect:
            info["window_rect"] = {
                "x": rect[0], "y": rect[1],
                "w": rect[2] - rect[0], "h": rect[3] - rect[1],
            }
        return info

    def _release_advanced_components(self) -> None:
        """Release all lazily-initialized advanced components"""
        if self._dc_cache:
            self._dc_cache.release()
            self._dc_cache = None
        if self._subwindow_compositor:
            self._subwindow_compositor.release()
            self._subwindow_compositor = None
