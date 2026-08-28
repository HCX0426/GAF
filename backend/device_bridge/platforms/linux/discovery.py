"""
Linux 设备发现器
基于 X11 XQueryTree / _NET_CLIENT_LIST (python-xlib) + ADB devices
依赖：python-xlib (X11 only)
参考：MaaFramework Linux 设备发现

窗口发现过滤规则：
- 排除无标题窗口 (WM_NAME 为空)
- 排除尺寸 < 200x200 的小窗口
- 排除窗口管理器装饰窗口 (override_redirect=True)
- 通过 _NET_WM_WINDOW_TYPE 过滤桌面/面板/工具栏
"""
import logging
import subprocess

from device_bridge.platforms.base import DeviceInfo, PlatformDeviceDiscoverer

logger = logging.getLogger(__name__)

# Window types to exclude (per EWMH _NET_WM_WINDOW_TYPE)
_EXCLUDED_WINDOW_TYPES = {
    '_NET_WM_WINDOW_TYPE_DESKTOP',
    '_NET_WM_WINDOW_TYPE_DOCK',
    '_NET_WM_WINDOW_TYPE_TOOLBAR',
    '_NET_WM_WINDOW_TYPE_MENU',
    '_NET_WM_WINDOW_TYPE_SPLASH',
    '_NET_WM_WINDOW_TYPE_NOTIFICATION',
}


def _check_xlib_available() -> bool:
    """Check if python-xlib is importable."""
    try:
        import Xlib  # noqa: F401
        return True
    except ImportError:
        return False


class LinuxDeviceDiscoverer(PlatformDeviceDiscoverer):
    """Linux 设备发现器"""

    def discover_windows(self) -> list[DeviceInfo]:
        """Discover Linux X11 windows via _NET_CLIENT_LIST (EWMH) or XQueryTree fallback."""
        if not _check_xlib_available():
            logger.warning('python-xlib not available, cannot discover windows')
            return []

        try:
            from Xlib import display as Xdisplay  # noqa: N812
        except ImportError as e:
            logger.warning('python-xlib import failed: %s', e)
            return []

        try:
            dpy = Xdisplay.Display()
            try:
                root = dpy.screen().root
                # Try EWMH _NET_CLIENT_LIST first (most reliable)
                client_windows = self._get_ewmh_client_list(dpy, root)
                if client_windows is None:
                    # Fallback to XQueryTree
                    client_windows = self._query_tree_windows(root)

                devices: list[DeviceInfo] = []
                for win in client_windows:
                    try:
                        device = self._window_to_device(dpy, win)
                        if device:
                            devices.append(device)
                    except Exception as e:
                        logger.debug('Failed to inspect window: %s', e)

                logger.info('Linux discovered %d windows', len(devices))
                return devices
            finally:
                dpy.close()
        except Exception as e:
            logger.error('Linux window discovery failed: %s', e)
            return []

    def discover_emulators(self) -> list[DeviceInfo]:
        """Discover emulators on Linux (process scan + ADB)."""
        devices: list[DeviceInfo] = []

        # Process-based detection (Android Studio emulator, etc.)
        try:
            result = subprocess.run(
                ['pgrep', '-lf', 'emulator|qemu|genymotion'],
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
                        platform='linux',
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
                    continue

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
                    platform='linux',
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
    def _get_ewmh_client_list(dpy, root):
        """Get window list via EWMH _NET_CLIENT_LIST property.

        Returns list of Xlib window objects, or None if property not supported.
        """
        try:
            from Xlib import Xatom
            atom = dpy.intern_atom('_NET_CLIENT_LIST')
            prop = root.get_full_property(atom, Xatom.WINDOW)
            if prop is None or not prop.value:
                return None
            windows = []
            for win_id in prop.value:
                try:
                    win = dpy.create_resource_object('window', win_id)
                    windows.append(win)
                except Exception:
                    logger.warning("linux discovery: failed to create window object (win_id=%s)", win_id, exc_info=True)
                    continue
            return windows
        except Exception as e:
            logger.debug('_NET_CLIENT_LIST not available: %s', e)
            return None

    @staticmethod
    def _query_tree_windows(root):
        """Fallback: get windows via XQueryTree (recursive)."""
        try:
            tree = root.query_tree()
            return list(tree.children)
        except Exception as e:
            logger.debug('XQueryTree failed: %s', e)
            return []

    @staticmethod
    def _window_to_device(dpy, win) -> DeviceInfo | None:
        """Convert Xlib window object to DeviceInfo, applying filters.

        Returns None if window should be excluded.
        """
        try:
            from Xlib import Xatom
            # Skip override_redirect windows (WM decorations, popups)
            attrs = win.get_attributes()
            if attrs.override_redirect:
                return None

            # Get WM_NAME (window title)
            name = win.get_wm_name()
            if not name:
                return None

            # Get WM_CLASS (process name proxy)
            wm_class = win.get_wm_class()
            process_name = wm_class[1] if wm_class and len(wm_class) >= 2 else (wm_class[0] if wm_class else '')

            # Get geometry
            geom = win.get_geometry()
            width = geom.width
            height = geom.height

            # Skip small windows
            if width < 200 or height < 200:
                return None

            # Check _NET_WM_WINDOW_TYPE (exclude desktop/dock/toolbar)
            window_type_atom = dpy.intern_atom('_NET_WM_WINDOW_TYPE')
            type_prop = win.get_full_property(window_type_atom, Xatom.ATOM)
            if type_prop and type_prop.value:
                for type_atom_id in type_prop.value:
                    try:
                        type_name = dpy.get_atom_name(type_atom_id)
                        if type_name in _EXCLUDED_WINDOW_TYPES:
                            return None
                    except Exception:
                        logger.warning("linux discovery: failed to get atom name (id=%s)", type_atom_id, exc_info=True)
                        continue

            # Get window id (decimal string)
            window_id = str(win.id)

            return DeviceInfo(
                name=name,
                device_type='window',
                identifier=window_id,
                resolution={'width': width, 'height': height},
                platform='linux',
                extra={
                    'process_name': process_name,
                    'window_class': wm_class[0] if wm_class else '',
                    'wm_name': name,
                    'is_game': False,  # No reliable detection on Linux
                },
            )
        except Exception as e:
            logger.debug('Window inspection failed: %s', e)
            return None
