"""start_app / stop_app 节点：应用生命周期控制。

C22 fix: frontend `PipelineNodeType` declares 'start_app' and 'stop_app'
but the agent registry had no matching `@register_node` entries, so
pipelines using these node types raised ValueError at parse time.

This module implements both nodes via ADB (Android/Emulator) or
subprocess (Windows). They are intentionally minimal — they wrap the
platform's app lifecycle command and return its exit status.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


def _run_adb(device, args: list[str], timeout: float = 10.0):
    """Run an ADB command targeting the given device.

    Returns (returncode, stdout, stderr). Raises subprocess.TimeoutExpired
    or other subprocess errors on failure.
    """
    serial = getattr(device, "adb_serial", None) or ""
    cmd = ["adb"] + (["-s", serial] if serial else []) + args
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


@register_node("start_app")
@dataclass
class StartAppNode(PipelineNode):
    """Start an application on the target device.

    config parameters:
    - package: Android package name (required for Android/Emulator)
    - activity: Android Activity name (optional; falls back to `monkey`
      launcher intent when omitted)
    - command: Windows launch command, e.g. ["notepad.exe", "file.txt"]
      (required for Windows device)
    - timeout: command timeout seconds (default 10)
    """

    node_type: str = "start_app"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "device_type": str(getattr(getattr(context, "device", None), "device_type", "") or "").lower(),
            "package": self.config.get("package", ""),
            "command": self.config.get("command", ""),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()
        device = getattr(context, "device", None)
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="start_app: no device in context",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_DISCONNECTED,
                ),
            )

        timeout = float(self.config.get("timeout", 10.0))
        device_type = str(getattr(device, "device_type", "")).lower()

        try:
            if device_type in ("emulator", "android"):
                package = self.config.get("package", "")
                if not package:
                    elapsed = time.monotonic() - start
                    return fail_result(
                        error_msg="start_app: 'package' config required for Android device",
                        elapsed_time=elapsed,
                        error_code=NodeErrorCode.PARAM_INVALID,
                        node_id=self.id,
                        node_type=self.node_type,
                        data=self._build_fail_diagnostics(
                            context, NodeErrorCode.PARAM_INVALID,
                            device_type=device_type, package="",
                        ),
                    )
                activity = self.config.get("activity", "")
                if activity:
                    args = ["shell", "am", "start", "-n", f"{package}/{activity}"]
                else:
                    args = [
                        "shell", "monkey",
                        "-p", package,
                        "-c", "android.intent.category.LAUNCHER",
                        "1",
                    ]
                rc, out, err = _run_adb(device, args, timeout=timeout)
            else:
                command = self.config.get("command", "")
                if not command:
                    elapsed = time.monotonic() - start
                    return fail_result(
                        error_msg="start_app: 'command' config required for Windows device",
                        elapsed_time=elapsed,
                        error_code=NodeErrorCode.PARAM_INVALID,
                        node_id=self.id,
                        node_type=self.node_type,
                        data=self._build_fail_diagnostics(
                            context, NodeErrorCode.PARAM_INVALID,
                            device_type=device_type, command="",
                        ),
                    )
                cmd_list = command.split() if isinstance(command, str) else list(command)
                proc = subprocess.Popen(
                    cmd_list,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.info("start_app: spawned PID %d (%s)", proc.pid, cmd_list[0])
                rc, out, err = 0, "", ""
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"start_app: command timed out after {timeout}s",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.TIMEOUT,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.TIMEOUT,
                    device_type=device_type, timeout=timeout,
                ),
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"start_app: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN,
                    device_type=device_type, exception=type(exc).__name__,
                ),
            )

        elapsed = time.monotonic() - start
        if rc != 0:
            return fail_result(
                error_msg=f"start_app: command failed (rc={rc}): {err.strip() or out.strip()}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_ERROR,
                    device_type=device_type, returncode=rc,
                ),
            )
        return success_result(
            data={
                "device_type": device_type,
                "returncode": rc,
                # Task 4.51 (P1-24~31, 2026-07-28): success path 补 coord_system 与识别类节点对齐
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            },
            elapsed_time=elapsed,
        )


@register_node("stop_app")
@dataclass
class StopAppNode(PipelineNode):
    """Stop an application on the target device.

    config parameters:
    - package: Android package name (required for Android/Emulator)
    - process: Windows process image name, e.g. "notepad.exe" (alternative
      to `command` for Windows)
    - command: explicit Windows command (overrides `process`)
    - force: force-kill the app (default True)
    - timeout: command timeout seconds (default 10)
    """

    node_type: str = "stop_app"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "device_type": str(getattr(getattr(context, "device", None), "device_type", "") or "").lower(),
            "package": self.config.get("package", ""),
            "process": self.config.get("process", ""),
            "force": bool(self.config.get("force", True)),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()
        device = getattr(context, "device", None)
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="stop_app: no device in context",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_DISCONNECTED,
                ),
            )

        timeout = float(self.config.get("timeout", 10.0))
        force = bool(self.config.get("force", True))
        device_type = str(getattr(device, "device_type", "")).lower()

        try:
            if device_type in ("emulator", "android"):
                package = self.config.get("package", "")
                if not package:
                    elapsed = time.monotonic() - start
                    return fail_result(
                        error_msg="stop_app: 'package' config required for Android device",
                        elapsed_time=elapsed,
                        error_code=NodeErrorCode.PARAM_INVALID,
                        node_id=self.id,
                        node_type=self.node_type,
                        data=self._build_fail_diagnostics(
                            context, NodeErrorCode.PARAM_INVALID,
                            device_type=device_type, package="",
                        ),
                    )
                args = (
                    ["shell", "am", "force-stop", package]
                    if force
                    else ["shell", "am", "kill", package]
                )
                rc, out, err = _run_adb(device, args, timeout=timeout)
            else:
                command = self.config.get("command", "")
                if command:
                    cmd_list = command.split() if isinstance(command, str) else list(command)
                else:
                    proc_name = self.config.get("process", "")
                    if not proc_name:
                        elapsed = time.monotonic() - start
                        return fail_result(
                            error_msg="stop_app: 'command' or 'process' config required for Windows device",
                            elapsed_time=elapsed,
                            error_code=NodeErrorCode.PARAM_INVALID,
                            node_id=self.id,
                            node_type=self.node_type,
                            data=self._build_fail_diagnostics(
                                context, NodeErrorCode.PARAM_INVALID,
                                device_type=device_type, process="",
                            ),
                        )
                    cmd_list = ["taskkill", "/IM", proc_name] + (["/F"] if force else [])
                proc = subprocess.run(
                    cmd_list,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                rc, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"stop_app: command timed out after {timeout}s",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.TIMEOUT,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.TIMEOUT,
                    device_type=device_type, timeout=timeout,
                ),
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"stop_app: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN,
                    device_type=device_type, exception=type(exc).__name__,
                ),
            )

        elapsed = time.monotonic() - start
        if rc != 0:
            return fail_result(
                error_msg=f"stop_app: command failed (rc={rc}): {err.strip() or out.strip()}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_ERROR,
                    device_type=device_type, returncode=rc,
                ),
            )
        return success_result(
            data={
                "device_type": device_type,
                "returncode": rc,
                "force": force,
                # Task 4.51 (P1-24~31, 2026-07-28): success path 补 coord_system 与识别类节点对齐
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            },
            elapsed_time=elapsed,
        )
