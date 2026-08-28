"""
ADB 截图降级链
按优先级尝试多种 ADB 截图方式：
  - 雷电 (LDPlayer):   ld_opengl → screencap(raw) → screencap_png
  - MuMu:              nemuipe → screencap(raw) → screencap_png
  - BlueStacks:        bluestacks → screencap(raw) → screencap_png
  - 通用/未知:         droidcast → screencap(raw) → screencap_png
参考：Alas 的 10种 ADB 截图方式（取 GAF 可用的非 root 方法）
"""
import logging
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LDOpenGLCapture singleton cache (N146 fix — backend side)
#
# The agent side already caches LDOpenGLCapture as a module-level singleton
# (see .ai-memory/lessons/2026-07-06-n146-ldopengl-singleton-ctypes-hot-loop.md).
# The backend _adb_screenshot module was NOT patched — every call to
# _capture_by_ld_opengl created a new LDOpenGLCapture() → ctypes.CDLL() →
# LoadLibrary, and when the instance was GC'd → FreeLibrary. Repeated
# load/unload of ldopengl64.dll destabilizes the vtable pointers and can
# cause ACCESS_VIOLATION (0xC0000005), corrupting LDPlayer's OpenGL
# renderer state and triggering GPU driver TDR (black screen).
# ---------------------------------------------------------------------------
_LDOPENGL_LOCK = threading.Lock()
_LDOPENGL_CAPTURE_INSTANCE: object | None = None


def _get_ldopengl_capture():
    """Return the process-wide LDOpenGLCapture singleton (backend side).

    Mirrors the agent-side get_ldopengl_capture() pattern from N146.
    The DLL is loaded exactly once and stays loaded for the process
    lifetime, preventing vtable invalidation from FreeLibrary.
    """
    global _LDOPENGL_CAPTURE_INSTANCE
    if _LDOPENGL_CAPTURE_INSTANCE is None:
        with _LDOPENGL_LOCK:
            if _LDOPENGL_CAPTURE_INSTANCE is None:
                from device_bridge.platforms.windows.ld_opengl import LDOpenGLCapture
                _LDOPENGL_CAPTURE_INSTANCE = LDOpenGLCapture()
                logger.info("LDOpenGLCapture singleton initialized (backend, N146 fix)")
    return _LDOPENGL_CAPTURE_INSTANCE

# All registered screenshot methods
_ALL_METHODS: dict[str, Callable[..., bytes | None]] = {}

# Emulator-specific priority chains (higher index = lower priority)
_EMULATOR_CHAINS: dict[str, list[str]] = {
    'ldplayer': ['ld_opengl', 'screencap', 'screencap_png'],
    'mumu': ['nemuipe', 'screencap', 'screencap_png'],
    'bluestacks': ['bluestacks', 'screencap', 'screencap_png'],
    # Generic fallback chain for unknown emulator types
    '__default__': ['droidcast', 'screencap', 'screencap_png'],
}

# Screenshot cache: device_serial -> (image_bytes, timestamp, method)
_screenshot_cache: dict[str, tuple] = {}
_CACHE_TTL = 5.0  # Cache valid for 5 seconds


def register_method(name: str, func: Callable) -> None:
    """Register a screenshot method into the method pool."""
    _ALL_METHODS[name] = func


def get_available_methods(emulator_type: str = '') -> list[str]:
    """Return available screenshot method names for an emulator type.

    Filters out methods that are registered only as placeholders and not
    actually implemented (e.g. 'bluestacks').
    """
    chain_key = emulator_type.lower() if emulator_type else ''
    method_names = _EMULATOR_CHAINS.get(chain_key, _EMULATOR_CHAINS['__default__'])
    return [name for name in method_names if name in _ALL_METHODS]


def capture(adb_serial: str, adb_executable: str = 'adb',
           use_cache: bool = True, emulator_type: str = '',
           method: str | None = None) -> tuple[bytes | None, str]:
    """Try screenshot methods in emulator-aware priority order.

    Args:
        adb_serial: ADB device serial (e.g., 127.0.0.1:5555)
        adb_executable: ADB executable path
        use_cache: Whether to use TTL cache (default True)
        emulator_type: Emulator type string to select optimal chain
        method: If provided, try only this method; otherwise use the chain.

    Returns:
        Tuple of (raw image bytes, method name). Bytes are None if all methods fail.
    """
    # Check cache first for immediate response (skip cache when a specific
    # method is requested so the caller can compare methods side-by-side).
    if use_cache and not method and adb_serial in _screenshot_cache:
        cached_data, cached_time, cached_method = _screenshot_cache[adb_serial]
        if time.time() - cached_time < _CACHE_TTL:
            logger.debug('Screenshot cache hit for %s (method=%s)', adb_serial, cached_method)
            return cached_data, cached_method

    # Build priority chain based on emulator type
    chain_key = emulator_type.lower() if emulator_type else ''
    method_names = _EMULATOR_CHAINS.get(chain_key, _EMULATOR_CHAINS['__default__'])

    # If a specific method is requested, only try that method.
    if method:
        method_names = [method]
        logger.debug('Screenshot forced method for %s: %s', adb_serial, method)
    else:
        logger.debug('Screenshot chain for %s (emulator=%s): %s',
                     adb_serial, emulator_type, method_names)

    for name in method_names:
        func = _ALL_METHODS.get(name)
        if not func:
            continue
        try:
            result = func(adb_serial, adb_executable)
            if result:
                logger.debug('Screenshot via %s succeeded for %s', name, adb_serial)
                # Update cache
                _screenshot_cache[adb_serial] = (result, time.time(), name)
                return result, name
        except Exception as e:
            logger.debug('ADB 截图方式 %s 失败: %s', name, e)
    return None, ''


def invalidate_cache(adb_serial: str) -> None:
    """Invalidate cache for a specific device (e.g., after operations)"""
    _screenshot_cache.pop(adb_serial, None)


def _capture_by_screencap(serial: str, adb: str) -> bytes | None:
    """ADB screencap 截图（raw 模式）
    使用 adb exec-out screencap（无 -p）获取原始 BGRA 数据，
    比 screencap -p 快约 3 倍（635ms vs 1905ms）。
    返回的 raw 字节由上层 views.py 统一做 JPEG 编码。
    """
    proc = subprocess.run(
        [adb, '-s', serial, 'exec-out', 'screencap'],
        capture_output=True, timeout=15,
    )
    if proc.returncode == 0 and len(proc.stdout) > 100:
        return proc.stdout
    return None


def _capture_by_screencap_png(serial: str, adb: str) -> bytes | None:
    """ADB screencap -p 截图（PNG 模式，备用）
    兜底方案，当 raw 模式解析失败时使用。
    """
    proc = subprocess.run(
        [adb, '-s', serial, 'exec-out', 'screencap', '-p'],
        capture_output=True, timeout=15,
    )
    if proc.returncode == 0 and len(proc.stdout) > 100:
        return proc.stdout
    return None


def _capture_by_droidcast(serial: str, adb: str) -> bytes | None:
    """DroidCast 截图
    通过 adb forward tcp 转发 + HTTP 请求拉取截图
    需要设备上已安装 DroidCast apk
    """
    try:
        result = subprocess.run(
            [adb, '-s', serial, 'forward', '--list'],
            capture_output=True, text=True, timeout=5,
        )
        target_port = None
        for line in result.stdout.strip().split('\n'):
            if 'tcp:53517' in line or 'tcp:53516' in line:
                parts = line.strip().split()
                if len(parts) >= 3:
                    target_port = parts[1].split(':')[-1]
                break

        if not target_port:
            subprocess.run(
                [adb, '-s', serial, 'forward', 'tcp:53517', 'tcp:53517'],
                capture_output=True, timeout=5,
            )
            target_port = '53517'

        import urllib.request
        req = urllib.request.Request(f'http://127.0.0.1:{target_port}/decive-screenshot', method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read()
    except Exception:
        logger.warning("adb screenshot: _capture_by_droidcast failed (serial=%s, port=%s)", serial, target_port, exc_info=True)
        return None


def _capture_by_nemuipe(serial: str, adb: str) -> bytes | None:
    """MuMu IPC 截图（MuMu 模拟器专用）
    通过 adb shell 执行 MuMu 的 IPC 截图命令
    """
    try:
        proc = subprocess.run(
            [adb, '-s', serial, 'shell', 'mumu', 'screencap'],
            capture_output=True, timeout=10,
        )
        if proc.returncode == 0 and len(proc.stdout) > 100:
            return proc.stdout
    except Exception:
        logger.debug('mumu screencap failed', exc_info=True)
    return None


def _capture_by_ld_opengl(serial: str, adb: str) -> bytes | None:
    """LDOpenGL 截图（雷电模拟器专用）
    通过 ldconsole screenshot 命令直接截取模拟器画面，
    比 ADB screencap 快 2-3 倍。

    N146 fix (backend side): uses the process-wide singleton instead of
    creating a new LDOpenGLCapture() on every call. Repeated ctypes.CDLL
    load/unload was causing ACCESS_VIOLATION crashes.
    """
    try:
        # Extract emulator index from ADB serial.
        # Supported serial formats:
        #   - 127.0.0.1:5555  -> adb port 5555
        #   - emulator-5554   -> console port 5554, adb port 5555
        index: int | None = None
        if ':' in serial:
            port = int(serial.split(':')[-1])
            # LDPlayer port mapping: index = (adb_port - 5555) / 2
            index = max(0, (port - 5555) // 2)
        elif serial.startswith('emulator-'):
            console_port = int(serial.split('-', 1)[1])
            # ADB port is typically console_port + 1 for LDPlayer
            adb_port = console_port + 1
            index = max(0, (adb_port - 5555) // 2)
        else:
            logger.debug('LDOpenGL requires an IP:port or emulator-NNNN serial, got %s', serial)
            return None

        logger.debug('LDOpenGL capture attempt for serial=%s index=%d', serial, index)
        # N146 fix: use singleton — DLL loaded once, never FreeLibrary'd
        capturer = _get_ldopengl_capture()
        result = capturer.capture(index=index)

        if result.get('success') and result.get('image_bytes'):
            logger.debug('LDOpenGL capture succeeded for serial=%s', serial)
            return result['image_bytes']
        logger.debug('LDOpenGL capture failed for serial=%s: %s', serial, result.get('error'))
    except Exception as e:
        logger.debug('LDOpenGL 截图失败: %s', e)
    return None


def _capture_by_bluestacks(serial: str, adb: str) -> bytes | None:
    """BlueStacks screenshot via BSTKService HTTP API.

    Attempts to forward the BlueStacks internal screenshot service port and
    fetch a JPEG/PNG image over HTTP. Falls back to the next method in the
    chain if the service is unreachable.
    """
    # BlueStacks internal screenshot service port. Some distributions use a
    # different port configured in bluestacks.conf; 55555 is the default used
    # by BSTKService for headless screenshot requests.
    service_port = 55555
    endpoints = ('/screenshot', '/screenshot.png')

    try:
        forward_proc = subprocess.run(
            [adb, '-s', serial, 'forward',
             f'tcp:{service_port}', f'tcp:{service_port}'],
            capture_output=True, timeout=5,
        )
        if forward_proc.returncode != 0:
            logger.debug(
                'BlueStacks port forward failed for %s: %s',
                serial, forward_proc.stderr.decode('utf-8', errors='ignore'),
            )
            return None

        for endpoint in endpoints:
            try:
                req = urllib.request.Request(
                    f'http://127.0.0.1:{service_port}{endpoint}',
                    method='GET',
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = resp.read()
                    if len(data) > 100:
                        logger.debug(
                            'BlueStacks screenshot succeeded for %s via %s',
                            serial, endpoint,
                        )
                        return data
            except urllib.error.HTTPError as exc:
                logger.debug(
                    'BlueStacks endpoint %s returned HTTP %s for %s',
                    endpoint, exc.code, serial,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    'BlueStacks endpoint %s failed for %s: %s',
                    endpoint, serial, exc,
                )
    except Exception as exc:  # noqa: BLE001
        logger.debug('BlueStacks screenshot failed for %s: %s', serial, exc)
    return None


register_method('ld_opengl', _capture_by_ld_opengl)
register_method('nemuipe', _capture_by_nemuipe)
register_method('bluestacks', _capture_by_bluestacks)
register_method('droidcast', _capture_by_droidcast)
register_method('screencap', _capture_by_screencap)  # raw mode (fast, ~635ms)
register_method('screencap_png', _capture_by_screencap_png)  # PNG mode fallback (~1905ms)
