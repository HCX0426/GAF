"""LDOpenGL capture — LDPlayer (Leidian) OpenGL screenshot via ldopengl64.dll

Reference: Alas's LDOpenGL implementation
Uses ldopengl64.dll to capture LDPlayer emulator's OpenGL rendered frame
directly from GPU memory, providing ultra-low-latency screenshots (~5ms).

API versions (P1-1 upgrade):
  v1 (legacy): ldopengl_capture(int hwnd, int width, int height, uint8_t* buffer)
    - Captures the OpenGL frame for the given LDPlayer window
    - Returns BGRA pixel data in buffer (width * height * 4 bytes)
    - Caller must know width/height in advance; mismatch → garbage frame

  v2 (LDPlayer 9 latest): ldopengl_capture_frame(int hwnd, uint64_t* frame_handle)
    + ldopengl_get_frame_info(uint64_t handle, int* w, int* h, int* ret)
    + ldopengl_copy_frame(uint64_t handle, uint8_t* buffer, int length)
    + ldopengl_release_frame(uint64_t handle)
    - DLL allocates frame buffer internally; emulator-side width/height
      are queried automatically (no need to parse `wm size`)
    - Frame handle must be released to avoid GPU memory leaks
    - Returns 0 on success, non-zero error code otherwise

  v3 (LDPlayer 14): CreateScreenShotInstance(int index, int pid) -> IScreenShotClass*
    + vtable[1]: void* cap(this)      — returns CPU-readable BGR frame (3 bytes/pixel)
    + vtable[2]: void release(this)   — frees object + frame buffer
    - Dimensions from `ldconsole list2` (matches emulator internal resolution)
    - Uses process ID (not HWND) to locate the LDPlayer renderer
    - Image is upside down (OpenGL origin at bottom-left) — flip vertically
    - Alas-compatible canonical path for LDPlayer 9/14
    - Latency: ~5ms capture + ~3ms memmove = ~8ms per screenshot

The capture() method auto-detects v3 (preferred for LDPlayer 14), then v2,
then falls back to v1 for older DLL versions.

Windows-only: requires ldopengl64.dll bundled with LDPlayer 9+.
"""
import ctypes
import ctypes.wintypes
import logging
import os
import platform
import subprocess
import threading
import time
from ctypes import POINTER, c_int, c_ubyte, c_uint32, c_uint64, c_void_p
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# LDPlayer window class names for FindWindow.
# LDPlayer 9 and earlier use "LDPlayerWnd"; LDPlayer 14 uses "LDPlayerMainFrame".
LDPLAYER_WINDOW_CLASSES = (
    "LDPlayerWnd",
    "LDPlayerMainFrame",
)
# Backward-compatible single class name (used by tests and older code).
LDPLAYER_WINDOW_CLASS = "LDPlayerWnd"

# v3 (IReadPixelsClass, deprecated) object layout offsets reverse-engineered
# from an earlier LDPlayer 14 ldopengl64.dll. Kept for reference only — the
# active v3 path now uses IScreenShotClass (Alas-compatible), which reads
# dimensions from `ldconsole list2` instead of object offsets. The previous
# IReadPixelsClass path produced black-white ghosting due to a 4-vs-3
# bytes-per-pixel mismatch.
LDOPENGL_V3_WIDTH_OFFSET = 0x6C
LDOPENGL_V3_HEIGHT_OFFSET = 0x70

# ldopengl64.dll relative paths within LDPlayer installation directory
LDOPENGL_DLL_PATHS = (
    "ldopengl64.dll",
    "shell/ldopengl64.dll",
    "vms/ldopengl64.dll",
)

# Timeout (seconds) for the ldopengl_capture DLL call. GPU-side frame
# reads normally complete in <10ms; 5s is the safety net for hung
# LDPlayer processes (P0-3 DLL timeout protection).
LDOPENGL_CAPTURE_TIMEOUT_SEC = 5.0

# Per-instance resolution cache for `ldconsole list2` lookups: index -> ((w, h), timestamp).
# ldconsole is a subprocess (~80ms); without caching, ld_opengl drops from ~38 to ~8 FPS.
_LDCONSOLE_RESOLUTION_CACHE: dict[int, tuple[tuple[int, int], float]] = {}
_LDCONSOLE_RESOLUTION_TTL = 60.0  # seconds; resolution rarely changes at runtime

# LDPlayer registry paths for installation directory discovery.
# Covers LDPlayer 4 / 5 / 9 / 12 / 14 / X plus a generic fallback.
LDPLAYER_REG_PATHS = (
    # LDPlayer 14 (latest as of 2026)
    r"SOFTWARE\leidian\LDPlayer14",
    r"SOFTWARE\leidian\ldplayer14",
    # LDPlayer 9
    r"SOFTWARE\leidian\LDPlayer9",
    r"SOFTWARE\leidian\ldplayer9",
    # LDPlayer 12
    r"SOFTWARE\leidian\LDPlayer12",
    r"SOFTWARE\leidian\ldplayer12",
    # LDPlayer X
    r"SOFTWARE\leidian\LDPlayerX",
    r"SOFTWARE\leidian\ldplayerx",
    # LDPlayer 4 / 5
    r"SOFTWARE\leidian\LDPlayer4",
    r"SOFTWARE\leidian\LDPlayer5",
    # Generic fallback
    r"SOFTWARE\leidian\LDPlayer",
    r"SOFTWARE\leidian\ldplayer",
)

# Candidate registry value names that store the install path.
# LDPlayer9 uses "InstallPath" (REG_SZ), older versions may use "InstallDir" or "Path".
LDPLAYER_REG_VALUE_NAMES = ("InstallPath", "InstallDir", "Path")


class LDOpenGLCapture:
    """LDPlayer OpenGL screenshot capture via ldopengl64.dll.

    Captures the emulator's OpenGL rendered frame directly from GPU memory.
    Much faster than ADB screencap (~5ms vs ~100ms).

    Auto-detects v3 (LDPlayer 14), v2 (LDPlayer 9 latest), falls back to v1.

    Windows-only: requires LDPlayer 9+ with ldopengl64.dll.
    """

    def __init__(self, ldplayer_dir: str | None = None):
        """Initialize LDOpenGL capture.

        Args:
            ldplayer_dir: Path to LDPlayer installation directory.
                          If None, auto-discovers via registry/PATH.
        """
        self._is_windows = platform.system() == "Windows"
        self._dll: ctypes.CDLL | None = None
        self._ldplayer_dir: Path | None = Path(ldplayer_dir) if ldplayer_dir else None
        # v1 API function pointer
        self._capture_fn: Any = None
        # v2 API function pointers (LDPlayer 9 latest)
        self._capture_frame_fn: Any = None
        self._get_frame_info_fn: Any = None
        self._copy_frame_fn: Any = None
        self._release_frame_fn: Any = None
        # v3 API function pointer (LDPlayer 14): CreateScreenShotInstance
        self._create_instance_fn: Any = None
        self._api_version: int = 0  # 0 = not loaded, 1 = v1, 2 = v2, 3 = v3
        self._initialized = False

    @property
    def api_version(self) -> int:
        """Loaded DLL API version: 0 (not loaded), 1 (v1), 2 (v2), 3 (v3)."""
        return self._api_version

    def is_available(self) -> bool:
        """Check if LDOpenGL capture is available on this system.

        Returns:
            True if ldopengl64.dll can be loaded (v1/v2/v3), False otherwise
        """
        if not self._is_windows:
            return False
        try:
            self._ensure_loaded()
            return self._api_version in (1, 2, 3)
        except Exception:
            return False

    def capture(self, hwnd: int, width: int, height: int) -> np.ndarray | None:
        """Capture LDPlayer window via OpenGL.

        Auto-selects v3 API if available (preferred for LDPlayer 14 — uses
        process ID instead of HWND), then v2 (LDPlayer 9 latest), then v1.

        Args:
            hwnd: LDPlayer window handle (used for v1/v2; v3 uses PID from
                find_ldplayer_window() instead).
            width: Capture width (v1 only — must match window's rendering
                resolution; ignored by v2/v3 which query emulator directly).
            height: Capture height (v1 only).

        Returns:
            BGR numpy array (height, width, 3), or None on failure
        """
        if not self._is_windows:
            logger.warning("LDOpenGL capture not available on %s", platform.system())
            return None

        try:
            self._ensure_loaded()
            if self._api_version == 3:
                return self._capture_v3(hwnd)
            elif self._api_version == 2:
                return self._capture_v2(hwnd)
            elif self._api_version == 1:
                return self._capture_v1(hwnd, width, height)
            else:
                logger.error("ldopengl64.dll not loaded or no capture function")
                return None

        except Exception as e:
            logger.error("LDOpenGL capture failed: %s", e)
            return None

    def _capture_v1(
        self, hwnd: int, width: int, height: int
    ) -> np.ndarray | None:
        """v1 legacy capture: ldopengl_capture(hwnd, w, h, buffer)."""
        if self._capture_fn is None:
            return None

        # Lazy import to avoid hard dependency on core.timeout at module load
        from core.timeout import TimeoutError, call_with_timeout

        # Allocate buffer for BGRA pixel data
        buffer_size = width * height * 4
        buffer = (c_ubyte * buffer_size)()

        try:
            result = call_with_timeout(
                self._capture_fn,
                LDOPENGL_CAPTURE_TIMEOUT_SEC,
                c_int(hwnd),
                c_int(width),
                c_int(height),
                buffer,
            )
        except TimeoutError as exc:
            logger.error(
                "ldopengl_capture (v1) timed out after %ss: %s",
                LDOPENGL_CAPTURE_TIMEOUT_SEC,
                exc,
            )
            return None

        if result != 0:
            logger.error("ldopengl_capture (v1) returned error code: %d", result)
            return None

        arr = np.frombuffer(buffer, dtype=np.uint8, count=buffer_size)
        arr = arr.reshape((height, width, 4))
        # BGRA -> BGR (drop alpha)
        return arr[:, :, :3].copy()

    def _capture_v2(self, hwnd: int) -> np.ndarray | None:
        """v2 capture: ldopengl_capture_frame + get_frame_info + copy + release.

        The DLL allocates the frame buffer internally; we just copy it out.
        Emulator-side width/height are queried via get_frame_info.
        """
        if (self._capture_frame_fn is None or self._get_frame_info_fn is None
                or self._copy_frame_fn is None or self._release_frame_fn is None):
            return None

        from core.timeout import TimeoutError, call_with_timeout

        # Step 1: capture_frame — returns a uint64 frame handle (0 on error).
        frame_handle = c_uint64(0)
        try:
            ret = call_with_timeout(
                self._capture_frame_fn,
                LDOPENGL_CAPTURE_TIMEOUT_SEC,
                c_int(hwnd),
                ctypes.byref(frame_handle),
            )
        except TimeoutError as exc:
            logger.error(
                "ldopengl_capture_frame (v2) timed out after %ss: %s",
                LDOPENGL_CAPTURE_TIMEOUT_SEC,
                exc,
            )
            return None

        if ret != 0 or frame_handle.value == 0:
            logger.error(
                "ldopengl_capture_frame (v2) failed: ret=%d handle=%d",
                ret, frame_handle.value,
            )
            return None

        try:
            # Step 2: query frame dimensions.
            w = c_int(0)
            h = c_int(0)
            inner_ret = c_int(0)
            try:
                info_ret = call_with_timeout(
                    self._get_frame_info_fn,
                    LDOPENGL_CAPTURE_TIMEOUT_SEC,
                    frame_handle,
                    ctypes.byref(w),
                    ctypes.byref(h),
                    ctypes.byref(inner_ret),
                )
            except TimeoutError as exc:
                logger.error(
                    "ldopengl_get_frame_info (v2) timed out: %s", exc,
                )
                return None

            if info_ret != 0 or inner_ret.value != 0:
                logger.error(
                    "ldopengl_get_frame_info (v2) failed: info_ret=%d inner=%d",
                    info_ret, inner_ret.value,
                )
                return None

            width = w.value
            height = h.value
            if width <= 0 or height <= 0:
                logger.error(
                    "ldopengl v2 returned invalid dimensions: %dx%d",
                    width, height,
                )
                return None

            # Step 3: copy BGRA pixel data into a local buffer.
            buffer_size = width * height * 4
            buffer = (c_ubyte * buffer_size)()
            try:
                copy_ret = call_with_timeout(
                    self._copy_frame_fn,
                    LDOPENGL_CAPTURE_TIMEOUT_SEC,
                    frame_handle,
                    buffer,
                    c_int(buffer_size),
                )
            except TimeoutError as exc:
                logger.error(
                    "ldopengl_copy_frame (v2) timed out: %s", exc,
                )
                return None

            if copy_ret != 0:
                logger.error(
                    "ldopengl_copy_frame (v2) failed: copy_ret=%d", copy_ret,
                )
                return None

            arr = np.frombuffer(buffer, dtype=np.uint8, count=buffer_size)
            arr = arr.reshape((height, width, 4))
            # BGRA -> BGR (drop alpha)
            return arr[:, :, :3].copy()

        finally:
            # Step 4: ALWAYS release the frame handle to avoid GPU
            # memory leaks. Even if earlier steps failed, the handle
            # was allocated by capture_frame and must be freed.
            try:
                call_with_timeout(
                    self._release_frame_fn,
                    LDOPENGL_CAPTURE_TIMEOUT_SEC,
                    frame_handle,
                )
            except Exception as exc:
                logger.warning(
                    "ldopengl_release_frame (v2) failed: %s — possible GPU memory leak",
                    exc,
                )

    def _capture_v3(self, hwnd: int) -> np.ndarray | None:
        """v3 capture via IScreenShotClass (Alas-compatible, LDPlayer 14).

        CreateScreenShotInstance(index, pid) returns an IScreenShotClass object.
        vtable[1]=cap returns a BGR frame buffer (3 bytes/pixel). The image is
        upside down (OpenGL origin at bottom-left), so flip it vertically.

        Dimensions come from `ldconsole list2` (stable across LDPlayer builds),
        with the window client size as a fallback.

        This replaces the previous CreateReadPixelsInstance (IReadPixelsClass)
        path which produced black-white ghosting because it read 4 bytes/pixel
        (BGRA) from a 3 bytes/pixel (BGR) buffer, shearing every row. Alas's
        IScreenShotClass path is the canonical reference for LDPlayer 9/14.
        """
        if self._create_instance_fn is None:
            return None

        from core.timeout import TimeoutError, call_with_timeout

        # IScreenShotClass vtable methods are __thiscall (stdcall on x64).
        # WINFUNCTYPE matches Alas; on x64 cdecl/stdcall share one ABI so
        # CFUNCTYPE would also work, but WINFUNCTYPE documents the intent.
        CAP_FN = ctypes.WINFUNCTYPE(c_void_p, c_void_p)
        RELEASE_FN = ctypes.WINFUNCTYPE(None, c_void_p)

        release_fn: Any = None
        instance_ptr: int = 0

        try:
            # Step 1: Resolve the LDPlayer process ID from the window handle.
            # v3 uses PID (not HWND) to locate the renderer.
            pid = self._get_pid_from_hwnd(hwnd)
            if pid == 0:
                logger.error(
                    "v3: GetWindowThreadProcessId returned 0 for hwnd=%s", hwnd,
                )
                return None

            # Step 2: Resolve dimensions. Prefer ldconsole list2 (matches the
            # emulator internal resolution); fall back to the window client size.
            width, height = self._get_resolution_from_ldconsole(0)
            if width <= 0 or height <= 0:
                width, height = self._get_window_client_size(hwnd)
            if width <= 0 or height <= 0:
                logger.error("v3: cannot resolve dimensions for hwnd=%s", hwnd)
                return None

            # Step 3: Create the IScreenShotClass instance.
            # CreateScreenShotInstance(index=0, pid) returns a heap-allocated
            # object whose first 8 bytes store the vtable pointer.
            try:
                instance_ptr = call_with_timeout(
                    self._create_instance_fn,
                    LDOPENGL_CAPTURE_TIMEOUT_SEC,
                    0,
                    pid,
                )
            except TimeoutError as exc:
                logger.error(
                    "v3: CreateScreenShotInstance timed out after %ss: %s",
                    LDOPENGL_CAPTURE_TIMEOUT_SEC,
                    exc,
                )
                return None

            if not instance_ptr:
                logger.error(
                    "v3: CreateScreenShotInstance returned NULL (pid=%d)", pid,
                )
                return None

            # Step 4: Resolve vtable and cap/release callables.
            # The first 8 bytes of the object store the vtable pointer.
            vtable_addr = ctypes.cast(instance_ptr, POINTER(c_void_p))[0]
            if not vtable_addr:
                logger.error("v3: vtable pointer is NULL")
                return None
            vtable = ctypes.cast(vtable_addr, POINTER(c_void_p))
            cap_fn = CAP_FN(vtable[1])
            release_fn = RELEASE_FN(vtable[2])

            # Step 5: Call cap() — returns a pointer to the BGR frame buffer
            # (3 bytes/pixel) owned by the object. Valid until release().
            try:
                frame_ptr = call_with_timeout(
                    cap_fn,
                    LDOPENGL_CAPTURE_TIMEOUT_SEC,
                    instance_ptr,
                )
            except TimeoutError as exc:
                logger.error(
                    "v3: cap() timed out after %ss: %s",
                    LDOPENGL_CAPTURE_TIMEOUT_SEC, exc,
                )
                return None

            if not frame_ptr:
                logger.error("v3: cap() returned NULL frame buffer")
                return None

            # Step 6: Copy BGR data out of the DLL-owned buffer. Must copy
            # BEFORE release() — the buffer is freed when object is destroyed.
            # IScreenShotClass returns BGR (3 bytes/pixel); image is upside down.
            buffer_size = width * height * 3
            arr = np.empty((height, width, 3), dtype=np.uint8)
            ctypes.memmove(arr.ctypes.data, frame_ptr, buffer_size)
            # Flip vertically: OpenGL stores the bottom row first.
            # Use numpy slicing (no cv2 dependency in agent).
            return arr[::-1].copy()

        finally:
            # Step 7: ALWAYS call release() to free the object and frame
            # buffer. Skipping leaks memory per frame.
            if release_fn is not None and instance_ptr:
                try:
                    call_with_timeout(
                        release_fn,
                        LDOPENGL_CAPTURE_TIMEOUT_SEC,
                        instance_ptr,
                    )
                except Exception as exc:
                    logger.warning(
                        "v3: release() failed: %s — possible memory leak", exc,
                    )

    @staticmethod
    def _get_pid_from_hwnd(hwnd: int) -> int:
        """Get the process ID of the window's owning process.

        Args:
            hwnd: Window handle

        Returns:
            Process ID (PID), or 0 on failure
        """
        if platform.system() != "Windows":
            return 0
        try:
            user32 = ctypes.windll.user32
            pid = c_uint32(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return pid.value
        except Exception as e:
            logger.debug("GetWindowThreadProcessId failed: %s", e)
            return 0

    def _get_resolution_from_ldconsole(self, index: int) -> tuple[int, int]:
        """Get emulator resolution from `ldconsole list2` output.

        list2 row format (comma-separated):
          index,name,topWnd,bndWnd,sysboot,playerpid,vboxpid,width,height,dpi

        Results are cached per index for 60 seconds (resolution rarely changes
        at runtime; only when the user resizes the emulator). Without caching
        every capture would spawn an ldconsole subprocess and drop ld_opengl
        from ~38 FPS to ~8 FPS.

        Returns:
            (width, height) for the matching instance index, or (0, 0) if the
            console executable is unavailable or the index is not found.
        """
        now = time.time()
        cached = _LDCONSOLE_RESOLUTION_CACHE.get(index)
        if cached and (now - cached[1]) < _LDCONSOLE_RESOLUTION_TTL:
            return cached[0]

        try:
            ldconsole = self._find_console_executable(str(self._ldplayer_dir or ""))
            if not ldconsole:
                return 0, 0
            proc = subprocess.run(
                [ldconsole, "list2"],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if proc.returncode != 0 or not proc.stdout:
                return 0, 0
            for line in proc.stdout.split(b"\n"):
                parts = line.strip().split(b",")
                if len(parts) != 10:
                    continue
                try:
                    if int(parts[0]) == index:
                        res = (int(parts[7]), int(parts[8]))
                        _LDCONSOLE_RESOLUTION_CACHE[index] = (res, now)
                        return res
                except (ValueError, IndexError):
                    continue
        except Exception as e:
            logger.debug("ldconsole list2 failed: %s", e)
        return 0, 0

    def _find_console_executable(self, ldplayer_dir: str = "") -> str | None:
        """Find ldconsole.exe/dnconsole.exe.

        Searches the provided install directory, the registry-discovered
        install path, and PATH. Returns the executable path or None.
        """
        candidates: list[str] = []
        if ldplayer_dir:
            candidates.append(ldplayer_dir)
        reg_dir = self._find_ldplayer_dir_from_registry()
        if reg_dir:
            candidates.append(str(reg_dir))

        for base in candidates:
            for exe in ("ldconsole.exe", "dnconsole.exe"):
                path = os.path.join(base, exe)
                if os.path.exists(path):
                    return path

        # PATH fallback
        import shutil
        for exe in ("ldconsole.exe", "dnconsole.exe"):
            found = shutil.which(exe)
            if found:
                return found
        return None

    @staticmethod
    def _get_window_client_size(hwnd: int) -> tuple[int, int]:
        """Get window client area size in pixels.

        Used as a fallback when `ldconsole list2` is unavailable.
        """
        if platform.system() != "Windows":
            return 0, 0
        try:
            user32 = ctypes.windll.user32
            rect = ctypes.wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            return int(rect.right - rect.left), int(rect.bottom - rect.top)
        except Exception as e:
            logger.debug("GetClientRect failed: %s", e)
            return 0, 0

    def _ensure_loaded(self) -> None:
        """Lazily load ldopengl64.dll and resolve capture functions.

        Tries v3 API first (preferred — LDPlayer 14 vtable-based PID
        capture); falls back to v2 (LDPlayer 9 latest), then v1 (legacy).
        """
        if self._initialized:
            return
        self._initialized = True

        if not self._is_windows:
            return

        dll_path = self._find_dll()
        if not dll_path:
            logger.warning("ldopengl64.dll not found")
            return

        try:
            self._dll = ctypes.CDLL(str(dll_path))
        except Exception as e:
            logger.error("Failed to load ldopengl64.dll: %s", e)
            self._dll = None
            return

        # Try v3 first (LDPlayer 14). Use CreateScreenShotInstance, the
        # Alas-proven factory that returns an IScreenShotClass object whose
        # vtable[1]=cap returns a CPU-readable BGR frame (3 bytes/pixel).
        # The previous CreateReadPixelsInstance (IReadPixelsClass) path read
        # 4 bytes/pixel (BGRA) and produced black-white ghosting; Alas's
        # IScreenShotClass path is the canonical reference for LDPlayer 9/14.
        try:
            self._create_instance_fn = self._dll.CreateScreenShotInstance
            self._create_instance_fn.argtypes = [c_int, c_int]
            self._create_instance_fn.restype = c_void_p
            self._api_version = 3
            logger.info(
                "ldopengl64.dll v3 API loaded from %s (LDPlayer 14 IScreenShotClass)",
                dll_path,
            )
            return
        except AttributeError:
            # v3 symbol not present — fall through to v2.
            self._create_instance_fn = None
        except Exception as e:
            logger.debug("v3 API load failed, falling back to v2: %s", e)
            self._create_instance_fn = None

        # Try v2 API next (LDPlayer 9 latest).
        # v2 symbols: ldopengl_capture_frame, ldopengl_get_frame_info,
        # ldopengl_copy_frame, ldopengl_release_frame.
        try:
            self._capture_frame_fn = self._dll.ldopengl_capture_frame
            self._capture_frame_fn.argtypes = [c_int, POINTER(c_uint64)]
            self._capture_frame_fn.restype = c_uint32

            self._get_frame_info_fn = self._dll.ldopengl_get_frame_info
            self._get_frame_info_fn.argtypes = [
                c_uint64, POINTER(c_int), POINTER(c_int), POINTER(c_int),
            ]
            self._get_frame_info_fn.restype = c_uint32

            self._copy_frame_fn = self._dll.ldopengl_copy_frame
            self._copy_frame_fn.argtypes = [c_uint64, POINTER(c_ubyte), c_int]
            self._copy_frame_fn.restype = c_uint32

            self._release_frame_fn = self._dll.ldopengl_release_frame
            self._release_frame_fn.argtypes = [c_uint64]
            self._release_frame_fn.restype = c_uint32

            self._api_version = 2
            logger.info(
                "ldopengl64.dll v2 API loaded from %s (LDPlayer 9 latest)",
                dll_path,
            )
            return
        except AttributeError:
            # v2 symbols not present — fall through to v1.
            self._capture_frame_fn = None
            self._get_frame_info_fn = None
            self._copy_frame_fn = None
            self._release_frame_fn = None
        except Exception as e:
            logger.debug("v2 API load failed, falling back to v1: %s", e)
            self._capture_frame_fn = None
            self._get_frame_info_fn = None
            self._copy_frame_fn = None
            self._release_frame_fn = None

        # Fall back to v1 (legacy) API.
        try:
            self._capture_fn = self._dll.ldopengl_capture
            self._capture_fn.argtypes = [c_int, c_int, c_int, POINTER(c_ubyte)]
            self._capture_fn.restype = c_uint32
            self._api_version = 1
            logger.info(
                "ldopengl64.dll v1 API loaded from %s (legacy)",
                dll_path,
            )
        except Exception as e:
            logger.error("Failed to load v1 ldopengl_capture: %s", e)
            self._dll = None
            self._capture_fn = None
            self._api_version = 0

    def _find_dll(self) -> Path | None:
        """Find ldopengl64.dll in LDPlayer installation directory or PATH.

        Returns:
            Path to ldopengl64.dll, or None if not found
        """
        # If user provided explicit directory
        if self._ldplayer_dir:
            for rel_path in LDOPENGL_DLL_PATHS:
                candidate = self._ldplayer_dir / rel_path
                if candidate.exists():
                    return candidate

        # Try registry discovery
        reg_dir = self._find_ldplayer_dir_from_registry()
        if reg_dir:
            for rel_path in LDOPENGL_DLL_PATHS:
                candidate = reg_dir / rel_path
                if candidate.exists():
                    return candidate

        # Try PATH
        import shutil
        found = shutil.which("ldopengl64.dll")
        if found:
            return Path(found)

        return None

    @staticmethod
    def _find_ldplayer_dir_from_registry() -> Path | None:
        """Find LDPlayer installation directory from Windows registry.

        Returns:
            Path to LDPlayer installation directory, or None if not found
        """
        if platform.system() != "Windows":
            return None

        try:
            import winreg

            # Try each path × each hive × each value name × 32/64-bit view.
            # LDPlayer install path may live under HKCU or HKLM, and 32-bit
            # installers on 64-bit Windows redirect to WOW6432Node.
            hives_views = (
                (winreg.HKEY_CURRENT_USER, 0),
                (winreg.HKEY_CURRENT_USER, winreg.KEY_WOW64_32KEY),
                (winreg.HKEY_LOCAL_MACHINE, 0),
                (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
            )
            for reg_path in LDPLAYER_REG_PATHS:
                for hive, wow_flag in hives_views:
                    try:
                        access = winreg.KEY_READ | wow_flag
                        with winreg.OpenKey(hive, reg_path, 0, access) as key:
                            for value_name in LDPLAYER_REG_VALUE_NAMES:
                                try:
                                    install_dir, _ = winreg.QueryValueEx(key, value_name)
                                    if install_dir:
                                        p = Path(install_dir)
                                        if p.exists():
                                            return p
                                except FileNotFoundError:
                                    continue
                    except OSError:
                        continue

        except Exception as e:
            logger.debug("Registry lookup failed: %s", e)

        return None

    @staticmethod
    def find_ldplayer_window() -> int:
        """Find LDPlayer window handle.

        Iterates through known LDPlayer window class names:
          - "LDPlayerWnd"        (LDPlayer 9 and earlier)
          - "LDPlayerMainFrame"  (LDPlayer 14)

        Returns:
            Window handle (HWND) as int, or 0 if not found
        """
        if platform.system() != "Windows":
            return 0

        try:
            user32 = ctypes.windll.user32
            # Try each known LDPlayer window class name.
            for class_name in LDPLAYER_WINDOW_CLASSES:
                hwnd = user32.FindWindowW(class_name, None)
                if hwnd:
                    return hwnd

            # Fallback: find by window title pattern "LDPlayer"
            hwnd = user32.FindWindowW(None, "LDPlayer")
            if hwnd:
                return hwnd

        except Exception as e:
            logger.debug("FindWindow failed: %s", e)

        return 0


# ==================== Module-level singleton (TD-011) ====================
# LDOpenGLCapture MUST be instantiated exactly once per process. Each
# instantiation calls ctypes.CDLL(dll_path) (LoadLibrary) in _ensure_loaded(),
# and when the instance is garbage-collected the CDLL wrapper is released
# (FreeLibrary). Repeated load/unload cycles — one per screenshot frame —
# eventually leave IScreenShotClass vtable pointers dangling, causing
# ACCESS_VIOLATION (0xC0000005) crashes in ldopengl64.dll after ~1 hour of
# per-second screenshot loops.
#
# The singleton ensures _ensure_loaded() runs exactly once: the DLL is loaded
# once, the v3 API factory pointer (CreateScreenShotInstance) is resolved
# once, and the DLL stays loaded for the process lifetime. Per-frame
# IScreenShotClass objects are still created/released inside _capture_v3
# (this is correct — Alas does the same), but they reference a stable DLL
# whose vtable memory is never freed.
#
# See docs/archive/active-tech-debt.md TD-011.
_LDOPENGL_LOCK = threading.Lock()
_LDOPENGL_CAPTURE_INSTANCE: LDOpenGLCapture | None = None


def get_ldopengl_capture() -> LDOpenGLCapture:
    """Return the process-wide LDOpenGLCapture singleton.

    Thread-safe via double-checked locking. The DLL is loaded exactly once;
    if the first load fails (LDPlayer not installed), subsequent calls return
    the same failed instance (api_version=0, is_available()=False) — restart
    the agent to retry discovery.

    Production callers (e.g. devices.adb.device._capture_ldopengl) MUST use
    this factory instead of constructing LDOpenGLCapture() directly. Tests
    may still construct LDOpenGLCapture() directly to test initialization
    behavior in isolation.

    Returns:
        The shared LDOpenGLCapture instance (api_version 0/1/2/3).
    """
    global _LDOPENGL_CAPTURE_INSTANCE
    if _LDOPENGL_CAPTURE_INSTANCE is None:
        with _LDOPENGL_LOCK:
            if _LDOPENGL_CAPTURE_INSTANCE is None:
                _LDOPENGL_CAPTURE_INSTANCE = LDOpenGLCapture()
    return _LDOPENGL_CAPTURE_INSTANCE
