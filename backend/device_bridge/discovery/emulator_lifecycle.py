"""
Emulator lifecycle control module
Reference Alas emulator management, provide start/stop/restart/create/delete operations
Current support: LDPlayer (Leidian), interface designed for cross-emulator brand extension

LDPlayer uses ldconsole.exe command line control:
  list2          — List all instances (name, index, status)
  launch --name  — Launch instance
  quit --name    — Quit instance
  reboot --name  — Reboot instance
  add --name     — Create new instance
  remove --name  — Delete instance

Phase 9.1 additions:
  health_check       — ADB connection + screen fps + ANR dialog detection
  auto_restart       — Auto-restart on unhealthy with retry limit (reference Alas stuck_timer)
  get_adb_serial     — Resolve ADB serial for a running instance
"""

import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EmulatorInstance:
    name: str
    index: int
    status: str = 'unknown'
    emulator_type: str = 'ldplayer'
    is_running: bool = False


@dataclass
class LifecycleResult:
    success: bool
    message: str
    instance: EmulatorInstance | None = None
    raw_output: str = ''


def _find_ldconsole() -> str | None:
    """查找 LDPlayer ldconsole.exe 的安装路径"""
    import shutil
    import winreg

    ld_path = shutil.which('ldconsole')
    if ld_path:
        return ld_path

    for reg_path in [
        r'SOFTWARE\leidian\ldplayer9',
        r'SOFTWARE\leidian\ldplayer',
        r'SOFTWARE\XuanZhi\LDPlayer',
    ]:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
            install_dir, _ = winreg.QueryValueEx(key, 'InstallDir')
            winreg.CloseKey(key)
            candidate = os.path.join(install_dir, 'ldconsole.exe')
            if os.path.isfile(candidate):
                return candidate
        except OSError:
            continue

    for default_path in [
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'XuanZhi', 'LDPlayer9', 'ldconsole.exe'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'XuanZhi', 'LDPlayer', 'ldconsole.exe'),
    ]:
        if os.path.isfile(default_path):
            return default_path

    return None


def _run_ldconsole(args: list[str], timeout: int = 30) -> str:
    """执行 ldconsole 命令并返回 stdout"""
    exe = _find_ldconsole()
    if not exe:
        return ''
    try:
        proc = subprocess.run(
            [exe] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        return proc.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.warning(f'ldconsole {args} 超时')
        return ''
    except Exception as e:
        logger.warning(f'ldconsole {args} 异常: {e}')
        return ''


def list_instances() -> list[EmulatorInstance]:
    """列出所有 LDPlayer 实例（名称、索引、运行状态）"""
    ldconsole = _find_ldconsole()
    if not ldconsole:
        return []

    results = []
    try:
        proc = subprocess.run(
            [ldconsole, 'list2'],
            capture_output=True, text=True, timeout=10,
        )
        for line in proc.stdout.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) >= 4:
                index = int(parts[0])
                name = parts[1]
                parts[2]
                parts[3]
                is_running = '1' in parts[4] if len(parts) > 4 else False
                int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0
                results.append(EmulatorInstance(
                    name=name,
                    index=index,
                    status='running' if is_running else 'stopped',
                    is_running=is_running,
                ))
    except Exception as e:
        logger.warning(f'ldconsole list2 异常: {e}')

    return results


def start_instance(name_or_index: str) -> LifecycleResult:
    """启动模拟器实例"""
    ldconsole = _find_ldconsole()
    if not ldconsole:
        return LifecycleResult(False, '未找到 ldconsole.exe，请确认雷电模拟器已安装')

    try:
        index = int(name_or_index) if name_or_index.isdigit() else None
        if index is not None:
            output = _run_ldconsole(['launch', '--index', str(index)])
        else:
            output = _run_ldconsole(['launch', '--name', name_or_index])

        if output and 'error' in output.lower():
            return LifecycleResult(False, f'启动失败: {output}')

        return LifecycleResult(
            True,
            f'模拟器 "{name_or_index}" 启动中',
            EmulatorInstance(name=name_or_index, index=index or 0, status='running'),
            raw_output=output,
        )
    except Exception as e:
        return LifecycleResult(False, f'启动异常: {e}')


def stop_instance(name_or_index: str) -> LifecycleResult:
    """关闭模拟器实例（非强制，保存状态）"""
    ldconsole = _find_ldconsole()
    if not ldconsole:
        return LifecycleResult(False, '未找到 ldconsole.exe')

    try:
        index = int(name_or_index) if name_or_index.isdigit() else None
        if index is not None:
            output = _run_ldconsole(['quit', '--index', str(index)])
        else:
            output = _run_ldconsole(['quit', '--name', name_or_index])

        return LifecycleResult(
            True,
            f'模拟器 "{name_or_index}" 已关闭',
            EmulatorInstance(name=name_or_index, index=index or 0, status='stopped'),
            raw_output=output,
        )
    except Exception as e:
        return LifecycleResult(False, f'关闭异常: {e}')


def restart_instance(name_or_index: str) -> LifecycleResult:
    """重启模拟器实例"""
    ldconsole = _find_ldconsole()
    if not ldconsole:
        return LifecycleResult(False, '未找到 ldconsole.exe')

    try:
        index = int(name_or_index) if name_or_index.isdigit() else None
        if index is not None:
            _run_ldconsole(['quit', '--index', str(index)])
            time.sleep(3)
            output = _run_ldconsole(['launch', '--index', str(index)])
        else:
            _run_ldconsole(['quit', '--name', name_or_index])
            time.sleep(3)
            output = _run_ldconsole(['launch', '--name', name_or_index])

        return LifecycleResult(
            True,
            f'模拟器 "{name_or_index}" 重启中',
            EmulatorInstance(name=name_or_index, index=index or 0, status='running'),
            raw_output=output,
        )
    except Exception as e:
        return LifecycleResult(False, f'重启异常: {e}')


def create_instance(name: str) -> LifecycleResult:
    """创建新的 LDPlayer 实例"""
    ldconsole = _find_ldconsole()
    if not ldconsole:
        return LifecycleResult(False, '未找到 ldconsole.exe')

    try:
        output = _run_ldconsole(['add', '--name', name], timeout=60)

        if output and 'error' in output.lower():
            return LifecycleResult(False, f'创建失败: {output}')

        instances = list_instances()
        created = next((i for i in instances if i.name == name), None)

        return LifecycleResult(
            True,
            f'实例 "{name}" 已创建',
            instance=created or EmulatorInstance(name=name, index=0, status='stopped'),
            raw_output=output,
        )
    except Exception as e:
        return LifecycleResult(False, f'创建异常: {e}')


def delete_instance(name_or_index: str) -> LifecycleResult:
    """删除 LDPlayer 实例"""
    ldconsole = _find_ldconsole()
    if not ldconsole:
        return LifecycleResult(False, '未找到 ldconsole.exe')

    try:
        index = int(name_or_index) if name_or_index.isdigit() else None
        if index is not None:
            _run_ldconsole(['quit', '--index', str(index)])
            time.sleep(2)
            output = _run_ldconsole(['remove', '--index', str(index)])
        else:
            _run_ldconsole(['quit', '--name', name_or_index])
            time.sleep(2)
            output = _run_ldconsole(['remove', '--name', name_or_index])

        return LifecycleResult(
            True,
            f'实例 "{name_or_index}" 已删除',
            raw_output=output,
        )
    except Exception as e:
        return LifecycleResult(False, f'删除异常: {e}')


def run_adb_command(adb_serial: str, command: str) -> LifecycleResult:
    """在指定 ADB 设备上执行原始命令"""
    from .emulator import _find_adb_executable
    adb = _find_adb_executable()
    if not adb:
        return LifecycleResult(False, '未找到 adb 可执行文件')

    args = command.strip().split()
    try:
        proc = subprocess.run(
            [adb, '-s', adb_serial] + args,
            capture_output=True, text=True, timeout=15,
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        output = stdout or stderr or '(无输出)'
        return LifecycleResult(
            True,
            'ADB 命令执行成功',
            raw_output=output,
        )
    except subprocess.TimeoutExpired:
        return LifecycleResult(False, 'ADB 命令超时')
    except Exception as e:
        return LifecycleResult(False, f'ADB 命令异常: {e}')


@dataclass
class HealthCheckResult:
    """Result of emulator health check"""
    instance_name: str
    instance_index: int
    is_healthy: bool
    adb_connected: bool = False
    screen_fps: float = 0.0
    anr_detected: bool = False
    response_time_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: str = ''
    error: str = ''


def get_adb_serial(instance: EmulatorInstance) -> str | None:
    """Resolve ADB serial for a running LDPlayer instance

    LDPlayer default ADB port formula: base_port(5555) + index * 2
    Also tries ldconsole --adb query if available.
    """
    if not instance.is_running:
        return None

    default_port = 5555 + instance.index * 2
    serial = f'127.0.0.1:{default_port}'

    output = _run_ldconsole(['adb', '--index', str(instance.index)])
    if output and ':' in output:
        for line in output.split('\n'):
            line = line.strip()
            if '127.0.0.1:' in line:
                match = re.search(r'127\.0\.0\.1:\d+', line)
                if match:
                    serial = match.group(0)
                    break

    return serial


def health_check(instance: EmulatorInstance, timeout: int = 10) -> HealthCheckResult:
    """Perform health check on an emulator instance

    Checks:
    1. ADB connection — verify device responds to shell echo
    2. Screen FPS estimate — measure screencap round-trip time
    3. ANR dialog detection — check for android.app.Dialog ANR windows via uiautomator

    Args:
        instance: EmulatorInstance to check
        timeout: ADB command timeout in seconds

    Returns:
        HealthCheckResult with detailed status
    """
    # B004 fix: use timezone-aware UTC timestamp (datetime.now() without tz
    # produces naive datetimes which break ISO parsing under USE_TZ=True).
    from datetime import datetime

    result = HealthCheckResult(
        instance_name=instance.name,
        instance_index=instance.index,
        is_healthy=False,
        checked_at=datetime.now(UTC).isoformat(),
    )

    if not instance.is_running:
        result.error = 'Instance is not running'
        return result

    serial = get_adb_serial(instance)
    if not serial:
        result.error = 'Cannot resolve ADB serial'
        return result

    from .emulator import _find_adb_executable
    adb = _find_adb_executable()
    if not adb:
        result.error = 'ADB executable not found'
        return result

    start_time = time.time()

    try:
        proc = subprocess.run(
            [adb, '-s', serial, 'shell', 'echo', '__HEALTH_CHECK__'],
            capture_output=True, text=True, timeout=timeout,
        )
        result.adb_connected = proc.returncode == 0 and '__HEALTH_CHECK__' in proc.stdout
    except subprocess.TimeoutExpired:
        result.adb_connected = False
        result.details['adb_error'] = 'ADB connection timeout'
    except Exception as e:
        result.adb_connected = False
        result.details['adb_error'] = str(e)

    if result.adb_connected:
        try:
            fps_start = time.time()
            subprocess.run(
                [adb, '-s', serial, 'shell', 'screencap', '-p', '/dev/null'],
                capture_output=True, text=True, timeout=timeout,
            )
            fps_elapsed = time.time() - fps_start
            result.screen_fps = round(1.0 / max(fps_elapsed, 0.001), 1)
            result.details['screencap_time_s'] = round(fps_elapsed, 3)
        except (subprocess.TimeoutExpired, Exception):
            result.screen_fps = 0.0
            result.details['screencap_error'] = 'Screen capture failed or timeout'

        try:
            anr_proc = subprocess.run(
                [adb, '-s', serial, 'shell', 'uiautomator', 'dump', '/dev/stdout'],
                capture_output=True, text=True, timeout=timeout,
            )
            anr_output = anr_proc.stdout.lower() + anr_proc.stderr.lower()
            result.anr_detected = any(
                keyword in anr_output
                for keyword in ['anr', 'application not responding', 'wait', 'force close']
            )
            if result.anr_detected:
                result.details['anr_keywords'] = [
                    kw for kw in ['anr', 'application not responding', 'wait', 'force close']
                    if kw in anr_output
                ]
        except (subprocess.TimeoutExpired, Exception):
            logger.debug('ANR check failed for %s', serial, exc_info=True)

    result.response_time_ms = round((time.time() - start_time) * 1000, 1)

    result.is_healthy = (
        result.adb_connected
        and not result.anr_detected
        and result.screen_fps > 0.1
    )

    if not result.is_healthy and not result.error:
        reasons = []
        if not result.adb_connected:
            reasons.append('ADB disconnected')
        if result.anr_detected:
            reasons.append('ANR detected')
        if result.screen_fps <= 0.1:
            reasons.append('Screen frozen')
        result.error = '; '.join(reasons)

    logger.info(
        f'Health check [{instance.name}]: healthy={result.is_healthy}, '
        f'adb={result.adb_connected}, fps={result.screen_fps}, '
        f'anr={result.anr_detected}, {result.response_time_ms}ms'
    )

    return result


def auto_restart(
    instance: EmulatorInstance,
    max_retries: int = 3,
    retry_interval: int = 10,
    health_timeout: int = 10,
) -> LifecycleResult:
    """Auto-restart unhealthy emulator instance with retry limit

    Reference Alas stuck_timer strategy: when emulator is stuck (ANR/frozen/ADB lost),
    attempt restart up to max_retries times before giving up.

    Flow:
    1. Health check the instance
    2. If healthy, return success immediately
    3. If unhealthy, stop → wait → start → re-check
    4. Repeat up to max_retries times
    5. If still unhealthy after all retries, report failure

    Args:
        instance: EmulatorInstance to auto-restart
        max_retries: Maximum restart attempts (default 3)
        retry_interval: Seconds between stop and start (default 10)
        health_timeout: Timeout per health check in seconds (default 10)

    Returns:
        LifecycleResult with success/failure and details
    """
    hc = health_check(instance, timeout=health_timeout)
    if hc.is_healthy:
        return LifecycleResult(
            True,
            f'Instance "{instance.name}" is healthy, no restart needed',
            instance=instance,
            raw_output=f'fps={hc.screen_fps}, adb={hc.adb_connected}',
        )

    name_or_index = str(instance.index) if instance.index >= 0 else instance.name
    last_error = hc.error or 'Unknown health issue'

    for attempt in range(1, max_retries + 1):
        logger.info(
            f'Auto-restart [{instance.name}] attempt {attempt}/{max_retries}: {last_error}'
        )

        stop_result = stop_instance(name_or_index)
        if not stop_result.success:
            last_error = f'Stop failed (attempt {attempt}): {stop_result.message}'
            continue

        time.sleep(retry_interval)

        start_result = start_instance(name_or_index)
        if not start_result.success:
            last_error = f'Start failed (attempt {attempt}): {start_result.message}'
            continue

        time.sleep(5)

        refreshed = list_instances()
        refreshed_inst = next(
            (i for i in refreshed if i.index == instance.index or i.name == instance.name),
            None,
        )
        if not refreshed_inst:
            last_error = f'Instance not found after restart (attempt {attempt})'
            continue

        time.sleep(3)

        recheck = health_check(refreshed_inst, timeout=health_timeout)
        if recheck.is_healthy:
            return LifecycleResult(
                True,
                f'Instance "{instance.name}" recovered after {attempt} restart(s)',
                instance=refreshed_inst,
                raw_output=(
                    f'restarts={attempt}, fps={recheck.screen_fps}, '
                    f'adb={recheck.adb_connected}, original_issue={hc.error}'
                ),
            )

        last_error = f'Still unhealthy after restart (attempt {attempt}): {recheck.error}'

    return LifecycleResult(
        False,
        f'Instance "{instance.name}" failed to recover after {max_retries} attempts: {last_error}',
        instance=instance,
        raw_output=f'max_retries={max_retries}, last_error={last_error}',
    )


def health_check_all(timeout: int = 10) -> list[HealthCheckResult]:
    """Run health check on all running instances

    Args:
        timeout: Per-instance health check timeout in seconds

    Returns:
        List of HealthCheckResult for each running instance
    """
    instances = list_instances()
    results = []
    for inst in instances:
        if inst.is_running:
            try:
                results.append(health_check(inst, timeout=timeout))
            except Exception as e:
                results.append(HealthCheckResult(
                    instance_name=inst.name,
                    instance_index=inst.index,
                    is_healthy=False,
                    error=f'Health check exception: {e}',
                ))
    return results


_monitor_thread: threading.Thread | None = None
_monitor_stop_event = threading.Event()


def start_health_monitor(
    interval: int = 60,
    callback=None,
    auto_restart_unhealthy: bool = False,
    max_retries: int = 3,
):
    """Start background thread for periodic health monitoring

    Args:
        interval: Check interval in seconds (default 60)
        callback: Optional callable(results: List[HealthCheckResult]) for custom handling
        auto_restart_unhealthy: If True, auto-restart unhealthy instances
        max_retries: Max retries for auto-restart (default 3)
    """
    global _monitor_thread, _monitor_stop_event

    if _monitor_thread and _monitor_thread.is_alive():
        logger.warning('Health monitor already running')
        return

    _monitor_stop_event.clear()

    def _monitor_loop():
        logger.info(f'Health monitor started (interval={interval}s)')
        while not _monitor_stop_event.is_set():
            try:
                results = health_check_all()
                for r in results:
                    if not r.is_healthy:
                        logger.warning(
                            f'Monitor: [{r.instance_name}] UNHEALTHY - {r.error}'
                        )
                        if auto_restart_unhealthy:
                            instances = list_instances()
                            inst = next(
                                (i for i in instances if i.index == r.instance_index),
                                None,
                            )
                            if inst:
                                ar = auto_restart(inst, max_retries=max_retries)
                                logger.info(
                                    f'Monitor auto-restart [{inst.name}]: {ar.success}'
                                )

                if callback:
                    try:
                        callback(results)
                    except Exception as e:
                        logger.error(f'Health monitor callback error: {e}')

            except Exception as e:
                logger.error(f'Health monitor loop error: {e}')

            _monitor_stop_event.wait(interval)

        logger.info('Health monitor stopped')

    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True, name='EmulatorHealthMonitor')
    _monitor_thread.start()


def stop_health_monitor():
    """Stop the background health monitoring thread"""
    global _monitor_stop_event
    _monitor_stop_event.set()
    logger.info('Health monitor stop requested')


@dataclass
class EmulatorConfig:
    """Emulator configuration parameters"""
    resolution: str | None = None
    dpi: int | None = None
    cpu_count: int | None = None
    memory_mb: int | None = None


def configure_instance(
    name_or_index: str,
    config: EmulatorConfig,
) -> LifecycleResult:
    """Configure emulator instance parameters (resolution, DPI, CPU, memory)

    Uses ldconsole modify command to change instance settings.
    The instance must be stopped before configuration changes.

    Supported config keys:
    - resolution: String like '1280x720' or '1920x1080'
    - dpi: Integer DPI value (120, 160, 240, 320, etc.)
    - cpu_count: Number of CPU cores (1, 2, 4, 8)
    - memory_mb: Memory size in MB (2048, 4096, 8192, etc.)

    Args:
        name_or_index: Instance name or index
        config: EmulatorConfig dataclass with settings to apply

    Returns:
        LifecycleResult with success/failure and details
    """
    ldconsole = _find_ldconsole()
    if not ldconsole:
        return LifecycleResult(False, '未找到 ldconsole.exe')

    index = int(name_or_index) if name_or_index.isdigit() else None

    applied = []
    errors = []

    def _modify(args_list: list[str], label: str):
        output = _run_ldconsole(['modify'] + args_list, timeout=30)
        if output and 'error' in output.lower():
            errors.append(f'{label}: {output}')
            return False
        applied.append(label)
        return True

    try:
        if config.resolution:
            parts = config.resolution.lower().split('x')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit:
                width, height = parts[0], parts[1]
                args = ['--index', str(index)] if index else ['--name', name_or_index]
                args += ['--resolution', f'{width},{height}']
                _modify(args, f'resolution={config.resolution}')
            else:
                errors.append(f'Invalid resolution format: {config.resolution} (expected WxH)')

        if config.dpi is not None:
            args = ['--index', str(index)] if index else ['--name', name_or_index]
            args += ['--dpi', str(config.dpi)]
            _modify(args, f'dpi={config.dpi}')

        if config.cpu_count is not None:
            args = ['--index', str(index)] if index else ['--name', name_or_index]
            args += ['--cpu', str(config.cpu_count)]
            _modify(args, f'cpu={config.cpu_count}')

        if config.memory_mb is not None:
            args = ['--index', str(index)] if index else ['--name', name_or_index]
            args += ['--memory', str(config.memory_mb)]
            _modify(args, f'memory={config.memory_mb}MB')

        if errors:
            return LifecycleResult(
                False,
                f'配置部分失败: {"; ".join(errors)}',
                raw_output=f'applied: {", ".join(applied)}; errors: {"; ".join(errors)}',
            )

        if not applied:
            return LifecycleResult(False, '无配置项需要修改')

        return LifecycleResult(
            True,
            f'实例 "{name_or_index}" 配置已更新: {", ".join(applied)}',
            raw_output=', '.join(applied),
        )
    except Exception as e:
        return LifecycleResult(False, f'配置异常: {e}')


def get_current_config(name_or_index: str) -> dict[str, Any]:
    """Get current configuration of an emulator instance

    Reads current settings from ldconsole query command.
    Returns a dict with resolution, dpi, cpu, memory info.

    Args:
        name_or_index: Instance name or index

    Returns:
        Dict with configuration values (may have missing keys if query fails)
    """
    result: dict[str, Any] = {'name_or_index': name_or_index}

    index = int(name_or_index) if name_or_index.isdigit() else None
    base_args = ['--index', str(index)] if index else ['--name', name_or_index]

    try:
        output = _run_ldconsole(['query'] + base_args, timeout=10)
        if output:
            for line in output.split('\n'):
                line = line.strip().lower()
                if 'resolution' in line or '宽' in line or '高' in line:
                    match = re.search(r'(\d+)\D*(\d+)', line)
                    if match:
                        result['resolution'] = f'{match.group(1)}x{match.group(2)}'
                elif 'dpi' in line:
                    match = re.search(r'(\d+)', line)
                    if match:
                        result['dpi'] = int(match.group(1))
                elif 'cpu' in line or '处理器' in line or '核心' in line:
                    match = re.search(r'(\d+)', line)
                    if match:
                        result['cpu_count'] = int(match.group(1))
                elif 'memory' in line or '内存' in line:
                    match = re.search(r'(\d+)', line)
                    if match:
                        result['memory_mb'] = int(match.group(1))
    except Exception as e:
        result['error'] = str(e)

    return result
