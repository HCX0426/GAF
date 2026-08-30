import contextlib
import importlib
import io
import logging
import socket
import struct
import time
from typing import Any

import numpy as np
from core.retry import retry_screenshot
from devices.base import BaseDevice, require_operable
from monitor.resources import record_screenshot
from PIL import Image

from .adb_constants import (
    ASCREENCAP_BMZ1_MAGIC,
    ASCREENCAP_METHOD,
    ASCREENCAP_NC_METHOD,
    ASCREENCAP_REMOTE_PATH,
    DROIDCAST_METHOD,
    DROIDCAST_RAW_METHOD,
    LDOPENGL_METHOD,
    NEMU_IPC_DLL_TIMEOUT_SEC,
    NEMU_IPC_METHOD,
    NEMU_METHOD,
    SCRCPY_METHOD,
    SCREENCAP_METHOD,
    SCREENCAP_NC_METHOD,
    U2_METHOD,
)

logger = logging.getLogger(__name__)


class ADBCaptureMixin(BaseDevice):
    """ADBDevice mixin — see devices/adb/device.py for full class (s36 split)."""

    @require_operable
    def capture_screen(self) -> np.ndarray | None:
        """截取屏幕画面（nemu→scrcpy→DroidCast_raw→DroidCast→u2→screencap 降级链）

        Returns:
            BGR 格式的 numpy 数组
        """
        result = None

        if self._screenshot_method != "auto":
            result = self._capture_by_method(self._screenshot_method)
        elif self._best_screenshot_method:
            try:
                result = self._capture_by_method(self._best_screenshot_method)
                if result is None:
                    logger.debug("最佳方法 %s 返回空结果，重新降级", self._best_screenshot_method)
                    self._best_screenshot_method = None
            except Exception:
                logger.debug("最佳方法 %s 失败，重新降级", self._best_screenshot_method)
                self._best_screenshot_method = None

        if result is None and self._screenshot_method == "auto":
            fallback_order = [
                NEMU_IPC_METHOD, NEMU_METHOD, LDOPENGL_METHOD, SCRCPY_METHOD, DROIDCAST_RAW_METHOD,
                DROIDCAST_METHOD, U2_METHOD, ASCREENCAP_NC_METHOD, ASCREENCAP_METHOD,
                SCREENCAP_NC_METHOD, SCREENCAP_METHOD,
            ]
            for method in fallback_order:
                try:
                    result = self._capture_by_method(method)
                    if result is not None:
                        self._best_screenshot_method = method
                        break
                except Exception as exc:
                    logger.warning("截图方法 %s 失败: %s", method, exc)

        if result is None:
            logger.error("所有截图方法均失败")
            return None

        record_screenshot()
        return result

    def _capture_by_method(self, method: str) -> np.ndarray | None:
        """根据指定方法截图

        Args:
            method: 截图方法名称

        Returns:
            BGR 格式的 numpy 数组
        """
        method_map = {
            SCREENCAP_METHOD: self._capture_screencap,
            SCREENCAP_NC_METHOD: self._capture_screencap_nc,
            ASCREENCAP_METHOD: self._capture_ascreencap,
            ASCREENCAP_NC_METHOD: self._capture_ascreencap_nc,
            DROIDCAST_METHOD: self._capture_droidcast,
            DROIDCAST_RAW_METHOD: self._capture_droidcast_raw,
            U2_METHOD: self._capture_uiautomator2,
            SCRCPY_METHOD: self._capture_scrcpy,
            NEMU_METHOD: self._capture_nemu,
            NEMU_IPC_METHOD: self._capture_nemu_ipc,
            LDOPENGL_METHOD: self._capture_ldopengl,
        }
        handler = method_map.get(method)
        if handler:
            return handler()
        logger.warning("未知截图方法: %s", method)
        return self._capture_screencap()

    @retry_screenshot()
    def _capture_nemu(self) -> np.ndarray | None:
        """使用 MuMu 模拟器共享内存截图（nemu）

        通过共享内存直接读取 MuMu 模拟器的显示缓冲区，
        延迟极低（5-15ms），仅适用于 MuMu 模拟器

        Returns:
            BGR 格式的 numpy 数组
        """
        try:
            import mmap

            nemu_hwnd = self._find_nemu_window()
            if not nemu_hwnd:
                raise RuntimeError("未找到 MuMu 模拟器窗口")

            shared_memory_name = "MuMuSharedMemory"
            buf_size = 1920 * 1080 * 4

            with mmap.mmap(-1, buf_size, tagname=shared_memory_name, access=mmap.ACCESS_READ) as mm:
                raw_data = mm.read(buf_size)
                # Detect all-zero buffer (MuMu shared memory not yet initialized).
                # mmap with tagname=-1 creates a page-file-backed mapping that
                # silently returns zero bytes when MuMu hasn't written yet,
                # which would produce a black image and pollute downstream OCR.
                if not any(raw_data[:4096]):  # sample first 4KB for speed
                    raise RuntimeError(
                        "MuMu 共享内存未初始化（全零），MuMu 可能未完全启动"
                    )
                img = np.frombuffer(raw_data, dtype=np.uint8).reshape((1080, 1920, 4))
                return img[:, :, :3][:, :, ::-1].copy()

        except ImportError as exc:
            raise NotImplementedError("mmap 模块不可用") from exc
        except Exception as exc:
            raise RuntimeError(f"nemu 共享内存截图失败: {exc}") from exc

    @retry_screenshot()
    def _capture_droidcast_raw(self) -> np.ndarray | None:
        """使用 DroidCast_raw 截图（原始帧传输 + lz4 解压）

        通过 HTTP 请求获取 DroidCast_raw 推送的原始帧数据，
        使用 lz4 解压后还原为图像，延迟低于 DroidCast PNG 模式

        Returns:
            BGR 格式的 numpy 数组
        """
        try:
            import requests

            url = f"http://127.0.0.1:{self._droidcast_port}/screenshot"
            response = requests.get(url, timeout=5)

            if response.status_code != 200:
                raise RuntimeError(f"DroidCast_raw 返回异常状态码: {response.status_code}")

            content_type = response.headers.get("Content-Type", "")

            if "lz4" in content_type or len(response.content) < 500000:
                try:
                    import lz4.frame

                    decompressed = lz4.frame.decompress(response.content)
                    img_array = np.frombuffer(decompressed, dtype=np.uint8)
                    expected_size = 1280 * 720 * 4
                    if img_array.size >= expected_size:
                        img_array = img_array[:expected_size].reshape((720, 1280, 4))
                        return img_array[:, :, :3][:, :, ::-1].copy()
                except ImportError:
                    logger.debug("lz4 库未安装，尝试 PNG 解码")
                except Exception:
                    logger.debug("lz4 解压失败，尝试 PNG 解码")

            try:
                img = Image.open(io.BytesIO(response.content))
                img_array = np.array(img)
                if img_array.ndim == 3 and img_array.shape[2] == 4:
                    img_array = img_array[:, :, :3]
                return img_array[:, :, ::-1].copy()
            except Exception:
                logger.debug("PNG 解码失败")
                return None

        except ImportError as exc:
            raise NotImplementedError("requests 库未安装") from exc
        except Exception as exc:
            raise RuntimeError(f"DroidCast_raw 截图失败: {exc}") from exc

    def _capture_scrcpy(self) -> np.ndarray | None:
        """使用 scrcpy 投屏截图（如果可用）

        优先使用 PyAV 解码 H.264 视频流（低延迟），
        降级到 python-scrcpy 的 last_frame 接口

        Returns:
            BGR 格式的 numpy 数组
        """
        try:
            return self._capture_scrcpy_pyav()
        except Exception as exc:
            logger.debug("scrcpy PyAV 模式失败，降级到 python-scrcpy: %s", exc)

        return self._capture_scrcpy_fallback()

    @retry_screenshot()
    def _capture_scrcpy_pyav(self) -> np.ndarray | None:
        """使用 PyAV 解码 scrcpy H.264 视频流

        通过 PyAV 直接解码 scrcpy 推送的 H.264 NAL 单元，
        延迟极低（10-30ms）

        Returns:
            BGR 格式的 numpy 数组
        """
        if importlib.util.find_spec("av") is None:
            raise NotImplementedError("PyAV 库未安装，请安装 av")

        if self._scrcpy_client is None:
            from scrcpy import Client

            self._scrcpy_client = Client(
                device=self._serial,
                max_fps=30,
                bitrate=8000000,
                no_window=True,
                encoder_name="OMX.google.h264.encoder",
            )
            self._scrcpy_client.start()
            time.sleep(0.5)

        frame = self._scrcpy_client.last_frame
        if frame is None:
            raise RuntimeError("scrcpy 尚未获取到帧数据")

        if isinstance(frame, np.ndarray):
            if frame.ndim == 3 and frame.shape[2] == 4:
                frame = frame[:, :, :3]
            return frame[:, :, ::-1].copy()

        img_array = np.array(frame)
        if img_array.ndim == 3 and img_array.shape[2] == 4:
            img_array = img_array[:, :, :3]
        return img_array[:, :, ::-1].copy()

    @retry_screenshot()
    def _capture_scrcpy_fallback(self) -> np.ndarray | None:
        """使用 python-scrcpy 的 last_frame 接口截图（降级方案）

        Returns:
            BGR 格式的 numpy 数组
        """
        try:
            from scrcpy import Client

            if self._scrcpy_client is None:
                self._scrcpy_client = Client(
                    device=self._serial,
                    max_fps=30,
                    bitrate=8000000,
                    no_window=True,
                )
                self._scrcpy_client.start()

            frame = self._scrcpy_client.last_frame
            if frame is None:
                logger.warning("scrcpy 尚未获取到帧数据")
                return None

            if isinstance(frame, np.ndarray):
                if frame.ndim == 3 and frame.shape[2] == 4:
                    frame = frame[:, :, :3]
                return frame[:, :, ::-1].copy()

            img_array = np.array(frame)
            if img_array.ndim == 3 and img_array.shape[2] == 4:
                img_array = img_array[:, :, :3]
            return img_array[:, :, ::-1].copy()

        except ImportError as exc:
            raise NotImplementedError("scrcpy 库未安装，请安装 python-scrcpy") from exc
        except Exception as exc:
            self._scrcpy_client = None
            raise RuntimeError(f"scrcpy 截图失败: {exc}") from exc

    @retry_screenshot()
    def _capture_droidcast(self) -> np.ndarray | None:
        """使用 DroidCast_raw 截图（HTTP 方式）

        通过 HTTP 请求获取 DroidCast 推送的截图数据

        Returns:
            BGR 格式的 numpy 数组
        """
        try:
            import requests

            url = f"http://127.0.0.1:{self._droidcast_port}/screenshot"
            response = requests.get(url, timeout=5)

            if response.status_code != 200:
                raise RuntimeError(f"DroidCast 返回异常状态码: {response.status_code}")

            img = Image.open(io.BytesIO(response.content))
            img_array = np.array(img)
            if img_array.ndim == 3 and img_array.shape[2] == 4:
                img_array = img_array[:, :, :3]
            return img_array[:, :, ::-1].copy()

        except ImportError as exc:
            raise NotImplementedError("requests 库未安装，请安装 requests") from exc
        except Exception as exc:
            raise RuntimeError(f"DroidCast 截图失败: {exc}") from exc

    @retry_screenshot()
    def _capture_uiautomator2(self) -> np.ndarray | None:
        """使用 uiautomator2 截图

        通过 uiautomator2 的 screenshot 接口获取画面

        Returns:
            BGR 格式的 numpy 数组
        """
        try:
            import uiautomator2 as u2

            if self._u2_device is None:
                self._u2_device = u2.connect(self._serial)

            img = self._u2_device.screenshot()
            img_array = np.array(img)
            if img_array.ndim == 3 and img_array.shape[2] == 4:
                img_array = img_array[:, :, :3]
            return img_array[:, :, ::-1].copy()

        except ImportError as exc:
            raise NotImplementedError("uiautomator2 库未安装，请安装 uiautomator2") from exc
        except Exception as exc:
            self._u2_device = None
            raise RuntimeError(f"uiautomator2 截图失败: {exc}") from exc

    @retry_screenshot()
    def _capture_screencap_nc(self) -> np.ndarray | None:
        """使用 adb screencap + nc (netcat) 截图

        通过 adb forward 端口转发，在设备端执行 screencap 并通过 nc 传输到本地，
        比 adb pull 方式更快（避免 PNG 编解码开销）

        Returns:
            BGR 格式的 numpy 数组
        """
        if not self._device:
            return None

        try:
            import threading

            local_port = 11112
            self._device.forward(f"tcp:{local_port}", "tcp:11112")
            self._forwarded_local_ports.add(local_port)

            shell_done = threading.Event()

            def _run_nc():
                """在独立线程中执行 nc 监听，避免与连接代码死锁"""
                with contextlib.suppress(Exception):
                    self._device.shell(
                        "screencap 2>/dev/null | nc -l -p 11112 2>/dev/null",
                        timeout=5,
                    )
                shell_done.set()

            t = threading.Thread(target=_run_nc, daemon=True)
            t.start()
            time.sleep(0.2)

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            try:
                sock.connect(("127.0.0.1", local_port))

                chunks = []
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
            finally:
                sock.close()

            raw = b"".join(chunks)
            if len(raw) < 12:
                raise RuntimeError(f"screencap+nc 返回数据过短: {len(raw)} bytes")

            width = struct.unpack("<I", raw[0:4])[0]
            height = struct.unpack("<I", raw[4:8])[0]
            pixel_format = struct.unpack("<I", raw[8:12])[0]

            header_size = 12
            if pixel_format == 1:
                channel = 4
            elif pixel_format == 2:
                channel = 3
                header_size = 16
            else:
                channel = 4

            pixel_data = raw[header_size:]
            expected_size = width * height * channel
            if len(pixel_data) < expected_size:
                raise RuntimeError(
                    f"screencap+nc 数据不完整: 期望 {expected_size}，实际 {len(pixel_data)}"
                )

            img_array = np.frombuffer(pixel_data[:expected_size], dtype=np.uint8)
            img_array = img_array.reshape((height, width, channel))

            if channel == 4:
                img_array = img_array[:, :, :3]

            return img_array[:, :, ::-1].copy()

        except Exception as exc:
            raise RuntimeError(f"screencap+nc 截图失败: {exc}") from exc

    @retry_screenshot()
    def _capture_screencap(self) -> np.ndarray | None:
        """使用 adb shell screencap 截图（最基础方式）

        Returns:
            BGR 格式的 numpy 数组
        """
        if not self._device:
            return None
        raw = self._device.screencap()
        img = Image.open(io.BytesIO(raw))
        img_array = np.array(img)
        if img_array.ndim == 3 and img_array.shape[2] == 4:
            img_array = img_array[:, :, :3]
        return img_array[:, :, ::-1].copy()

    def _ascreencap_reposition_byte_pointer(self, byte_array: bytes) -> bytes:
        """Reposition byte pointer to BMZ1 magic header.

        Some devices emit linker warnings before the actual payload, so we
        scan for the BMZ1 magic and remember the offset for subsequent calls.
        """
        while byte_array[self._ascreencap_bytepointer:self._ascreencap_bytepointer + 4] != b"BMZ1":
            self._ascreencap_bytepointer += 1
            if self._ascreencap_bytepointer >= len(byte_array):
                self._ascreencap_bytepointer = 0
                raise RuntimeError(
                    "Repositioning byte pointer failed, corrupted aScreenCap data received"
                )
        return byte_array[self._ascreencap_bytepointer:]

    def _ascreencap_uncompress(self, screenshot: bytes) -> np.ndarray:
        """Uncompress ascreencap BMZ1 stream into a BGR numpy array.

        Header layout (5 uint32, 20 bytes):
            magic, uncompressed_size, _, width, height
        Payload is lz4-compressed raw BGR pixels.
        """
        try:
            import cv2
            from lz4.block import decompress
        except ImportError as exc:
            raise NotImplementedError(
                "ascreencap requires lz4 and opencv-python, please install them"
            ) from exc

        raw_compressed = self._ascreencap_reposition_byte_pointer(screenshot)
        header = np.frombuffer(raw_compressed[0:20], dtype=np.uint32)
        if header[0] != ASCREENCAP_BMZ1_MAGIC:
            header = header.byteswap()
            if header[0] != ASCREENCAP_BMZ1_MAGIC:
                raise RuntimeError(
                    f"aScreenCap header verification failure, corrupted image received. "
                    f"HEADER IN HEX = {header.tobytes().hex()}"
                )

        _, uncompressed_size, _, width, height = header
        channel = 3
        data = decompress(raw_compressed[20:], uncompressed_size=uncompressed_size)

        image = np.frombuffer(data, dtype=np.uint8)
        if image is None or image.size == 0:
            raise RuntimeError("Empty image after reading from buffer")

        try:
            image = image[-int(width * height * channel):].reshape(height, width, channel)
        except ValueError as exc:
            raise RuntimeError(f"Cannot reshape ascreencap payload: {exc}") from exc

        # np.frombuffer returns a read-only view; flip/cvtColor need a writable copy
        image = cv2.flip(image, 0)
        cv2.cvtColor(image, cv2.COLOR_BGR2RGB, dst=image)
        return image

    def _ascreencap_load_screenshot(self, screenshot: bytes, method: int) -> bytes:
        """Normalize line endings in ascreencap stdout.

        Some devices mangle binary stdout with CRLF translation; method 0/1/2
        try different normalization strategies.
        """
        if method == 0:
            return screenshot
        if method == 1:
            return screenshot.replace(b"\r\n", b"\n")
        if method == 2:
            return screenshot.replace(b"\r\r\n", b"\n")
        raise ValueError(f"Unknown ascreencap load method: {method}")

    @retry_screenshot()
    def _capture_ascreencap(self) -> np.ndarray | None:
        """使用 ascreencap 原生二进制截图（BMZ1 + lz4 压缩）

        通过 adb shell 调用设备端 ascreencap 二进制，输出 BMZ1 压缩流，
        本地 lz4 解压后还原为 BGR 图像。比 screencap -p 更快。

        Returns:
            BGR 格式的 numpy 数组
        """
        if not self._device:
            return None
        if not self._ascreencap_available:
            raise NotImplementedError("ascreencap binary not available on device")

        try:
            from lz4.block import LZ4BlockError  # noqa: F401
        except ImportError as exc:
            raise NotImplementedError(
                "ascreencap requires lz4, please install lz4"
            ) from exc

        try:
            content = self._device.shell(
                f"{ASCREENCAP_REMOTE_PATH} --pack 2 --stdout",
                timeout=5,
            )
        except Exception as exc:
            raise RuntimeError(f"ascreencap shell 调用失败: {exc}") from exc

        if isinstance(content, str):
            content = content.encode("latin-1", errors="ignore")

        # Try different line-ending normalization strategies
        for method in (0, 1, 2):
            try:
                normalized = self._ascreencap_load_screenshot(content, method)
                return self._ascreencap_uncompress(normalized)
            except RuntimeError:
                self._ascreencap_bytepointer = 0
                continue
            except Exception:
                self._ascreencap_bytepointer = 0
                continue

        raise RuntimeError("ascreencap 解压失败：所有 line-ending 策略均失败")

    @retry_screenshot()
    def _capture_ascreencap_nc(self) -> np.ndarray | None:
        """使用 ascreencap + netcat 隧道截图

        通过 adb forward 端口转发，在设备端执行 ascreencap 并通过 nc 传输到本地，
        避免 adb shell 的 CRLF 转换问题，比纯 ascreencap 更稳定。

        Returns:
            BGR 格式的 numpy 数组
        """
        if not self._device:
            return None
        if not self._ascreencap_available:
            raise NotImplementedError("ascreencap binary not available on device")

        try:
            import threading

            from lz4.block import LZ4BlockError  # noqa: F401
        except ImportError as exc:
            raise NotImplementedError(
                "ascreencap_nc requires lz4, please install lz4"
            ) from exc

        local_port = 11113
        self._device.forward(f"tcp:{local_port}", "tcp:11113")
        self._forwarded_local_ports.add(local_port)

        shell_done = threading.Event()

        def _run_nc():
            with contextlib.suppress(Exception):
                self._device.shell(
                    f"{ASCREENCAP_REMOTE_PATH} --pack 2 --stdout | nc -l -p 11113 2>/dev/null",
                    timeout=5,
                )
            shell_done.set()

        t = threading.Thread(target=_run_nc, daemon=True)
        t.start()
        time.sleep(0.2)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            sock.connect(("127.0.0.1", local_port))
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            sock.close()

        raw = b"".join(chunks)
        if len(raw) < 500:
            raise RuntimeError(f"ascreencap+nc 返回数据过短: {len(raw)} bytes")

        return self._ascreencap_uncompress(raw)

    def _load_nemu_ipc_lib(self) -> Any:
        """Load MuMu12 external_renderer_ipc.dll via the platforms.windows wrapper.

        Delegates DLL discovery and loading to NemuIpcLib (in
        platforms/windows/nemu_ipc.py) so this module does not touch
        ctypes.CDLL directly (GAF backend-conventions §11). Returns a
        cached NemuIpcLib instance or raises NotImplementedError on
        non-Windows platforms or missing DLL.

        The returned NemuIpcLib instance is a drop-in replacement for
        the raw ctypes.CDLL: it exposes nemu_connect / nemu_disconnect /
        nemu_capture_display / nemu_input_event_touch_down /
        nemu_input_event_touch_up as bound methods with identical
        signatures, so callers (including nemu_keepalive.make_ping_fn)
        can use it transparently.
        """
        if self._nemu_ipc_lib is not None:
            return self._nemu_ipc_lib

        from platforms.windows.nemu_ipc import NemuIpcLib

        self._nemu_ipc_lib = NemuIpcLib.from_nemu_folder(self._nemu_folder)
        return self._nemu_ipc_lib

    def _nemu_ipc_connect(self) -> int:
        """Connect to MuMu12 emulator via NemuIpc.

        Returns the connection id (>0) on success. Raises RuntimeError on
        connection failure.

        P1-2: Emits human-readable error messages via format_nemu_error().
        P1-3: Starts the keepalive thread after a successful connection.
        """
        # Return cached connection id without reloading DLL
        if self._nemu_ipc_connect_id > 0:
            return self._nemu_ipc_connect_id

        from core.timeout import TimeoutError, call_with_timeout
        from platforms.windows.nemu_ipc_errors import (
            format_nemu_error,
            get_error_recovery_hint,
        )

        lib = self._load_nemu_ipc_lib()
        try:
            connect_id = call_with_timeout(
                lib.nemu_connect,
                NEMU_IPC_DLL_TIMEOUT_SEC,
                self._nemu_folder.encode("utf-8"),
                self._nemu_instance_id,
            )
        except TimeoutError as exc:
            raise RuntimeError(
                f"NemuIpc nemu_connect timed out after {NEMU_IPC_DLL_TIMEOUT_SEC}s"
            ) from exc
        if connect_id == 0:
            # nemu_connect returns 0 on failure — the underlying RPC error
            # is not surfaced, so emit a generic message with recovery hint.
            raise RuntimeError(
                "NemuIpc nemu_connect returned 0 — emulator not running, "
                "wrong nemu_folder, or emulator still booting"
            )
        if connect_id < 0:
            # Negative return codes map to Windows RPC errors.
            hint = get_error_recovery_hint(connect_id) or ""
            raise RuntimeError(
                format_nemu_error(connect_id, context="nemu_connect")
                + (f" — {hint}" if hint else "")
            )
        self._nemu_ipc_connect_id = connect_id
        logger.info("NemuIpc connected: id=%s", connect_id)

        # P1-3: Start keepalive thread to prevent idle-timeout disconnects.
        self._start_nemu_keepalive(lib)

        return connect_id

    def _nemu_ipc_disconnect(self) -> None:
        """Disconnect from MuMu12 emulator.

        P1-3: Stops the keepalive thread before disconnecting to avoid
        a race where the ping loop fires between releasing the connect_id
        and clearing the local field.
        """
        # P1-3: Stop keepalive first to prevent ping-after-disconnect errors.
        self._stop_nemu_keepalive()

        if self._nemu_ipc_connect_id == 0 or self._nemu_ipc_lib is None:
            return
        try:
            self._nemu_ipc_lib.nemu_disconnect(self._nemu_ipc_connect_id)
        except Exception as exc:
            logger.debug("NemuIpc disconnect error: %s", exc)
        self._nemu_ipc_connect_id = 0

    def _start_nemu_keepalive(self, lib: Any) -> None:
        """P1-3: Start the NemuIpc keepalive thread (idempotent).

        Args:
            lib: Loaded external_renderer_ipc.dll CDLL instance.
        """
        from platforms.windows.nemu_keepalive import (
            DEFAULT_KEEPALIVE_INTERVAL_SEC,
            NemuIpcKeepalive,
            make_ping_fn,
        )

        # Stop any existing keepalive before starting a new one.
        self._stop_nemu_keepalive()

        ping_fn = make_ping_fn(
            lib,
            connect_id_getter=lambda: self._nemu_ipc_connect_id,
            timeout_sec=NEMU_IPC_DLL_TIMEOUT_SEC,
        )

        def _on_ping_failure(ret_code: int) -> None:
            from platforms.windows.nemu_ipc_errors import is_recoverable_error
            logger.warning(
                "NemuIpc keepalive ping failed (ret=%d); recoverable=%s",
                ret_code,
                is_recoverable_error(ret_code),
            )
            # Force reconnect on recoverable errors; ignore transient ones.
            # The next screenshot call will trigger _nemu_ipc_connect().
            if is_recoverable_error(ret_code):
                logger.info("Forcing NemuIpc reconnect due to keepalive failure")
                # Stop keepalive before clearing state to avoid races.
                self._stop_nemu_keepalive()
                self._nemu_ipc_connect_id = 0

        self._nemu_keepalive = NemuIpcKeepalive(
            ping_fn=ping_fn,
            interval_sec=DEFAULT_KEEPALIVE_INTERVAL_SEC,
            on_failure=_on_ping_failure,
        )
        self._nemu_keepalive.start()

    def _stop_nemu_keepalive(self) -> None:
        """P1-3: Stop the NemuIpc keepalive thread (idempotent)."""
        if self._nemu_keepalive is not None:
            try:
                self._nemu_keepalive.stop()
            except Exception as exc:
                logger.debug("NemuIpc keepalive stop error: %s", exc)
            self._nemu_keepalive = None

    def _nemu_ipc_get_resolution(self) -> tuple[int, int]:
        """Query emulator resolution via nemu_capture_display with null pixels pointer.

        P1-2: Emits human-readable error messages via format_nemu_error()
        and triggers disconnect + reconnect on recoverable errors.
        """
        from core.timeout import TimeoutError, call_with_timeout
        from platforms.windows.nemu_ipc_errors import (
            format_nemu_error,
            is_recoverable_error,
        )

        if self._nemu_ipc_connect_id == 0:
            self._nemu_ipc_connect()
        lib = self._load_nemu_ipc_lib()

        # B012: use NemuIpcLib pointer factory methods instead of importing
        # ctypes directly in this non-platform module.
        width_ptr = lib.make_int_ptr(0)
        height_ptr = lib.make_int_ptr(0)
        nullptr = lib.make_null_int_ptr()

        try:
            ret = call_with_timeout(
                lib.nemu_capture_display,
                NEMU_IPC_DLL_TIMEOUT_SEC,
                self._nemu_ipc_connect_id,
                0,  # display_id
                0,  # length (0 = query only)
                width_ptr,
                height_ptr,
                nullptr,
            )
        except TimeoutError as exc:
            self._nemu_ipc_disconnect()
            raise RuntimeError(
                f"nemu_capture_display timed out during get_resolution "
                f"after {NEMU_IPC_DLL_TIMEOUT_SEC}s"
            ) from exc
        if ret != 0:
            # P1-2: Surface the actual Windows RPC error code.
            msg = format_nemu_error(ret, context="nemu_capture_display(get_resolution)")
            if is_recoverable_error(ret):
                logger.warning("NemuIpc recoverable error — forcing reconnect: %s", msg)
                self._nemu_ipc_disconnect()
            raise RuntimeError(msg)
        self._nemu_ipc_width = lib.deref_int_ptr(width_ptr)
        self._nemu_ipc_height = lib.deref_int_ptr(height_ptr)
        return self._nemu_ipc_width, self._nemu_ipc_height

    @retry_screenshot()
    def _capture_nemu_ipc(self) -> np.ndarray | None:
        """使用 MuMu12 NemuIpc DLL 截图（external_renderer_ipc.dll）

        通过 NemuIpcLib 调用 nemu_capture_display RPC 直接读取模拟器显示缓冲区，
        延迟极低（5-15ms），仅适用于 MuMu12 >= 3.8.13。

        P1-2: Emits human-readable error messages via format_nemu_error()
        and triggers disconnect + reconnect on recoverable errors.

        Returns:
            BGR 格式的 numpy 数组
        """
        try:
            import cv2
            from core.timeout import TimeoutError, call_with_timeout
            from platforms.windows.nemu_ipc_errors import (
                format_nemu_error,
                is_recoverable_error,
            )

            if self._nemu_ipc_connect_id == 0:
                self._nemu_ipc_connect()
            lib = self._load_nemu_ipc_lib()

            # Ensure resolution is known
            if self._nemu_ipc_width == 0 or self._nemu_ipc_height == 0:
                self._nemu_ipc_get_resolution()

            width = self._nemu_ipc_width
            height = self._nemu_ipc_height
            length = width * height * 4
            # B012: use NemuIpcLib pointer factory methods instead of
            # importing ctypes directly in this non-platform module.
            width_ptr = lib.make_int_ptr(width)
            height_ptr = lib.make_int_ptr(height)
            pixels_pointer = lib.make_ubyte_ptr(length)

            try:
                ret = call_with_timeout(
                    lib.nemu_capture_display,
                    NEMU_IPC_DLL_TIMEOUT_SEC,
                    self._nemu_ipc_connect_id,
                    0,  # display_id
                    length,
                    width_ptr,
                    height_ptr,
                    pixels_pointer,
                )
            except TimeoutError as exc:
                self._nemu_ipc_disconnect()
                raise RuntimeError(
                    f"nemu_capture_display timed out during screenshot "
                    f"after {NEMU_IPC_DLL_TIMEOUT_SEC}s"
                ) from exc
            if ret != 0:
                # P1-2: Surface the actual Windows RPC error code.
                msg = format_nemu_error(ret, context="nemu_capture_display(screenshot)")
                if is_recoverable_error(ret):
                    logger.warning(
                        "NemuIpc recoverable error — forcing reconnect: %s", msg,
                    )
                    self._nemu_ipc_disconnect()
                raise RuntimeError(msg)

            # Image is BGRA, upside down
            image = np.ctypeslib.as_array(
                lib.deref_ubyte_contents(pixels_pointer)
            ).reshape((height, width, 4))
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
            image = cv2.flip(image, 0)
            return image

        except NotImplementedError:
            raise
        except Exception as exc:
            self._nemu_ipc_disconnect()
            raise RuntimeError(f"NemuIpc 截图失败: {exc}") from exc

    @retry_screenshot()
    def _capture_ldopengl(self) -> np.ndarray | None:
        """使用 LDPlayer OpenGL 截图（ldopengl64.dll）

        通过 ctypes 调用 ldopengl 直接读取 LDPlayer 模拟器的 OpenGL
        渲染帧，延迟极低（~5ms），仅适用于 LDPlayer 9+。

        自动检测 API 版本：
          v3 (LDPlayer 14): 使用 PID 实例化 IScreenShotClass，尺寸由
            DLL 内部读取，跳过 wm size 调用以提升速度。
          v2 (LDPlayer 9): 4 步 frame handle 流程，尺寸由 get_frame_info 返回。
          v1 (legacy): 需要显式传入 width/height，通过 wm size 解析。

        Returns:
            BGR 格式的 numpy 数组
        """
        try:
            from platforms.windows.ldopengl import LDOpenGLCapture, get_ldopengl_capture

            # TD-011: use the process-wide singleton. Constructing
            # LDOpenGLCapture() per call re-loads ldopengl64.dll via
            # ctypes.CDLL, and the subsequent GC-triggered FreeLibrary
            # eventually leaves IScreenShotClass vtable pointers dangling,
            # causing ACCESS_VIOLATION (0xC0000005) after ~1 hour of
            # per-second screenshot loops. The singleton loads the DLL
            # exactly once for the process lifetime.
            capture = get_ldopengl_capture()
            if not capture.is_available():
                raise RuntimeError("ldopengl64.dll 不可用（非 Windows 或 LDPlayer 未安装）")

            hwnd = LDOpenGLCapture.find_ldplayer_window()
            if not hwnd:
                raise RuntimeError("未找到 LDPlayer 窗口")

            # v3/v2 query dimensions from the DLL itself — skip wm size.
            # v1 needs explicit width/height matching the rendering resolution.
            width = 0
            height = 0
            if capture.api_version <= 1:
                width = 720
                height = 1280
                try:
                    if self._device is not None:
                        size_str = self._device.shell("wm size").output or ""
                        # Parse "Physical size: 720x1280"
                        if "size:" in size_str:
                            parts = size_str.split("size:")[-1].strip().split("x")
                            if len(parts) == 2:
                                width = int(parts[0])
                                height = int(parts[1])
                except Exception:
                    logger.debug("wm size 获取失败，使用默认 720x1280")

            image = capture.capture(hwnd, width, height)
            if image is None:
                raise RuntimeError("ldopengl_capture 返回空结果")
            return image

        except NotImplementedError:
            raise
        except Exception as exc:
            raise RuntimeError(f"LDOpenGL 截图失败: {exc}") from exc

    def _find_nemu_window(self) -> int | None:
        """查找 MuMu 模拟器窗口句柄

        Returns:
            窗口句柄，未找到返回 None
        """
        try:
            from platforms.windows.window import find_window_by_class

            # MuMu12 registers its top-level window under either "MuMuPlayer"
            # (newer builds) or "MuMu" (older builds). Try both.
            for class_name in ("MuMuPlayer", "MuMu"):
                hwnd = find_window_by_class(class_name)
                if hwnd:
                    return hwnd
        except Exception:
            logger.debug("find_nemu_window failed (best-effort), returning None", exc_info=True)
        return None
