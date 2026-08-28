"""Emulator auto-discovery: detect emulators via process names, registry, and ADB port scanning"""

import glob
import logging
import os
import socket
import subprocess
import xml.etree.ElementTree as ET
from typing import Any

logger = logging.getLogger(__name__)

# Process name to emulator type mapping for fast detection
PROCESS_EMULATOR_MAP: dict[str, str] = {
    "dnplayer.exe": "ldplayer",
    "dnplayer9.exe": "ldplayer",
    "LdVBoxHeadless.exe": "ldplayer",
    "MuMuPlayer.exe": "mumu",
    "NemuHeadless.exe": "mumu",
    "HD-Player.exe": "bluestacks",
    "Bluestacks.exe": "bluestacks",
    "MEmu.exe": "memu",
    "MEmuHeadless.exe": "memu",
    "Nox.exe": "nox",
    "NoxVMHandle.exe": "nox",
    "XiaoyaoHelper.exe": "xiaoyao",
}

# Common ADB installation paths to search for adb executable
ADB_SEARCH_PATHS = [
    r"E:\game\leidian\LDPlayer14\adb.exe",
    r"D:\game\leidian\LDPlayer14\adb.exe",
    r"C:\game\leidian\LDPlayer14\adb.exe",
    r"E:\game\leidian\LDPlayer9\adb.exe",
    r"D:\leidian\LDPlayer9\adb.exe",
    r"C:\leidian\LDPlayer9\adb.exe",
    r"D:\LDPlayer\LDPlayer9\adb.exe",
    r"C:\LDPlayer\LDPlayer9\adb.exe",
    r"E:\Program Files\Netease\MuMu Player 12\adb.exe",
    r"D:\Program Files\Netease\MuMu Player 12\adb.exe",
    r"C:\Program Files\Netease\MuMu Player 12\adb.exe",
    r"E:\Program Files\BlueStacks_nxt\HD-Adb.exe",
    r"D:\Program Files\BlueStacks_nxt\HD-Adb.exe",
    r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
    r"E:\Program Files\Nox\bin\adb.exe",
    r"D:\Program Files\Nox\bin\adb.exe",
    r"C:\Program Files\Nox\bin\adb.exe",
    r"E:\Program Files\Microvirt\MEmu\adb.exe",
    r"D:\Program Files\Microvirt\MEmu\adb.exe",
    r"C:\Program Files\Microvirt\MEmu\adb.exe",
]

EMULATOR_CONFIGS = {
    "mumu": {
        "name": "MuMu Emulator",
        "reg_paths": [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\MuMuPlayer-12.0",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\MuMuPlayer",
        ],
        "default_adb_port": 7555,
        "process_names": ["MuMuPlayer.exe", "NemuHeadless.exe"],
    },
    "ldplayer": {
        "name": "LDPlayer",
        "reg_paths": [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\leidian",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\雷电模拟器",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\LDPlayer9",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\LDPlayer14",
            r"SOFTWARE\leidian\LDPlayer9",
            r"SOFTWARE\leidian\LDPlayer14",
        ],
        "default_adb_port": 5555,
        "process_names": ["dnplayer.exe", "dnplayer9.exe", "dnplayer14.exe", "LdVBoxHeadless.exe"],
    },
    "bluestacks": {
        "name": "BlueStacks",
        "reg_paths": [
            r"SOFTWARE\BlueStacks\InstallDir",
            r"SOFTWARE\BlueStacks_nxt",
        ],
        "default_adb_port": 5555,
        "process_names": ["HD-Player.exe", "Bluestacks.exe"],
    },
    "xiaoyao": {
        "name": "Xiaoyao Emulator",
        "reg_paths": [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\逍遥模拟器",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Microvirt",
        ],
        "default_adb_port": 21503,
        "process_names": ["XiaoyaoHelper.exe"],
    },
    "nox": {
        "name": "NoxPlayer",
        "reg_paths": [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Nox",
            r"SOFTWARE\Nox\bin",
        ],
        "default_adb_port": 62001,
        "process_names": ["Nox.exe", "NoxVMHandle.exe"],
    },
}

# MuiCache: tracks executables recently run by user (HKCU\...\Explorer\MuiCache)
# Each value name is the full path to .exe, data format is "<friendly name>"
# We scan for emulator executable names to find install paths
MUICACHE_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\MuiCache"
MUICACHE_EMULATOR_EXES: dict[str, str] = {
    "MuMuPlayer.exe": "mumu",
    "MuMuPlayerGlobal.exe": "mumu",
    "NemuPlayer.exe": "mumu",
    "dnplayer.exe": "ldplayer",
    "dnplayer9.exe": "ldplayer",
    "HD-Player.exe": "bluestacks",
    "Bluestacks.exe": "bluestacks",
    "Nox.exe": "nox",
    "NoxVMHandle.exe": "nox",
    "MEmu.exe": "memu",
    "XiaoyaoHelper.exe": "xiaoyao",
}

# UserAssist: tracks recently run programs (ROT13 encrypted value names)
# HKCU\...\Explorer\UserAssist\{CEBFF5CD-...}\Count
USERASSIST_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"
USERASSIST_GUIDS = [
    "{CEBFF5CD-ACE2-4F4F-9178-9926F41749EA}",  # Windows 7+
    "{F4E57C4B-2036-45F0-A9AB-443BCFE33D9F}",  # Windows 10+ (alternate)
]

# VirtualBox config file patterns for emulator instance discovery
# LDPlayer/MuMu/Nox all use VirtualBox under the hood, with .vbox config files
VBOX_CONF_SEARCH_PATHS = [
    # LDPlayer
    r"E:\leidian\LDPlayer9\vms\*.vbox",
    r"D:\leidian\LDPlayer9\vms\*.vbox",
    r"C:\leidian\LDPlayer9\vms\*.vbox",
    r"E:\LDPlayer9\vms\*.vbox",
    r"D:\LDPlayer9\vms\*.vbox",
    r"C:\LDPlayer9\vms\*.vbox",
    # MuMu (uses NemuBox config)
    r"E:\Program Files\Netease\MuMu Player 12\vms\*.vbox",
    r"D:\Program Files\Netease\MuMu Player 12\vms\*.vbox",
    r"C:\Program Files\Netease\MuMu Player 12\vms\*.vbox",
    r"E:\Program Files\Netease\MuMuPlayer-12.0\vms\*.vbox",
    r"D:\Program Files\Netease\MuMuPlayer-12.0\vms\*.vbox",
    r"C:\Program Files\Netease\MuMuPlayer-12.0\vms\*.vbox",
    # Nox
    r"E:\Program Files\Nox\bin\BignoxVMS\*.vbox",
    r"D:\Program Files\Nox\bin\BignoxVMS\*.vbox",
    r"C:\Program Files\Nox\bin\BignoxVMS\*.vbox",
    # MEmu
    r"E:\Program Files\Microvirt\MEmu\MemuHyperv VMs\*.vbox",
    r"D:\Program Files\Microvirt\MEmu\MemuHyperv VMs\*.vbox",
    r"C:\Program Files\Microvirt\MEmu\MemuHyperv VMs\*.vbox",
]

# Mapping from .vbox file path patterns to emulator type
VBOX_PATH_TYPE_MAP = [
    ("leidian", "ldplayer"),
    ("LDPlayer", "ldplayer"),
    ("MuMu", "mumu"),
    ("Netease", "mumu"),
    ("Nemu", "mumu"),
    ("Nox", "nox"),
    ("BignoxVMS", "nox"),
    ("MEmu", "memu"),
    ("Microvirt", "memu"),
    ("Xiaoyao", "xiaoyao"),
]


def _rot13(text: str) -> str:
    """Apply ROT13 transformation (used by UserAssist registry values)"""
    result = []
    for ch in text:
        if "A" <= ch <= "Z":
            result.append(chr((ord(ch) - ord("A") + 13) % 26 + ord("A")))
        elif "a" <= ch <= "z":
            result.append(chr((ord(ch) - ord("a") + 13) % 26 + ord("a")))
        else:
            result.append(ch)
    return "".join(result)


class EmulatorDiscovery:
    """Emulator auto-discovery: detect via process names (fast), registry, and ADB port scanning"""

    def __init__(self):
        self._winreg = None
        self._adb_path: str | None = None
        try:
            import winreg
            self._winreg = winreg
        except ImportError:
            logger.warning("winreg module unavailable, registry discovery will be skipped")

        # Discover ADB path on initialization
        self._adb_path = self._discover_adb_path()

    @staticmethod
    def _discover_adb_path() -> str | None:
        """Find ADB executable from common installation paths

        Returns:
            Path to adb.exe if found, None otherwise
        """
        # Check if adb is in system PATH first
        try:
            result = subprocess.run(
                ["adb", "version"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            if result.returncode == 0:
                return "adb"
        except Exception:
            pass

        # Search common emulator ADB paths
        for adb_path in ADB_SEARCH_PATHS:
            if os.path.isfile(adb_path):
                logger.info("Found ADB at: %s", adb_path)
                return adb_path

        logger.warning("ADB not found in PATH or common paths")
        return None

    def _read_registry(self, key_path: str, value_name: str = "InstallPath") -> str | None:
        """读取 Windows 注册表值

        Args:
            key_path: 注册表键路径
            value_name: 值名称

        Returns:
            注册表值，失败返回 None
        """
        if self._winreg is None:
            return None
        try:
            key = self._winreg.OpenKey(self._winreg.HKEY_LOCAL_MACHINE, key_path)
            value, _ = self._winreg.QueryValueEx(key, value_name)
            self._winreg.CloseKey(key)
            return str(value) if value else None
        except OSError:
            try:
                key = self._winreg.OpenKey(self._winreg.HKEY_CURRENT_USER, key_path)
                value, _ = self._winreg.QueryValueEx(key, value_name)
                self._winreg.CloseKey(key)
                return str(value) if value else None
            except OSError:
                return None

    def _check_adb_port(self, port: int, timeout: float = 1.0) -> bool:
        """Check if ADB port is reachable

        Args:
            port: Port number
            timeout: Timeout in seconds

        Returns:
            True if port is reachable
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _discover_by_process(self) -> dict[str, bool]:
        """Fast detection by checking running emulator processes

        Returns:
            Dictionary mapping emulator type to whether it's running
        """
        running: dict[str, bool] = {}
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                try:
                    proc_name = proc.info['name']
                    if proc_name and proc_name.lower() in PROCESS_EMULATOR_MAP:
                        emu_type = PROCESS_EMULATOR_MAP[proc_name.lower()]
                        running[emu_type] = True
                        logger.debug("Found running process: %s -> %s", proc_name, emu_type)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except ImportError:
            logger.warning("psutil not available, process detection skipped")
        except Exception as exc:
            logger.warning("Process detection error: %s", exc)
        return running

    def _discover_by_muicache(self) -> dict[str, str]:
        """Discover emulator install paths via MuiCache registry entries.

        MuiCache tracks executables recently run by the user. Each value name
        is the full path to the .exe file, allowing us to locate emulator
        install directories even when standard uninstall keys are missing.

        Returns:
            Dict mapping emulator type to install path (directory of .exe)
        """
        found: dict[str, str] = {}
        if self._winreg is None:
            return found
        try:
            # MuiCache values live under HKCU only
            key = self._winreg.OpenKey(
                self._winreg.HKEY_CURRENT_USER, MUICACHE_KEY
            )
            try:
                index = 0
                while True:
                    try:
                        value_name, _value, _ = self._winreg.EnumValue(key, index)
                        index += 1
                        # value_name is typically "C:\\Path\\To\\app.exe"
                        basename = os.path.basename(value_name)
                        emu_type = MUICACHE_EMULATOR_EXES.get(basename)
                        if emu_type and emu_type not in found:
                            install_dir = os.path.dirname(value_name)
                            found[emu_type] = install_dir
                            logger.debug(
                                "MuiCache found %s at %s", emu_type, install_dir
                            )
                    except OSError:
                        # No more values
                        break
            finally:
                self._winreg.CloseKey(key)
        except OSError as exc:
            logger.debug("MuiCache key not accessible: %s", exc)
        return found

    def _discover_by_userassist(self) -> dict[str, str]:
        """Discover emulators via UserAssist registry entries.

        UserAssist tracks recently run programs with ROT13-encrypted value
        names. We decode each value name and check for emulator executable
        patterns. This catches emulators that were run but may not be running
        now and are missing from MuiCache.

        Returns:
            Dict mapping emulator type to install path
        """
        found: dict[str, str] = {}
        if self._winreg is None:
            return found

        for guid in USERASSIST_GUIDS:
            count_key_path = f"{USERASSIST_KEY}\\{guid}\\Count"
            try:
                key = self._winreg.OpenKey(
                    self._winreg.HKEY_CURRENT_USER, count_key_path
                )
                try:
                    index = 0
                    while True:
                        try:
                            value_name, _value, _ = self._winreg.EnumValue(key, index)
                            index += 1
                            # Decode ROT13 to get the original path
                            decoded = _rot13(value_name)
                            # UserAssist paths may have a prefix like
                            # "\\Device\\HarddiskVolumeN\\..." or be plain paths
                            if ":" not in decoded:
                                continue
                            basename = os.path.basename(decoded)
                            emu_type = MUICACHE_EMULATOR_EXES.get(basename)
                            if emu_type and emu_type not in found:
                                install_dir = os.path.dirname(decoded)
                                found[emu_type] = install_dir
                                logger.debug(
                                    "UserAssist found %s at %s",
                                    emu_type, install_dir,
                                )
                        except OSError:
                            break
                finally:
                    self._winreg.CloseKey(key)
            except OSError:
                # GUID key may not exist on this system, try next
                continue
        return found

    def _discover_by_vbox_conf(self) -> list[dict[str, Any]]:
        """Discover emulator instances by scanning VirtualBox config files.

        LDPlayer, MuMu, Nox, and MEmu all use VirtualBox under the hood and
        store per-instance configuration in .vbox XML files. Each .vbox file
        contains VM name, OSType, and hardware settings, allowing us to
        enumerate all configured emulator instances.

        Returns:
            List of dicts with keys: name, type, vbox_path, vm_name
        """
        instances: list[dict[str, Any]] = []
        seen_paths: set = set()

        for pattern in VBOX_CONF_SEARCH_PATHS:
            try:
                matches = glob.glob(pattern)
            except Exception as exc:
                logger.debug("glob error for %s: %s", pattern, exc)
                continue

            for vbox_path in matches:
                if vbox_path in seen_paths:
                    continue
                seen_paths.add(vbox_path)

                # Determine emulator type from path
                emu_type = "unknown"
                for marker, type_name in VBOX_PATH_TYPE_MAP:
                    if marker.lower() in vbox_path.lower():
                        emu_type = type_name
                        break

                # Parse .vbox XML to extract VM name
                vm_name = os.path.splitext(os.path.basename(vbox_path))[0]
                try:
                    tree = ET.parse(vbox_path)
                    root = tree.getroot()
                    # VirtualBox XML uses namespace; find Machine element
                    machine_elem = root.find(".//{*}Machine")
                    if machine_elem is not None:
                        name_attr = machine_elem.get("name")
                        if name_attr:
                            vm_name = name_attr
                except Exception as exc:
                    # ParseError, OSError (file not found), or any other
                    # XML parsing issue — fall back to filename-based name
                    logger.debug("Failed to parse %s: %s", vbox_path, exc)

                instances.append({
                    "name": f"{emu_type} - {vm_name}",
                    "type": emu_type,
                    "vbox_path": vbox_path,
                    "vm_name": vm_name,
                    "install_path": os.path.dirname(os.path.dirname(vbox_path)),
                })
                logger.debug(
                    "vbox-conf found %s instance: %s", emu_type, vm_name
                )

        return instances

    def discover_mumu(self) -> dict[str, Any] | None:
        """发现 MuMu 模拟器

        Returns:
            模拟器信息字典，未发现返回 None
        """
        config = EMULATOR_CONFIGS["mumu"]
        install_path = None
        for reg_path in config["reg_paths"]:
            install_path = self._read_registry(reg_path, "InstallPath")
            if install_path:
                break

        port = config["default_adb_port"]
        if not self._check_adb_port(port):
            adb_devices = self._get_adb_devices()
            for dev in adb_devices:
                if "127.0.0.1" in dev and str(port) in dev:
                    break
            else:
                logger.debug("MuMu 模拟器 ADB 端口 %d 不可达", port)
                return None

        return {
            "name": config["name"],
            "type": "mumu",
            "adb_port": port,
            "adb_serial": f"127.0.0.1:{port}",
            "install_path": install_path or "",
        }

    def discover_ldplayer(self) -> dict[str, Any] | None:
        """发现雷电模拟器

        Returns:
            模拟器信息字典，未发现返回 None
        """
        config = EMULATOR_CONFIGS["ldplayer"]
        install_path = None
        for reg_path in config["reg_paths"]:
            install_path = self._read_registry(reg_path, "InstallPath")
            if not install_path:
                install_path = self._read_registry(reg_path, "DisplayIcon")
            if install_path:
                break

        port = config["default_adb_port"]
        if not self._check_adb_port(port):
            logger.debug("雷电模拟器 ADB 端口 %d 不可达", port)
            return None

        return {
            "name": config["name"],
            "type": "ldplayer",
            "adb_port": port,
            "adb_serial": f"127.0.0.1:{port}",
            "install_path": install_path or "",
        }

    def discover_bluestacks(self) -> dict[str, Any] | None:
        """发现蓝叠模拟器

        Returns:
            模拟器信息字典，未发现返回 None
        """
        config = EMULATOR_CONFIGS["bluestacks"]
        install_path = None
        for reg_path in config["reg_paths"]:
            install_path = self._read_registry(reg_path, "InstallDir")
            if not install_path:
                install_path = self._read_registry(reg_path, "ClientBinDirectory")
            if install_path:
                break

        if not self._check_adb_port(config["default_adb_port"]):
            logger.debug("蓝叠模拟器 ADB 端口 %d 不可达", config["default_adb_port"])
            return None

        return {
            "name": config["name"],
            "type": "bluestacks",
            "adb_port": config["default_adb_port"],
            "adb_serial": f"127.0.0.1:{config['default_adb_port']}",
            "install_path": install_path or "",
        }

    def discover_xiaoyao(self) -> dict[str, Any] | None:
        """发现逍遥模拟器

        Returns:
            模拟器信息字典，未发现返回 None
        """
        config = EMULATOR_CONFIGS["xiaoyao"]
        install_path = None
        for reg_path in config["reg_paths"]:
            install_path = self._read_registry(reg_path, "InstallPath")
            if not install_path:
                install_path = self._read_registry(reg_path, "DisplayIcon")
            if install_path:
                break

        if not self._check_adb_port(config["default_adb_port"]):
            logger.debug("逍遥模拟器 ADB 端口 %d 不可达", config["default_adb_port"])
            return None

        return {
            "name": config["name"],
            "type": "xiaoyao",
            "adb_port": config["default_adb_port"],
            "adb_serial": f"127.0.0.1:{config['default_adb_port']}",
            "install_path": install_path or "",
        }

    def discover_nox(self) -> dict[str, Any] | None:
        """发现夜神模拟器

        Returns:
            模拟器信息字典，未发现返回 None
        """
        config = EMULATOR_CONFIGS["nox"]
        install_path = None
        for reg_path in config["reg_paths"]:
            install_path = self._read_registry(reg_path, "InstallPath")
            if not install_path:
                install_path = self._read_registry(reg_path, "UninstallString")
            if install_path:
                break

        if not self._check_adb_port(config["default_adb_port"]):
            logger.debug("夜神模拟器 ADB 端口 %d 不可达", config["default_adb_port"])
            return None

        return {
            "name": config["name"],
            "type": "nox",
            "adb_port": config["default_adb_port"],
            "adb_serial": f"127.0.0.1:{config['default_adb_port']}",
            "install_path": install_path or "",
        }

    def scan_adb_ports(self, start: int = 5554, end: int = 5684, timeout: float = 0.15) -> list[str]:
        """扫描 ADB 端口范围，发现活跃的 ADB 设备

        Args:
            start: 起始端口（包含）。默认 5554 (LDPlayer/BlueStacks 基准端口)
            end: 终止端口（包含）。默认 5684 — 覆盖 LDPlayer 多开 65 个实例
                (5554/5556/5558/...，每实例 +2)，之前 5584 只覆盖 15 个，
                多开场景会漏检。
            timeout: 单端口连接超时。默认 0.15s — 本地回环 RST 判定在毫秒级，
                130 端口 / 32 并发 / 0.15s ≈ 0.6~1s；keep 全端口覆盖不丢设备。

        Returns:
            ADB serial 列表（如 ['127.0.0.1:5555', '127.0.0.1:62001']）
        """
        import concurrent.futures

        discovered = []
        ports = range(start, end + 1)
        # 并发探测本地回环端口：TCP connect 是纯 I/O，线程池并行把串行
        # ~130s 压缩到亚秒级，同时保持全端口覆盖 (多实例/不同模拟器端口段)。
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
            futures = {
                executor.submit(self._check_adb_port, port, timeout): port
                for port in ports
            }
            for fut in concurrent.futures.as_completed(futures):
                port = futures[fut]
                try:
                    reachable = fut.result()
                except Exception:
                    reachable = False
                if reachable:
                    serial = f"127.0.0.1:{port}"
                    discovered.append(serial)
                    logger.debug("发现 ADB 端口: %s", serial)
        discovered.sort(key=lambda s: int(s.rsplit(":", 1)[1]))
        return discovered

    def discover_all(self) -> list[dict[str, Any]]:
        """Discover all emulators with fast process detection first

        Discovery phases:
            1. Process detection (fastest, indicates running emulators)
            2. Per-emulator registry + ADB port check (precise)
            3. MuiCache discovery (catches emulators missing from uninstall keys)
            4. UserAssist discovery (catches recently-run emulators)
            5. vbox-conf discovery (enumerates all configured instances)
            6. ADB port scan fallback (catches unknown emulators)

        Returns:
            List of emulator info dicts, each containing
            {name, type, adb_port, adb_serial, install_path, [discovery_source]}
        """
        results: list[dict[str, Any]] = []
        seen_serials: set = set()

        # Phase 1: Fast detection by running processes (skip registry if process found)
        running_emulators = self._discover_by_process()
        logger.info("Process detection found: %s", list(running_emulators.keys()))

        # Phase 2: Check each emulator type with priority for running ones
        discover_methods = [
            ("ldplayer", self.discover_ldplayer),
            ("mumu", self.discover_mumu),
            ("bluestacks", self.discover_bluestacks),
            ("nox", self.discover_nox),
            ("xiaoyao", self.discover_xiaoyao),
        ]

        for emu_type, method in discover_methods:
            try:
                # Skip detailed discovery if process not running (faster)
                if running_emulators and not running_emulators.get(emu_type):
                    logger.debug("Skipping %s (process not running)", emu_type)
                    continue

                info = method()
                if info:
                    info["discovery_source"] = "registry+adb"
                    results.append(info)
                    seen_serials.add(info["adb_serial"])
                    logger.info(
                        "Discovered emulator: %s (type=%s, port=%d)",
                        info["name"], info["type"], info["adb_port"],
                    )
            except Exception as exc:
                logger.warning("Emulator discovery method %s error: %s", method.__name__, exc)

        # Phase 3: MuiCache discovery — fill in install paths for emulators
        # that were not found via standard registry keys
        muicache_paths = self._discover_by_muicache()
        if muicache_paths:
            logger.info("MuiCache found paths: %s", list(muicache_paths.keys()))
            for emu_type, install_path in muicache_paths.items():
                # Skip if already discovered via registry+adb
                if any(r["type"] == emu_type for r in results):
                    continue
                config = EMULATOR_CONFIGS.get(emu_type)
                if not config:
                    continue
                port = config["default_adb_port"]
                serial = f"127.0.0.1:{port}"
                if serial in seen_serials:
                    continue
                results.append({
                    "name": config["name"],
                    "type": emu_type,
                    "adb_port": port,
                    "adb_serial": serial,
                    "install_path": install_path,
                    "discovery_source": "muicache",
                })
                seen_serials.add(serial)

        # Phase 4: UserAssist discovery — catches recently-run emulators
        userassist_paths = self._discover_by_userassist()
        if userassist_paths:
            logger.info(
                "UserAssist found paths: %s", list(userassist_paths.keys())
            )
            for emu_type, install_path in userassist_paths.items():
                if any(r["type"] == emu_type for r in results):
                    continue
                config = EMULATOR_CONFIGS.get(emu_type)
                if not config:
                    continue
                port = config["default_adb_port"]
                serial = f"127.0.0.1:{port}"
                if serial in seen_serials:
                    continue
                results.append({
                    "name": config["name"],
                    "type": emu_type,
                    "adb_port": port,
                    "adb_serial": serial,
                    "install_path": install_path,
                    "discovery_source": "userassist",
                })
                seen_serials.add(serial)

        # Phase 5: vbox-conf discovery — enumerate all configured instances
        vbox_instances = self._discover_by_vbox_conf()
        if vbox_instances:
            logger.info("vbox-conf found %d instances", len(vbox_instances))
            for inst in vbox_instances:
                emu_type = inst["type"]
                config = EMULATOR_CONFIGS.get(emu_type)
                port = config["default_adb_port"] if config else 5555
                serial = f"127.0.0.1:{port}"
                # Always include vbox instances (they may be additional
                # multi-instance configs even if base emulator already found)
                results.append({
                    "name": inst["name"],
                    "type": emu_type,
                    "adb_port": port,
                    "adb_serial": serial,
                    "install_path": inst["install_path"],
                    "discovery_source": "vbox-conf",
                    "vbox_path": inst["vbox_path"],
                    "vm_name": inst["vm_name"],
                })
                seen_serials.add(serial)

        # Phase 6: Fallback to ADB port scan if nothing found
        if not results:
            logger.info("No emulators found via registry/process/muicache/userassist/vbox, trying ADB port scan")
            adb_ports = self.scan_adb_ports()
            for serial in adb_ports:
                if serial not in seen_serials:
                    results.append({
                        "name": f"ADB Device ({serial})",
                        "type": "adb",
                        "adb_port": int(serial.split(":")[-1]),
                        "adb_serial": serial,
                        "install_path": "",
                        "discovery_source": "adb-scan",
                    })
                    seen_serials.add(serial)

        return results

    def _get_adb_devices(self) -> list[str]:
        """Get device list via adb devices command using discovered ADB path

        Returns:
            List of ADB device serial numbers
        """
        adb_cmd = self._adb_path or "adb"
        try:
            result = subprocess.run(
                [adb_cmd, "devices"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            devices = []
            for line in result.stdout.strip().splitlines()[1:]:
                if line.strip() and "\tdevice" in line:
                    devices.append(line.split("\t")[0].strip())
            return devices
        except Exception as exc:
            logger.warning("ADB devices command failed: %s", exc)
            return []
