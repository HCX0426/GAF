"""DPI awareness utilities — 3-level fallback per MaaFramework pattern.

Reference: MaaFramework window_scale() + ok-script composite_hwnds DPI handling.

Three-tier DPI awareness strategy (most-precise to least-precise):
1. SetThreadDpiAwarenessContext(PER_MONITOR_AWARE_V2) — thread-level, Win10 1703+
2. SetProcessDpiAwareness(PER_MONITOR_DPI_AWARE) — process-level, Win 8.1+
3. SetProcessDPIAware() — system-level, legacy fallback

Per-window DPI queries via GetDpiForWindow() (Win10 1607+) provide the
exact scale factor for a specific hwnd; older systems fall back to
GetDeviceCaps(LOGPIXELSX) on the screen DC.

Cross-platform: Windows-only. Non-Windows platforms get scale=1.0.
"""

import contextlib
import ctypes
import ctypes.wintypes
import logging
import platform

logger = logging.getLogger(__name__)

# DPI awareness context values (passed to SetThreadDpiAwarenessContext).
# These are special pseudo-handle values defined in windef.h as
# DPI_AWARENESS_CONTEXT_* (negative integers cast to DPI_AWARENESS_CONTEXT).
DPI_AWARENESS_CONTEXT_INVALID = None  # sentinel
DPI_AWARENESS_CONTEXT_UNAWARE = -1
DPI_AWARENESS_CONTEXT_SYSTEM_AWARE = -2
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE = -3
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4

# SetProcessDpiAwareness values
PROCESS_DPI_UNAWARE = 0
PROCESS_SYSTEM_DPI_AWARE = 1
PROCESS_PER_MONITOR_DPI_AWARE = 2

# GetDeviceCaps index
LOGPIXELSX = 88

# Standard DPI
STANDARD_DPI = 96.0


def is_windows() -> bool:
    """Return True on Windows (where DPI APIs are meaningful)."""
    return platform.system() == "Windows"


def apply_dpi_awareness() -> str:
    """Apply the best available DPI awareness mode for this process.

    Tries three levels in order, returns the name of the level that succeeded:
    - "per_monitor_v2" — thread-level Per-Monitor v2 (best)
    - "per_monitor"    — process-level Per-Monitor
    - "system"         — process-level System DPI aware (legacy)
    - "unaware"        — none succeeded (or non-Windows)

    Idempotent: calling multiple times is safe. The first successful call
    wins; subsequent calls are no-ops.
    """
    if not is_windows():
        return "unaware"

    try:
        user32 = ctypes.windll.user32

        # Level 1: SetThreadDpiAwarenessContext (Win10 1703+)
        # Available in user32.dll. Returns the old context (non-NULL) on success.
        try:
            user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
            user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            old = user32.SetThreadDpiAwarenessContext(
                ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
            )
            if old:
                logger.debug("DPI awareness set: per_monitor_v2 (thread-level)")
                return "per_monitor_v2"
        except (AttributeError, OSError) as exc:
            logger.debug("SetThreadDpiAwarenessContext unavailable: %s", exc)

        # Level 2: SetProcessDpiAwareness (Win 8.1+)
        try:
            shcore = ctypes.windll.shcore
            shcore.SetProcessDpiAwareness.restype = ctypes.c_long  # HRESULT
            shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
            hr = shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
            if hr >= 0:
                logger.debug("DPI awareness set: per_monitor (process-level)")
                return "per_monitor"
            # E_ACCESSDENIED means already set — that's fine
            logger.debug("SetProcessDpiAwareness hr=0x%08X", hr & 0xFFFFFFFF)
        except (AttributeError, OSError) as exc:
            logger.debug("SetProcessDpiAwareness unavailable: %s", exc)

        # Level 3: SetProcessDPIAware (legacy, Vista+)
        try:
            if user32.SetProcessDPIAware():
                logger.debug("DPI awareness set: system (legacy)")
                return "system"
        except (AttributeError, OSError) as exc:
            logger.debug("SetProcessDPIAware unavailable: %s", exc)

    except Exception as exc:
        logger.warning("DPI awareness setup failed: %s", exc)

    return "unaware"


def get_dpi_for_window(hwnd: int) -> int:
    """Return the DPI for the given window.

    Uses GetDpiForWindow (Win10 1607+) when available; falls back to
    GetDeviceCaps(LOGPIXELSX) on the screen DC for older systems.

    Args:
        hwnd: Target window handle. If 0 or invalid, queries the screen DPI.

    Returns:
        DPI value (typically 96/120/144/168/192 for 100%/125%/150%/175%/200%).
        Returns 96 on non-Windows or failure.
    """
    if not is_windows():
        return 96

    try:
        user32 = ctypes.windll.user32

        # Preferred: GetDpiForWindow (Win10 1607+)
        try:
            user32.GetDpiForWindow.restype = ctypes.c_uint
            user32.GetDpiForWindow.argtypes = [ctypes.wintypes.HWND]
            if hwnd:
                dpi = user32.GetDpiForWindow(hwnd)
                if dpi > 0:
                    return int(dpi)
        except (AttributeError, OSError):
            pass

        # Fallback: GetDeviceCaps on screen DC
        dc = user32.GetDC(0)
        if not dc:
            return 96
        try:
            dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, LOGPIXELSX)
            return int(dpi) if dpi > 0 else 96
        finally:
            user32.ReleaseDC(0, dc)
    except Exception as exc:
        logger.debug("get_dpi_for_window failed: %s", exc)
        return 96


def get_dpi_scale_factor(hwnd: int = 0) -> float:
    """Return DPI scale factor (1.0 = 100%, 1.5 = 150%, etc.) for hwnd.

    Convenience wrapper around get_dpi_for_window. Applies DPI awareness
    on first call if not already applied.

    Args:
        hwnd: Target window handle. 0 = screen-level DPI.

    Returns:
        Scale factor (e.g. 1.0, 1.25, 1.5, 2.0). Returns 1.0 on non-Windows.
    """
    if not is_windows():
        return 1.0
    dpi = get_dpi_for_window(hwnd)
    return dpi / STANDARD_DPI


# Apply DPI awareness on module import (idempotent).
_dpi_awareness_level: str = "unaware"
with contextlib.suppress(Exception):
    _dpi_awareness_level = apply_dpi_awareness()
