"""Pseudo-minimizer: transparent layered window for background screenshots.

Creates a transparent, click-through window that covers the target window,
allowing PrintWindow/GDI screenshots to capture the target even when it is
covered by other windows or minimized. Uses WS_EX_LAYERED + WS_EX_TRANSPARENT
+ alpha=0 for full invisibility with SW_SHOWNOACTIVATE to avoid stealing focus.

Reference: MaaFramework's pseudo-minimization strategy.
"""

import contextlib
import ctypes
import ctypes.wintypes
import logging
import threading
import time

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# Window style constants
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000

# ShowWindow constants
SW_SHOWNOACTIVATE = 4
SW_HIDE = 0
SW_SHOW = 5

# SetWindowPos flags
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

# Layered window attributes
LWA_ALPHA = 0x02
GWL_EXSTYLE = -20


class PseudoMinimizer:
    """Manages a transparent overlay window for pseudo-minimization.

    When a game window needs to run in the background but still be screenshotted,
    this class creates a transparent, click-through overlay that sits on top of
    the target window. The overlay allows GDI/PrintWindow to capture content while
    the real window stays hidden or covered.

    Usage:
        pm = PseudoMinimizer()
        pm.minimize(hwnd)      # Create transparent overlay
        screenshot = capture()  # Screenshot through overlay
        pm.restore(hwnd)        # Remove overlay, show original
    """

    def __init__(self, poll_interval_ms: int = 100):
        """Initialize pseudo-minimizer

        Args:
            poll_interval_ms: Interval (ms) for foreground recovery polling
        """
        self._poll_interval = poll_interval_ms / 1000.0
        self._overlays: dict[int, int] = {}  # hwnd -> overlay_hwnd
        self._original_styles: dict[int, int] = {}
        self._lock = threading.Lock()
        self._poll_thread: threading.Thread | None = None
        self._stop_polling = False

    def minimize(self, hwnd: int) -> bool:
        """Create transparent overlay to pseudo-minimize a window

        The original window is hidden and replaced by an invisible overlay
        at the same position and size. Screenshots can still be taken through
        the overlay using PrintWindow.

        Args:
            hwnd: Target window handle to pseudo-minimize

        Returns:
            True if overlay was created successfully
        """
        with self._lock:
            if hwnd in self._overlays:
                logger.debug("hwnd=%s already pseudo-minimized", hwnd)
                return True

            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top

            if width <= 0 or height <= 0:
                logger.warning("Invalid window dimensions for hwnd=%s", hwnd)
                return False

            # Save original extended style
            orig_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            self._original_styles[hwnd] = orig_style

            # Create transparent overlay window
            overlay_wndclass = f"GAF_PseudoMin_{hwnd}"

            wc = ctypes.WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(wc)
            wc.lpfnWndProc = ctypes.WNDPROC(self._static_wnd_proc)
            wc.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
            wc.lpszClassName = overlay_wndclass

            atom = user32.RegisterClassExW(ctypes.byref(wc))
            if atom == 0:
                logger.warning("Failed to register overlay window class")

            ex_style = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            style = WS_POPUP | WS_VISIBLE

            overlay_hwnd = user32.CreateWindowExW(
                ex_style,
                overlay_wndclass,
                "",
                style,
                rect.left, rect.top, width, height,
                None, None, wc.hInstance, None,
            )

            if not overlay_hwnd:
                logger.error("Failed to create overlay window for hwnd=%s", hwnd)
                return False

            # Set fully transparent (alpha=0)
            user32.SetLayeredWindowAttributes(overlay_hwnd, 0, 0, LWA_ALPHA)

            # Position overlay exactly over target
            user32.SetWindowPos(
                overlay_hwnd, hwnd,
                0, 0, width, height,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )

            # Hide original window
            user32.ShowWindow(hwnd, SW_HIDE)

            self._overlays[hwnd] = overlay_hwnd
            logger.info(
                "Pseudo-minimized hwnd=%s, overlay=%s, geometry=%dx%d",
                hwnd, overlay_hwnd, width, height,
            )
            return True

    def restore(self, hwnd: int) -> bool:
        """Restore a pseudo-minimized window to its original state

        Removes the transparent overlay and shows the original window.

        Args:
            hwnd: Target window handle to restore

        Returns:
            True if restoration was successful
        """
        with self._lock:
            overlay_hwnd = self._overlays.pop(hwnd, None)
            if overlay_hwnd is None:
                logger.debug("hwnd=%s not pseudo-minimized", hwnd)
                return False

            # Destroy overlay
            user32.DestroyWindow(overlay_hwnd)

            # Restore original extended style
            orig_style = self._original_styles.pop(hwnd, None)
            if orig_style is not None:
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, orig_style)

            # Show original window
            user32.ShowWindow(hwnd, SW_SHOW)
            logger.info("Restored hwnd=%s from pseudo-minimization", hwnd)
            return True

    def is_minimized(self, hwnd: int) -> bool:
        """Check if a window is currently pseudo-minimized

        Args:
            hwnd: Window handle to check

        Returns:
            True if the window has an active overlay
        """
        return hwnd in self._overlays

    def get_overlay_hwnd(self, hwnd: int) -> int | None:
        """Get the overlay window handle for a pseudo-minimized window

        Args:
            hwnd: Original window handle

        Returns:
            Overlay handle, or None if not pseudo-minimized
        """
        return self._overlays.get(hwnd)

    def start_foreground_polling(self, hwnd: int) -> None:
        """Start background thread to recover foreground when lost

        Some games detect loss of foreground and pause rendering. This thread
        periodically checks if the target is foreground and uses tricks to
        maintain its foreground status.

        Args:
            hwnd: Window handle to protect
        """
        self._stop_polling = False
        self._poll_thread = threading.Thread(
            target=self._poll_foreground, args=(hwnd,), daemon=True
        )
        self._poll_thread.start()
        logger.info("Started foreground polling for hwnd=%s", hwnd)

    def stop_foreground_polling(self) -> None:
        """Stop the foreground recovery polling thread"""
        self._stop_polling = True
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)
        self._poll_thread = None
        logger.info("Stopped foreground polling")

    def _poll_foreground(self, hwnd: int) -> None:
        """Background loop: periodically ensure hwnd can receive input

        Uses Alt-key trick to work around Windows foreground lock restrictions.
        """
        while not self._stop_polling:
            try:
                fg = user32.GetForegroundWindow()
                if fg != hwnd and fg != self._overlays.get(hwnd):
                    user32.keybd_event(0x12, 0, 0, 0)
                    user32.keybd_event(0x12, 0, 2, 0)
            except Exception:
                pass
            time.sleep(self._poll_interval)

    def release_all(self) -> None:
        """Release all overlays and stop polling"""
        self.stop_foreground_polling()
        with self._lock:
            for hwnd in list(self._overlays.keys()):
                with contextlib.suppress(Exception):
                    self.restore(hwnd)
        logger.info("Released all pseudo-minimizer resources")

    @staticmethod
    def _static_wnd_proc(hwnd, msg, wparam, lparam):
        """Static window procedure for overlay windows — discard all messages"""
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def __len__(self) -> int:
        return len(self._overlays)

    def __contains__(self, hwnd: int) -> bool:
        return hwnd in self._overlays
