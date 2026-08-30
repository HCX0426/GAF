"""Worker entry point: parse CLI args, create WorkerConnection, start connection

Integrates DeviceCenter (auto-discovery), HealthChecker (background polling),
and TaskOrchestrator (task execution) into a unified lifecycle.
"""

import argparse
import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from client.connection import WorkerConnection
from client.handler import MessageHandler
from core.config import WorkerConfig
from core.constants import EventType
from core.orchestrator import TaskOrchestrator
from devices.center import DeviceCenter
from devices.health_checker import DeviceHealthChecker
from devices.manager import DeviceManager
from image.processor import ImageProcessor
from monitor.manager import MonitorManager
from monitor.resources import ResourceMonitor
from utils.log_rotation import DateRotatingFileHandler

logger = logging.getLogger(__name__)

# Module-level reference to shared components (accessible from handlers)
_health_checker: DeviceHealthChecker | None = None
_device_center: DeviceCenter | None = None

# Injected after the WebSocket connection is established (see run_worker). The
# health-checker thread (plain threading) calls this from its poll loop to
# asynchronously report a device's current health status to the backend via a
# `device.sync` frame. Guarantees devices that disappear from ADB/windows are
# marked offline in the backend instead of staying stale "online".
DeviceStatusSender = Any  # callable(device_data: dict) -> None
_device_status_sender: DeviceStatusSender | None = None

# TD-339 (2026-07-23): Agent standalone process singleton lock.
# Prevents multiple agent processes from running simultaneously when launched
# manually (python -m src) — backend's worker_runtime.py only protects the
# backend-auto-start path. Uses a PID file under %TEMP%\gaf_agent_lock\
# mirroring backend's manager.lock + agent.pid design.
_AGENT_LOCK_DIR = os.path.join(tempfile.gettempdir(), 'gaf_agent_lock')
_AGENT_PID_FILE = os.path.join(_AGENT_LOCK_DIR, 'standalone.pid')


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running.

    Uses psutil when available (cross-platform); falls back to Windows
    OpenProcess on Windows, and os.kill(pid, 0) on POSIX.
    """
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    if os.name == 'nt':
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except OSError:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_singleton_lock() -> bool:
    """Acquire the agent singleton PID-file lock.

    Returns True if the lock was acquired (no other agent running), False if
    another live agent process holds it. Stale PID files (dead PID) are
    reclaimed automatically.

    TD-339: This protects the standalone agent process itself, distinct from
    backend/workers/worker_runtime.py which protects the backend-auto-start
    path (TD-217). Both use the same lock directory for consistency.
    """
    os.makedirs(_AGENT_LOCK_DIR, exist_ok=True)

    # Check for an existing live PID
    if os.path.exists(_AGENT_PID_FILE):
        try:
            with open(_AGENT_PID_FILE) as f:
                existing_pid = int(f.read().strip())
            if _is_pid_alive(existing_pid) and existing_pid != os.getpid():
                logger.error(
                    "Agent singleton lock held by PID %d (lock file: %s). "
                    "Only one agent process may run at a time. "
                    "Stop the other agent first or remove the lock file.",
                    existing_pid, _AGENT_PID_FILE,
                )
                return False
            logger.info(
                "Reclaiming stale agent lock (PID %d not alive).", existing_pid
            )
        except (ValueError, OSError):
            logger.info("Corrupt agent lock file; reclaiming.")

    # Write our PID
    try:
        with open(_AGENT_PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
    except OSError as exc:
        logger.error("Failed to write agent lock file %s: %s", _AGENT_PID_FILE, exc)
        return False
    logger.info("Acquired agent singleton lock (PID %d).", os.getpid())
    return True


def release_singleton_lock() -> None:
    """Release the agent singleton PID-file lock on shutdown."""
    try:
        if os.path.exists(_AGENT_PID_FILE):
            os.remove(_AGENT_PID_FILE)
    except OSError:
        pass


def get_health_checker() -> DeviceHealthChecker | None:
    """Get the global health checker instance."""
    return _health_checker


def get_device_center() -> DeviceCenter | None:
    """Get the global device center instance."""
    return _device_center


def _default_server_url() -> str:
    """Construct default server URL from env vars."""
    ws_path = os.environ.get("GAF_WS_AGENT_PATH", "ws/protocol/agents/")
    return os.environ.get("GAF_SERVER_URL", f"ws://127.0.0.1:8000/{ws_path}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="GAF Agent 客户端")
    parser.add_argument(
        "--server-url",
        type=str,
        default=_default_server_url(),
        help="Server WebSocket 地址",
    )
    parser.add_argument(
        "--agent-token",
        type=str,
        default="",
        help="Agent 认证 Token",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        default=False,
        help="以本地模式运行（不连接 Server）",
    )
    parser.add_argument(
        "--health-interval",
        type=float,
        default=30.0,
        help="设备健康检查轮询间隔（秒），默认 30.0（N154: 原 5.0 导致 adb subprocess 风暴）",
    )
    parser.add_argument(
        "--no-auto-discover",
        action="store_true",
        default=False,
        help="禁用启动时自动设备发现",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="日志文件路径；指定时输出到此文件（追加模式），未指定时输出到 stderr",
    )
    parser.add_argument(
        "--record",
        type=str,
        default=None,
        metavar="NAME",
        help="录制模式：录制全局鼠标/键盘操作和截图，保存到 ./recordings/<NAME>.gafrecord。"
             "按 Ctrl+C 停止录制。仅 Windows 可用。",
    )
    parser.add_argument(
        "--record-no-screenshots",
        action="store_true",
        default=False,
        help="录制时不捕获截图（仅记录鼠标/键盘事件）",
    )
    parser.add_argument(
        "--record-interval",
        type=float,
        default=2.0,
        help="录制截图间隔（秒），默认 2.0",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="启用调试可视化（模板匹配等节点的中间过程图保存到 --debug-dir）",
    )
    parser.add_argument(
        "--debug-dir",
        type=str,
        default="./debug",
        help="调试图像输出根目录，默认 ./debug",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="日志级别，默认 INFO。DEBUG 会打印每个节点/Payload/Future 状态，用于排查任务失败原因",
    )
    parser.add_argument(
        "--skip-singleton-check",
        action="store_true",
        default=False,
        help="跳过单例进程锁检查 (TD-339), 仅限调试场景使用",
    )
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> WorkerConfig:
    """Build WorkerConfig from CLI args, loading token from multiple sources.

    Token priority: CLI arg > env GAF_AGENT_TOKEN > local encrypted file
    Debug mode priority: CLI --debug > env GAF_DEBUG > config default
    """
    # N196: 统一调试模式 — CLI --debug 覆盖 env GAF_DEBUG, 否则用 env 值
    cli_debug = getattr(args, "debug", False)
    env_debug = os.environ.get("GAF_DEBUG", "").lower() in ("true", "1", "yes")
    debug_mode = cli_debug or env_debug

    return WorkerConfig.from_args(
        server_url=args.server_url,
        agent_token=args.agent_token,
        is_local=args.local,
        debug_mode=debug_mode,
        debug_dir=getattr(args, "debug_dir", "./debug"),
    )


def _setup_devices(device_manager: DeviceManager, args: argparse.Namespace) -> None:
    """Auto-discover and register all available devices.

    Scans for emulators (ADB) and Windows game windows, creates device
    instances, and registers them with both DeviceManager and HealthChecker.
    """
    global _device_center, _health_checker

    _device_center = DeviceCenter()

    if not args.no_auto_discover:
        logger.info("开始自动设备发现...")
        try:
            discovered = _device_center.auto_discover()
            logger.info("自动发现完成: 发现 %d 个设备", len(discovered))
            for dev in discovered:
                logger.info("  - [%s] %s (%s)", dev.device_id, dev.name, type(dev).__name__)
        except Exception as exc:
            logger.warning("自动设备发现失败（非致命）: %s", exc)

    # Also ensure any manually pre-registered devices are covered
    existing_count = device_manager.device_count
    if existing_count == 0 and _device_center:
        # Transfer discovered devices into the orchestrator's manager
        for dev_info in _device_center.list_devices():
            dev = _device_center.get_device(dev_info.get('device_id', ''))
            if dev and not device_manager.get_device(dev.device_id):
                device_manager.add_device(dev)

    total = device_manager.device_count
    logger.info("设备管理器就绪: %d 个设备", total)


def _setup_health_checker(
    device_manager: DeviceManager,
    interval: float,
) -> DeviceHealthChecker:
    """Initialize and start the background health checking service.

    Registers all known devices from DeviceManager into the checker,
    starts the polling thread, and wires status-change callbacks.

    Args:
        device_manager: Device manager containing registered devices
        interval: Polling interval in seconds

    Returns:
        The started HealthChecker instance
    """
    global _health_checker

    _health_checker = DeviceHealthChecker(interval=interval)

    # Register all managed devices for health monitoring
    for dev_info in device_manager.list_devices():
        dev = device_manager.get_device(dev_info.get('device_id', ''))
        if dev is None:
            continue

        dev_type_name = type(dev).__name__
        if 'Windows' in dev_type_name or 'windows' in dev.device_id.lower():
            getattr(dev, '_window_title', None)
            # Try to extract process info from window manager
            wm = getattr(dev, '_window_mgr', None)
            if wm and hasattr(wm, '_hwnd'):
                try:
                    hwnd_val = wm._hwnd
                    if hwnd_val:
                        _health_checker.add_windows_device(
                            device_id=dev.device_id,
                            hwnd=hwnd_val,
                            window_title=getattr(dev, '_window_title', None),
                        )
                        continue
                except Exception:
                    pass
            # Fallback: register without hwnd (process-only check)
            _health_checker.add_windows_device(
                device_id=dev.device_id,
                window_title=getattr(dev, '_window_title', dev.name),
            )
        elif 'ADB' in dev_type_name or 'adb' in dev.device_id.lower():
            serial = getattr(dev, 'serial', None) or getattr(dev, '_serial', '')
            # Improved device_type detection: check serial prefix (emulator-XXXX) and device_id
            serial_lower = (serial or '').lower()
            is_emulator = (
                serial_lower.startswith('emulator-') or
                'emu' in dev.device_id.lower() or
                getattr(dev, 'is_emulator', False)
            )
            # N197: 模拟器注册时传入 window_title, 让健康检查器能检查窗口存在性.
            # 雷电模拟器窗口关闭后 ADB 进程可能仍在, 需结合窗口存在性判断.
            win_title = getattr(dev, 'name', None) if is_emulator else None
            _health_checker.add_adb_device(
                device_id=dev.device_id,
                adb_serial=serial or dev.device_id,
                device_type='emulator' if is_emulator else 'adb',
                window_title=win_title,
            )

    # Wire status change callback: log + sync the new status to the backend so
    # a device that vanishes (ADB/window gone) is marked offline there, instead
    # of leaving a stale "online" record.
    def _on_status_change(device_id: str, old_status: str, new_status: str) -> None:
        logger.info(
            "设备状态变更: %s (%s → %s)",
            device_id, old_status, new_status,
        )
        result = _health_checker.get_status(device_id) if _health_checker else None
        if result:
            logger.debug("  原因: %s", result.reason)
        _report_device_status(device_manager, device_id, new_status)

    _health_checker.on_status_change = _on_status_change

    # Start background polling
    if _health_checker.device_count > 0:
        _health_checker.start()
        logger.info(
            "健康检查已启动: %d 个设备, 间隔=%.1fs",
            _health_checker.device_count, interval,
        )
    else:
        logger.warning("无设备注册到健康检查器，跳过启动")

    return _health_checker


def _report_device_status(
    device_manager: DeviceManager,
    device_id: str,
    new_status: str,
) -> None:
    """Report a device's current health status to the backend via device.sync.

    Called by the health-checker thread on every online/offline transition.
    Constructs a single-device ``device.sync`` payload (matching the shape
    ``connection._sync_devices`` sends) and hands it to the injected async
    sender. Sent from the background thread → the sender schedules the actual
    WS send on the agent's event loop.

    Args:
        device_manager: Device manager holding the device objects.
        device_id: Device identifier that changed status.
        new_status: Health status from the checker ("online" / "offline"/"error").
    """
    dev = device_manager.get_device(device_id)
    if dev is None:
        logger.warning("无法上报状态：设备不存在 device_id=%s", device_id)
        return

    # Normalize device_type to the backend vocabulary (windows / emulator),
    # mirroring connection._sync_devices.
    raw_type = str(getattr(dev, "device_type", "emulator")).lower()
    dev_type = "windows" if raw_type in ("windows", "window", "win32", "pc") else "emulator"

    # Collapse health status to backend Device.Status vocabulary
    # (online / offline / busy). "error" counts as offline (unreachable).
    status = "online" if new_status == "online" else "offline"

    sender = _device_status_sender
    if sender is None:
        logger.debug("设备状态上报未注入 sender，跳过 device_id=%s", device_id)
        return

    try:
        sender({
            "device_id": dev.device_id,
            "name": dev.name,
            "device_type": dev_type,
            "status": status,
            "adb_serial": getattr(dev, "serial", "") or "",
            "emulator": getattr(dev, "emulator_type", "") or "",
        })
    except Exception:
        logger.exception("上报设备状态失败: device_id=%s", device_id)


async def run_worker(config: WorkerConfig, args: argparse.Namespace = None) -> None:
    """Create and start the Worker client with full component initialization.

    术语 (OQ-10, 2026-08-29): 本进程为 **Worker**（自动化执行节点，
    原 "Agent"）。"Agent" 保留给未来 AI 智能体（backend/gaf_ai）。

    Initializes DeviceManager, DeviceCenter (auto-discovery),
    HealthChecker (background polling), ImageProcessor, MonitorManager,
    TaskOrchestrator, MessageHandler, and WebSocket connection.
    """
    if args is None:
        args = parse_args()

    device_manager = DeviceManager()
    image_processor = ImageProcessor()

    # Create the shared resource monitor early so screenshot paths can record FPS
    # before the WebSocket connection is established.
    resource_monitor = ResourceMonitor()

    # Step 1: Auto-discover and register devices
    _setup_devices(device_manager, args)

    # Step 2: Initialize orchestrator with device manager
    orchestrator = TaskOrchestrator(
        device_manager=device_manager,
        image_processor=image_processor,
    )

    # Step 3: Initialize monitor manager
    monitor_manager = MonitorManager(
        device_manager=device_manager,
        image_processor=image_processor,
    )
    orchestrator.set_monitor_manager(monitor_manager)

    # Step 3.1: Start monitor thread (popup detection, story skip, etc.)
    # Background daemon thread; failure is non-fatal — orchestrator still works.
    try:
        monitor_manager.start()
        logger.info("MonitorManager started")
    except Exception as exc:
        logger.warning("MonitorManager start failed (non-fatal): %s", exc)

    # Step 3.5: Register default OCR engine (RapidOCR)
    # Lightweight ONNX-based OCR, default per docs/architecture/optimal-solution.md.
    # PaddleOCR is optional (register manually if needed).
    try:
        from recognition.ocr.rapid_engine import RapidOCREngine
        orchestrator.register_ocr_engine(RapidOCREngine(), "rapid")
        logger.info("默认 OCR 引擎 RapidOCR 已注册")
    except ImportError:
        logger.warning("RapidOCR 未安装，OCR 功能将回退到 mock。请执行: pip install rapidocr-onnxruntime")
    except Exception as exc:
        logger.warning("注册 RapidOCR 引擎失败（非致命）: %s", exc)

    # Step 4: Start health checker (background thread)
    health_interval = getattr(args, 'health_interval', 30.0)
    _setup_health_checker(device_manager, health_interval)

    # Store references for external access (e.g., handler callbacks)
    orchestrator._health_checker = _health_checker
    orchestrator._device_center = _device_center

    # Step 5: Create message handler and connect
    handler = MessageHandler(orchestrator=orchestrator)

    if config.is_local:
        logger.info("Agent 以本地模式运行，跳过 WebSocket 连接")
        logger.info("设备数=%d, 健康检查=%s",
                     device_manager.device_count,
                     '运行中' if (_health_checker and _health_checker.is_running) else '未启动')
        # Stop monitor thread before exiting local mode (no finally block ahead)
        try:
            monitor_manager.stop()
        except Exception as exc:
            logger.warning("MonitorManager stop failed (local mode): %s", exc)
        return

    connection = WorkerConnection(config=config, resource_monitor=resource_monitor)
    await connection.connect()

    # Inject the device-status sender used by the health-checker thread (plain
    # threading) to push online/offline transitions to the backend. It runs the
    # async send on this event loop via run_coroutine_threadsafe.
    _agent_loop = asyncio.get_running_loop()

    def _schedule_device_send(data: dict) -> None:
        async def _do() -> None:
            if not connection.connected:
                return
            try:
                await connection.send_message(
                    "device.sync", {"devices": [data], "count": 1}
                )
                logger.info("已上报设备状态: %s → %s", data.get("device_id"), data.get("status"))
            except Exception as exc:
                logger.warning("设备状态上报发送失败: %s", exc)

        try:
            asyncio.run_coroutine_threadsafe(_do(), _agent_loop)
        except Exception as exc:
            logger.warning("调度设备状态上报失败: %s", exc)

    global _device_status_sender
    _device_status_sender = _schedule_device_send

    # Step 6: Sync discovered devices to server after connection established
    if connection.connected and device_manager.device_count > 0:
        try:
            logger.info("开始同步本地设备到 Server...")
            await connection._sync_devices(device_manager)
            logger.info("设备同步完成")
        except Exception as exc:
            logger.warning("设备同步失败（非致命）: %s", exc)

    try:
        await connection.listen(handler)
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在断开连接...")
    finally:
        # Clean up monitor manager (stop background thread)
        try:
            monitor_manager.stop()
        except Exception as exc:
            logger.warning("MonitorManager stop failed: %s", exc)
        # Clean up health checker
        if _health_checker and _health_checker.is_running:
            _health_checker.stop()
            logger.info("健康检查已停止")
        await connection.disconnect()


def run_record(args: argparse.Namespace) -> None:
    """Run recording mode: capture global mouse/keyboard + screenshots.

    Saves to ./recordings/<NAME>.gafrecord. Press Ctrl+C to stop.
    After stopping, uploads the recording (with screenshots) to the
    backend when a server_url/token is available (s45).
    """
    import os
    import time

    from core.recording import RecordingEngine
    from core.recording_api import RecordingAPIClient

    name = args.record or f"recording_{int(time.time())}"
    screenshot_dir = os.path.join("./recordings", "screenshots", name)
    os.makedirs(screenshot_dir, exist_ok=True)

    engine = RecordingEngine(screenshot_dir=screenshot_dir)
    engine.start(name=name)

    capture_screenshots = not args.record_no_screenshots
    engine.start_capture(
        capture_screenshots=capture_screenshots,
        screenshot_interval=args.record_interval,
    )

    logger.info("=" * 60)
    logger.info("录制模式已启动")
    logger.info("  名称: %s", name)
    logger.info("  截图: %s (间隔 %.1fs)", "开启" if capture_screenshots else "关闭", args.record_interval)
    logger.info("  截图目录: %s", screenshot_dir)
    logger.info("按 Ctrl+C 停止录制")
    logger.info("=" * 60)

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止录制...")

    data = engine.stop()
    if data:
        filepath = os.path.join("./recordings", f"{name}.gafrecord")
        engine.save(filepath)
        logger.info("录制完成:")
        logger.info("  文件: %s", filepath)
        logger.info("  时长: %.1fs", data.duration)
        logger.info("  事件数: %d", len(data.events))
        logger.info("  截图数: %d", sum(1 for e in data.events if e.event_type == EventType.SCREENSHOT))

        # s45: 上传录制 + 截图到 backend（token 缺失时跳过并提示）
        try:
            from core.recording import RecordingData
            payload = data.to_dict() if isinstance(data, RecordingData) else data
            client = RecordingAPIClient(server_url=args.server_url, token=args.agent_token)
            if not client.token:
                logger.info("未配置 agent token（--agent-token / GAF_AGENT_TOKEN / TokenStore），跳过上传。")
                return
            result = client.upload_recording(payload)
            if not result:
                logger.warning("上传录制失败，截图保留在本地: %s", screenshot_dir)
                return
            recording_id = result.get("id") or result.get("recording", {}).get("id")
            if recording_id is None:
                logger.warning("上传响应缺少 recording id，跳过截图上传: %s", str(result)[:200])
                return
            events = payload.get("events", []) if isinstance(payload, dict) else getattr(payload, "events", [])
            stats = client.upload_screenshots(int(recording_id), events)
            logger.info("截图上传完成: 成功 %d, 跳过 %d, 失败 %s",
                        stats["uploaded"], stats["skipped"], stats["failed"] or "无")
        except Exception as exc:
            logger.warning("录制上传异常: %r", exc)


def main() -> None:
    """Agent main entry point"""
    args = parse_args()

    # Configure logging root handlers.
    #
    # N197 归一化 (2026-08-09): 日志写到 <DEBUG_DIR>/<YYYYMMDD>/agent/system/agent.log,
    # 按日期轮转 + gzip 压缩 + 自动清理过期 (默认 30 天).
    # --log-file 显式传入时仍可覆盖为固定文件路径 (调试用).
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_file = args.log_file
    if not log_file:
        # 优先级: GAF_AGENT_LOG_FILE > GAF_DEBUG_DIR > ../debug/ (相对 agent CWD)
        env_log = os.environ.get("GAF_AGENT_LOG_FILE")
        if env_log:
            log_file = env_log
        else:
            debug_dir = os.environ.get("GAF_DEBUG_DIR")
            if not debug_dir:
                debug_dir = str(Path("..") / "debug")
            debug_path = Path(debug_dir)
            debug_path.mkdir(parents=True, exist_ok=True)
            # N197: 日期分桶 + 轮转 handler
            file_handler = DateRotatingFileHandler(
                debug_root=str(debug_path),
                app_name="agent",
                log_name="agent",
                retention_days=30,
            )
            handlers.append(file_handler)
    else:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, mode='a', encoding='utf-8'))
    log_level = getattr(logging, (args.log_level or "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] [AGENT] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )

    # Recording mode: capture global events, then exit (no agent connection)
    if args.record is not None:
        run_record(args)
        return

    # TD-339 (2026-07-23): Acquire standalone agent singleton lock before
    # starting the connection. Prevents multiple agent processes from running
    # simultaneously when launched manually (python -m src).
    if not args.skip_singleton_check and not acquire_singleton_lock():
        logger.error("另一个 Agent 进程正在运行, 退出. (使用 --skip-singleton-check 可绕过, 仅限调试)")
        sys.exit(1)

    config = build_config(args)

    try:
        asyncio.run(run_worker(config, args))
    except KeyboardInterrupt:
        logger.info("Agent 已停止")
    finally:
        release_singleton_lock()


if __name__ == "__main__":
    main()
