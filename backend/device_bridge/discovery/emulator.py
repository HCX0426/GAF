"""
模拟器自动发现模块
参考 Alas 5途径扫描 + ADB 端口识别模拟器品牌
支持 MuMu / 雷电(LDPlayer) / 蓝叠(BlueStacks) / 逍遥(Memu) / 夜神(Nox) 5 种模拟器
"""

import contextlib
import logging
import os
import re
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


EMULATOR_PORT_RANGES: dict[str, list[tuple[int, int]]] = {
    'mumu': [(7555, 7555), (16384, 17408)],
    'ldplayer': [(5555, 5585)],
    'bluestacks': [(5555, 5595)],
    'nox': [(62001, 63025)],
    'memu': [(21503, 21523)],
}

EMULATOR_PROCESS_NAMES: dict[str, list[str]] = {
    'mumu': ['NemuPlayer.exe', 'MuMuPlayer.exe', 'MuMuPlayerGlobal.exe', 'nemu.exe', 'MuMuEmu.exe'],
    'ldplayer': ['dnplayer.exe', 'LdVBoxHeadless.exe', 'ldconsole.exe'],
    'bluestacks': ['Bluestacks.exe', 'HD-Player.exe', 'BSTKService.exe'],
    'nox': ['Nox.exe', 'NoxVMHandle.exe', 'NoxPlayer.exe'],
    'memu': ['MEmu.exe', 'MemuHyperv VM.exe', 'MEmuConsole.exe'],
}

EMULATOR_DISPLAY_NAMES: dict[str, str] = {
    'mumu': 'MuMu模拟器',
    'ldplayer': '雷电模拟器',
    'bluestacks': '蓝叠模拟器',
    'nox': '夜神模拟器',
    'memu': '逍遥模拟器',
}


@dataclass
class EmulatorInfo:
    """模拟器信息

    ``status`` uses raw string values that align with ``Device.Status``
    (online/offline/busy) so EmulatorInfo → Device conversion does not
    require value translation. The constants below centralize the
    allowed values to avoid typos at assignment sites.
    """
    # Status constants (align with agents.Device.Status values where applicable)
    STATUS_DISCOVERED = 'discovered'
    STATUS_RUNNING = 'running'  # ADB-connected = running = will become Device online

    name: str
    emulator: str
    adb_port: int
    adb_serial: str
    status: str = STATUS_DISCOVERED
    resolution: dict | None = None
    android_version: str = ''


def _identify_emulator_by_port(port: int) -> str | None:
    """根据 ADB 端口范围判断模拟器品牌"""
    for emu_type, ranges in EMULATOR_PORT_RANGES.items():
        for low, high in ranges:
            if low <= port <= high:
                return emu_type
    return None


def _find_adb_executable() -> str | None:
    """查找可用的 adb 可执行文件路径"""
    import shutil
    import winreg
    if os.name == 'nt':
        adb_in_path = shutil.which('adb')
        if adb_in_path:
            return adb_in_path
        # Search registry for LDPlayer install dirs (ldplayer9 / ldplayer / ldplayer14)
        for reg_subkey in [r'SOFTWARE\leidian\ldplayer9', r'SOFTWARE\leidian\ldplayer14', r'SOFTWARE\leidian\ldplayer']:
            for access_flag in [winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY]:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_subkey, 0, access_flag)
                    install_dir, _ = winreg.QueryValueEx(key, 'InstallDir')
                    winreg.CloseKey(key)
                    candidate = os.path.join(install_dir, 'adb.exe')
                    if os.path.isfile(candidate):
                        return candidate
                except Exception as e:
                    logger.warning('Registry adb lookup failed for %s: %s', reg_subkey, e)
        ld_default = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'LDPlayer9', 'adb.exe')
        if os.path.isfile(ld_default):
            return ld_default
        mumu_default = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Netease', 'MuMuPlayer-12.0', 'shell', 'adb.exe')
        if os.path.isfile(mumu_default):
            return mumu_default
        nox_default = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Nox', 'bin', 'nox_adb.exe')
        if os.path.isfile(nox_default):
            return nox_default
        bs_default = os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'BlueStacks_nxt', 'HD-Adb.exe')
        if os.path.isfile(bs_default):
            return bs_default
        memu_default = os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'Microvirt', 'MEmu', 'adb.exe')
        if os.path.isfile(memu_default):
            return memu_default
    else:
        return shutil.which('adb')
    return None


def _scan_running_processes() -> dict[str, list[int]]:
    """扫描运行中的模拟器进程，返回 {emulator_type: [pids]}"""
    result: dict[str, list[int]] = {}
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name']):
            proc_name = proc.info.get('name', '')
            for emu_type, names in EMULATOR_PROCESS_NAMES.items():
                if proc_name in names:
                    result.setdefault(emu_type, []).append(proc.info['pid'])
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f'进程扫描异常: {e}')
    return result


def _scan_adb_devices() -> list[EmulatorInfo]:
    """通过 adb devices -l 扫描已连接设备，并根据端口识别模拟器品牌"""
    results: list[EmulatorInfo] = []
    try:
        adb_exe = _find_adb_executable()
        if not adb_exe:
            logger.info('未找到 adb 可执行文件，跳过 ADB 设备扫描')
            return results
        proc = subprocess.run(
            [adb_exe, 'devices', '-l'],
            capture_output=True, text=True, timeout=10,
        )
        for line in proc.stdout.strip().split('\n')[1:]:
            line = line.strip()
            if not line or 'daemon' in line.lower():
                continue
            parts = line.split()
            if len(parts) < 2 or parts[1] != 'device':
                continue

            serial = parts[0]
            model = ''
            for part in parts[2:]:
                if part.startswith('model:'):
                    model = part.split(':', 1)[1]

            adb_port = 0
            adb_serial = serial
            if ':' in serial:
                with contextlib.suppress(ValueError):
                    adb_port = int(serial.split(':')[1])
                adb_serial = serial
            elif serial.startswith('emulator-'):
                try:
                    console_port = int(serial.split('-')[1])
                    adb_port = console_port + 1
                    adb_serial = f'127.0.0.1:{adb_port}'
                except ValueError:
                    pass

            emu_type = _identify_emulator_by_port(adb_port) if adb_port else None
            if not emu_type and model:
                model_lower = model.lower()
                if 'mumu' in model_lower or 'nemu' in model_lower:
                    emu_type = 'mumu'
                elif 'ldplayer' in model_lower or 'leidian' in model_lower:
                    emu_type = 'ldplayer'
                elif 'bluestacks' in model_lower or 'bst' in model_lower:
                    emu_type = 'bluestacks'
                elif 'nox' in model_lower:
                    emu_type = 'nox'
                elif 'memu' in model_lower:
                    emu_type = 'memu'

            display_name = EMULATOR_DISPLAY_NAMES.get(emu_type, '未知模拟器') if emu_type else model or serial
            name = f'{display_name}-{adb_port}' if adb_port else display_name

            results.append(EmulatorInfo(
                name=name,
                emulator=emu_type or 'unknown',
                adb_port=adb_port,
                adb_serial=adb_serial,
                status='discovered',
            ))
    except FileNotFoundError:
        logger.info('adb 命令未找到，跳过 ADB 设备扫描')
    except subprocess.TimeoutExpired:
        logger.warning('adb devices 命令超时')
    except Exception as e:
        logger.warning(f'ADB 扫描异常: {e}')
    return results


def _scan_config_files() -> list[EmulatorInfo]:
    """通过配置文件扫描已安装的模拟器实例"""
    results: list[EmulatorInfo] = []
    local_app_data = os.environ.get('LOCALAPPDATA', '')

    results.extend(_scan_ldplayer_config(local_app_data))
    results.extend(_scan_mumu_config(local_app_data))
    results.extend(_scan_bluestacks_config())
    results.extend(_scan_memu_config(local_app_data))
    results.extend(_scan_nox_config(local_app_data))

    return results


def _scan_ldplayer_config(local_app_data: str) -> list[EmulatorInfo]:
    """扫描雷电模拟器配置文件
    1. 先查注册表 InstallDir
    2. 再查 LOCALAPPDATA 默认路径
    3. 最后通过运行进程反推安装路径
    """
    results: list[EmulatorInfo] = []
    install_dir = None

    try:
        import winreg
        for reg_path in [
            r'SOFTWARE\leidian\ldplayer9',
            r'SOFTWARE\leidian\ldplayer',
            r'SOFTWARE\XuanZhi\LDPlayer',
        ]:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                install_dir, _ = winreg.QueryValueEx(key, 'InstallDir')
                winreg.CloseKey(key)
                if install_dir:
                    break
            except OSError:
                continue
    except ImportError:
        pass

    if not install_dir:
        for default_path in [
            os.path.join(local_app_data, 'XuanZhi', 'LDPlayer9'),
            os.path.join(local_app_data, 'XuanZhi', 'LDPlayer'),
        ]:
            if os.path.exists(default_path):
                install_dir = default_path
                break

    if not install_dir:
        try:
            import psutil
            for proc in psutil.process_iter(['name', 'exe']):
                if proc.info.get('name', '').lower() == 'dnplayer.exe' and proc.info.get('exe'):
                    proc_dir = os.path.dirname(proc.info['exe'])
                    if os.path.exists(os.path.join(proc_dir, 'vms')):
                        install_dir = proc_dir
                        break
        except Exception as e:
            logger.warning('LDPlayer process scan failed: %s', e)

    if not install_dir:
        return results

    config_dir = os.path.join(install_dir, 'vms', 'config')
    if not os.path.exists(config_dir):
        return results

    try:
        for filename in os.listdir(config_dir):
            if re.match(r'leidian\d+\.config$', filename):
                m = re.search(r'leidian(\d+)', filename)
                idx = int(m.group(1)) if m else 0
                adb_port = 5555 + idx * 2
                results.append(EmulatorInfo(
                    name=f'雷电模拟器-{idx + 1}',
                    emulator='ldplayer',
                    adb_port=adb_port,
                    adb_serial=f'127.0.0.1:{adb_port}',
                    status='discovered',
                ))
    except Exception as e:
        logger.warning(f'雷电配置扫描异常: {e}')
    return results


def _scan_mumu_config(local_app_data: str) -> list[EmulatorInfo]:
    """扫描 MuMu 模拟器配置文件（支持 MuMu 6 / X / 12）"""
    results: list[EmulatorInfo] = []

    for config_dir_path in [
        os.path.join(local_app_data, 'MuMu', 'emulator', 'nemu'),
        os.path.join(local_app_data, 'MuMuPlayerGlobal', 'shell', 'nemu'),
        os.path.join(local_app_data, 'MuMuPlayer-12.0', 'shell', 'vms'),
    ]:
        if not os.path.exists(config_dir_path):
            continue
        try:
            idx = 0
            for item in os.listdir(config_dir_path):
                if item.startswith('EmulatorConfig') and item.endswith('.ini'):
                    config_path = os.path.join(config_dir_path, item)
                    adb_port = _parse_config_port(config_path)
                    instance_name = item.replace('EmulatorConfig', '').replace('.ini', '')
                    is_mumu12 = 'MuMuPlayer-12.0' in config_dir_path
                    if adb_port == 0:
                        adb_port = (16384 + 32 * idx) if is_mumu12 else 7555
                    label = 'MuMu12' if is_mumu12 else 'MuMu'
                    results.append(EmulatorInfo(
                        name=f'{label}-{instance_name}' if instance_name else f'{label}-{idx + 1}',
                        emulator='mumu',
                        adb_port=adb_port,
                        adb_serial=f'127.0.0.1:{adb_port}',
                        status='discovered',
                    ))
                    idx += 1
        except Exception as e:
            logger.warning(f'MuMu 配置扫描异常: {e}')
    return results


def _scan_bluestacks_config() -> list[EmulatorInfo]:
    """扫描蓝叠模拟器配置（注册表 + bluestacks.conf）"""
    results: list[EmulatorInfo] = []
    try:
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r'SOFTWARE\BlueStacks\Guests\Android')
            idx = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, idx)
                    try:
                        subkey = winreg.OpenKey(key, subkey_name)
                        adb_port = 5555
                        try:
                            boot_params, _ = winreg.QueryValueEx(subkey, 'BootParameters')
                            if 'adb_port=' in boot_params:
                                port_str = boot_params.split('adb_port=', 1)[1].split()[0]
                                adb_port = int(port_str)
                        except Exception as e:
                            logger.warning('BlueStacks BootParameters parse failed for %s: %s', subkey_name, e)
                        results.append(EmulatorInfo(
                            name=f'蓝叠-{subkey_name}',
                            emulator='bluestacks',
                            adb_port=adb_port,
                            adb_serial=f'127.0.0.1:{adb_port}',
                            status='discovered',
                        ))
                        winreg.CloseKey(subkey)
                    except Exception as e:
                        logger.warning('BlueStacks subkey processing failed: %s', e)
                    idx += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except OSError:
            pass
    except ImportError:
        pass

    try:
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\BlueStacks_nxt')
            install_dir, _ = winreg.QueryValueEx(key, 'InstallDir')
            winreg.CloseKey(key)
            conf_path = os.path.join(install_dir, 'bluestacks.conf')
            if os.path.exists(conf_path):
                with open(conf_path, encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        m = re.match(r'bst\.instance\.(\w+)\.adb_port="(\d+)"', line.strip())
                        if m:
                            instance_name = m.group(1)
                            adb_port = int(m.group(2))
                            results.append(EmulatorInfo(
                                name=f'蓝叠5-{instance_name}',
                                emulator='bluestacks',
                                adb_port=adb_port,
                                adb_serial=f'127.0.0.1:{adb_port}',
                                status='discovered',
                            ))
        except OSError:
            pass
    except ImportError:
        pass

    return results


def _scan_memu_config(local_app_data: str) -> list[EmulatorInfo]:
    """扫描逍遥模拟器配置文件"""
    results: list[EmulatorInfo] = []
    vm_dir = os.path.join(local_app_data, 'Microvirt', 'MemuHyperv VMs')
    if not os.path.exists(vm_dir):
        return results
    try:
        for item in os.listdir(vm_dir):
            if item.startswith('Memu_'):
                vm_path = os.path.join(vm_dir, item)
                if os.path.isdir(vm_path):
                    memu_file = os.path.join(vm_path, f'{item}.memu')
                    adb_port = _parse_config_port(memu_file)
                    if adb_port == 0:
                        adb_port = 21503
                    display_name = item.replace('Memu_', '')
                    results.append(EmulatorInfo(
                        name=f'逍遥-{display_name}',
                        emulator='memu',
                        adb_port=adb_port,
                        adb_serial=f'127.0.0.1:{adb_port}',
                        status='discovered',
                    ))
    except Exception as e:
        logger.warning(f'逍遥配置扫描异常: {e}')
    return results


def _scan_nox_config(local_app_data: str) -> list[EmulatorInfo]:
    """扫描夜神模拟器配置文件"""
    results: list[EmulatorInfo] = []
    vm_dir = os.path.join(local_app_data, 'Nox', 'BignoxVMS')
    if not os.path.exists(vm_dir):
        return results
    try:
        for item in os.listdir(vm_dir):
            item_path = os.path.join(vm_dir, item)
            if os.path.isdir(item_path):
                config_file = os.path.join(item_path, 'clone_info.ini')
                adb_port = _parse_config_port(config_file)
                if adb_port == 0:
                    adb_port = 62001
                results.append(EmulatorInfo(
                    name=f'夜神-{item}',
                    emulator='nox',
                    adb_port=adb_port,
                    adb_serial=f'127.0.0.1:{adb_port}',
                    status='discovered',
                ))
    except Exception as e:
        logger.warning(f'夜神配置扫描异常: {e}')
    return results


def _parse_config_port(config_path: str) -> int:
    """解析配置文件中的 ADB 端口"""
    if not os.path.exists(config_path):
        return 0
    try:
        with open(config_path, encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if 'adb_port' in line.lower() or 'adbPort' in line:
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        return int(parts[1].strip().strip('"'))
    except Exception as e:
        logger.warning('Failed to parse config port from %s: %s', config_path, e)
    return 0


EMULATOR_EXECUTABLE_KEYWORDS = [
    'nemu', 'mumu', 'ldplayer', 'dnplayer', 'bluestacks', 'bstk',
    'nox', 'memu', 'leidian', '雷电', '逍遥', '夜神', '蓝叠',
]


def _verify_emulator_installed(emu_type: str, path_hint: str = '') -> bool:
    """验证模拟器可执行文件是否存在（对注册表发现的条目二次检查）

    仅对注册表来源（非配置文件/ADB 来源）的模拟器做可执行文件验证。
    """
    executable_hints = {
        'mumu': ['MuMuPlayer.exe', 'NemuPlayer.exe', 'MuMuManager.exe'],
        'ldplayer': ['dnplayer.exe', 'ldconsole.exe', 'ld.exe', 'LdPlayer.exe'],
        'bluestacks': ['BlueStacks.exe', 'bstk.exe', 'HD-Player.exe', 'BSPlayer.exe'],
        'nox': ['Nox.exe', 'nox_player.exe', 'NoxVMHandle.exe'],
        'memu': ['MEmu.exe', 'memuconsole.exe', 'MEmuPlayer.exe'],
    }
    exe_names = executable_hints.get(emu_type, [emu_type + '.exe'])
    search_paths = [os.environ.get('PROGRAMFILES', 'C:\\Program Files'),
                    os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'),
                    os.path.expandvars('%LOCALAPPDATA%')]

    all_search = list(search_paths)
    if path_hint and os.path.exists(path_hint):
        all_search.insert(0, os.path.dirname(path_hint))

    for base in all_search:
        for root, dirs, files in os.walk(base):
            depth = root.replace(base, '').count(os.sep)
            if depth > 3:
                dirs.clear()
                continue
            for f in files:
                if f.lower() in [e.lower() for e in exe_names]:
                    return True

    return False


def _scan_muicache_registry() -> list[EmulatorInfo]:
    """通过 Windows MuiCache 注册表扫描模拟器安装路径
    MuiCache 记录应用程序的 FriendlyName → 可执行文件路径映射
    """
    results: list[EmulatorInfo] = []
    if os.name != 'nt':
        return results
    try:
        import winreg
        mui_paths = [
            r'Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache',
        ]
        for mui_path in mui_paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, mui_path)
                idx = 0
                while True:
                    try:
                        value_name, value_data, value_type = winreg.EnumValue(key, idx)
                        lower_name = value_name.lower()
                        lower_data = value_data.lower() if isinstance(value_data, str) else ''
                        matched = any(
                            kw in lower_name or kw in lower_data
                            for kw in EMULATOR_EXECUTABLE_KEYWORDS
                        )
                        if not matched:
                            idx += 1
                            continue
                        emu_type = 'unknown'
                        for kw, emu in [
                            ('mumu', 'mumu'), ('nemu', 'mumu'),
                            ('ldplayer', 'ldplayer'), ('dnplayer', 'ldplayer'), ('leidian', 'ldplayer'),
                            ('bluestacks', 'bluestacks'), ('bstk', 'bluestacks'),
                            ('nox', 'nox'),
                            ('memu', 'memu'),
                        ]:
                            if kw in lower_name or kw in lower_data:
                                emu_type = emu
                                break
                        path = value_data if isinstance(value_data, str) else value_name
                        if not _verify_emulator_installed(emu_type, path):
                            idx += 1
                            continue
                        _vms_dir = None
                        if 'vms' in path.lower():
                            _vms_dir = os.path.dirname(path)
                        elif os.path.dirname(path):
                            parent = os.path.dirname(path)
                            candidate = os.path.join(parent, 'vms')
                            if os.path.exists(candidate):
                                _vms_dir = candidate
                        if _vms_dir:
                            try:
                                for fn in os.listdir(_vms_dir):
                                    if fn.endswith('.config') or fn.endswith('.memu') or fn.endswith('.ini'):
                                        cfg = os.path.join(_vms_dir, fn)
                                        adb_port = _parse_config_port(cfg) or _guess_default_port(emu_type)
                                        name = f'{EMULATOR_DISPLAY_NAMES.get(emu_type, emu_type)}-MuiCache'
                                        results.append(EmulatorInfo(
                                            name=name,
                                            emulator=emu_type,
                                            adb_port=adb_port,
                                            adb_serial=f'127.0.0.1:{adb_port}',
                                            status='discovered',
                                        ))
                            except Exception as e:
                                logger.warning('MuiCache vms dir scan failed: %s', e)
                        if not _vms_dir:
                            adb_port = _guess_default_port(emu_type)
                            results.append(EmulatorInfo(
                                name=f'{EMULATOR_DISPLAY_NAMES.get(emu_type, emu_type)}-MuiCache',
                                emulator=emu_type,
                                adb_port=adb_port,
                                adb_serial=f'127.0.0.1:{adb_port}',
                                status='discovered',
                            ))
                        idx += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except OSError:
                continue
    except ImportError:
        pass
    except Exception as e:
        logger.debug('MuiCache 注册表扫描异常: %s', e)
    return results


def _scan_userassist_registry() -> list[EmulatorInfo]:
    """通过 Windows UserAssist 注册表扫描模拟器启动历史
    UserAssist 记录用户启动过的应用程序及其运行次数，可用于发现未在配置文件中注册的实例
    """
    results: list[EmulatorInfo] = []
    if os.name != 'nt':
        return results
    try:
        import winreg
        userassist_paths = [
            r'Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist\{CEBFF5CD-ACE2-4F4F-9178-9926F41749EA}\Count',
            r'Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist\{F4E57C4B-2036-45F0-A9AB-443BCFE33D9F}\Count',
        ]
        for ua_path in userassist_paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, ua_path)
                idx = 0
                while True:
                    try:
                        value_name, value_data, value_type = winreg.EnumValue(key, idx)
                        try:
                            decoded = _rot13_decode(value_name) if isinstance(value_name, str) else value_name
                        except Exception:
                            decoded = value_name
                        lower = decoded.lower()
                        matched = any(kw in lower for kw in EMULATOR_EXECUTABLE_KEYWORDS)
                        if not matched:
                            idx += 1
                            continue
                        emu_type = 'unknown'
                        for kw, emu in [
                            ('mumu', 'mumu'), ('nemu', 'mumu'),
                            ('ldplayer', 'ldplayer'), ('dnplayer', 'ldplayer'), ('leidian', 'ldplayer'),
                            ('bluestacks', 'bluestacks'), ('bstk', 'bluestacks'),
                            ('nox', 'nox'),
                            ('memu', 'memu'),
                        ]:
                            if kw in lower:
                                emu_type = emu
                                break
                        if not _verify_emulator_installed(emu_type, decoded):
                            idx += 1
                            continue
                        adb_port = _guess_default_port(emu_type)
                        results.append(EmulatorInfo(
                            name=f'{EMULATOR_DISPLAY_NAMES.get(emu_type, emu_type)}-UserAssist',
                            emulator=emu_type,
                            adb_port=adb_port,
                            adb_serial=f'127.0.0.1:{adb_port}',
                            status='discovered',
                        ))
                        idx += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except OSError:
                continue
    except ImportError:
        pass
    except Exception as e:
        logger.debug('UserAssist 注册表扫描异常: %s', e)
    return results


def _rot13_decode(text: str) -> str:
    """ROT13 解码 UserAssist 中的编码路径"""
    result = []
    for ch in text:
        if 'a' <= ch <= 'z':
            result.append(chr((ord(ch) - ord('a') + 13) % 26 + ord('a')))
        elif 'A' <= ch <= 'Z':
            result.append(chr((ord(ch) - ord('A') + 13) % 26 + ord('A')))
        else:
            result.append(ch)
    return ''.join(result)


def _guess_default_port(emu_type: str) -> int:
    """根据模拟器类型返回默认 ADB 端口"""
    defaults = {'mumu': 7555, 'ldplayer': 5555, 'bluestacks': 5555, 'nox': 62001, 'memu': 21503}
    return defaults.get(emu_type, 5555)


def scan_all_emulators() -> list[EmulatorInfo]:
    """Scan all emulator types with fast-path prioritization

    Optimization strategy:
    - Phase 1 (fast <1s): Running processes + ADB devices
    - Phase 2 (medium <3s): Config files scan
    - Phase 3 (slow, optional): Registry scan only if no results yet
    - Total timeout: 15 seconds
    """
    import time
    start_time = time.time()
    seen_serials = set()
    seen_ports = set()  # Track ports to avoid duplicates
    merged = []

    def _is_duplicate(emu: EmulatorInfo) -> bool:
        """Check if emulator is duplicate by serial or port"""
        # Primary: check by adb_serial (most reliable)
        key = emu.adb_serial or f'{emu.emulator}:{emu.adb_port}'
        if key in seen_serials:
            return True
        # Secondary: check by port alone (catches same port from different sources)
        return bool(emu.adb_port and emu.adb_port in seen_ports)

    def _add_emulator(emu: EmulatorInfo) -> None:
        """Add emulator to merged list with deduplication"""
        key = emu.adb_serial or f'{emu.emulator}:{emu.adb_port}'
        seen_serials.add(key)
        if emu.adb_port:
            seen_ports.add(emu.adb_port)
        merged.append(emu)

    def _merge_results(results: list[EmulatorInfo]) -> None:
        """Merge scan results into unified list with deduplication"""
        for emu in results:
            if _is_duplicate(emu):
                # Check if we should upgrade existing entry with better info
                for existing in merged:
                    existing_key = existing.adb_serial or f'{existing.emulator}:{existing.adb_port}'
                    emu_key = emu.adb_serial or f'{emu.emulator}:{emu.adb_port}'
                    # Prefer: known emulator type over unknown, or ADB-confirmed over config-only
                    if existing_key == emu_key and existing.emulator == 'unknown' and emu.emulator != 'unknown':
                        existing.emulator = emu.emulator
                        existing.name = emu.name
                    # Prefer ADB-connected over registry-only
                    if existing.adb_port == 0 and emu.adb_port and emu.adb_port == existing.adb_port:
                        existing.adb_port = emu.adb_port
                        existing.adb_serial = emu.adb_serial
                        existing.name = emu.name
                        existing.status = EmulatorInfo.STATUS_RUNNING  # ADB-connected means running
                continue
            _add_emulator(emu)

    # Phase 1: Fast path - running processes + ADB devices (<2 seconds)
    logger.info('Phase 1: Fast scan (processes + ADB)')
    running = _scan_running_processes()
    adb_results = _scan_adb_devices()
    _merge_results(adb_results)

    # Mark running emulators
    if running:
        for emu in merged:
            if emu.emulator in running:
                emu.status = EmulatorInfo.STATUS_RUNNING

    phase1_time = time.time() - start_time
    logger.info(f'Phase 1 completed in {phase1_time:.2f}s, found {len(merged)} emulators')

    # If already found emulators via ADB, skip slow registry scans
    if merged:
        logger.info(f'Skipping slow registry scans ({len(merged)} already found via ADB)')
        if merged:
            logger.info(f'模拟器扫描完成，共发现 {len(merged)} 个实例 (fast path, {time.time()-start_time:.2f}s)')
        return merged

    # Phase 2: Medium path - config files scan (<5 seconds)
    if time.time() - start_time < 10:
        logger.info('Phase 2: Config files scan')
        config_results = _scan_config_files()
        _merge_results(config_results)

        # Update status based on running processes
        if running:
            for emu in merged:
                if emu.emulator in running:
                    emu.status = EmulatorInfo.STATUS_RUNNING

        phase2_time = time.time() - start_time
        logger.info(f'Phase 2 completed in {phase2_time:.2f}s, total: {len(merged)} emulators')

        # If found results, return early
        if merged:
            if merged:
                logger.info(f'模拟器扫描完成，共发现 {len(merged)} 个实例 (config path, {time.time()-start_time:.2f}s)')
            return merged

    # Phase 3: Slow path - registry scan only if nothing found yet (<10 seconds remaining)
    if time.time() - start_time < 12:
        logger.info('Phase 3: Registry scan (slow)')
        try:
            registry_results = _scan_muicache_registry() + _scan_userassist_registry()
            _merge_results(registry_results)
        except Exception as e:
            logger.warning(f'Registry scan failed: {e}')

    # Final status update
    if running:
        for emu in merged:
            if emu.emulator in running:
                emu.status = EmulatorInfo.STATUS_RUNNING

    total_time = time.time() - start_time
    if merged:
        logger.info(f'模拟器扫描完成，共发现 {len(merged)} 个实例 (total: {total_time:.2f}s)')
    else:
        logger.info(f'未发现模拟器 (total: {total_time:.2f}s)')
    return merged
