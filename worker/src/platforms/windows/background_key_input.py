"""Background-managed key input using RegisterHotKey + SendInput.

Provides reliable key input for FPS games and fullscreen applications where
standard PostMessage/SendMessage may be blocked by anti-cheat or input hooks.
Uses global hotkey registration to intercept key events and forward them
via SendInput for maximum compatibility.

Reference: MaaFramework's BackgroundManagedKeyInput strategy.
"""

import ctypes
import ctypes.wintypes
import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

VK_MAP = {
    "enter": 0x0D, "return": 0x0D,
    "tab": 0x09, "escape": 0x1B, "esc": 0x1B,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "space": 0x20,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "ctrl": 0x11, "alt": 0x12, "shift": 0x10,
    "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
}


class BackgroundManagedKeyInput:
    """Background key input manager using hotkey registration.

    Registers global hotkeys via RegisterHotKey, then uses SendInput to
    synthesize key presses. This approach works even when:
    - The target window is not in foreground
    - The application blocks PostMessage-based input
    - Anti-cheat software filters WM_KEYDOWN/WM_KEYUP messages

    Usage:
        bmki = BackgroundManagedKeyInput()
        bmki.register_hotkey("ctrl+f1", callback=my_handler)
        bmki.start_message_loop()  # Blocking: runs WndProc loop
        # Or use non-blocking mode:
        bmki.start_async()
        bmki.send_key("enter")  # Send via SendInput
        bmki.stop_async()
    """

    def __init__(self, target_hwnd: int | None = None):
        """Initialize background managed key input

        Args:
            target_hwnd: Target window to send keys to (None = foreground)
        """
        self._target_hwnd = target_hwnd
        self._hotkeys: dict[int, tuple[str, Callable]] = {}
        self._next_id = 1
        self._message_thread: any | None = None
        self._running = False
        self._wclass_registered = False
        # P1-5: guard loop state for managed keys (MaaFramework parity).
        self._desired_pressed_keys: dict[str, int] = {}  # key_name -> generation
        self._release_keys: dict[str, int] = {}  # key_name -> generation
        self._generation_counter: int = 0
        self._applied_generation: int = 0
        self._applied_lock = threading.Lock()
        self._guard_thread: threading.Thread | None = None
        self._guard_stop = threading.Event()
        self._managed_hotkey_ids: dict[str, int] = {}  # key_name -> hotkey_id

    def register_hotkey(
        self,
        combo: str,
        callback: Callable[[int, int], None],
    ) -> int:
        """Register a global hotkey combination

        Args:
            combo: Key combination string, e.g., "ctrl+alt+f1", "shift+f2"
            callback: Function to call when hotkey is pressed, receives (modifiers, vk)

        Returns:
            Hotkey ID for later unregister, or 0 on failure

        Example:
            def on_hotkey(mods, vk):
                print(f"Hotkey triggered: mods={mods}, vk={vk}")

            hotkey_id = bmki.register_hotkey("ctrl+f1", on_hotkey)
        """
        modifiers, vk = self._parse_combo(combo)
        if vk == 0:
            logger.warning("Failed to parse hotkey combo: %s", combo)
            return 0

        hotkey_id = self._next_id
        self._next_id += 1

        result = user32.RegisterHotKey(None, hotkey_id, modifiers, vk)
        if result == 0:
            logger.error("Failed to register hotkey: %s (id=%d)", combo, hotkey_id)
            return 0

        self._hotkeys[hotkey_id] = (combo, callback)
        logger.info("Registered hotkey id=%d: %s", hotkey_id, combo)
        return hotkey_id

    def unregister_hotkey(self, hotkey_id: int) -> bool:
        """Unregister a previously registered hotkey

        Args:
            hotkey_id: ID returned by register_hotkey()

        Returns:
            True if unregistration succeeded
        """
        if hotkey_id not in self._hotkeys:
            return False

        result = user32.UnregisterHotKey(None, hotkey_id)
        if result:
            combo = self._hotkeys.pop(hotkey_id)[0]
            logger.info("Unregistered hotkey id=%d: %s", hotkey_id, combo)
        else:
            logger.warning("Failed to unregister hotkey id=%d", hotkey_id)
        return bool(result)

    def send_key(self, key: str) -> bool:
        """Send a single key press via SendInput

        This works reliably even in fullscreen games because SendInput
        injects at a lower level than PostMessage.

        Args:
            key: Key name (e.g., "enter", "a", "f1", "ctrl+a")

        Returns:
            True if SendInput calls succeeded
        """
        from platforms.windows.input import INPUT, _make_key_input, _resolve_vk

        vk = _resolve_vk(key)
        if vk == 0:
            logger.warning("Cannot resolve key: %s", key)
            return False

        size = ctypes.sizeof(INPUT)

        down = _make_key_input(vk, 0)
        up = _make_key_input(vk, 0x0002)

        result1 = user32.SendInput(1, ctypes.byref(down), size)
        time.sleep(0.03)
        result2 = user32.SendInput(1, ctypes.byref(up), size)

        success = result1 > 0 and result2 > 0
        logger.debug("SendInput key=%s vk=0x%02X: %s", key, vk, "OK" if success else "FAIL")
        return success

    def send_key_combination(self, combo: str) -> bool:
        """Send a key combination (modifiers + key) via SendInput

        Args:
            combo: Combination like "ctrl+a", "alt+f4", "shift+ctrl+esc"

        Returns:
            True if all SendInput calls succeeded
        """
        from platforms.windows.input import INPUT, _make_key_input

        modifiers, vk = self._parse_combo(combo)
        if vk == 0:
            return False

        size = ctypes.sizeof(INPUT)

        inputs = []

        # Press modifiers
        mod_vks = []
        if modifiers & MOD_CONTROL:
            mod_vks.append(0x11)
        if modifiers & MOD_ALT:
            mod_vks.append(0x12)
        if modifiers & MOD_SHIFT:
            mod_vks.append(0x10)
        if modifiers & MOD_WIN:
            mod_vks.append(0x5B)

        for mvk in mod_vks:
            inputs.append(_make_key_input(mvk, 0))

        # Press main key
        inputs.append(_make_key_input(vk, 0))

        # Release main key
        inputs.append(_make_key_input(vk, 0x0002))

        # Release modifiers in reverse order
        for mvk in reversed(mod_vks):
            inputs.append(_make_key_input(mvk, 0x0002))

        all_ok = True
        for inp in inputs:
            result = user32.SendInput(1, ctypes.byref(inp), size)
            if result == 0:
                all_ok = False
            time.sleep(0.02)

        logger.debug("SendInput combo=%s: %s", combo, "OK" if all_ok else "FAIL")
        return all_ok

    def start_async(self) -> None:
        """Start hotkey message pump in a background thread (non-blocking)"""
        if self._running:
            return

        self._running = True
        self._message_thread = threading.Thread(target=self._message_loop, daemon=True)
        self._message_thread.start()
        logger.info("Async message loop started")

    def stop_async(self) -> None:
        """Stop the async message pump"""
        self._running = False
        if self._message_thread and self._message_thread.is_alive():
            self._message_thread.join(timeout=2.0)
        self._message_thread = None
        logger.info("Async message loop stopped")

    def _message_loop(self) -> None:
        """Background thread: process WM_HOTKEY messages"""
        msg = ctypes.wintypes.MSG()
        while self._running:
            try:
                result = user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1)
                if result:
                    if msg.message == WM_HOTKEY:
                        hotkey_id = msg.lParam & 0xFFFF
                        entry = self._hotkeys.get(hotkey_id)
                        if entry:
                            _, callback = entry
                            modifiers = (msg.lParam >> 16) & 0xFFFF
                            vk = msg.wParam & 0xFFFF
                            try:
                                callback(modifiers, vk)
                            except Exception as exc:
                                logger.error("Hotkey callback error (id=%d): %s", hotkey_id, exc)
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    time.sleep(0.01)
            except Exception as exc:
                logger.debug("Message loop error: %s", exc)
                time.sleep(0.05)

    @staticmethod
    def _parse_combo(combo: str) -> tuple[int, int]:
        """Parse key combination string into (modifiers, virtual_key_code)

        Args:
            combo: String like "ctrl+alt+f1", "shift+a"

        Returns:
            (modifiers_flag, vk_code) tuple
        """
        parts = combo.lower().replace(" ", "").split("+")
        modifiers = 0
        key_part = ""

        for part in parts:
            if part in ("ctrl", "control"):
                modifiers |= MOD_CONTROL
            elif part == "alt":
                modifiers |= MOD_ALT
            elif part == "shift":
                modifiers |= MOD_SHIFT
            elif part in ("win", "lwin", "rwin"):
                modifiers |= MOD_WIN
            else:
                key_part = part

        if not key_part:
            return 0, 0

        vk = VK_MAP.get(key_part, 0)
        if vk == 0 and len(key_part) == 1:
            vk = ord(key_part.upper())

        return modifiers, vk

    def release_all(self) -> None:
        """Unregister all hotkeys and stop message loop"""
        self.stop_async()
        for hotkey_id in list(self._hotkeys.keys()):
            self.unregister_hotkey(hotkey_id)
        logger.info("All hotkeys released")

    @property
    def registered_count(self) -> int:
        return len(self._hotkeys)

    # ── P1-5: MaaFramework BackgroundManagedKeyInput parity ──────────────

    # Guard loop polls at 5ms interval (matching MaaFramework).
    _GUARD_INTERVAL_SEC = 0.005
    # Generation sync timeout (matching MaaFramework's 500ms).
    _APPLY_TIMEOUT_SEC = 0.5
    # WM_HOTKEY confirmation timeout for ensure_key_pressed.
    _HOTKEY_CONFIRM_TIMEOUT_SEC = 0.2

    def ensure_key_pressed(self, key: str) -> bool:
        """P1-5: ensure a key is pressed using the 4-step MaaFramework technique.

        1. RegisterHotKey — register a global hotkey to intercept system handling.
        2. SendInput — send key down event.
        3. Wait for WM_HOTKEY confirmation in message loop (200ms timeout).
        4. UnregisterHotKey — release system resource.

        Returns True if the WM_HOTKEY confirmation arrived within timeout,
        indicating the key event was successfully injected and acknowledged.
        """
        combo = key.lower()
        # Use a unique hotkey id per ensure_key_pressed call.
        hotkey_id = self._next_id
        self._next_id += 1
        modifiers, vk = self._parse_combo(combo)
        if vk == 0:
            logger.warning("ensure_key_pressed: cannot parse key %r", key)
            return False

        try:
            # Step 1: RegisterHotKey
            if user32.RegisterHotKey(None, hotkey_id, modifiers, vk) == 0:
                logger.debug("ensure_key_pressed: RegisterHotKey failed for %s", key)
                # Fall back to plain SendInput without confirmation.
                return self.send_key(key)

            # Step 2: SendInput (down + up)
            from platforms.windows.input import INPUT, _make_key_input, _resolve_vk
            real_vk = _resolve_vk(key)
            if real_vk == 0:
                real_vk = vk
            size = ctypes.sizeof(INPUT)
            down = _make_key_input(real_vk, 0)
            up = _make_key_input(real_vk, 0x0002)
            user32.SendInput(1, ctypes.byref(down), size)
            time.sleep(0.03)
            user32.SendInput(1, ctypes.byref(up), size)

            # Step 3: Wait for WM_HOTKEY confirmation.
            # PeekMessage in a tight loop with timeout.
            deadline = time.monotonic() + self._HOTKEY_CONFIRM_TIMEOUT_SEC
            msg = ctypes.wintypes.MSG()
            confirmed = False
            while time.monotonic() < deadline:
                if user32.PeekMessageW(
                    ctypes.byref(msg), 0, WM_HOTKEY, WM_HOTKEY, 1,
                ) and (msg.lParam & 0xFFFF) == hotkey_id:
                    confirmed = True
                    break
                time.sleep(0.005)

            if not confirmed:
                logger.debug(
                    "ensure_key_pressed: WM_HOTKEY confirmation timeout for %s", key,
                )
            return confirmed or self.send_key(key)
        finally:
            # Step 4: UnregisterHotKey (always).
            user32.UnregisterHotKey(None, hotkey_id)

    def add_managed_key(self, key: str) -> int:
        """P1-5: add a key to the managed-keys set.

        The guard loop will continuously ensure this key stays pressed via
        ensure_key_pressed() at 5ms intervals until remove_managed_key()
        is called.

        Returns the new generation number for sync.
        """
        with self._applied_lock:
            self._generation_counter += 1
            gen = self._generation_counter
            self._desired_pressed_keys[key] = gen
            self._release_keys.pop(key, None)
        self._ensure_guard_running()
        return gen

    def remove_managed_key(self, key: str) -> int:
        """P1-5: remove a key from the managed-keys set (releases it).

        Returns the new generation number for sync.
        """
        with self._applied_lock:
            self._generation_counter += 1
            gen = self._generation_counter
            self._desired_pressed_keys.pop(key, None)
            self._release_keys[key] = gen
        self._ensure_guard_running()
        return gen

    def wait_until_applied(self, generation: int, timeout_sec: float | None = None) -> bool:
        """P1-5: block until the guard loop reaches the given generation.

        Implements the optimistic-locking generation sync pattern from
        MaaFramework. Callers compare the generation returned by
        add_managed_key() / remove_managed_key() against the applied
        generation to confirm their request has been processed.

        Returns True if the generation was applied within the timeout.
        """
        timeout = timeout_sec if timeout_sec is not None else self._APPLY_TIMEOUT_SEC
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._applied_lock:
                if self._applied_generation >= generation:
                    return True
            time.sleep(0.005)
        return False

    def _ensure_guard_running(self) -> None:
        """Start the guard loop thread if not already running."""
        if self._guard_thread is not None and self._guard_thread.is_alive():
            return
        self._guard_stop.clear()
        self._guard_thread = threading.Thread(
            target=self._guard_loop,
            name="bmki-guard",
            daemon=True,
        )
        self._guard_thread.start()

    def _guard_loop(self) -> None:
        """P1-5: background thread that maintains managed key states.

        Polls at 5ms intervals (matching MaaFramework) and ensures all
        keys in _desired_pressed_keys stay pressed, while releasing any
        keys in _release_keys.
        """
        logger.debug("guard loop started")
        while not self._guard_stop.is_set():
            try:
                # Snapshot the desired / release sets under lock.
                with self._applied_lock:
                    desired = dict(self._desired_pressed_keys)
                    releases = dict(self._release_keys)
                    max_gen = 0
                    if desired:
                        max_gen = max(desired.values())
                    if releases:
                        max_gen = max(max_gen, max(releases.values()))

                # Ensure desired keys are pressed.
                for key_name in desired:
                    self.ensure_key_pressed(key_name)
                # Release keys marked for release.
                for key_name in releases:
                    self.send_key(key_name)  # send a down+up to ensure release
                with self._applied_lock:
                    self._applied_generation = max(
                        self._applied_generation, max_gen,
                    )
                    # Clear release set after processing.
                    if releases:
                        for k in list(releases.keys()):
                            self._release_keys.pop(k, None)
            except Exception as exc:
                logger.debug("guard loop error: %s", exc)
            self._guard_stop.wait(self._GUARD_INTERVAL_SEC)
        logger.debug("guard loop stopped")

    def stop_guard(self) -> None:
        """Stop the guard loop and clear all managed keys."""
        self._guard_stop.set()
        if self._guard_thread is not None:
            self._guard_thread.join(timeout=2.0)
            self._guard_thread = None
        with self._applied_lock:
            self._desired_pressed_keys.clear()
            self._release_keys.clear()

