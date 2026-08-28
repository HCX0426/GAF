"""
LDOpenGL screenshot module for LDPlayer emulator (backend wrapper).

Ref: Alas LDOpenGL — uses ldopengl64.dll to capture OpenGL buffer directly.
This backend implementation mirrors the agent/src/platforms/windows/ldopengl.py
v1/v2/v3 API support so that the Django backend can serve LDPlayer screenshots
through the test-screenshot endpoint and report the real method as 'ld_opengl'.

API versions:
  v1 (legacy): ldopengl_capture(hwnd, w, h, buffer)
  v2 (LDPlayer 9 latest): ldopengl_capture_frame + get_frame_info + copy + release
  v3 (LDPlayer 14): CreateScreenShotInstance -> IScreenShotClass vtable cap/release (Alas-compatible)
"""
import ctypes
import logging
import os
import platform
import subprocess
import tempfile
import time
from ctypes import POINTER, c_int, c_ubyte, c_uint32, c_uint64, c_void_p
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# LDPlayer window class names for FindWindow.
LDPLAYER_WINDOW_CLASSES = (
    "LDPlayerWnd",
    "LDPlayerMainFrame",
)

# v3 (IReadPixelsClass, deprecated) object layout offsets reverse-engineered
# from an earlier LDPlayer 14 ldopengl64.dll. Kept for reference only — the
# active v3 path now uses IScreenShotClass (Alas-compatible), which reads
# dimensions from `ldconsole list2` instead of object offsets. The previous
# IReadPixelsClass path produced black-white ghosting due to a 4-vs-3
# bytes-per-pixel mismatch.
LDOPENGL_V3_WIDTH_OFFSET = 0x6C
LDOPENGL_V3_HEIGHT_OFFSET = 0x70

# Relative paths where ldopengl64.dll may live inside the install directory.
LDOPENGL_DLL_PATHS = (
    "ldopengl64.dll",
    "shell/ldopengl64.dll",
    "vms/ldopengl64.dll",
)

# Safety timeout for DLL calls (seconds). The calls normally finish in <10ms;
# this is only a guardrail against a hung LDPlayer renderer process.
LDOPENGL_CAPTURE_TIMEOUT_SEC = 5.0

# Per-instance resolution cache for `ldconsole list2` lookups: index -> ((w, h), timestamp).
# ldconsole is a subprocess (~80ms); without caching, ld_opengl drops from ~38 to ~8 FPS.
_LDCONSOLE_RESOLUTION_CACHE: dict[int, tuple[tuple[int, int], float]] = {}
_LDCONSOLE_RESOLUTION_TTL = 60.0  # seconds; resolution rarely changes at runtime

# Registry paths covering LDPlayer 4/5/9/12/14/X plus generic fallback.
LDPLAYER_REG_PATHS = (
    r"SOFTWARE\leidian\LDPlayer14",
    r"SOFTWARE\leidian\ldplayer14",
    r"SOFTWARE\leidian\LDPlayer9",
    r"SOFTWARE\leidian\ldplayer9",
    r"SOFTWARE\leidian\LDPlayer12",
    r"SOFTWARE\leidian\ldplayer12",
    r"SOFTWARE\leidian\LDPlayerX",
    r"SOFTWARE\leidian\ldplayerx",
    r"SOFTWARE\leidian\LDPlayer4",
    r"SOFTWARE\leidian\LDPlayer5",
    r"SOFTWARE\leidian\LDPlayer",
    r"SOFTWARE\leidian\ldplayer",
)

# Candidate registry value names that store the install path.
LDPLAYER_REG_VALUE_NAMES = ("InstallPath", "InstallDir", "Path")


class LDOpenGLCapture:
    """Capture screenshot from LDPlayer via ldopengl64.dll OpenGL buffer.

    Auto-detects v3 (LDPlayer 14), v2 (LDPlayer 9 latest) and falls back to v1.
    The public backend-compatible method is capture(index=0), which returns a
    dict with JPEG-encoded image_bytes on success.
    """

    def __init__(self, ldplayer_dir: str | None = None):
        self._is_windows = platform.system() == "Windows"
        self._dll: ctypes.CDLL | None = None
        self._ldplayer_dir: Path | None = Path(ldplayer_dir) if ldplayer_dir else None
        # v1
        self._capture_fn: Any = None
        # v2
        self._capture_frame_fn: Any = None
        self._get_frame_info_fn: Any = None
        self._copy_frame_fn: Any = None
        self._release_frame_fn: Any = None
        # v3
        self._create_instance_fn: Any = None
        self._api_version: int = 0  # 0 = not loaded, 1 = v1, 2 = v2, 3 = v3
        self._initialized = False

    @property
    def api_version(self) -> int:
        """Loaded DLL API version: 0 (not loaded), 1 (v1), 2 (v2), 3 (v3)."""
        return self._api_version

    def is_available(self) -> bool:
        """Check if LDOpenGL capture is available on this system."""
        if not self._is_windows:
            return False
        try:
            self._ensure_loaded()
            return self._api_version in (1, 2, 3)
        except Exception:
            logger.warning("LDOpenGL: is_available check failed", exc_info=True)
            return False

    def capture(self, index: int = 0) -> dict:
        """Capture screenshot from an LDPlayer instance.

        Args:
            index: LDPlayer instance index (from ldconsole list). For single
                   instance setups the first LDPlayer window found is used.

        Returns:
            dict with keys: success, image_bytes, resolution, error
        """
        if not self._is_windows:
            return {"success": False, "error": "LDOpenGL only available on Windows"}

        try:
            self._ensure_loaded()
            if self._api_version == 0:
                return {"success": False, "error": "ldopengl64.dll not loaded or unsupported"}

            # Locate the LDPlayer window for this instance.
            hwnd = self._find_window_for_index(index)
            if not hwnd:
                # Single-instance fallback: any LDPlayer window.
                hwnd = self._find_any_ldplayer_window()
            if not hwnd:
                return {"success": False, "error": f"LDPlayer window not found for index {index}"}

            # v2/v3 query dimensions from the emulator; v1 needs the client size.
            client_width, client_height = 0, 0
            if self._api_version == 1:
                client_width, client_height = self._get_window_client_size(hwnd)
                if client_width <= 0 or client_height <= 0:
                    return {"success": False, "error": "Failed to get LDPlayer window size"}

            if self._api_version == 3:
                arr = self._capture_v3(hwnd, index)
            elif self._api_version == 2:
                arr = self._capture_v2(hwnd)
            else:
                arr = self._capture_v1(hwnd, client_width, client_height)

            if arr is None:
                return {"success": False, "error": "LDOpenGL capture returned no image"}

            # Encode BGR numpy array to JPEG bytes for the backend response.
            _, buf = cv2.imencode(".jpg", arr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return {
                "success": True,
                "image_bytes": buf.tobytes(),
                "resolution": {"width": arr.shape[1], "height": arr.shape[0]},
            }
        except Exception as e:
            logger.error("LDOpenGL capture failed: %s", e)
            return {"success": False, "error": f"LDOpenGL capture error: {e}"}

    # ------------------------------------------------------------------
    # DLL loading & API resolution
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        """Lazily load ldopengl64.dll and resolve capture functions."""
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
            logger.info("ldopengl64.dll v3 API loaded (IScreenShotClass) from %s", dll_path)
            return
        except AttributeError:
            self._create_instance_fn = None
        except Exception as e:
            logger.debug("v3 CreateScreenShotInstance load failed, falling back to v2: %s", e)
            self._create_instance_fn = None

        # Try v2 next (LDPlayer 9 latest).
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
            logger.info("ldopengl64.dll v2 API loaded from %s", dll_path)
            return
        except AttributeError:
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

        # Fall back to v1 (legacy).
        try:
            self._capture_fn = self._dll.ldopengl_capture
            self._capture_fn.argtypes = [c_int, c_int, c_int, POINTER(c_ubyte)]
            self._capture_fn.restype = c_uint32
            self._api_version = 1
            logger.info("ldopengl64.dll v1 API loaded from %s", dll_path)
        except Exception as e:
            logger.error("Failed to load any ldopengl64 capture API: %s", e)
            self._dll = None
            self._api_version = 0

    def _find_dll(self) -> Path | None:
        """Find ldopengl64.dll in install directory, registry or PATH."""
        if self._ldplayer_dir:
            for rel in LDOPENGL_DLL_PATHS:
                candidate = self._ldplayer_dir / rel
                if candidate.exists():
                    return candidate

        reg_dir = self._find_ldplayer_dir_from_registry()
        if reg_dir:
            for rel in LDOPENGL_DLL_PATHS:
                candidate = reg_dir / rel
                if candidate.exists():
                    return candidate

        # Search common install paths (covers manual/custom installs).
        for base in self._common_install_paths():
            for rel in LDOPENGL_DLL_PATHS:
                candidate = Path(base) / rel
                if candidate.exists():
                    return candidate

        # PATH fallback
        import shutil
        found = shutil.which("ldopengl64.dll")
        if found:
            return Path(found)

        return None

    @staticmethod
    def _find_ldplayer_dir_from_registry() -> Path | None:
        """Find LDPlayer installation directory from Windows registry."""
        if platform.system() != "Windows":
            return None
        try:
            import winreg
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
    def _common_install_paths() -> tuple[str, ...]:
        """Common LDPlayer installation paths across drives and versions."""
        bases = []
        for drive in "EDC":
            bases.extend([
                rf"{drive}:\game\leidian\LDPlayer14",
                rf"{drive}:\game\leidian\LDPlayer9",
                rf"{drive}:\game\leidian\LDPlayer12",
                rf"{drive}:\game\leidian\LDPlayer4",
                rf"{drive}:\game\leidian\LDPlayer",
                rf"{drive}:\LDPlayer\LDPlayer14",
                rf"{drive}:\LDPlayer\LDPlayer9",
                rf"{drive}:\LDPlayer\LDPlayer12",
                rf"{drive}:\LDPlayer\LDPlayer4",
                rf"{drive}:\LDPlayer\LDPlayer",
                rf"{drive}:\leidian\LDPlayer14",
                rf"{drive}:\leidian\LDPlayer9",
                rf"{drive}:\leidian\LDPlayer12",
                rf"{drive}:\leidian\LDPlayer4",
                rf"{drive}:\leidian\LDPlayer",
            ])
        bases.extend([
            r"C:\Program Files\leidian\LDPlayer14",
            r"C:\Program Files\leidian\LDPlayer9",
            r"C:\Program Files\leidian\LDPlayer12",
            r"C:\Program Files\leidian\LDPlayer4",
            r"C:\Program Files\leidian\LDPlayer",
            r"C:\Program Files (x86)\leidian\LDPlayer14",
            r"C:\Program Files (x86)\leidian\LDPlayer9",
            r"C:\Program Files (x86)\leidian\LDPlayer12",
            r"C:\Program Files (x86)\leidian\LDPlayer4",
            r"C:\Program Files (x86)\leidian\LDPlayer",
        ])
        return tuple(bases)

    # ------------------------------------------------------------------
    # Capture implementations
    # ------------------------------------------------------------------
    def _capture_v1(self, hwnd: int, width: int, height: int) -> np.ndarray | None:
        """v1 legacy capture: ldopengl_capture(hwnd, w, h, buffer)."""
        if self._capture_fn is None:
            return None
        buffer_size = width * height * 4
        buffer = (c_ubyte * buffer_size)()
        result = self._capture_fn(c_int(hwnd), c_int(width), c_int(height), buffer)
        if result != 0:
            logger.error("ldopengl_capture (v1) returned error code: %d", result)
            return None
        arr = np.frombuffer(buffer, dtype=np.uint8, count=buffer_size)
        arr = arr.reshape((height, width, 4))
        return arr[:, :, :3].copy()

    def _capture_v2(self, hwnd: int) -> np.ndarray | None:
        """v2 capture: ldopengl_capture_frame + get_frame_info + copy + release."""
        if (self._capture_frame_fn is None or self._get_frame_info_fn is None
                or self._copy_frame_fn is None or self._release_frame_fn is None):
            return None

        frame_handle = c_uint64(0)
        ret = self._capture_frame_fn(c_int(hwnd), ctypes.byref(frame_handle))
        if ret != 0 or frame_handle.value == 0:
            logger.error("ldopengl_capture_frame (v2) failed: ret=%d handle=%d", ret, frame_handle.value)
            return None

        try:
            w = c_int(0)
            h = c_int(0)
            inner_ret = c_int(0)
            info_ret = self._get_frame_info_fn(frame_handle, ctypes.byref(w), ctypes.byref(h), ctypes.byref(inner_ret))
            if info_ret != 0 or inner_ret.value != 0:
                logger.error("ldopengl_get_frame_info (v2) failed: info_ret=%d inner=%d", info_ret, inner_ret.value)
                return None

            width, height = w.value, h.value
            if width <= 0 or height <= 0:
                logger.error("ldopengl v2 returned invalid dimensions: %dx%d", width, height)
                return None

            buffer_size = width * height * 4
            buffer = (c_ubyte * buffer_size)()
            copy_ret = self._copy_frame_fn(frame_handle, buffer, c_int(buffer_size))
            if copy_ret != 0:
                logger.error("ldopengl_copy_frame (v2) failed: copy_ret=%d", copy_ret)
                return None

            arr = np.frombuffer(buffer, dtype=np.uint8, count=buffer_size)
            arr = arr.reshape((height, width, 4))
            return arr[:, :, :3].copy()
        finally:
            try:
                self._release_frame_fn(frame_handle)
            except Exception as exc:
                logger.warning("ldopengl_release_frame (v2) failed: %s", exc)

    def _capture_v3(self, hwnd: int, index: int = 0) -> np.ndarray | None:
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

        # IScreenShotClass vtable methods are __thiscall (stdcall on x64).
        # WINFUNCTYPE matches Alas; on x64 cdecl/stdcall share one ABI so
        # CFUNCTYPE would also work, but WINFUNCTYPE documents the intent.
        CAP_FN = ctypes.WINFUNCTYPE(c_void_p, c_void_p)  # noqa: N806
        RELEASE_FN = ctypes.WINFUNCTYPE(None, c_void_p)  # noqa: N806

        release_fn: Any = None
        instance_ptr: int = 0

        try:
            pid = self._get_pid_from_hwnd(hwnd)
            if pid == 0:
                logger.error("v3: GetWindowThreadProcessId returned 0 for hwnd=%s", hwnd)
                return None

            # Resolve dimensions: prefer ldconsole list2 (matches the emulator
            # internal resolution), fall back to the window client size.
            width, height = self._get_resolution_from_ldconsole(index)
            if width <= 0 or height <= 0:
                width, height = self._get_window_client_size(hwnd)
            if width <= 0 or height <= 0:
                logger.error("v3: cannot resolve dimensions for index %d", index)
                return None

            instance_ptr = self._create_instance_fn(index, pid)
            if not instance_ptr:
                logger.error(
                    "v3: CreateScreenShotInstance returned NULL (index=%d pid=%d)",
                    index, pid,
                )
                return None

            vtable_addr = ctypes.cast(instance_ptr, POINTER(c_void_p))[0]
            if not vtable_addr:
                logger.error("v3: vtable pointer is NULL")
                return None
            vtable = ctypes.cast(vtable_addr, POINTER(c_void_p))
            cap_fn = CAP_FN(vtable[1])
            release_fn = RELEASE_FN(vtable[2])

            frame_ptr = cap_fn(instance_ptr)
            if not frame_ptr:
                logger.error("v3: cap() returned NULL frame buffer")
                return None

            # IScreenShotClass returns BGR (3 bytes/pixel). Image is upside down.
            buffer_size = width * height * 3
            arr = np.empty((height, width, 3), dtype=np.uint8)
            ctypes.memmove(arr.ctypes.data, frame_ptr, buffer_size)
            # Flip vertically: OpenGL stores the bottom row first.
            arr = cv2.flip(arr, 0)
            return arr
        finally:
            if release_fn is not None and instance_ptr:
                try:
                    release_fn(instance_ptr)
                except Exception as exc:
                    logger.warning("v3: release() failed: %s", exc)

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

    # ------------------------------------------------------------------
    # Window helpers
    # ------------------------------------------------------------------
    def _find_window_for_index(self, index: int) -> int:
        """Find the LDPlayer window handle for the given instance index.

        This is a best-effort match. LDPlayer window titles vary by version and
        user configuration, so for the common single-instance case we fall back
        to the first LDPlayer window found.
        """
        hwnd = self._find_any_ldplayer_window()
        if not hwnd:
            return 0

        if index <= 0:
            return hwnd

        # Multi-instance: attempt to enumerate windows and pick by title pattern.
        # LDPlayer multi-instance titles are often "LDPlayer-{index}" or contain
        # the instance index. This is heuristic and may be refined later.
        try:
            user32 = ctypes.windll.user32

            results = []

            def enum_callback(hwnd_extra, _extra):
                try:
                    cls = self._get_window_class(hwnd_extra)
                    if cls not in LDPLAYER_WINDOW_CLASSES:
                        return True
                    title = self._get_window_text(hwnd_extra)
                    results.append((hwnd_extra, title))
                except Exception:
                    logger.debug('window enum callback failed', exc_info=True)
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)  # noqa: N806
            user32.EnumWindows(EnumWindowsProc(enum_callback), 0)

            # Prefer exact title containing the index digit.
            for h, title in results:
                if str(index) in title:
                    return h
            # Otherwise return the first found window.
            return results[0][0]
        except Exception as e:
            logger.debug("Window enumeration for index %d failed: %s", index, e)
            return hwnd

    @staticmethod
    def _find_any_ldplayer_window() -> int:
        """Find any LDPlayer window by class name or title."""
        if platform.system() != "Windows":
            return 0
        try:
            user32 = ctypes.windll.user32
            for class_name in LDPLAYER_WINDOW_CLASSES:
                hwnd = user32.FindWindowW(class_name, None)
                if hwnd:
                    return hwnd
            hwnd = user32.FindWindowW(None, "LDPlayer")
            if hwnd:
                return hwnd
        except Exception as e:
            logger.debug("FindWindow failed: %s", e)
        return 0

    @staticmethod
    def _get_window_class(hwnd: int) -> str:
        """Get window class name."""
        user32 = ctypes.windll.user32
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    @staticmethod
    def _get_window_text(hwnd: int) -> str:
        """Get window title text."""
        user32 = ctypes.windll.user32
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    @staticmethod
    def _get_window_client_size(hwnd: int) -> tuple[int, int]:
        """Get window client area size in pixels."""
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

    @staticmethod
    def _get_pid_from_hwnd(hwnd: int) -> int:
        """Get the process ID of the window's owning process."""
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

    # ------------------------------------------------------------------
    # Legacy fallback: ldconsole screenshot command
    # ------------------------------------------------------------------
    def _capture_via_ldconsole(self, index: int, ldplayer_dir: str) -> dict:
        """Fallback: use ldconsole/dnconsole screenshot command."""
        try:
            ldconsole = self._find_console_executable(ldplayer_dir)
            if not ldconsole:
                return {"success": False, "error": "ldconsole.exe not found"}

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                temp_path = f.name

            try:
                result = subprocess.run(
                    [ldconsole, "screenshot", "--index", str(index), "--filename", temp_path],
                    capture_output=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if result.returncode != 0 or not os.path.exists(temp_path):
                    stderr = result.stderr.decode("cp936", errors="replace")
                    return {"success": False, "error": f"ldconsole screenshot failed: {stderr}"}

                img = cv2.imread(temp_path)
                if img is None:
                    return {"success": False, "error": "Failed to read screenshot file"}

                height, width = img.shape[:2]
                _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                return {
                    "success": True,
                    "image_bytes": buf.tobytes(),
                    "resolution": {"width": width, "height": height},
                }
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        except Exception as e:
            return {"success": False, "error": f"ldconsole screenshot error: {e}"}

    def _find_console_executable(self, ldplayer_dir: str = "") -> str | None:
        """Find ldconsole.exe/dnconsole.exe."""
        candidates = []
        if ldplayer_dir:
            candidates.append(ldplayer_dir)
        reg_dir = self._find_ldplayer_dir_from_registry()
        if reg_dir:
            candidates.append(str(reg_dir))
        candidates.extend(self._common_install_paths())

        for base in candidates:
            for exe in ("ldconsole.exe", "dnconsole.exe"):
                path = os.path.join(base, exe)
                if os.path.exists(path):
                    return path

        # PATH fallback
        for exe in ("ldconsole.exe", "dnconsole.exe"):
            for search_dir in os.environ.get("PATH", "").split(os.pathsep):
                path = os.path.join(search_dir.strip('"'), exe)
                if os.path.exists(path):
                    return path

        # Last resort: scan running processes.
        try:
            import win32api
            import win32con
            import win32process
            for pid in win32process.EnumProcesses():
                try:
                    handle = win32api.OpenProcess(
                        win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                        False,
                        pid,
                    )
                    name = win32process.GetModuleFileNameEx(handle, 0)
                    win32api.CloseHandle(handle)
                    lowered = name.lower()
                    if lowered.endswith("ldconsole.exe") or lowered.endswith("dnconsole.exe"):
                        return name
                except Exception:
                    logger.warning("LDOpenGL: process scan iteration failed (pid=%s)", pid, exc_info=True)
                    continue
        except Exception as e:
            logger.debug("Process scan for LDPlayer console failed: %s", e)
        return None
