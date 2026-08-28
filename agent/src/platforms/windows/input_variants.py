"""Windows input method compatibility and foreground management.

This module previously hosted 9 InputVariant subclasses mirroring MaaFramework's
Win32InputMethod enum. The production code path only uses the 3-method string
system in ``platforms.windows.input`` (SendInput / PostMessage / PseudoBackground).
The 9-variant subclasses were only exercised by tests and added 1300+ lines of
dead code.

After TD-090 cleanup, this module retains only:
  1. ``Win32InputMethod`` enum — used by the compatibility table below.
  2. ``_VARIANT_DESCRIPTIONS`` — human-readable descriptions for introspection.
  3. Introspection helpers: ``list_available_variants`` / ``list_all_variants``
     / ``get_variant_description`` / ``get_variant_info``.
  4. ``bring_to_foreground`` — AttachThreadInput trick used by PseudoBackground.
  5. ``INPUT_COMPATIBILITY_TABLE`` + query functions — window-class → method
     compatibility mapping used by ``device.py`` auto-mode resolution.

Reference: open-source-ref/MaaFramework/source/MaaWin32ControlUnit/Manager/Win32ControlUnitMgr.cpp
"""

from __future__ import annotations

import ctypes
import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32


# ── Win32InputMethod enum ─────────────────────────────────────────────


class Win32InputMethod(Enum):
    """Enumeration of the 9 MaaFramework Win32 input method variants.

    Mirrors MaaWin32InputMethod enum from MaaFramework source.
    PostThreadMessage is deprecated and kept for enumeration completeness only.
    """

    SEIZE = "seize"
    SEND_MESSAGE = "send_message"
    POST_MESSAGE = "post_message"
    LEGACY_EVENT = "legacy_event"
    SEND_MESSAGE_CURSOR_POS = "send_message_cursor_pos"
    POST_MESSAGE_CURSOR_POS = "post_message_cursor_pos"
    SEND_MESSAGE_WINDOW_POS = "send_message_window_pos"
    POST_MESSAGE_WINDOW_POS = "post_message_window_pos"
    POST_THREAD_MESSAGE = "post_thread_message"  # Deprecated

    @property
    def is_deprecated(self) -> bool:
        """Whether this method is deprecated and should not be used."""
        return self == Win32InputMethod.POST_THREAD_MESSAGE

    @property
    def is_foreground(self) -> bool:
        """Whether this method requires the target window to be in foreground."""
        return self in (Win32InputMethod.SEIZE, Win32InputMethod.LEGACY_EVENT)

    @property
    def is_background(self) -> bool:
        """Whether this method works when the target window is in background."""
        return not self.is_foreground


# ── Variant descriptions (for GUI / introspection) ─────────────────────

_VARIANT_DESCRIPTIONS: dict[Win32InputMethod, str] = {
    Win32InputMethod.SEIZE:
        "Foreground SendInput with SetForegroundWindow + AttachThreadInput. "
        "Works with fullscreen apps and games. Target must be focusable.",
    Win32InputMethod.SEND_MESSAGE:
        "Synchronous SendMessageW to target window. Background-safe. "
        "Blocks until the window processes the message.",
    Win32InputMethod.POST_MESSAGE:
        "Asynchronous PostMessageW to target window. Background-safe. "
        "Returns immediately without waiting for processing.",
    Win32InputMethod.LEGACY_EVENT:
        "Legacy keybd_event / mouse_event API. Deprecated by Microsoft but "
        "retained for compatibility with very old applications.",
    Win32InputMethod.SEND_MESSAGE_CURSOR_POS:
        "SendMessage + SetCursorPos save/restore + BlockInput. "
        "Saves cursor position, moves it to target, sends message, restores. "
        "Blocks real mouse input during operation.",
    Win32InputMethod.POST_MESSAGE_CURSOR_POS:
        "PostMessage + SetCursorPos save/restore + BlockInput. "
        "Same as SendMessage variant but asynchronous.",
    Win32InputMethod.SEND_MESSAGE_WINDOW_POS:
        "SendMessage + move window to align cursor + 60fps tracking. "
        "Moves target window so client (x,y) is under current cursor. "
        "FPS-friendly: works with games that capture real mouse position.",
    Win32InputMethod.POST_MESSAGE_WINDOW_POS:
        "PostMessage + move window to align cursor + 60fps tracking. "
        "Same as SendMessage variant but asynchronous.",
    Win32InputMethod.POST_THREAD_MESSAGE:
        "[DEPRECATED] PostThreadMessage. Removed from MaaFramework due to "
        "reliability issues. Raises NotImplementedError if used.",
}


# ── Introspection helpers ─────────────────────────────────────────────


def list_available_variants() -> list[Win32InputMethod]:
    """List all available (non-deprecated) input variants.

    Returns:
        List of Win32InputMethod values, excluding deprecated methods.
    """
    return [m for m in Win32InputMethod if not m.is_deprecated]


def list_all_variants() -> list[Win32InputMethod]:
    """List all input variants including deprecated ones.

    Returns:
        List of all Win32InputMethod values.
    """
    return list(Win32InputMethod)


def get_variant_description(method: Win32InputMethod) -> str:
    """Get human-readable description for an input method.

    Args:
        method: Win32InputMethod enum value.

    Returns:
        Description string.
    """
    return _VARIANT_DESCRIPTIONS.get(method, f"Unknown method: {method}")


def get_variant_info() -> list[dict[str, Any]]:
    """Get metadata for all variants (for GUI / introspection).

    Returns:
        List of dicts with keys: method, value, description, is_deprecated,
        is_foreground, is_background.
    """
    return [
        {
            "method": method.name,
            "value": method.value,
            "description": get_variant_description(method),
            "is_deprecated": method.is_deprecated,
            "is_foreground": method.is_foreground,
            "is_background": method.is_background,
        }
        for method in Win32InputMethod
    ]


# ── Foreground management ─────────────────────────────────────────────


def bring_to_foreground(hwnd_target: int, *, log: bool = True) -> bool:
    """Bring target window to foreground using AttachThreadInput trick.

    Cross-process SetForegroundWindow is normally rejected by the OS
    unless the caller is the foreground process. Attaching the input
    processing queues of the current thread and the foreground thread
    makes SetForegroundWindow succeed.

    Args:
        hwnd_target: Handle of the window to bring to foreground.
        log: If True, log success/failure for diagnostics.

    Returns:
        True if hwnd_target is foreground after the call (or already was),
        False otherwise.
    """
    if not hwnd_target:
        return True  # Desktop target, no foreground needed

    if user32.GetForegroundWindow() == hwnd_target:
        return True

    kernel32 = ctypes.windll.kernel32
    fg_hwnd = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
    cur_thread = kernel32.GetCurrentThreadId()

    attached = False
    if fg_thread and fg_thread != cur_thread:
        attached = bool(user32.AttachThreadInput(cur_thread, fg_thread, True))

    try:
        user32.SetForegroundWindow(hwnd_target)
        time.sleep(0.05)  # let OS complete focus switch
        success = user32.GetForegroundWindow() == hwnd_target
        if log:
            logger.info(
                "bring_to_foreground: target=%s, prev_fg=%s, fg_thread=%s, "
                "cur_thread=%s, attached=%s, success=%s",
                hwnd_target, fg_hwnd, fg_thread, cur_thread, attached, success,
            )
        return success
    except Exception as exc:
        logger.warning("bring_to_foreground failed: %s", exc)
        return False
    finally:
        if attached:
            user32.AttachThreadInput(cur_thread, fg_thread, False)


# ── Window-class → input-method compatibility ─────────────────────────
#
# Industry knowledge (validated against BD2/Unity/Unreal/Godot + standard
# Win32 apps): some window classes block specific input methods. The table
# below captures the known compatibility so that auto-mode can pick a
# method that actually works instead of silently failing.
#
# Reference:
#   - MaaFramework source: docs/ InputController compatibility notes
#   - BD2-AUTO field testing (Unity game): PostMessage mouse ignored
#   - Unity: uses RawInput, ignores WM_LBUTTONDOWN/UP sent via PostMessage
#   - Unreal: similar to Unity for mouse; keyboard messages usually work
#   - Standard Win32: all methods work; PostMessage preferred for background

# Legacy method string (device.py WindowsInputHandler) ↔ Win32InputMethod enum
_LEGACY_TO_ENUM: dict[str, Win32InputMethod] = {
    "SendInput": Win32InputMethod.SEIZE,
    "PostMessage": Win32InputMethod.POST_MESSAGE,
    "PseudoBackground": Win32InputMethod.SEIZE,  # pseudo-bg uses SendInput internally
}

_ENUM_TO_LEGACY: dict[Win32InputMethod, str] = {
    Win32InputMethod.SEIZE: "SendInput",
    Win32InputMethod.LEGACY_EVENT: "SendInput",  # closest legacy equivalent
    Win32InputMethod.SEND_MESSAGE: "PostMessage",
    Win32InputMethod.POST_MESSAGE: "PostMessage",
    Win32InputMethod.SEND_MESSAGE_CURSOR_POS: "PostMessage",
    Win32InputMethod.POST_MESSAGE_CURSOR_POS: "PostMessage",
    Win32InputMethod.SEND_MESSAGE_WINDOW_POS: "PostMessage",
    Win32InputMethod.POST_MESSAGE_WINDOW_POS: "PostMessage",
}

# Window-class → compatibility info
# `recommended`: methods known to work; first item = best choice
# `blocked`: methods known to be ignored/blocked by this window class
# `reason`: human-readable explanation
INPUT_COMPATIBILITY_TABLE: dict[str, dict[str, Any]] = {
    "UnityWndClass": {
        "recommended": [Win32InputMethod.SEIZE, Win32InputMethod.LEGACY_EVENT],
        "blocked": [
            Win32InputMethod.SEND_MESSAGE,
            Win32InputMethod.POST_MESSAGE,
            Win32InputMethod.SEND_MESSAGE_CURSOR_POS,
            Win32InputMethod.POST_MESSAGE_CURSOR_POS,
        ],
        "reason": (
            "Unity uses RawInput and ignores WM_LBUTTONDOWN/UP sent via "
            "PostMessage/SendMessage. Foreground SendInput works. "
            "SendMessageWithWindowPos may work but is unreliable."
        ),
    },
    "UnrealWindow": {
        "recommended": [Win32InputMethod.SEIZE, Win32InputMethod.LEGACY_EVENT],
        "blocked": [
            Win32InputMethod.SEND_MESSAGE,
            Win32InputMethod.POST_MESSAGE,
        ],
        "reason": (
            "Unreal Engine games typically use RawInput for mouse and "
            "ignore PostMessage/SendMessage mouse events. SendInput works "
            "when the window is in foreground."
        ),
    },
    "LaunchUnrealUWindowsClient": {
        "recommended": [
            Win32InputMethod.POST_MESSAGE,
            Win32InputMethod.SEND_MESSAGE,
            Win32InputMethod.SEIZE,
        ],
        "blocked": [],
        "reason": (
            "Unreal launcher windows are standard Win32 and accept all "
            "message-based input. PostMessage preferred for background."
        ),
    },
    "Godot_Engine_Wnd": {
        "recommended": [Win32InputMethod.SEIZE, Win32InputMethod.LEGACY_EVENT],
        "blocked": [
            Win32InputMethod.SEND_MESSAGE,
            Win32InputMethod.POST_MESSAGE,
        ],
        "reason": (
            "Godot engine games often use RawInput and ignore "
            "PostMessage/SendMessage mouse events."
        ),
    },
    "GLFW30": {  # Some emulators use GLFW
        "recommended": [Win32InputMethod.SEIZE],
        "blocked": [
            Win32InputMethod.SEND_MESSAGE,
            Win32InputMethod.POST_MESSAGE,
        ],
        "reason": "GLFW-based windows often block message-based mouse input.",
    },
    # Default for standard Win32 windows (empty/unknown class)
    "": {
        "recommended": [
            Win32InputMethod.POST_MESSAGE,
            Win32InputMethod.SEND_MESSAGE,
            Win32InputMethod.SEIZE,
        ],
        "blocked": [],
        "reason": (
            "Standard Win32 windows accept all input methods. PostMessage "
            "preferred for background operation."
        ),
    },
}


def recommend_input_method(window_class: str) -> Win32InputMethod:
    """Recommend the best input method for a given window class.

    Args:
        window_class: Win32 window class name (e.g. "UnityWndClass").
            Empty string for unknown/standard windows.

    Returns:
        Win32InputMethod enum value recommended for this window class.
        Falls back to SEIZE (SendInput) for unknown game-like classes
        and POST_MESSAGE for standard windows.

    Examples:
        >>> recommend_input_method("UnityWndClass")
        <Win32InputMethod.SEIZE: 'seize'>
        >>> recommend_input_method("")
        <Win32InputMethod.POST_MESSAGE: 'post_message'>
    """
    info = INPUT_COMPATIBILITY_TABLE.get(window_class)
    if info and info["recommended"]:
        return info["recommended"][0]
    # Unknown class: assume standard Win32 → PostMessage for background safety
    return Win32InputMethod.POST_MESSAGE


def get_blocked_input_methods(window_class: str) -> list[Win32InputMethod]:
    """Get the list of input methods known to be blocked by this window class.

    Args:
        window_class: Win32 window class name.

    Returns:
        List of Win32InputMethod values that are known to be ignored or
        blocked by this window class. Empty list if no known blocks.
    """
    info = INPUT_COMPATIBILITY_TABLE.get(window_class)
    if info:
        return list(info["blocked"])
    return []


def get_compatibility_reason(window_class: str) -> str:
    """Get the human-readable reason for the compatibility mapping.

    Args:
        window_class: Win32 window class name.

    Returns:
        Explanation string for why certain methods are recommended/blocked.
    """
    info = INPUT_COMPATIBILITY_TABLE.get(window_class, {})
    return info.get("reason", "Unknown window class; using default compatibility.")


def recommend_legacy_input_method(window_class: str) -> str:
    """Recommend a legacy input method string for WindowsInputHandler.

    This is a bridge function for device.py's legacy WindowsInputHandler,
    which uses string method names ("SendInput"/"PostMessage"/
    "PseudoBackground") instead of the Win32InputMethod enum.

    Args:
        window_class: Win32 window class name.

    Returns:
        One of "SendInput", "PostMessage", "PseudoBackground" — the
        legacy method string most likely to work for this window class.
    """
    enum_method = recommend_input_method(window_class)
    return _ENUM_TO_LEGACY.get(enum_method, "SendInput")


def is_input_method_compatible(
    method: Win32InputMethod, window_class: str,
) -> bool:
    """Check whether a specific input method is compatible with a window class.

    Args:
        method: Win32InputMethod enum value to check.
        window_class: Win32 window class name.

    Returns:
        True if the method is in the recommended list or not in the
        blocked list. False if explicitly blocked.
    """
    info = INPUT_COMPATIBILITY_TABLE.get(window_class)
    if not info:
        return True  # unknown class → assume compatible
    return method not in info["blocked"]


def get_compatibility_info(window_class: str) -> dict[str, Any]:
    """Get full compatibility info for a window class.

    Args:
        window_class: Win32 window class name.

    Returns:
        Dict with keys: recommended (list of enum), blocked (list of enum),
        reason (str), recommended_legacy (str). For unknown classes,
        returns the default (standard Win32) compatibility.
    """
    info = INPUT_COMPATIBILITY_TABLE.get(window_class, INPUT_COMPATIBILITY_TABLE[""])
    return {
        "recommended": list(info["recommended"]),
        "blocked": list(info["blocked"]),
        "reason": info["reason"],
        "recommended_legacy": recommend_legacy_input_method(window_class),
    }
