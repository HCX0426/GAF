"""Build RuntimeDisplayContext from a live WindowsDevice.

Queries the bound window's client rect, DPI, screen resolution, and
client-to-screen origin, then populates a RuntimeDisplayContext for
the CoordinateTransformer to consume.

Returns None for non-Windows devices or when no hwnd is bound, so
callers (orchestrator) can simply check for None and fall back to
the legacy raw-pixel coordinate path.

Fullscreen detection compares the client rect against the *containing
monitor's* resolution (via MonitorFromWindow + GetMonitorInfoW) within
FULLSCREEN_ERROR_TOLERANCE. When fullscreen is detected, the client
screen origin is forced to (0, 0) since the client area covers the
entire screen.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging

from platforms.windows.dpi import get_dpi_scale_factor
from utils.coord_transformer import CoordinateTransformer
from utils.display_context import RuntimeDisplayContext

logger = logging.getLogger(__name__)

# Cache the user32 handle (module-level for performance)
_user32 = ctypes.windll.user32
_dwmapi = ctypes.windll.dwmapi  # cached for DwmGetWindowAttribute fallback

# Constants for MonitorFromWindow + GetMonitorInfo
_MONITOR_DEFAULTTONEAREST = 0x00000002


class _MONITORINFO(ctypes.Structure):
    """MONITORINFO struct for GetMonitorInfoW."""

    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("rcMonitor", ctypes.wintypes.RECT),
        ("rcWork", ctypes.wintypes.RECT),
        ("dwFlags", ctypes.wintypes.DWORD),
    ]


def _get_monitor_resolution(hwnd: int) -> tuple[int, int]:
    """Get the resolution of the monitor that contains the given window.

    Uses MonitorFromWindow + GetMonitorInfoW for per-monitor correctness
    (handles multi-monitor setups where the window is on a non-primary
    monitor with a different resolution than the primary).

    Args:
        hwnd: Window handle

    Returns:
        Tuple of (width, height) in physical pixels. Falls back to
        GetSystemMetrics (primary monitor) if the monitor query fails.
    """
    try:
        hmonitor = _user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
        if not hmonitor:
            raise OSError("MonitorFromWindow returned NULL")
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(mi)
        if not _user32.GetMonitorInfoW(hmonitor, ctypes.byref(mi)):
            raise OSError("GetMonitorInfoW failed")
        w = mi.rcMonitor.right - mi.rcMonitor.left
        h = mi.rcMonitor.bottom - mi.rcMonitor.top
        if w > 0 and h > 0:
            return (w, h)
    except Exception as exc:
        logger.debug(
            "_get_monitor_resolution: monitor query failed (hwnd=%s): %s; "
            "falling back to GetSystemMetrics",
            hwnd, exc,
        )
    # Fallback: primary monitor resolution
    return (_user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1))


def build_display_context(
    device,
    original_base_res: tuple[int, int] = (1920, 1080),
) -> RuntimeDisplayContext | None:
    """Build a RuntimeDisplayContext from a WindowsDevice's bound window.

    Args:
        device: A WindowsDevice instance (must have hwnd property and
                get_client_rect method). Non-WindowsDevice inputs return None.
        original_base_res: Reference resolution (width, height) that all
                ROI coordinates are defined against. Defaults to 1920x1080.

    Returns:
        Populated RuntimeDisplayContext, or None if:
          - device is not a WindowsDevice
          - device has no bound hwnd
          - client rect query fails
    """
    # Duck-type: WindowsDevice has hwnd + get_client_rect
    hwnd = getattr(device, "hwnd", None)
    if not hwnd:
        logger.debug(
            "build_display_context: no hwnd on device=%s; skipping display context",
            getattr(device, "device_id", device),
        )
        return None

    get_client_rect = getattr(device, "get_client_rect", None)
    if get_client_rect is None:
        logger.debug("build_display_context: device has no get_client_rect; skipping")
        return None

    # 1. Client physical rect (window's renderable area, in physical pixels)
    client_rect = get_client_rect()
    if not client_rect:
        logger.warning("build_display_context: GetClientRect failed for hwnd=%s", hwnd)
        return None
    # client_rect = (0, 0, w, h)
    client_phys_w = client_rect[2] - client_rect[0]
    client_phys_h = client_rect[3] - client_rect[1]
    if client_phys_w <= 0 or client_phys_h <= 0:
        # Fallback: DwmGetWindowAttribute(EXTENDED_FRAME_BOUNDS) for Unity
        # windows where GetClientRect returns zero size even when the window
        # is visible and in the foreground. See N199 lesson for details.
        logger.warning(
            "build_display_context: GetClientRect returned zero %s for hwnd=%s; "
            "trying DwmGetWindowAttribute(EXTENDED_FRAME_BOUNDS) fallback",
            client_rect, hwnd,
        )
        try:
            rect = ctypes.wintypes.RECT()
            ret = _dwmapi.DwmGetWindowAttribute(
                ctypes.wintypes.HWND(hwnd),
                9,  # DWMWA_EXTENDED_FRAME_BOUNDS
                ctypes.byref(rect),
                ctypes.sizeof(ctypes.wintypes.RECT),
            )
            if ret == 0 and rect.right > 0 and rect.bottom > 0:
                client_phys_w = rect.right - rect.left
                client_phys_h = rect.bottom - rect.top
                logger.info(
                    "build_display_context: DwmGetWindowAttribute fallback "
                    "succeeded for hwnd=%s: %dx%d",
                    hwnd, client_phys_w, client_phys_h,
                )
            else:
                logger.warning(
                    "build_display_context: DwmGetWindowAttribute fallback "
                    "also failed for hwnd=%s (ret=%d, rect=%s)",
                    hwnd, ret, (rect.left, rect.top, rect.right, rect.bottom),
                )
                return None
        except Exception as exc:
            logger.warning(
                "build_display_context: DwmGetWindowAttribute fallback "
                "exception for hwnd=%s: %s",
                hwnd, exc,
            )
            return None

    # 2. DPI scale (1.0 = 100%, 1.25 = 125%, etc.)
    # Importing platforms.windows.dpi triggers apply_dpi_awareness() at module
    # load, so the process is guaranteed DPI-aware here.
    dpi_scale = get_dpi_scale_factor(hwnd)
    if dpi_scale <= 0:
        logger.warning("build_display_context: invalid dpi_scale=%s; defaulting to 1.0", dpi_scale)
        dpi_scale = 1.0

    # 3. Client logical size = physical / DPI (rounded)
    # For DPI-aware processes rendering at native resolution, this equals
    # physical when dpi_scale==1.0. For DPI-virtualized GDI apps, logical <
    # physical. For D3D/Vulkan games (BD2), logical == physical == swap chain
    # size, so the logical layer is mostly transparent.
    client_log_w = max(1, int(round(client_phys_w / dpi_scale)))
    client_log_h = max(1, int(round(client_phys_h / dpi_scale)))

    # 4. Screen physical resolution — use MonitorFromWindow + GetMonitorInfo
    # for per-monitor-correct resolution (handles multi-monitor setups where
    # the window is on a non-primary monitor). Falls back to GetSystemMetrics
    # (primary monitor) if the monitor query fails.
    screen_phys_w, screen_phys_h = _get_monitor_resolution(hwnd)

    # 5. Client area top-left in screen-physical coords
    # Reuse WindowManager.client_to_screen if available; otherwise call
    # ClientToScreen directly.
    client_origin: tuple[int, int] | None = None
    client_to_screen_fn = getattr(device._window_mgr, "client_to_screen", None)  # type: ignore[attr-defined]
    if client_to_screen_fn is not None:
        client_origin = client_to_screen_fn(0, 0)
    if client_origin is None:
        # Direct ctypes fallback
        pt = ctypes.wintypes.POINT(0, 0)
        client_origin = (pt.x, pt.y) if _user32.ClientToScreen(hwnd, ctypes.byref(pt)) else (0, 0)

    # 6. Fullscreen detection: client rect vs screen rect within tolerance.
    # When fullscreen, the client area covers the entire screen, so
    # client_screen_origin must be (0, 0) — override whatever ClientToScreen
    # returned (it may report non-zero if a taskbar or hidden chrome exists).
    from utils.coord_transformer import CoordinateTransformer  # avoid cycle
    tolerance = CoordinateTransformer.FULLSCREEN_ERROR_TOLERANCE
    is_fullscreen = (
        abs(client_phys_w - screen_phys_w) < tolerance
        and abs(client_phys_h - screen_phys_h) < tolerance
    )
    if is_fullscreen:
        client_origin = (0, 0)

    # 7. Build context
    ctx = RuntimeDisplayContext(
        original_base_width=original_base_res[0],
        original_base_height=original_base_res[1],
        hwnd=hwnd,
        is_fullscreen=is_fullscreen,
        dpi_scale=dpi_scale,
        client_logical_width=client_log_w,
        client_logical_height=client_log_h,
        client_physical_width=client_phys_w,
        client_physical_height=client_phys_h,
        screen_physical_width=screen_phys_w,
        screen_physical_height=screen_phys_h,
        client_screen_origin_x=client_origin[0],
        client_screen_origin_y=client_origin[1],
    )

    # 8. Sanity check: warn if window_rect vs client_rect diverge significantly
    # (indicates a titled window where screenshot pixels include the title bar
    #  but click coords are client-relative — needs PW_CLIENTONLY capture).
    try:
        win_rect = device.get_window_rect()  # (l, t, r, b)
        if win_rect:
            win_w = win_rect[2] - win_rect[0]
            win_h = win_rect[3] - win_rect[1]
            # If window rect is meaningfully larger than client rect, the
            # screenshot (which uses window rect) won't line up with click
            # coords (which use client rect). Warn loudly.
            if (win_w - client_phys_w) > 5 or (win_h - client_phys_h) > 5:
                logger.warning(
                    "build_display_context: window rect (%dx%d) larger than client rect (%dx%d) — "
                    "title bar/borders detected. Screenshot pixels include chrome but click coords "
                    "are client-relative; coordinate scaling may be off by the chrome offset. "
                    "Consider PW_CLIENTONLY capture for this window.",
                    win_w, win_h, client_phys_w, client_phys_h,
                )
    except Exception:
        pass

    logger.info(
        "build_display_context: %s | hwnd=%s | fullscreen=%s",
        ctx, hwnd, is_fullscreen,
    )
    return ctx


def build_transformer(
    device,
    original_base_res: tuple[int, int] = (1920, 1080),
) -> CoordinateTransformer | None:
    """Build a CoordinateTransformer from a WindowsDevice.

    Convenience wrapper: builds the display context, then wraps it in a
    CoordinateTransformer. Returns None if the context can't be built
    (non-Windows device, no hwnd, etc.).

    Args:
        device: A WindowsDevice instance.
        original_base_res: Reference resolution (width, height).

    Returns:
        CoordinateTransformer instance, or None.
    """
    ctx = build_display_context(device, original_base_res)
    if ctx is None:
        return None
    return CoordinateTransformer(ctx, logger=logger)
