"""截图管理器：多策略截图（WGC→DXGI→GDI→PrintWindow 降级链）"""

import concurrent.futures
import contextlib
import ctypes
import ctypes.wintypes
import logging
import time

import numpy as np
from core.retry import retry_screenshot

# Apply DPI awareness at module import — without this, GDI/PrintWindow return
# DPI-virtualized logical pixels (e.g. 1024x576) instead of physical pixels
# (1536x864), breaking coord_transformer's scale_ratio. Importing dpi triggers
# apply_dpi_awareness() at module load (idempotent across re-imports).
from platforms.windows import dpi  # noqa: F401

logger = logging.getLogger(__name__)

# TD-396: dedicated workers for bounded screenshot capture. A wedged DXGI
# AcquireNextFrame blocks forever at the COM layer, so screenshots run here
# and the caller enforces a wall-clock timeout (dropping the stuck worker).
_SHOT_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="gaf-shot",
)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# Window class names that indicate a game/engine render window. For these,
# GDI Bitblt cannot capture occluded content (it captures whatever is visible
# on screen, which may be a foreground IDE window). PrintWindow sends WM_PRINT
# directly to the target window, so it can capture occluded game content.
# Used by _detect_best_method to override the benchmark's "fastest wins" rule.
_GAME_WINDOW_CLASSES = frozenset({
    "UnityWndClass",        # Unity engine (BD2, etc.)
    "UnrealWindow",         # Unreal engine
    "LaunchUnrealUWindowsClient",
    "Godot_Engine_Wnd",    # Godot
    "FFXIVGAME",           # Final Fantasy XIV
    "ArenaNet_Dx_Window_Class",  # Guild Wars 2
    "CrypticWindow",        # Star Trek Online / Neverwinter
})


class ScreenshotManager:
    """截图管理器：支持 WGC、DXGI、GDI、PrintWindow 四种截图策略，自动降级

    降级链：WGC → DXGI → GDI → PrintWindow
    首次连接时可运行竞速测试自动选择最佳方式。
    """

    WGC = "wgc"
    DXGI = "dxgi"
    GDI = "gdi"
    PRINTWINDOW = "printwindow"

    def __init__(self, hwnd: int | None = None, method: str = "auto",
                 client_only: bool = False):
        self._hwnd = hwnd
        # Normalize method to lowercase so backend Title-case identifiers
        # ("PrintWindow", "WGC", "DXGI", "GDI") work the same as the agent's
        # own lowercase constants ("printwindow", "wgc", ...). Without this
        # normalization, a device whose screenshot_method was auto-benchmarked
        # and stored as "PrintWindow" by the backend never matches the
        # fallback_order list (which holds lowercase constants), so
        # ScreenshotManager silently falls through to WGC — which returns
        # black frames for occluded GPU-rendered windows like BrownDust II.
        self._method = method.lower() if isinstance(method, str) else method
        self._best_method: str | None = None
        self._wgc_instance = None
        self._dxgi_instance = None
        # List of BenchmarkResult from benchmark_capture_methods (NamedTuple).
        # [0].method gives the fastest reliable method name. None before
        # first benchmark run; empty list if benchmark ran but all methods
        # failed.
        self._benchmark_results: list | None = None
        # When True, PrintWindow capture uses PW_CLIENTONLY flag to skip the
        # title bar (cleaner screenshots for LDPlayer / emulators). Default
        # False for backward compat; enable per-device via constructor.
        self._client_only = bool(client_only)

    def set_hwnd(self, hwnd: int) -> None:
        """设置目标窗口句柄"""
        self._hwnd = hwnd
        self._best_method = None
        self._benchmark_results = None
        self._release_wgc()
        self._release_dxgi()

    def set_method(self, method: str) -> None:
        """Switch the active capture method at runtime.

        Used by debug-mode AI auto-heal (project_rules.md §4.8.2): when
        template_match fails and the diagnostic finds a better method, this
        switches the manager to use that method for subsequent captures
        without recreating the instance (preserves hwnd / client_only state).

        Args:
            method: One of WGC/DXGI/GDI/PRINTWINDOW (case-insensitive),
                    or "auto" to re-trigger benchmark on next capture.
        """
        normalized = method.lower() if isinstance(method, str) else method
        if normalized not in (self.WGC, self.DXGI, self.GDI, self.PRINTWINDOW, "auto"):
            logger.warning("set_method: unknown method %r, ignoring", method)
            return
        logger.info("ScreenshotManager method switched: %s -> %s", self._method, normalized)
        self._method = normalized
        # Clear cached best_method so _detect_best_method re-runs if needed.
        self._best_method = None
        # Release any cached WGC instance — different method may not need it.
        self._release_wgc()
        self._release_dxgi()

    def release(self) -> None:
        """释放截图管理器资源（WGC / DXGI 实例等）"""
        self._release_wgc()
        self._release_dxgi()

    def capture(self) -> np.ndarray | None:
        """截取屏幕画面，自动选择最佳策略

        TD-396: 整条策略链在专用工作线程上执行并施加墙钟超时 — DXGI 的
        ``IDXGIOutputDuplication.AcquireNextFrame`` 在部分驱动/桌面会话状态下
        会忽略超时参数永久阻塞（COM 层不返回），把 pipeline 线程直接卡死。
        超时后截图线程被放弃、本实例短期内不再尝试截图（降级返回 None），
        pipeline 得以继续而不是永久挂起。

        Returns:
            BGR 格式的 numpy 数组，失败返回 None
        """
        if time.time() < getattr(self, "_shot_disabled_until", 0.0):
            return None
        try:
            future = _SHOT_EXECUTOR.submit(self._capture_impl)
        except RuntimeError:
            return None
        try:
            return future.result(timeout=3.0)
        except concurrent.futures.TimeoutError:
            logger.error(
                "截图链超时 (3s): 策略线程被放弃, 60s 内不再尝试 (%s)",
                self._get_window_class_name(),
            )
            self._shot_disabled_until = time.time() + 60.0
            return None
        except Exception as exc:  # noqa: BLE001 — capture failures are non-fatal
            logger.warning("截图链失败: %s", exc)
            return None

    def _capture_impl(self) -> np.ndarray | None:
        """实际策略链：按 fallback 顺序尝试各截图方法。"""
        method = (
            self._detect_best_method()
            if self._method == "auto"
            else self._method
        )

        capture_map = {
            self.WGC: self._capture_wgc,
            self.DXGI: self._capture_dxgi,
            self.GDI: self._capture_gdi,
            self.PRINTWINDOW: self._capture_printwindow,
        }

        all_methods = [self.WGC, self.DXGI, self.GDI, self.PRINTWINDOW]
        # Try the selected method first, then the rest in the preferred order.
        # This lets a game-window PrintWindow fallback to WGC/DXGI when it
        # returns a black frame.
        fallback_order = [method] + [m for m in all_methods if m != method]

        for current in fallback_order:
            try:
                result = capture_map[current]()
                if result is not None:
                    black_ratio = self._compute_black_ratio(result)
                    logger.info(
                        "截图方法尝试: method=%s, hwnd=%s, class=%s, shape=%s, black_ratio=%.3f",
                        current,
                        hex(self._hwnd) if self._hwnd else "none",
                        self._get_window_class_name(),
                        result.shape,
                        black_ratio,
                    )
                    if black_ratio > 0.95:
                        logger.warning(
                            "截图方法 %s 返回 %.1f%% 黑屏，尝试下一降级方案",
                            current, black_ratio * 100.0,
                        )
                        continue
                    self._best_method = current
                    logger.info(
                        "截图成功: method=%s, hwnd=%s, class=%s, shape=%s, black_ratio=%.3f",
                        current,
                        hex(self._hwnd) if self._hwnd else "none",
                        self._get_window_class_name(),
                        result.shape,
                        black_ratio,
                    )
                    return result
                else:
                    logger.info("截图方法 %s 返回 None", current)
            except Exception as exc:
                logger.warning("截图方法 %s 失败: %s", current, exc)

        logger.error(
            "所有截图方法均失败: hwnd=%s, class=%s, requested=%s",
            hex(self._hwnd) if self._hwnd else "none",
            self._get_window_class_name(),
            method,
        )
        return None

    def _compute_black_ratio(self, frame: np.ndarray) -> float:
        """计算黑屏像素占比，用于自动降级"""
        if frame.size == 0:
            return 1.0
        # A pixel is considered black when all channels are near zero.
        dark = np.all(frame < 15, axis=2)
        return float(np.mean(dark))

    @retry_screenshot()
    def _capture_wgc(self) -> np.ndarray | None:
        """WGC 高性能截图（Windows 10 1903+）"""
        try:
            from platforms.windows.wgc import Win32WGC
        except ImportError as exc:
            raise RuntimeError("WGC 模块不可用") from exc

        if self._hwnd is None:
            return None

        if self._wgc_instance is None:
            wgc = Win32WGC()
            if not wgc.initialize(self._hwnd):
                raise RuntimeError("WGC 初始化失败")
            self._wgc_instance = wgc

        return self._wgc_instance.capture()

    def _release_wgc(self) -> None:
        """释放 WGC 实例资源"""
        if self._wgc_instance:
            with contextlib.suppress(Exception):
                self._wgc_instance.release()
            self._wgc_instance = None

    @retry_screenshot()
    def _capture_dxgi(self) -> np.ndarray | None:
        """DXGI Desktop Duplication 截图（Windows 8+）

        Uses the pure-ctypes DXGICapture class (platforms.windows.dxgi_capture)
        which wraps IDXGIOutputDuplication for GPU-direct desktop capture.
        Falls back through the degradation chain if DXGI is unavailable.
        """
        try:
            from platforms.windows.dxgi_capture import DXGICapture
        except ImportError as exc:
            raise RuntimeError(f"DXGI 模块不可用: {exc}") from exc

        if self._dxgi_instance is None:
            cap = DXGICapture()
            hwnd = self._hwnd or 0
            if not cap.initialize(hwnd):
                raise RuntimeError("DXGI 初始化失败")
            self._dxgi_instance = cap

        return self._dxgi_instance.capture()

    def _release_dxgi(self) -> None:
        """释放 DXGI 实例资源"""
        if self._dxgi_instance:
            with contextlib.suppress(Exception):
                self._dxgi_instance.release()
            self._dxgi_instance = None

    @retry_screenshot()
    def _capture_gdi(self) -> np.ndarray | None:
        """GDI 截图（使用 ctypes 调用 BitBlt）

        When client_only=True, captures only the client area (excludes title
        bar / borders) using GetDC + GetClientRect. This matches the
        coordinate system expected by coord_transformer (client-physical
        pixels). When client_only=False (legacy), uses GetWindowDC +
        GetWindowRect to include non-client chrome.
        """
        hwnd = user32.GetDesktopWindow() if not self._hwnd else self._hwnd

        if self._client_only and self._hwnd:
            # Client-area capture: GetDC returns client-area DC, GetClientRect
            # gives client dims. BitBlt origin (0,0) is the client top-left.
            rect = ctypes.wintypes.RECT()
            user32.GetClientRect(self._hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
        else:
            # Full-window capture (legacy): GetWindowRect includes title bar.
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top

        if width <= 0 or height <= 0:
            return None

        # GetDC returns client-area DC; GetWindowDC returns full-window DC.
        # When client_only=True we want GetDC so BitBlt reads client pixels.
        src_dc = user32.GetDC(self._hwnd) if self._client_only and self._hwnd else user32.GetWindowDC(hwnd)
        dst_dc = gdi32.CreateCompatibleDC(src_dc)
        bitmap = gdi32.CreateCompatibleBitmap(src_dc, width, height)
        gdi32.SelectObject(dst_dc, bitmap)

        try:
            srccopy = 0x00CC0020
            gdi32.BitBlt(dst_dc, 0, 0, width, height, src_dc, 0, 0, srccopy)

            bmi_fields = [
                ("biSize", ctypes.wintypes.DWORD),
                ("biWidth", ctypes.wintypes.LONG),
                ("biHeight", ctypes.wintypes.LONG),
                ("biPlanes", ctypes.wintypes.WORD),
                ("biBitCount", ctypes.wintypes.WORD),
                ("biCompression", ctypes.wintypes.DWORD),
                ("biSizeImage", ctypes.wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.wintypes.LONG),
                ("biYPelsPerMeter", ctypes.wintypes.LONG),
                ("biClrUsed", ctypes.wintypes.DWORD),
                ("biClrImportant", ctypes.wintypes.DWORD),
            ]
            bitmap_info_header = type(
                "BITMAPINFOHEADER", (ctypes.Structure,), {"_fields_": bmi_fields}
            )
            bi = bitmap_info_header()
            bi.biSize = ctypes.sizeof(bitmap_info_header)
            bi.biWidth = width
            bi.biHeight = -height  # top-down
            bi.biPlanes = 1
            bi.biBitCount = 32
            bi.biCompression = 0  # BI_RGB

            buf_size = width * height * 4
            buf = ctypes.create_string_buffer(buf_size)

            gdi32.GetDIBits(
                dst_dc, bitmap, 0, height,
                buf, ctypes.byref(bi), 0  # DIB_RGB_COLORS
            )

            img = np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 4))
            img_bgr = img[:, :, :3].copy()

            return img_bgr
        finally:
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(dst_dc)
            user32.ReleaseDC(hwnd, src_dc)

    @retry_screenshot()
    def _capture_printwindow(self) -> np.ndarray | None:
        """PrintWindow 截图（支持后台窗口）

        When client_only=True, uses GetClientRect + PW_CLIENTONLY flag to
        capture only the client area (skips title bar / borders). This is
        preferred for LDPlayer and other emulators where title bar pixels
        would otherwise pollute ROI matching.
        """
        if not self._hwnd:
            return None

        if self._client_only:
            # Client-area capture: use GetClientRect + PW_CLIENTONLY
            rect = ctypes.wintypes.RECT()
            user32.GetClientRect(self._hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
        else:
            # Full-window capture (legacy behavior): GetWindowRect
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(self._hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top

        if width <= 0 or height <= 0:
            return None

        src_dc = user32.GetWindowDC(self._hwnd)
        dst_dc = gdi32.CreateCompatibleDC(src_dc)
        bitmap = gdi32.CreateCompatibleBitmap(src_dc, width, height)
        gdi32.SelectObject(dst_dc, bitmap)

        try:
            # PW_RENDERFULLCONTENT = 0x02 (render full content even for occluded windows)
            # PW_CLIENTONLY = 0x01 (clip to client area, skip non-client region)
            # Combine both when client_only=True; otherwise use RENDERFULLCONTENT only.
            pw_render_full_content = 0x02
            pw_client_only = 0x01
            flags = pw_render_full_content | (pw_client_only if self._client_only else 0)
            user32.PrintWindow(self._hwnd, dst_dc, flags)

            bmi_fields = [
                ("biSize", ctypes.wintypes.DWORD),
                ("biWidth", ctypes.wintypes.LONG),
                ("biHeight", ctypes.wintypes.LONG),
                ("biPlanes", ctypes.wintypes.WORD),
                ("biBitCount", ctypes.wintypes.WORD),
                ("biCompression", ctypes.wintypes.DWORD),
                ("biSizeImage", ctypes.wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.wintypes.LONG),
                ("biYPelsPerMeter", ctypes.wintypes.LONG),
                ("biClrUsed", ctypes.wintypes.DWORD),
                ("biClrImportant", ctypes.wintypes.DWORD),
            ]
            bitmap_info_header = type(
                "BITMAPINFOHEADER", (ctypes.Structure,), {"_fields_": bmi_fields}
            )
            bi = bitmap_info_header()
            bi.biSize = ctypes.sizeof(bitmap_info_header)
            bi.biWidth = width
            bi.biHeight = -height
            bi.biPlanes = 1
            bi.biBitCount = 32
            bi.biCompression = 0

            buf_size = width * height * 4
            buf = ctypes.create_string_buffer(buf_size)

            gdi32.GetDIBits(
                dst_dc, bitmap, 0, height,
                buf, ctypes.byref(bi), 0
            )

            img = np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 4))
            img_bgr = img[:, :, :3].copy()

            return img_bgr
        finally:
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(dst_dc)
            user32.ReleaseDC(self._hwnd, src_dc)

    def _detect_best_method(self) -> str:
        """检测最佳截图方式

        优先级（自上而下）：
        1. 游戏类窗口（UnityWndClass/UnrealWindow 等）→ 直接返回 PrintWindow。
           原因：GDI BitBlt 只能截取屏幕可见内容，被遮挡时截到的是前景窗口
           的像素；而游戏窗口在自动化场景下经常被 IDE/浏览器遮挡。PrintWindow
           通过 WM_PRINT 让目标窗口自己渲染，可以正确截取被遮挡的游戏画面。
           benchmark 只测速度不测可靠性，对游戏窗口会选 GDI（最快但截不到遮挡）。
        2. 非游戏窗口 → 跑 benchmark 选最快方法（WGC/DXGI/GDI）。
        3. benchmark 失败且 hwnd 存在 → PrintWindow（兜底）。
        4. 无 hwnd → GDI（截桌面）。
        """
        if self._best_method:
            return self._best_method

        # 1. Game window heuristic — prefer PrintWindow (N141).
        # GDI BitBlt can only capture visible screen pixels, so when a game
        # window is occluded by an IDE/browser it captures the foreground
        # window instead. WGC can work for occluded GPU windows on Windows 10
        # 1903+, but empirically it is unreliable across driver/config combos.
        # PrintWindow sends WM_PRINT to the target window and is the stable
        # choice for UnityWndClass / UnrealWindow / etc. If PrintWindow fails
        # or returns a black frame, the fallback chain below will try WGC /
        # GDI / DXGI so we never get stuck on a single method.
        if self._hwnd and self._is_game_window():
            logger.info(
                "检测到游戏引擎窗口类，优先使用 PrintWindow（被遮挡游戏画面更可靠）"
            )
            self._best_method = self.PRINTWINDOW
            return self.PRINTWINDOW

        # 2. Run benchmark for non-game windows.
        if self._benchmark_results is None and self._hwnd:
            try:
                logger.info("首次连接，开始竞速测试以选择最佳截图方式...")
                from platforms.windows.benchmark import benchmark_capture_methods

                self._benchmark_results = benchmark_capture_methods(self._hwnd)
            except Exception as exc:
                logger.info("竞速测试跳过: %s", exc)
                self._benchmark_results = []

        if self._benchmark_results:
            # benchmark_capture_methods returns BenchmarkResult NamedTuples
            # sorted reliable-first then by speed. [0] is the fastest
            # reliable method. .method / [0] both give the name (NamedTuple
            # supports both attribute and index access).
            best = self._benchmark_results[0]
            fastest = best.method if hasattr(best, "method") else best[0]
            self._best_method = fastest
            # Log reliability info to surface unreliable-but-fast methods
            # (e.g., GDI on occluded windows) that were demoted.
            if hasattr(best, "is_reliable") and hasattr(best, "reliability"):
                logger.info(
                    "竞速测试结果: 最佳方法=%s (latency=%.1fms, reliability=%.3f, "
                    "is_reliable=%s)",
                    fastest, best.latency_ms, best.reliability, best.is_reliable,
                )
                # If the chosen method has unreliable siblings, log them
                # for debugging.
                unreliable = [
                    r for r in self._benchmark_results
                    if hasattr(r, "is_reliable") and not r.is_reliable
                ]
                if unreliable:
                    logger.warning(
                        "以下截图方法不可靠 (与 PrintWindow ground-truth 差异大)，"
                        "已降级排序: %s",
                        [(r.method, f"rel={r.reliability:.3f}") for r in unreliable],
                    )
            else:
                logger.info("竞速测试结果: 最佳方法=%s", fastest)
            return fastest

        # 3. Benchmark failed but hwnd exists — PrintWindow is the safest
        # fallback (works for occluded windows).
        if self._hwnd:
            return self.PRINTWINDOW

        # 4. No hwnd — desktop capture, use GDI.
        return self.GDI

    def _get_window_class_name(self) -> str:
        """Return the class name of the bound hwnd, or empty string on failure."""
        if not self._hwnd:
            return ""
        try:
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW.argtypes = [
                ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int,
            ]
            user32.GetClassNameW.restype = ctypes.c_int
            if user32.GetClassNameW(self._hwnd, class_name, 256) > 0:
                return class_name.value
        except Exception as exc:
            logger.debug("GetClassNameW failed: %s", exc)
        return ""

    def _is_game_window(self) -> bool:
        """Check if the bound hwnd belongs to a known game engine window class.

        Returns False if hwnd is not bound or class retrieval fails.
        """
        return self._get_window_class_name() in _GAME_WINDOW_CLASSES
