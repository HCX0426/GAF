"""UIAutomation session helpers (spec-2026-08-26 P2, TD-398).

Semantic-layer operations that inject through the accessibility tree
instead of simulated key/mouse events: locate a control by Name or
automation_id under a root window, then SetValue / Invoke / read state.

Unlike SendInput/PostMessage these do NOT require the target window to be
foreground or visible — that is the whole point for browser/desktop use
(Chrome omnibox text entry that keyboard injection kept corrupting).

Backed by the `uiautomation` package (ctypes COM wrapper, no compilation).
"""

import contextlib
import logging
import time

logger = logging.getLogger(__name__)

_CONTROL_TYPES = {
    "edit": "EditControl",
    "button": "ButtonControl",
    "document": "DocumentControl",
    "combo": "ComboBoxControl",
}


def _uia():
    import uiautomation as auto
    return auto


def _resolve_root(hwnd: int):
    """Resolve UIA root element for a window handle."""
    from uiautomation import ControlFromHandle
    return ControlFromHandle(hwnd)


def find_control(
    hwnd: int,
    control_type: str = "edit",
    name: str | None = None,
    automation_id: str | None = None,
    timeout: float = 3.0,
):
    """Find a UIA control under the given window with retry (controls may
    load late). Returns the control element or None."""
    if not hwnd:
        return None
    auto = _uia()
    root = _resolve_root(hwnd)
    if root is None:
        return None

    ctype = _CONTROL_TYPES.get(control_type.lower()) or control_type
    ctrl_cls = getattr(auto, ctype, None)
    search = {}
    if name:
        search["Name"] = name
    if automation_id:
        search["AutomationId"] = automation_id

    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while True:
        try:
            if ctrl_cls is not None:
                ctrl = ctrl_cls(searchDepth=0xFFFFFFFF, f=(root,), **search)
            else:
                ctrl = root.FindControl(
                    getattr(auto, "ControlType", None) and auto.ClassNameControl,  # pragma: no cover
                    **search,
                )
            if ctrl and ctrl.Exists(0.1):
                return ctrl
        except Exception as exc:  # noqa: BLE001 — COM/timing errors are retried
            last_err = exc
        if time.monotonic() >= deadline:
            break
        time.sleep(0.2)

    logger.debug("uia find_control miss: hwnd=%s type=%s name=%s aid=%s err=%s",
                 hwnd, control_type, name, automation_id, last_err)
    return None


def set_value(
    hwnd: int,
    value: str,
    name: str | None = None,
    automation_id: str | None = None,
    timeout: float = 3.0,
) -> bool:
    """Set a control's value via the ValuePattern (no focus needed)."""
    ctrl = find_control(hwnd, "edit", name=name, automation_id=automation_id, timeout=timeout)
    if ctrl is None:
        logger.warning("uia set_value: control not found (hwnd=%s name=%s aid=%s)",
                       hwnd, name, automation_id)
        return False
    try:
        vp = ctrl.GetValuePattern()
        vp.SetValue(value)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("uia set_value failed: %s", exc)
        return False


def invoke(
    hwnd: int,
    name: str | None = None,
    automation_id: str | None = None,
    timeout: float = 3.0,
) -> bool:
    """Invoke a control (button) via the InvokePattern."""
    ctrl = find_control(hwnd, "button", name=name, automation_id=automation_id, timeout=timeout)
    if ctrl is None:
        logger.warning("uia invoke: control not found (hwnd=%s name=%s aid=%s)",
                       hwnd, name, automation_id)
        return False
    try:
        ctrl.GetInvokePattern().Invoke()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("uia invoke failed: %s", exc)
        return False


def get_state(
    hwnd: int,
    name: str | None = None,
    automation_id: str | None = None,
    control_type: str = "edit",
    timeout: float = 3.0,
) -> dict:
    """Read a control's value/name/rect/visibility for verification."""
    ctrl = find_control(hwnd, control_type, name=name, automation_id=automation_id, timeout=timeout)
    if ctrl is None:
        return {"found": False}
    try:
        rect = ctrl.BoundingRectangle
        state = {
            "found": True,
            "name": ctrl.Name,
            "value": None,
            "control_type": str(ctrl.ControlTypeName),
            "offscreen": bool(ctrl.IsOffscreen),
            "rect": [rect.left, rect.top, rect.right, rect.bottom] if rect else None,
        }
        with contextlib.suppress(Exception):  # noqa: BLE001 — non-value controls
            state["value"] = ctrl.GetValuePattern().Value
        return state
    except Exception as exc:  # noqa: BLE001
        logger.warning("uia get_state failed: %s", exc)
        return {"found": False, "error": str(exc)}


def get_active_window_title() -> str:
    """Return the foreground window title via UIA (desktop-level)."""
    try:
        auto = _uia()
        return auto.GetForegroundControl().Name or ""
    except Exception:  # noqa: BLE001
        return ""


def select_option(
    hwnd: int,
    option: str,
    name: str | None = None,
    automation_id: str | None = None,
    timeout: float = 3.0,
    exact: bool = True,
) -> bool:
    """Select an option in a ComboBox via ExpandCollapse + SelectionItem.

    Opens the combo, locates a ListItem whose Name matches ``option``
    (exact match by default, substring when ``exact=False``), selects it
    via SelectionItemPattern, then collapses the combo. Returns False when
    the combo or the option cannot be found/selected.
    """
    combo = find_control(hwnd, "combo", name=name, automation_id=automation_id, timeout=timeout)
    if combo is None:
        logger.warning("uia select: combo not found (hwnd=%s name=%s aid=%s)",
                       hwnd, name, automation_id)
        return False
    try:
        # Expand if the combo supports ExpandCollapsePattern.
        with contextlib.suppress(Exception):  # noqa: BLE001 — combo may be permanently expanded
            combo.GetExpandCollapsePattern().Expand()
        item = None
        for candidate in combo.GetChildren():
            for descendant in _walk_controls(candidate, max_depth=4):
                if not descendant.ControlTypeName:
                    continue
                if "ListItem" not in descendant.ControlTypeName:
                    continue
                item_name = descendant.Name or ""
                hit = item_name == option if exact else option.lower() in item_name.lower()
                if hit:
                    item = descendant
                    break
            if item is not None:
                break
        if item is None:
            logger.warning("uia select: option %r not found in combo (hwnd=%s)", option, hwnd)
            return False
        try:
            item.GetSelectionItemPattern().Select()
        except Exception:  # noqa: BLE001 — some combo items are Invoke-only
            item.Invoke()
        with contextlib.suppress(Exception):  # noqa: BLE001 — collapse is best-effort
            combo.GetExpandCollapsePattern().Collapse()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("uia select failed: %s", exc)
        return False


def scroll(
    hwnd: int,
    direction: str,
    amount: str = "small",
    name: str | None = None,
    automation_id: str | None = None,
    control_type: str = "document",
    timeout: float = 3.0,
) -> bool:
    """Scroll a ScrollPattern-capable control (no focus needed).

    ``direction``: up/down/left/right. ``amount``: small|large (only used
    for vertical/horizontal axis movement; the orthogonal axis stays put).

    Implementation notes (2026-08-26 e2e):
    - The uiautomation library's ``ScrollPattern`` wrapper class forwards
      ``Current*``/``Scroll`` onto the element and breaks for controls that
      are not pre-mixed with ScrollPatternControl; raw comtypes via
      ``GetPattern(UIA_ScrollPatternId)`` -> ``GetPatternIdInterface`` ->
      ``QueryInterface`` is the reliable path.
    - Many modern containers (Chrome page scroll regions, Win11 Explorer
      lists) do NOT expose IScrollProvider at all (`GetPattern` returns
      None); returns False with a clear message in that case.
    """
    ctrl = find_control(hwnd, control_type, name=name, automation_id=automation_id, timeout=timeout)
    if ctrl is None:
        logger.warning("uia scroll: control not found (hwnd=%s name=%s aid=%s)",
                       hwnd, name, automation_id)
        return False
    try:
        auto = _uia()
        # UIA_ScrollPatternId = 10006. GetCurrentPattern returns None when
        # the control does not support the pattern.
        raw = ctrl.GetPattern(10006)
        if raw is None:
            logger.warning(
                "uia scroll: control does not expose ScrollPattern "
                "(hwnd=%s name=%s) — modern browsers/Explorer regions often "
                "rely on ScrollItemPattern instead",
                hwnd, name,
            )
            return False
        iface = auto.GetPatternIdInterface(10006)
        sp = raw.QueryInterface(iface)
        scroll_amount = auto.ScrollAmount
        if amount == "large":
            v_amount = scroll_amount.LargeIncrement if direction in ("down",) else scroll_amount.LargeDecrement if direction in ("up",) else scroll_amount.NoAmount
            h_amount = scroll_amount.LargeIncrement if direction in ("right",) else scroll_amount.LargeDecrement if direction in ("left",) else scroll_amount.NoAmount
        else:
            v_amount = scroll_amount.SmallIncrement if direction in ("down",) else scroll_amount.SmallDecrement if direction in ("up",) else scroll_amount.NoAmount
            h_amount = scroll_amount.SmallIncrement if direction in ("right",) else scroll_amount.SmallDecrement if direction in ("left",) else scroll_amount.NoAmount
        sp.Scroll(h_amount, v_amount)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("uia scroll failed: %s", exc)
        return False


def _walk_controls(root, max_depth: int = 3):
    """Yield a control and its descendants (BFS, depth-limited)."""
    from collections import deque

    queue = deque([(root, 0)])
    while queue:
        ctrl, depth = queue.popleft()
        yield ctrl
        if depth >= max_depth:
            continue
        try:
            for child in ctrl.GetChildren():
                queue.append((child, depth + 1))
        except Exception as exc:  # noqa: BLE001 — tree walk is best-effort
            logger.debug("uia tree walk skipped a control (depth=%s): %s", depth, exc)
            continue
