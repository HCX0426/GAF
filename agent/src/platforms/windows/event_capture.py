"""Windows global event capture using pynput.

Captures mouse clicks, keyboard presses, and periodic screenshots,
feeding them into a RecordingEngine instance.
"""

from __future__ import annotations

import io
import logging
import threading
import time
from typing import TYPE_CHECKING

from PIL import Image
from pynput import keyboard, mouse

if TYPE_CHECKING:
    from core.recording import RecordingEngine

logger = logging.getLogger(__name__)


class WindowsEventCapture:
    """Capture global mouse/keyboard events and screenshots via pynput + mss.

    This class bridges pynput's global listeners with RecordingEngine's
    record_* methods, providing the missing event source for C2/C3/C4.
    """

    def __init__(
        self,
        recording_engine: RecordingEngine,
        capture_screenshots: bool = True,
        screenshot_interval: float = 2.0,
        screenshot_scale: float = 0.5,
    ) -> None:
        """Initialize the event capture.

        Args:
            recording_engine: The RecordingEngine to feed events into.
            capture_screenshots: Whether to capture periodic screenshots.
            screenshot_interval: Seconds between screenshot captures.
            screenshot_scale: Downscale factor for screenshots (0.5 = half size).
        """
        self._engine = recording_engine
        self._capture_screenshots = capture_screenshots
        self._screenshot_interval = screenshot_interval
        self._screenshot_scale = screenshot_scale

        self._keyboard_listener: keyboard.Listener | None = None
        self._mouse_listener: mouse.Listener | None = None
        self._screenshot_thread: threading.Thread | None = None
        self._running = False
        self._sct = None  # mss instance (lazy import in start())

        # Click dedup: pynput fires on_click twice (press + release).
        # Only record on press to avoid duplicate events.
        self._last_click_time: float = 0.0
        self._click_dedup_window: float = 0.05  # 50ms dedup window

    def start(self) -> None:
        """Start capturing global events. Must be called after RecordingEngine.start()."""
        if self._running:
            logger.warning("WindowsEventCapture already running")
            return

        self._running = True

        # Keyboard listener: capture key presses
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=None,
        )
        self._keyboard_listener.daemon = True
        self._keyboard_listener.start()

        # Mouse listener: capture clicks (press only, not release)
        self._mouse_listener = mouse.Listener(
            on_click=self._on_mouse_click,
        )
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

        # Screenshot thread: periodic full-screen captures
        if self._capture_screenshots:
            import mss  # Lazy import to avoid mss dependency in test envs
            self._sct = mss.mss()
            self._screenshot_thread = threading.Thread(
                target=self._screenshot_loop, daemon=True, name="recording-screenshot"
            )
            self._screenshot_thread.start()

        logger.info(
            "WindowsEventCapture started (screenshots=%s, interval=%.1fs)",
            self._capture_screenshots,
            self._screenshot_interval,
        )

    def stop(self) -> None:
        """Stop capturing events. Safe to call multiple times."""
        self._running = False

        if self._keyboard_listener is not None:
            self._keyboard_listener.stop()
            self._keyboard_listener = None

        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None

        if self._screenshot_thread is not None and self._screenshot_thread.is_alive():
            self._screenshot_thread.join(timeout=2.0)
            self._screenshot_thread = None

        if self._sct is not None:
            self._sct.close()
            self._sct = None

        logger.info("WindowsEventCapture stopped")

    def _on_key_press(self, key: object) -> None:
        """Handle keyboard key press event from pynput."""
        if not self._running:
            return
        try:
            # pynput returns Key enum for special keys, KeyCode for regular keys
            if isinstance(key, keyboard.Key):
                key_str = key.name  # e.g. 'enter', 'space', 'shift'
            elif isinstance(key, keyboard.KeyCode):
                key_str = key.char if key.char else f"vk_{key.vk}"
            else:
                key_str = str(key)
        except Exception:
            key_str = str(key)

        self._engine.record_key(key_str)

    def _on_mouse_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        """Handle mouse click event from pynput. Only records press events."""
        if not self._running or not pressed:
            return

        # Dedup: ignore clicks within 50ms of the last one (pynput may fire twice)
        now = time.time()
        if now - self._last_click_time < self._click_dedup_window:
            return
        self._last_click_time = now

        # Map pynput Button to string
        button_map = {
            mouse.Button.left: "left",
            mouse.Button.right: "right",
            mouse.Button.middle: "middle",
        }
        button_str = button_map.get(button, str(button))

        self._engine.record_click(x, y, button_str)

    def _screenshot_loop(self) -> None:
        """Periodically capture screenshots in a background thread."""
        while self._running:
            time.sleep(self._screenshot_interval)
            if not self._running or self._sct is None:
                break
            try:
                png_data = self._capture_screen_png()
                if png_data:
                    self._engine.record_screenshot(png_data)
            except Exception:
                logger.exception("Screenshot capture failed during recording")

    def _capture_screen_png(self) -> bytes | None:
        """Capture the full screen and return PNG bytes.

        Returns:
            PNG image bytes, or None on failure.
        """
        if self._sct is None:
            return None

        monitor = self._sct.monitors[0]  # All monitors combined
        raw = self._sct.grab(monitor)

        # Convert BGRA -> RGB and downscale
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        if self._screenshot_scale < 1.0:
            new_size = (
                int(img.width * self._screenshot_scale),
                int(img.height * self._screenshot_scale),
            )
            img = img.resize(new_size, Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
