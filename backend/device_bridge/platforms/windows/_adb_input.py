"""
ADB 输入降级链
按优先级尝试多种 ADB 输入方式：
  1. minitouch — 高性能触摸输入，通过 socket 通信
  2. MaaTouch — MaaFramework 高性能触摸输入代理
  3. sendevent — 直接 Linux input 事件注入
  4. ADB input — 兜底，始终可用
参考：Alas 的 6 种 ADB 输入方式（取 GAF 可用的非 root 方法）

Port allocation (TD-123):
  minitouch/MaaTouch ports are dynamically allocated per device serial
  (CRC32 hash + linear probe) to support multi-emulator parallel runs.
  Port range: minitouch [11111, 11611), maatouch [13113, 13613).
"""
import logging
import socket
import subprocess
import threading
import time
import zlib
from collections.abc import Callable

from device_bridge.platforms.base import InputResult

logger = logging.getLogger(__name__)

_CHAIN: dict[str, Callable[..., InputResult | None]] = {}

# Port allocation constants (TD-123).
# High port range avoids system services; per-serial hash ensures
# stable allocation across restarts (same serial -> same port).
_MINITOUCH_PORT_BASE = 11111
_MINITOUCH_PORT_RANGE = 500
_MAATOUCH_PORT_BASE = 13113
_MAATOUCH_PORT_RANGE = 500

# serial -> {'minitouch': port, 'maatouch': port}
_PORT_REGISTRY: dict[str, dict[str, int]] = {}
_PORT_LOCK = threading.Lock()


def register_method(name: str, func: Callable) -> None:
    _CHAIN[name] = func


def _allocate_port(serial: str, kind: str) -> int:
    """Allocate a stable per-serial port for minitouch or maatouch.

    Uses CRC32(serial) % range to compute a preferred port, then linearly
    probes for an available port if the preferred one is occupied.
    The result is cached in `_PORT_REGISTRY` so subsequent calls for the
    same serial+kind return the same port without re-probing.

    Args:
        serial: ADB device serial (e.g. "emulator-5554", "192.168.1.100:5555")
        kind: "minitouch" or "maatouch"

    Returns:
        Available port number in the configured range.

    Raises:
        RuntimeError: If no port is available in the range.
    """
    if kind == "minitouch":
        base, range_size = _MINITOUCH_PORT_BASE, _MINITOUCH_PORT_RANGE
    elif kind == "maatouch":
        base, range_size = _MAATOUCH_PORT_BASE, _MAATOUCH_PORT_RANGE
    else:
        raise ValueError(f"Unknown port kind: {kind!r} (expected 'minitouch' or 'maatouch')")

    with _PORT_LOCK:
        if serial in _PORT_REGISTRY and kind in _PORT_REGISTRY[serial]:
            return _PORT_REGISTRY[serial][kind]

        preferred = base + (zlib.crc32(serial.encode("utf-8")) % range_size)

        for offset in range(range_size):
            port = base + ((preferred - base + offset) % range_size)
            # Probe port availability by attempting to bind.
            # SO_REUSEADDR is intentionally NOT set: we want to detect
            # ports actually in use by another minitouch/maatouch forward.
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                probe.bind(("127.0.0.1", port))
                probe.close()
                _PORT_REGISTRY.setdefault(serial, {})[kind] = port
                logger.debug(
                    "Allocated port %d for serial=%s kind=%s", port, serial, kind
                )
                return port
            except OSError:
                probe.close()
                continue

        raise RuntimeError(
            f"No available port in [{base}, {base + range_size}) for serial={serial} kind={kind}"
        )


def _ensure_minitouch_running(serial: str, adb: str) -> bool:
    """确保 minitouch 服务正在运行 (TD-123: port dynamically allocated)."""
    try:
        port = _allocate_port(serial, "minitouch")
        result = subprocess.run(
            [adb, '-s', serial, 'shell', 'ps', '-A'],
            capture_output=True, text=True, timeout=5,
        )
        if 'minitouch' in result.stdout:
            return True

        forward_check = subprocess.run(
            [adb, '-s', serial, 'forward', '--list'],
            capture_output=True, text=True, timeout=5,
        )
        has_forward = f'tcp:{port}' in forward_check.stdout

        if not has_forward:
            subprocess.run(
                [adb, '-s', serial, 'forward', f'tcp:{port}', f'tcp:{port}'],
                capture_output=True, timeout=5,
            )

        subprocess.run(
            [adb, '-s', serial, 'shell',
             '/data/local/tmp/minitouch -d /dev/input/event2 &'],
            capture_output=True, timeout=5,
        )
        time.sleep(0.3)
        return True
    except Exception:
        logger.warning("adb input: _ensure_minitouch_running failed (serial=%s)", serial, exc_info=True)
        return False


def _input_by_minitouch(serial: str, adb: str, action: str, **kwargs) -> InputResult | None:
    """minitouch 触摸输入
    使用 minitouch 二进制通过 socket 发送触摸事件。
    需要设备上已部署 /data/local/tmp/minitouch。

    TD-123: port is dynamically allocated per serial to support
    multi-emulator parallel runs.
    """
    try:
        port = _allocate_port(serial, "minitouch")
        if not _ensure_minitouch_running(serial, adb):
            return None

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect(('127.0.0.1', port))

        start = time.perf_counter()

        if action == 'click':
            x, y = kwargs.get('x', 0), kwargs.get('y', 0)
            sock.send(f'd 0 {x} {y} 50\nc\nu 0\n'.encode())
        elif action == 'swipe':
            x1, y1 = kwargs.get('x1', 0), kwargs.get('y1', 0)
            x2, y2 = kwargs.get('x2', 0), kwargs.get('y2', 0)
            duration_ms = kwargs.get('duration_ms', 300)
            steps = max(5, duration_ms // 16)
            for i in range(steps + 1):
                t = i / steps
                cx = int(x1 + (x2 - x1) * t)
                cy = int(y1 + (y2 - y1) * t)
                cmd = 'd' if i == 0 else ('u' if i == steps else 'm')
                sock.send(f'{cmd} 0 {cx} {cy} 50\n'.encode())
            sock.send(b'c\n')
        elif action == 'key':
            kwargs.get('key', '')
            logger.debug('minitouch 不支持按键输入，回退')

        sock.close()

        elapsed_ms = (time.perf_counter() - start) * 1000
        return InputResult(success=True, latency_ms=elapsed_ms, method='minitouch')
    except Exception as e:
        logger.debug('minitouch 输入失败: %s', e)
        return None


def _input_by_maatouch(serial: str, adb: str, action: str, **kwargs) -> InputResult | None:
    """MaaTouch 触摸输入
    MaaFramework 的高性能触摸输入代理，通过 socket 协议通信。
    需要设备上已部署 MaaTouch agent。

    TD-123: port is dynamically allocated per serial to support
    multi-emulator parallel runs.
    """
    try:
        port = _allocate_port(serial, "maatouch")
        forward_check = subprocess.run(
            [adb, '-s', serial, 'forward', '--list'],
            capture_output=True, text=True, timeout=5,
        )
        has_forward = f'tcp:{port}' in forward_check.stdout
        if not has_forward:
            subprocess.run(
                [adb, '-s', serial, 'forward', f'tcp:{port}', f'tcp:{port}'],
                capture_output=True, timeout=5,
            )

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect(('127.0.0.1', port))

        start = time.perf_counter()

        if action == 'click':
            x, y = kwargs.get('x', 0), kwargs.get('y', 0)
            sock.send(f'T {x} {y}\n'.encode())
        elif action == 'swipe':
            x1, y1 = kwargs.get('x1', 0), kwargs.get('y1', 0)
            x2, y2 = kwargs.get('x2', 0), kwargs.get('y2', 0)
            duration_ms = kwargs.get('duration_ms', 300)
            sock.send(f'S {x1} {y1} {x2} {y2} {duration_ms}\n'.encode())
        elif action == 'key':
            key = kwargs.get('key', '')
            sock.send(f'K {key}\n'.encode())

        sock.close()

        elapsed_ms = (time.perf_counter() - start) * 1000
        return InputResult(success=True, latency_ms=elapsed_ms, method='maatouch')
    except Exception as e:
        logger.debug('MaaTouch 输入失败: %s', e)
        return None


def _input_by_sendevent(serial: str, adb: str, action: str, **kwargs) -> InputResult | None:
    """sendevent 直接事件注入
    通过 adb shell sendevent 直接写入 Linux input 事件。
    需要 root 权限或 SELinux 放行。
    """
    try:
        start = time.perf_counter()

        if action == 'click':
            x, y = kwargs.get('x', 0), kwargs.get('y', 0)
            device = _find_touch_device(serial, adb)
            if not device:
                return None
            # Batch all sendevent commands into a single adb shell call
            # (TD-087: was 7 separate subprocess.run calls).
            shell_script = '; '.join([
                f'sendevent {device} 3 57 0',
                f'sendevent {device} 3 53 {x}',
                f'sendevent {device} 3 54 {y}',
                f'sendevent {device} 1 330 1',
                f'sendevent {device} 0 0 0',
                f'sendevent {device} 1 330 0',
                f'sendevent {device} 0 0 0',
            ])
            subprocess.run(
                [adb, '-s', serial, 'shell', shell_script],
                capture_output=True, timeout=2,
            )
        elif action == 'swipe':
            x1, y1 = kwargs.get('x1', 0), kwargs.get('y1', 0)
            x2, y2 = kwargs.get('x2', 0), kwargs.get('y2', 0)
            duration_ms = kwargs.get('duration_ms', 300)
            device = _find_touch_device(serial, adb)
            if not device:
                return None
            steps = max(5, duration_ms // 16)
            step_delay = duration_ms / 1000 / steps
            # Batch all sendevent commands into a single adb shell call with
            # inline sleep for step delays (TD-087: was 2+steps subprocess
            # calls, now 1).
            parts = [
                f'sendevent {device} 3 57 0',
                f'sendevent {device} 3 53 {x1}',
                f'sendevent {device} 3 54 {y1}',
                f'sendevent {device} 1 330 1',
                f'sendevent {device} 0 0 0',
            ]
            for i in range(1, steps + 1):
                t = i / steps
                cx = int(x1 + (x2 - x1) * t)
                cy = int(y1 + (y2 - y1) * t)
                parts.append(f'sendevent {device} 3 53 {cx}')
                parts.append(f'sendevent {device} 3 54 {cy}')
                parts.append(f'sendevent {device} 0 0 0')
                parts.append(f'sleep {step_delay:.6f}')
            parts.append(f'sendevent {device} 1 330 0')
            parts.append(f'sendevent {device} 0 0 0')
            shell_script = '; '.join(parts)
            subprocess.run(
                [adb, '-s', serial, 'shell', shell_script],
                capture_output=True, timeout=duration_ms / 1000 + 5,
            )
        elif action == 'key':
            return None

        elapsed_ms = (time.perf_counter() - start) * 1000
        return InputResult(success=True, latency_ms=elapsed_ms, method='sendevent')
    except Exception as e:
        logger.debug('sendevent 输入失败: %s', e)
        return None


def _find_touch_device(serial: str, adb: str) -> str | None:
    """查找触摸输入设备路径"""
    try:
        proc = subprocess.run(
            [adb, '-s', serial, 'shell', 'getevent', '-pl'],
            capture_output=True, text=True, timeout=5,
        )
        current_device = None
        for line in proc.stdout.split('\n'):
            line = line.strip()
            if line.startswith('add device'):
                current_device = line.split(':')[0].split()[-1]
            if current_device and ('ABS_MT_POSITION' in line or 'ABS_MT_TOUCH' in line or 'touch' in line.lower()):
                return current_device
        return '/dev/input/event2'
    except Exception:
        return '/dev/input/event2'


def _input_by_adb_input(serial: str, adb: str, action: str, **kwargs) -> InputResult | None:
    """ADB input 兜底输入
    使用 adb shell input 命令，兼容性最好但延迟较高。
    """
    try:
        start = time.perf_counter()

        if action == 'click':
            x, y = kwargs.get('x', 0), kwargs.get('y', 0)
            subprocess.run(
                [adb, '-s', serial, 'shell', 'input', 'tap', str(x), str(y)],
                capture_output=True, timeout=5,
            )
        elif action == 'swipe':
            x1, y1 = kwargs.get('x1', 0), kwargs.get('y1', 0)
            x2, y2 = kwargs.get('x2', 0), kwargs.get('y2', 0)
            duration_ms = kwargs.get('duration_ms', 300)
            subprocess.run(
                [adb, '-s', serial, 'shell', 'input', 'swipe',
                 str(x1), str(y1), str(x2), str(y2), str(duration_ms)],
                capture_output=True, timeout=10,
            )
        elif action == 'key':
            key = kwargs.get('key', '')
            key_map = {
                'enter': 'KEYCODE_ENTER', 'back': 'KEYCODE_BACK',
                'home': 'KEYCODE_HOME', 'menu': 'KEYCODE_MENU',
                'space': 'KEYCODE_SPACE', 'escape': 'KEYCODE_ESCAPE',
                'tab': 'KEYCODE_TAB', 'delete': 'KEYCODE_DEL',
                'up': 'KEYCODE_DPAD_UP', 'down': 'KEYCODE_DPAD_DOWN',
                'left': 'KEYCODE_DPAD_LEFT', 'right': 'KEYCODE_DPAD_RIGHT',
                'volume_up': 'KEYCODE_VOLUME_UP', 'volume_down': 'KEYCODE_VOLUME_DOWN',
                'power': 'KEYCODE_POWER', 'search': 'KEYCODE_SEARCH',
            }
            adb_key = key_map.get(key.lower(), key.upper())
            subprocess.run(
                [adb, '-s', serial, 'shell', 'input', 'keyevent', adb_key],
                capture_output=True, timeout=5,
            )

        elapsed_ms = (time.perf_counter() - start) * 1000
        return InputResult(success=True, latency_ms=elapsed_ms, method='adb_input')
    except Exception as e:
        logger.warning('ADB input 失败: %s', e)
        return InputResult(success=False, error=str(e), method='adb_input')


def execute(adb_serial: str, adb_executable: str = 'adb', action: str = 'click', **kwargs) -> InputResult:
    """按优先级降级链执行输入操作

    Args:
        adb_serial: ADB 设备序列号（如 127.0.0.1:5555）
        adb_executable: adb 可执行文件路径
        action: 操作类型 — 'click', 'swipe', 'key'
        **kwargs: 操作参数 (x, y, x1, y1, x2, y2, duration_ms, key)

    Returns:
        InputResult
    """
    for name, func in _CHAIN.items():
        try:
            result = func(adb_serial, adb_executable, action, **kwargs)
            if result and result.success:
                logger.debug('ADB 输入 [%s] 方式 %s 成功 (%.1fms)', action, name, result.latency_ms)
                return result
        except Exception as e:
            logger.debug('ADB 输入方式 %s 失败: %s', name, e)

    return InputResult(success=False, error='所有 ADB 输入方式均失败', method='')


def click(adb_serial: str, x: int, y: int, adb_executable: str = 'adb') -> InputResult:
    return execute(adb_serial, adb_executable, 'click', x=x, y=y)


def swipe(adb_serial: str, x1: int, y1: int, x2: int, y2: int,
          duration_ms: int = 300, adb_executable: str = 'adb') -> InputResult:
    return execute(adb_serial, adb_executable, 'swipe',
                   x1=x1, y1=y1, x2=x2, y2=y2, duration_ms=duration_ms)


def key_press(adb_serial: str, key: str, adb_executable: str = 'adb') -> InputResult:
    return execute(adb_serial, adb_executable, 'key', key=key)


register_method('minitouch', _input_by_minitouch)
register_method('maatouch', _input_by_maatouch)
register_method('sendevent', _input_by_sendevent)
register_method('adb_input', _input_by_adb_input)
