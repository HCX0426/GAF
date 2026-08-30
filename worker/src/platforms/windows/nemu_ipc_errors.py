"""P1-2 NemuIpc error code mapping — Windows RPC error codes.

MuMu12's external_renderer_ipc.dll returns Windows RPC error codes when
the underlying IPC call fails. Mapping these to human-readable messages
helps diagnose emulator-side problems (wrong install path, emulator not
running, crashed mid-call, etc.).

Reference: Alas `nemu_ipc.py` error code constants.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# Windows RPC error codes returned by NemuIpc functions.
# These are standard Windows RPC_S_* codes that surface when the
# emulator-side IPC endpoint is unreachable or misbehaving.
NEMU_IPC_ERROR_CODES: dict[int, str] = {
    # 1722 — RPC_S_SERVER_UNAVAILABLE
    # The RPC server is unavailable. Most common: emulator process is
    # not running, or the nemu_folder path is wrong (DLL loaded but
    # cannot find the shared-memory endpoint).
    1722: "RPC server unavailable (emulator not running or wrong nemu_folder)",

    # 1726 — RPC_S_CALL_FAILED
    # The remote procedure call failed. Emulator process crashed mid-call
    # or its IPC thread is wedged. Recovery: disconnect + reconnect.
    1726: "RPC call failed (emulator crashed or IPC thread wedged)",

    # 1745 — RPC_S_NOT_REGISTERED
    # The RPC server is not registered. NemuIpc service endpoint not yet
    # advertised — emulator is still booting. Retry after a short delay.
    1745: "RPC server not registered (emulator still booting, retry)",

    # 1783 — RPC_S_INVALID_BINDING
    # The RPC binding handle is invalid. connect_id is stale (emulator
    # restarted) or never was valid. Recovery: full disconnect + reconnect.
    1783: "RPC invalid binding handle (stale connect_id, reconnect required)",

    # 1702 — RPC_S_INVALID_RPC_PROTSEQ (less common, wrong protocol)
    1702: "RPC invalid protocol sequence",

    # 1703 — RPC_S_INVALID_ENDPOINT_FORMAT
    1703: "RPC invalid endpoint format",

    # 1717 — RPC_S_NO_MORE_BINDINGS
    1717: "RPC no more bindings (emulator connection limit reached)",

    # 1721 — RPC_S_OUT_OF_RESOURCES
    1721: "RPC out of resources (emulator shared memory exhausted)",

    # 1750 — RPC_S_INVALID_AUTH_IDENTITY
    1750: "RPC invalid auth identity",
}


def format_nemu_error(ret_code: int, context: str = "") -> str:
    """Format a NemuIpc return code as a human-readable error message.

    Args:
        ret_code: Integer return code from nemu_connect /
            nemu_capture_display / nemu_disconnect.
        context: Optional context string (e.g. "nemu_connect",
            "nemu_capture_display") for richer diagnostics.

    Returns:
        Human-readable error message. Returns "success" for code 0.
    """
    if ret_code == 0:
        return "success"

    base_msg = NEMU_IPC_ERROR_CODES.get(
        ret_code,
        f"unknown NemuIpc error code {ret_code}",
    )
    if context:
        return f"{context}: {base_msg} (code={ret_code})"
    return f"{base_msg} (code={ret_code})"


def is_recoverable_error(ret_code: int) -> bool:
    """Check if a NemuIpc error is recoverable via disconnect + reconnect.

    Args:
        ret_code: Integer return code.

    Returns:
        True if a disconnect/reconnect cycle is recommended; False if
        the error indicates a permanent misconfiguration (wrong path,
        emulator not installed) or success.
    """
    # 0 = success; not an error, no recovery needed.
    if ret_code == 0:
        return False
    # 1745 (RPC_S_NOT_REGISTERED) — emulator still booting; retry
    # without full reconnect (just wait and retry).
    # 1726 (RPC_S_CALL_FAILED) — emulator crashed mid-call; reconnect.
    # 1783 (RPC_S_INVALID_BINDING) — stale handle; reconnect.
    # 1722 (RPC_S_SERVER_UNAVAILABLE) — emulator not running; reconnect
    # will also fail, but it's worth trying after a delay.
    return ret_code in (1722, 1726, 1745, 1783, 1717, 1721)


def is_emulator_booting(ret_code: int) -> bool:
    """Check if the error indicates the emulator is still booting.

    Args:
        ret_code: Integer return code.

    Returns:
        True if the emulator appears to be still starting up (retry
        after a delay is recommended).
    """
    return ret_code == 1745  # RPC_S_NOT_REGISTERED


def get_error_recovery_hint(ret_code: int) -> str | None:
    """Get a user-facing recovery hint for the given error code.

    Args:
        ret_code: Integer return code.

    Returns:
        Optional hint string with recommended next step.
    """
    hints = {
        1722: "Check that the emulator is running and the nemu_folder path is correct",
        1726: "Emulator may have crashed — restart MuMu12 and retry",
        1745: "Emulator is still booting — wait 5-10s and retry",
        1783: "Connection handle is stale — disconnecting and reconnecting",
        1717: "Too many active emulator connections — close unused instances",
        1721: "Emulator shared memory exhausted — restart MuMu12",
    }
    return hints.get(ret_code)
