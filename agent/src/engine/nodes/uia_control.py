"""UIAutomation semantic nodes (spec-2026-08-26 P2, TD-398).

Semantic-layer operations that act through the Windows accessibility tree
instead of simulated key/mouse events — no foreground/visibility required.
Use for browser/desktop automation where SendInput injection is unreliable.

Node types:
- uia_set_value      : set an edit control's value by Name or AutomationId
- uia_invoke         : invoke a button by Name or AutomationId
- uia_select         : select an option in a ComboBox by option text
- uia_scroll         : scroll a ScrollPattern control (up/down/left/right)
- uia_get_state      : read a control's value/name/rect/visibility into a var
- uia_get_window_title: read the foreground window title
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


def _device_hwnd(device: Any):
    """Best-effort resolve of the window handle bound to a Windows device."""
    if device is None:
        return None
    mgr = getattr(device, "_window_mgr", None)
    if mgr is not None:
        hwnd = getattr(mgr, "hwnd", None)
        if hwnd:
            return int(hwnd)
    hwnd = getattr(device, "_hwnd", None)
    return int(hwnd) if hwnd else None


def _uia_available() -> bool:
    try:
        import uiautomation  # noqa: F401
        return True
    except ImportError:
        return False


def _require_window(context: PipelineContext):
    """Return (hwnd, None, None, None) on success else (None, None, msg, code)."""
    device = getattr(context, "device", None)
    if device is None:
        return None, None, "uia: no device in context", NodeErrorCode.DEVICE_DISCONNECTED
    if not _uia_available():
        return None, None, "uia: uiautomation package not installed", NodeErrorCode.DEVICE_DISCONNECTED
    hwnd = _device_hwnd(device)
    if hwnd is None:
        return None, None, "uia: no window handle on device", NodeErrorCode.DEVICE_DISCONNECTED
    return hwnd, device, None, None


@register_node("uia_set_value")
@dataclass
class UiaSetValueNode(PipelineNode):
    """Set an edit control's value via UIAutomation (no focus needed).

    config parameters:
    - value: text to set (required)
    - control_name: control Name (e.g. "地址和搜索栏")
    - control_automation_id: control AutomationId
    - timeout: find timeout seconds (default 3)
    """

    node_type: str = "uia_set_value"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "control_name": self.config.get("control_name", ""),
            "control_automation_id": self.config.get("control_automation_id", ""),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()
        value = self.config.get("value", "")
        if not value:
            return fail_result(
                error_msg="uia_set_value: 'value' config required",
                elapsed_time=time.monotonic() - start,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id, node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.PARAM_INVALID),
            )
        hwnd, _, err, code = _require_window(context)
        if err:
            return fail_result(
                error_msg=err, elapsed_time=time.monotonic() - start,
                error_code=code, node_id=self.id, node_type=self.node_type,
                data=self._build_fail_diagnostics(context, code),
            )
        from platforms.windows.uia import uia_session

        ok = uia_session.set_value(
            hwnd, value,
            name=self.config.get("control_name") or None,
            automation_id=self.config.get("control_automation_id") or None,
            timeout=float(self.config.get("timeout", 3.0)),
        )
        elapsed = time.monotonic() - start
        if not ok:
            return fail_result(
                error_msg=(
                    f"uia_set_value: control not found/settable "
                    f"(name={self.config.get('control_name','')!r})"
                ),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id, node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.UNKNOWN),
            )
        context.set_variable(f"{self.id}_uia_value", {"value": value, "ok": True})
        return success_result(
            data={"value": value, "ok": True, "coord_system": getattr(context, "coord_system", "") or "legacy"},
            elapsed_time=elapsed,
        )


@register_node("uia_invoke")
@dataclass
class UiaInvokeNode(PipelineNode):
    """Invoke a button via UIAutomation.

    config parameters:
    - control_name: button Name
    - control_automation_id: button AutomationId
    - timeout: find timeout seconds (default 3)
    """

    node_type: str = "uia_invoke"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "control_name": self.config.get("control_name", ""),
            "control_automation_id": self.config.get("control_automation_id", ""),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()
        hwnd, _, err, code = _require_window(context)
        if err:
            return fail_result(
                error_msg=err, elapsed_time=time.monotonic() - start,
                error_code=code, node_id=self.id, node_type=self.node_type,
                data=self._build_fail_diagnostics(context, code),
            )
        from platforms.windows.uia import uia_session

        ok = uia_session.invoke(
            hwnd,
            name=self.config.get("control_name") or None,
            automation_id=self.config.get("control_automation_id") or None,
            timeout=float(self.config.get("timeout", 3.0)),
        )
        elapsed = time.monotonic() - start
        if not ok:
            return fail_result(
                error_msg="uia_invoke: control not found/invokable",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id, node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.UNKNOWN),
            )
        return success_result(
            data={"ok": True, "coord_system": getattr(context, "coord_system", "") or "legacy"},
            elapsed_time=elapsed,
        )


@register_node("uia_select")
@dataclass
class UiaSelectNode(PipelineNode):
    """Select an option in a ComboBox via UIAutomation.

    config parameters:
    - option: option text to select (required)
    - control_name / control_automation_id: locate the combo control
    - exact: exact-match option name (default true; false = substring)
    - timeout: find timeout seconds (default 3)
    """

    node_type: str = "uia_select"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "option": self.config.get("option", ""),
            "control_name": self.config.get("control_name", ""),
            "control_automation_id": self.config.get("control_automation_id", ""),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()
        option = self.config.get("option", "")
        if not option:
            return fail_result(
                error_msg="uia_select: 'option' config required",
                elapsed_time=time.monotonic() - start,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id, node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.PARAM_INVALID),
            )
        hwnd, _, err, code = _require_window(context)
        if err:
            return fail_result(
                error_msg=err, elapsed_time=time.monotonic() - start,
                error_code=code, node_id=self.id, node_type=self.node_type,
                data=self._build_fail_diagnostics(context, code),
            )
        from platforms.windows.uia import uia_session

        ok = uia_session.select_option(
            hwnd, option,
            name=self.config.get("control_name") or None,
            automation_id=self.config.get("control_automation_id") or None,
            timeout=float(self.config.get("timeout", 3.0)),
            exact=bool(self.config.get("exact", True)),
        )
        elapsed = time.monotonic() - start
        if not ok:
            return fail_result(
                error_msg=f"uia_select: option {option!r} not selectable "
                          f"(combo={self.config.get('control_name','')!r})",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id, node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.UNKNOWN),
            )
        context.set_variable(f"{self.id}_uia_select", {"option": option, "ok": True})
        return success_result(
            data={"option": option, "ok": True, "coord_system": getattr(context, "coord_system", "") or "legacy"},
            elapsed_time=elapsed,
        )


@register_node("uia_scroll")
@dataclass
class UiaScrollNode(PipelineNode):
    """Scroll a ScrollPattern-capable control via UIAutomation.

    config parameters:
    - direction: up | down | left | right (required)
    - amount: small | large (default small)
    - control_name / control_automation_id: locate the scrollable control
    - control_type: UIA control type for the scroll region (default "document")
    - timeout: find timeout seconds (default 3)
    """

    node_type: str = "uia_scroll"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "direction": self.config.get("direction", ""),
            "control_name": self.config.get("control_name", ""),
            "control_automation_id": self.config.get("control_automation_id", ""),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()
        direction = str(self.config.get("direction", "")).lower()
        if direction not in ("up", "down", "left", "right"):
            return fail_result(
                error_msg="uia_scroll: 'direction' must be up/down/left/right",
                elapsed_time=time.monotonic() - start,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id, node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.PARAM_INVALID),
            )
        hwnd, _, err, code = _require_window(context)
        if err:
            return fail_result(
                error_msg=err, elapsed_time=time.monotonic() - start,
                error_code=code, node_id=self.id, node_type=self.node_type,
                data=self._build_fail_diagnostics(context, code),
            )
        from platforms.windows.uia import uia_session

        ok = uia_session.scroll(
            hwnd, direction,
            amount=str(self.config.get("amount", "small")),
            name=self.config.get("control_name") or None,
            automation_id=self.config.get("control_automation_id") or None,
            control_type=self.config.get("control_type", "document"),
            timeout=float(self.config.get("timeout", 3.0)),
        )
        elapsed = time.monotonic() - start
        if not ok:
            return fail_result(
                error_msg=f"uia_scroll: control not scrollable ({direction})",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id, node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.UNKNOWN),
            )
        return success_result(
            data={"direction": direction, "ok": True, "coord_system": getattr(context, "coord_system", "") or "legacy"},
            elapsed_time=elapsed,
        )


@register_node("uia_get_state")
@dataclass
class UiaGetStateNode(PipelineNode):
    """Read a control's state into a context variable for verification.

    config parameters:
    - control_name / control_automation_id: locate control
    - var: context variable name to write result into (default
      f"{node_id}_uia_state")
    - control_type: "edit" | "button" | "document" (default "edit")
    - timeout: find timeout seconds (default 3)
    """

    node_type: str = "uia_get_state"
    _default_var: str = ""

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "control_name": self.config.get("control_name", ""),
            "control_automation_id": self.config.get("control_automation_id", ""),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()
        hwnd, _, err, code = _require_window(context)
        if err:
            return fail_result(
                error_msg=err, elapsed_time=time.monotonic() - start,
                error_code=code, node_id=self.id, node_type=self.node_type,
                data=self._build_fail_diagnostics(context, code),
            )
        from platforms.windows.uia import uia_session

        state = uia_session.get_state(
            hwnd,
            name=self.config.get("control_name") or None,
            automation_id=self.config.get("control_automation_id") or None,
            control_type=self.config.get("control_type", "edit"),
            timeout=float(self.config.get("timeout", 3.0)),
        )
        var = self.config.get("var") or f"{self.id}_uia_state"
        context.set_variable(var, state)
        elapsed = time.monotonic() - start
        return success_result(
            data={"var": var, "state": state, "coord_system": getattr(context, "coord_system", "") or "legacy"},
            elapsed_time=elapsed,
        )


@register_node("uia_get_window_title")
@dataclass
class UiaGetWindowTitleNode(PipelineNode):
    """Read the foreground window title (verification without screenshots)."""

    node_type: str = "uia_get_window_title"

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()
        from platforms.windows.uia import uia_session

        title = uia_session.get_active_window_title()
        var = self.config.get("var") or f"{self.id}_window_title"
        context.set_variable(var, {"title": title})
        return success_result(
            data={"var": var, "title": title},
            elapsed_time=time.monotonic() - start,
        )
