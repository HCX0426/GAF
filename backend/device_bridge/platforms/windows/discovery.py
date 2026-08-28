"""
Windows 平台设备发现器
包含窗口枚举、模拟器扫描、ADB 设备发现
参考：Alas 的 5途径扫描 + 8类模拟器管理
"""
import logging
import subprocess

from device_bridge.platforms.base import DeviceInfo, PlatformDeviceDiscoverer
from device_bridge.platforms.windows._constants import SYSTEM_PROCESS_BLACKLIST

logger = logging.getLogger(__name__)

GAME_PROCESS_NAMES = [
    'BlueArchive.exe',
    'Arknights.exe',
    'GenshinImpact.exe',
    'StarRail.exe',
    'NIKKE.exe',
    'AzurLane.exe',
    'GirlsFrontline.exe',
    'PunishingGrayRaven.exe',
    'FateGrandOrder.exe',
    'HonkaiImpact3.exe',
    # R37-P0: BrownDust II support
    # BD2 实际进程名是 "BrownDust II.exe" (带空格，Neowiz 启动器安装版)
    # "BrownDust2.exe" 是旧版/Steam 版命名，保留兼容
    'BrownDust II.exe',
    'BrownDust2.exe',
    'browndust2.exe',
]


def _enum_windows() -> list[dict]:
    """枚举所有顶层可见窗口（直接调用 Win32 API）"""
    windows: list[dict] = []
    try:
        import win32gui
        import win32process
    except ImportError:
        logger.warning('pywin32 未安装，无法扫描窗口')
        return windows

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        if win32gui.IsIconic(hwnd):
            return True

        title = win32gui.GetWindowText(hwnd)
        if not title.strip():
            return True

        try:
            rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            rect = (0, 0, 0, 0)

        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        if width < 200 or height < 200:
            return True

        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = _get_process_name(pid)
        except Exception:
            process_name = ''

        try:
            window_class = win32gui.GetClassName(hwnd)
        except Exception:
            window_class = ''

        if process_name.lower() in SYSTEM_PROCESS_BLACKLIST:
            return True

        is_game = process_name in GAME_PROCESS_NAMES
        windows.append({
            'title': title,
            'process_name': process_name,
            'window_class': window_class,
            'hwnd': str(hwnd),
            'resolution': {'width': width, 'height': height},
            'is_game': is_game,
        })
        return True

    try:
        win32gui.EnumWindows(callback, 0)
    except Exception as e:
        logger.warning('EnumWindows 失败: %s', e)
    return windows


def _get_process_name(pid: int) -> str:
    try:
        import win32api
        import win32con
        import win32process
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid)
        if handle:
            name = win32process.GetModuleFileNameEx(handle, 0)
            import win32file
            win32file.CloseHandle(handle)
            if name:
                return name.split('\\')[-1]
    except Exception as e:
        # B008 fix: log instead of swallowing — process query failures (e.g.
        # access denied for system processes) are common but should be visible.
        logger.warning('GetModuleFileNameEx failed for pid=%s: %s', pid, e)
    return ''


class WindowsDeviceDiscoverer(PlatformDeviceDiscoverer):
    """Windows 设备发现器，支持窗口枚举 + 模拟器扫描 + ADB 设备发现"""

    def discover_windows(self) -> list[DeviceInfo]:
        """发现 Windows 窗口设备"""
        try:
            windows = _enum_windows()
            return [
                DeviceInfo(
                    name=w['title'],
                    device_type='window',
                    identifier=w['hwnd'],
                    resolution=w['resolution'],
                    platform='windows',
                    extra={'process_name': w['process_name'], 'window_class': w.get('window_class', ''), 'is_game': w['is_game']},
                )
                for w in windows
            ]
        except Exception as e:
            logger.warning('Windows 窗口发现失败: %s', e)
            return []

    def discover_emulators(self) -> list[DeviceInfo]:
        """发现模拟器设备（委托给 emulator.py）"""
        try:
            from device_bridge.discovery.emulator import scan_all_emulators
            emulators = scan_all_emulators()
            return [
                DeviceInfo(
                    name=e.name,
                    device_type='emulator',
                    identifier=f'127.0.0.1:{e.adb_port}',
                    resolution=e.resolution or {'width': 0, 'height': 0},
                    platform='windows',
                    extra={
                        'emulator': e.emulator,
                        'adb_port': e.adb_port,
                        'status': e.status,
                        'android_version': e.android_version,
                    },
                )
                for e in emulators
            ]
        except Exception as e:
            logger.warning('模拟器发现失败: %s', e)
            return []

    def discover_adb_devices(self) -> list[DeviceInfo]:
        """发现 ADB 连接的设备（通过 adb devices 命令）"""
        devices: list[DeviceInfo] = []
        try:
            result = subprocess.run(
                ['adb', 'devices'],
                capture_output=True, text=True, timeout=10,
            )
            lines = result.stdout.strip().split('\n')[1:]
            for line in lines:
                parts = line.strip().split('\t')
                if len(parts) == 2 and parts[1] == 'device':
                    serial = parts[0]
                    devices.append(DeviceInfo(
                        name=f'ADB-{serial}',
                        device_type='adb',
                        identifier=serial,
                        platform='windows',
                        extra={'adb_serial': serial},
                    ))
        except FileNotFoundError:
            logger.warning('adb 命令未找到，跳过 ADB 设备发现')
        except subprocess.TimeoutExpired:
            logger.warning('adb devices 超时')
        except Exception as e:
            logger.warning('ADB 设备发现失败: %s', e)
        return devices
