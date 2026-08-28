"""MuMu12 NemuIpc DLL wrapper — external_renderer_ipc.dll loading and bindings.

Loads MuMu12's external_renderer_ipc.dll and exposes its RPC functions
(nemu_connect / nemu_disconnect / nemu_capture_display /
nemu_input_event_touch_down / nemu_input_event_touch_up) as Python methods.

The wrapper is a drop-in replacement for the raw ctypes.CDLL instance:
each method delegates to the underlying CDLL function with the same
signature, so callers can pass a NemuIpcLib instance anywhere that
previously expected a CDLL (e.g. to nemu_keepalive.make_ping_fn).

Windows-only: requires MuMu12 >= 3.8.13 with external_renderer_ipc.dll.
Non-Windows callers must guard the import (try/except NotImplementedError).
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)


# MuMu12 NemuIpc DLL relative paths (under nemu_folder).
# The DLL ships with MuMu12 >= 3.8.13 and lives under shell/sdk/ (older
# installs) or nx_device/12.0/shell/sdk/ (newer installs).
NEMU_IPC_DLL_PATHS = (
    "shell/sdk/external_renderer_ipc.dll",
    "nx_device/12.0/shell/sdk/external_renderer_ipc.dll",
)


class NemuIpcLib:
    """Wrapper for MuMu12 external_renderer_ipc.dll.

    Loads the DLL on construction and exposes the five RPC functions
    used by GAF as bound methods. Methods match the CDLL function
    signatures verbatim (same arg order, same return type) so this
    class is interchangeable with a raw ctypes.CDLL instance from the
    caller's perspective.

    Usage:
        lib = NemuIpcLib.from_nemu_folder(nemu_folder)
        connect_id = lib.nemu_connect(folder.encode("utf-8"), instance_id)
        ret = lib.nemu_capture_display(connect_id, 0, length, w_ptr, h_ptr, px_ptr)
        lib.nemu_disconnect(connect_id)
    """

    def __init__(self, dll_path: str):
        """Load external_renderer_ipc.dll from the given absolute path.

        Args:
            dll_path: Absolute path to external_renderer_ipc.dll.

        Raises:
            OSError: If the DLL cannot be loaded (missing dependencies,
                wrong architecture, etc.).
        """
        self._dll = ctypes.CDLL(dll_path)
        self._dll_path = dll_path

    @classmethod
    def from_nemu_folder(cls, nemu_folder: str) -> NemuIpcLib:
        """Locate and load external_renderer_ipc.dll under nemu_folder.

        Tries each known relative DLL path under the supplied MuMu12
        install directory. Returns the first one that loads successfully.

        Args:
            nemu_folder: MuMu12 installation directory.

        Returns:
            Loaded NemuIpcLib instance.

        Raises:
            NotImplementedError: On non-Windows platforms, when
                nemu_folder is empty, or when no DLL path exists.
        """
        if not sys.platform.startswith("win"):
            raise NotImplementedError("NemuIpc only supported on Windows")

        if not nemu_folder:
            raise NotImplementedError(
                "NemuIpc requires nemu_folder to be set (MuMu12 install path)"
            )

        for rel_path in NEMU_IPC_DLL_PATHS:
            dll_path = os.path.abspath(os.path.join(nemu_folder, rel_path))
            if not os.path.exists(dll_path):
                continue
            try:
                instance = cls(dll_path)
                logger.info("NemuIpc DLL loaded: %s", dll_path)
                return instance
            except OSError as exc:
                logger.warning(
                    "NemuIpc DLL load failed for %s: %s", dll_path, exc,
                )
                continue

        raise NotImplementedError(
            f"NemuIpc requires MuMu12 >= 3.8.13, none of the DLL paths exist: "
            f"{[os.path.join(nemu_folder, p) for p in NEMU_IPC_DLL_PATHS]}"
        )

    @property
    def dll_path(self) -> str:
        """Absolute path to the loaded DLL."""
        return self._dll_path

    @property
    def raw(self) -> ctypes.CDLL:
        """Underlying CDLL instance (for advanced use)."""
        return self._dll

    def nemu_connect(self, nemu_folder_bytes: bytes, instance_id: int) -> int:
        """Connect to a MuMu12 emulator instance.

        Args:
            nemu_folder_bytes: MuMu12 install path encoded as UTF-8 bytes.
            instance_id: Emulator instance ID (0-based).

        Returns:
            Connection ID (>0) on success, 0 or negative RPC error code
            on failure.
        """
        return self._dll.nemu_connect(nemu_folder_bytes, instance_id)

    def nemu_disconnect(self, connect_id: int) -> int:
        """Disconnect from a MuMu12 emulator instance.

        Args:
            connect_id: Connection ID returned by nemu_connect.

        Returns:
            0 on success, non-zero RPC error code on failure.
        """
        return self._dll.nemu_disconnect(connect_id)

    def nemu_capture_display(
        self,
        connect_id: int,
        display_id: int,
        length: int,
        width_ptr: Any,
        height_ptr: Any,
        pixels_ptr: Any,
    ) -> int:
        """Capture the emulator's display buffer via shared memory.

        When length=0 and pixels_ptr is a null pointer, this performs
        a resolution query only (no pixel data is copied). Otherwise
        the BGRA pixel data is written into the buffer pointed to by
        pixels_ptr.

        Args:
            connect_id: Connection ID returned by nemu_connect.
            display_id: Display index (usually 0).
            length: Pixel buffer size in bytes (width*height*4), or 0
                for a resolution-only query.
            width_ptr: ctypes pointer to c_int receiving the width.
            height_ptr: ctypes pointer to c_int receiving the height.
            pixels_ptr: ctypes pointer to the pixel buffer, or a null
                pointer for resolution-only queries.

        Returns:
            0 on success, non-zero RPC error code on failure.
        """
        return self._dll.nemu_capture_display(
            connect_id, display_id, length,
            width_ptr, height_ptr, pixels_ptr,
        )

    def nemu_input_event_touch_down(
        self,
        connect_id: int,
        display_id: int,
        x: int,
        y: int,
    ) -> int:
        """Send a touch-down event at (x, y).

        Args:
            connect_id: Connection ID returned by nemu_connect.
            display_id: Display index (usually 0).
            x: X coordinate in emulator resolution.
            y: Y coordinate in emulator resolution.

        Returns:
            0 on success, non-zero RPC error code on failure.
        """
        return self._dll.nemu_input_event_touch_down(
            connect_id, display_id, x, y,
        )

    def nemu_input_event_touch_up(
        self,
        connect_id: int,
        display_id: int,
    ) -> int:
        """Send a touch-up event (release).

        Args:
            connect_id: Connection ID returned by nemu_connect.
            display_id: Display index (usually 0).

        Returns:
            0 on success, non-zero RPC error code on failure.
        """
        return self._dll.nemu_input_event_touch_up(connect_id, display_id)

    # -- Pointer factory helpers (B012: keep ctypes inside platforms/windows/) --

    @staticmethod
    def make_int_ptr(value: int = 0) -> Any:
        """Create a ctypes c_int pointer initialized to value.

        Encapsulates ctypes.pointer(ctypes.c_int(value)) so callers in
        non-platform modules (e.g. devices/adb/device.py) do not need
        to import ctypes directly (GAF backend-conventions §11).

        Args:
            value: Initial integer value (default 0).

        Returns:
            Opaque ctypes pointer object (pass to nemu_capture_display).
        """
        return ctypes.pointer(ctypes.c_int(value))

    @staticmethod
    def make_null_int_ptr() -> Any:
        """Create a null ctypes c_int pointer (for resolution-only queries).

        Encapsulates ctypes.POINTER(ctypes.c_int)() so callers do not
        need to import ctypes directly.

        Returns:
            Null ctypes pointer object (pass to nemu_capture_display as
            pixels_ptr for resolution queries).
        """
        return ctypes.POINTER(ctypes.c_int)()

    @staticmethod
    def make_ubyte_ptr(length: int) -> Any:
        """Create a ctypes c_ubyte buffer pointer of the given length.

        Encapsulates ctypes.pointer((ctypes.c_ubyte * length)()) so
        callers do not need to import ctypes directly.

        Args:
            length: Buffer size in bytes (e.g. width * height * 4 for BGRA).

        Returns:
            Opaque ctypes pointer object (pass to nemu_capture_display as
            pixels_ptr; use deref_ubyte_contents() to read the buffer).
        """
        return ctypes.pointer((ctypes.c_ubyte * length)())

    @staticmethod
    def deref_int_ptr(ptr: Any) -> int:
        """Read the integer value from a ctypes c_int pointer.

        Args:
            ptr: ctypes c_int pointer (from make_int_ptr).

        Returns:
            The integer value stored at the pointer.
        """
        return ptr.contents.value

    @staticmethod
    def deref_ubyte_contents(ptr: Any) -> Any:
        """Get the underlying c_ubyte array from a ctypes pointer.

        The returned object can be passed to np.ctypeslib.as_array() for
        zero-copy conversion to a numpy array.

        Args:
            ptr: ctypes c_ubyte pointer (from make_ubyte_ptr).

        Returns:
            The ctypes c_ubyte array (ptr.contents).
        """
        return ptr.contents
