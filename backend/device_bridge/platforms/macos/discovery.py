"""
macOS 设备发现器
基于 CGWindowListCopyWindowInfo (pyobjc-framework-Quartz) + ADB devices
依赖：pyobjc-framework-Quartz (macOS only)
参考：MaaFramework macOS 设备发现

窗口发现过滤规则：
- 排除系统进程 (Dock, Finder, SystemUIServer, etc.)
- 排除无标题窗口
- 排除尺寸 < 200x200 的小窗口
- 标记游戏进程 (可选)
"""
import logging
import subprocess

from device_bridge.platforms.base import DeviceInfo, PlatformDeviceDiscoverer

logger = logging.getLogger(__name__)

# System process blacklist (won't be exposed as controllable windows)
SYSTEM_PROCESS_BLACKLIST = {
    'Dock', 'Finder', 'SystemUIServer', 'ControlCenter',
    'WindowServer', 'loginwindow', 'AirPlayUIAgent', 'Spotlight',
    'coreservicesd', 'cfprefsd', 'mdworker_shared', 'distnoted',
    'usernoted', 'bird', 'cloudd', 'iCloudHelper', 'PhotosAgent',
    'sharingd', 'rapportd', 'bluetoothd', 'coreaudiod',
}

# Common game processes (for tagging)
GAME_PROCESS_NAMES = {
    'dota2', 'csgo', 'csgos2', 'hl2', 'tf2', 'steam',
    'EpicGamesLauncher', 'Battle.net', 'League of Legends',
    'GenshinImpact', 'Yuanshen',
}


def _check_quartz_available() -> bool:
    """Check if Quartz framework is importable."""
    try:
        from Quartz import CGWindowListCopyWindowInfo  # noqa: F401
        return True
    except ImportError:
        return False


class MacOSDeviceDiscoverer(PlatformDeviceDiscoverer):
    """macOS 设备发现器"""

    def discover_windows(self) -> list[DeviceInfo]:
        """Discover macOS windows via CGWindowListCopyWindowInfo."""
        if not _check_quartz_available():
            logger.warning('Quartz framework not available, cannot discover windows')
            return []

        try:
            from CoreFoundation import CFArrayGetCount, CFArrayGetValueAtIndex
            from Quartz import (
                CGWindowListCopyWindowInfo,
                kCGNullWindowID,
                kCGWindowListOptionOnScreenOnly,
            )
        except ImportError as e:
            logger.warning('pyobjc frameworks not available: %s', e)
            return []

        try:
            window_list = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly,
                kCGNullWindowID,
            )
            if window_list is None:
                return []

            count = CFArrayGetCount(window_list)
            devices: list[DeviceInfo] = []

            for i in range(count):
                window_info = CFArrayGetValueAtIndex(window_list, i)
                if window_info is None:
                    continue

                # Extract fields from CFDictionary
                owner_name = self._cf_dict_get_string(window_info, 'kCGWindowOwnerName')
                window_name = self._cf_dict_get_string(window_info, 'kCGWindowName')
                window_class = self._cf_dict_get_string(window_info, 'kCGWindowOwnerName')  # Same as owner for macOS
                window_number = self._cf_dict_get_int(window_info, 'kCGWindowNumber')
                bounds = self._cf_dict_get_dict(window_info, 'kCGWindowBounds')
                layer = self._cf_dict_get_int(window_info, 'kCGWindowLayer', default=0)
                is_onscreen = self._cf_dict_get_bool(window_info, 'kCGWindowIsOnscreen', default=False)

                # Skip windows above normal layer (menu bar, dock, etc.)
                if layer != 0:
                    continue
                # Skip if not on screen
                if not is_onscreen:
                    continue
                # Skip system processes
                if owner_name in SYSTEM_PROCESS_BLACKLIST:
                    continue
                # Skip windows without title (unless owner name is meaningful)
                title = window_name or owner_name
                if not title or title == owner_name and owner_name in {'Window Server'}:
                    continue

                # Extract bounds
                width = self._cf_dict_get_int(bounds, 'Width', default=0) if bounds else 0
                height = self._cf_dict_get_int(bounds, 'Height', default=0) if bounds else 0

                # Skip small windows
                if width < 200 or height < 200:
                    continue

                is_game = owner_name in GAME_PROCESS_NAMES

                devices.append(DeviceInfo(
                    name=title,
                    device_type='window',
                    identifier=str(window_number),
                    resolution={'width': width, 'height': height},
                    platform='macos',
                    extra={
                        'process_name': owner_name,
                        'window_class': window_class,
                        'window_name': window_name,
                        'is_game': is_game,
                        'layer': layer,
                    },
                ))

            logger.info('macOS discovered %d windows', len(devices))
            return devices
        except Exception as e:
            logger.error('macOS window discovery failed: %s', e)
            return []

    def discover_emulators(self) -> list[DeviceInfo]:
        """Discover emulators on macOS (process scan + ADB)."""
        devices: list[DeviceInfo] = []

        # Process-based detection (Android Studio emulator, etc.)
        try:
            result = subprocess.run(
                ['pgrep', '-lf', 'emulator|qemu'],
                capture_output=True,
                timeout=3,
                check=False,
                text=True,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split(None, 1)
                    if len(parts) < 2:
                        continue
                    pid_str, cmdline = parts
                    devices.append(DeviceInfo(
                        name=f'Emulator (pid {pid_str})',
                        device_type='emulator',
                        identifier=f'pid:{pid_str}',
                        resolution={'width': 0, 'height': 0},
                        platform='macos',
                        extra={'cmdline': cmdline[:200]},
                    ))
        except FileNotFoundError:
            pass  # pgrep not available
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            logger.debug('pgrep emulator scan failed: %s', e)

        # ADB-based detection (cross-platform)
        adb_devices = self.discover_adb_devices()
        for adb_dev in adb_devices:
            if adb_dev not in devices:
                devices.append(adb_dev)

        return devices

    def discover_adb_devices(self) -> list[DeviceInfo]:
        """Discover ADB-connected devices via `adb devices`."""
        devices: list[DeviceInfo] = []

        try:
            result = subprocess.run(
                ['adb', 'devices', '-l'],
                capture_output=True,
                timeout=5,
                check=False,
                text=True,
            )
            if result.returncode != 0:
                return devices

            # Parse output:
            # List of devices attached
            # emulator-5554 device product:sdk_gphone64_x86_64 model:sdk_gphone64_x86_64 device:emu64x64 transport_id:1
            lines = result.stdout.splitlines()
            if len(lines) < 2:
                return devices

            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                serial = parts[0]
                state = parts[1]
                if state != 'device':
                    continue  # offline, unauthorized, etc.

                # Parse extra fields (product, model, device, transport_id)
                extra_info = {}
                for field in parts[2:]:
                    if ':' in field:
                        key, value = field.split(':', 1)
                        extra_info[key] = value

                model = extra_info.get('model', 'Android Device')
                devices.append(DeviceInfo(
                    name=model,
                    device_type='adb',
                    identifier=serial,
                    resolution={'width': 0, 'height': 0},
                    platform='macos',
                    extra={
                        'state': state,
                        'product': extra_info.get('product', ''),
                        'transport_id': extra_info.get('transport_id', ''),
                    },
                ))
        except FileNotFoundError:
            logger.debug('adb command not found in PATH')
        except subprocess.TimeoutExpired:
            logger.warning('adb devices timed out')
        except Exception as e:
            logger.error('ADB device discovery failed: %s', e)

        return devices

    @staticmethod
    def _cf_dict_get_string(cf_dict, key: str) -> str:
        """Get string value from CFDictionary by key (uses pyobjc NSString bridge)."""
        try:
            value = cf_dict.get(key) if hasattr(cf_dict, 'get') else None
            if value is None:
                return ''
            if isinstance(value, str):
                return value
            return str(value)
        except Exception:
            return ''

    @staticmethod
    def _cf_dict_get_int(cf_dict, key: str, default: int = 0) -> int:
        """Get int value from CFDictionary by key."""
        try:
            value = cf_dict.get(key) if hasattr(cf_dict, 'get') else None
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _cf_dict_get_bool(cf_dict, key: str, default: bool = False) -> bool:
        """Get bool value from CFDictionary by key."""
        try:
            value = cf_dict.get(key) if hasattr(cf_dict, 'get') else None
            if value is None:
                return default
            return bool(value)
        except Exception:
            return default

    @staticmethod
    def _cf_dict_get_dict(cf_dict, key: str):
        """Get nested CFDictionary value by key."""
        try:
            value = cf_dict.get(key) if hasattr(cf_dict, 'get') else None
            return value
        except Exception:
            logger.warning("macOS discovery: _cf_dict_get_dict failed (key=%r)", key, exc_info=True)
            return None
