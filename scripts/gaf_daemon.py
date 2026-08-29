"""
GAF 服务守护进程 — 进程管理 + 看门狗自动重启 (TD-352).

替代 PowerShell 脚本 gaf_services.ps1 的服务管理职责，提供:

  - start:    detached 模式启动所有服务 + 看门狗, 立即返回
  - stop:     按反向顺序停止所有服务 + 终止 daemon
  - restart:  stop + start
  - status:   显示各服务进程状态 (含 daemon 状态)
  - daemon:   前台模式 (调试用, Ctrl+C 退出)
  - monitor:  仅启动看门狗 (不启动服务, 用于外部启动场景)

PID 文件: debug/gaf_daemon.pid — 单例检测 + stop 定位

用法:
    python scripts/gaf_daemon.py start      # detached 启动, 立即返回
    python scripts/gaf_daemon.py status     # 查看状态
    python scripts/gaf_daemon.py stop       # 停止所有服务 + 终止 daemon
    python scripts/gaf_daemon.py daemon     # 前台模式 (调试)
"""

import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Optional

# N205 (2026-08-21): 日志轮转 handler 唯一来源 = agent/src/utils/log_rotation.py.
# scripts 端不再维护 _log_rotation.py 副本 (已删除), 统一从 agent 包导入,
# 消除两份重复实现漂移.
_GAF_ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
_AGENT_UTILS_DIR = _GAF_ROOT_FOR_IMPORT / "agent" / "src" / "utils"
if str(_AGENT_UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_UTILS_DIR))
from log_rotation import DateRotatingFileHandler  # noqa: E402

# spec 2026-08-29 P1/P2: 服务健康探针层 + 健康快照文件 (供 monitors/status 读取)
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from services.health import (
    HEALTH_STATUS_FILE,
    check_all,
    scan_log_errors,
    write_health_snapshot,
)  # noqa: E402

# =============================================================================
# 路径常量
# =============================================================================
GAF_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = GAF_ROOT / "backend"
AGENT_DIR = GAF_ROOT / "agent"
FRONTEND_DIR = GAF_ROOT / "frontend"
DEBUG_DIR = GAF_ROOT / "debug"
ENV_FILE = GAF_ROOT / ".env"
PID_FILE = DEBUG_DIR / "gaf_daemon.pid"

# spec 2026-08-29-services-management-monitor P1:
# 服务终端输出目录 (固定路径, 便于前端统一 tail/排查; 不进入日期归档目录).
# 布局: debug/system/services/<name>.log (+ <name>.log.1 轮转备份)
SERVICE_LOG_DIR = DEBUG_DIR / "system" / "services"
MAX_SERVICE_LOG_BYTES = 5 * 1024 * 1024  # 单服务终端日志 5MB 轮转

PYTHON_EXE = Path("D:/code/environment/conda/envs/gaf/python.exe")
REDIS_SERVER_EXE = Path("D:/code/environment/redis/redis-server.exe")
REDIS_CLI_EXE = Path("D:/code/environment/redis/redis-cli.exe")
NPM_EXE = "D:/code/environment/node/nodejs/npm.cmd"

# 默认端口
DEFAULT_REDIS_PORT = 6379
DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 5173

# 看门狗配置
WATCHDOG_INTERVAL = 15  # 检查周期 (秒)
MAX_RESTART_COUNT = 3    # 30 分钟内最大重启次数
RESTART_WINDOW = 1800    # 重启计数窗口 (秒, 30 分钟)
STOP_TIMEOUT = 5         # 等待进程退出的最大时间 (秒)
# spec 2026-08-29 P2: 健康探针周期 (每轮看门狗循环内执行, 与 WATCHDOG_INTERVAL 对齐)
HEALTH_CHECK_INTERVAL = WATCHDOG_INTERVAL


# =============================================================================
# PID 文件管理
# =============================================================================

def _read_pid_file() -> Optional[int]:
    """读取 PID 文件, 返回 PID 或 None."""
    try:
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            return pid
    except (ValueError, OSError):
        pass
    return None


def _write_pid_file():
    """写入当前进程 PID."""
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def _remove_pid_file():
    """删除 PID 文件 (仅当 PID 匹配时)."""
    try:
        if PID_FILE.exists():
            content = PID_FILE.read_text().strip()
            if content == str(os.getpid()):
                PID_FILE.unlink()
    except OSError:
        pass


def _no_console_flags() -> int:
    """Windows 下给控制台子进程加 CREATE_NO_WINDOW, 防 detached daemon 弹窗.

    daemon 以 DETACHED_PROCESS 启动 (无控制台), 若再 spawn 控制台程序
    (redis-cli/tasklist/taskkill) 而不指定 flag, Windows 会为其分配一个
    可见的空白终端窗口一闪而过.
    """
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


def _is_process_alive(pid: int) -> bool:
    """检查指定 PID 是否存活."""
    if sys.platform == "win32":
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, timeout=5,
                creationflags=_no_console_flags(),
            )
            # tasklist 输出可能为本地化编码 (GBK), 用 bytes 判定避免解码崩溃
            out = proc.stdout or b""
            return str(pid).encode("ascii") in out
        except (subprocess.TimeoutExpired, OSError):
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def check_daemon_running() -> Optional[int]:
    """检查 daemon 是否已在运行, 返回 PID 或 None."""
    pid = _read_pid_file()
    if pid is not None and _is_process_alive(pid):
        return pid
    # PID 文件存在但进程已死, 清理
    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except OSError:
            pass
    return None


# =============================================================================
# 日志配置
# =============================================================================
logger = logging.getLogger("gaf_daemon")


def setup_logging():
    """配置日志输出到 stdout + 日期分桶文件 (N197 归一化)."""
    log_format = "%(asctime)s [%(levelname)s] %(message)s"
    formatter = logging.Formatter(log_format, datefmt="%H:%M:%S")

    # stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    # N197 (2026-08-09): 日期分桶 + 轮转 handler
    # 日志路径: debug/YYYYMMDD/backend/system/daemon.log
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = DateRotatingFileHandler(
        debug_root=str(DEBUG_DIR),
        app_name="backend",
        log_name="daemon",
        retention_days=30,
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(file_handler)

    logger.setLevel(logging.INFO)


# =============================================================================
# 服务终端日志 (spec 2026-08-29-services-management-monitor P1)
# =============================================================================

def service_log_path(name: str) -> Path:
    """返回服务终端日志文件路径 (固定位置 + 简单大小轮转)."""
    return SERVICE_LOG_DIR / f"{name}.log"


def _open_service_log(name: str) -> BinaryIO | None:
    """打开服务终端日志文件 (追加模式), 超过阈值则先轮转为 <name>.log.1.

    返回可写的二进制文件对象, 供 subprocess.Popen 的 stdout/stderr 使用.
    打开失败 (磁盘/权限) 返回 None, 由调用方 fallback 到 DEVNULL.
    """
    try:
        SERVICE_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = service_log_path(name)
        if path.exists() and path.stat().st_size > MAX_SERVICE_LOG_BYTES:
            backup = path.with_suffix(".log.1")
            if backup.exists():
                backup.unlink()
            path.replace(backup)
        return open(path, "ab")  # noqa: SIM115 - 句柄由 Popen/ServiceInfo 生命周期管理
    except OSError:
        logger.error("  [%s] 打开终端日志失败, 回退 DEVNULL", name)
        return None


# =============================================================================
# 配置读取
# =============================================================================

def _read_env(key: str, default: str = "") -> str:
    """从 .env 文件读取配置值."""
    try:
        text = ENV_FILE.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                continue
            k, v = stripped.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return default


def load_config() -> dict:
    """加载守护进程配置 (从 .env + 默认值)."""
    redis_url = _read_env("REDIS_URL", f"redis://localhost:{DEFAULT_REDIS_PORT}/0")
    redis_port = DEFAULT_REDIS_PORT
    m = re.search(r":(\d+)", redis_url)
    if m:
        redis_port = int(m.group(1))

    backend_port = int(_read_env("BACKEND_PORT", str(DEFAULT_BACKEND_PORT)))
    frontend_port = int(_read_env("FRONTEND_PORT", str(DEFAULT_FRONTEND_PORT)))
    celery_mode = _read_env("GAF_CELERY_MODE", "eager").lower()

    return {
        "redis_port": redis_port,
        "backend_port": backend_port,
        "frontend_port": frontend_port,
        "celery_mode": celery_mode,
    }


# =============================================================================
# 服务定义
# =============================================================================

def build_services(cfg: dict) -> dict:
    """构建服务定义字典 (根据 eager/celery 模式)."""
    redis_port = cfg["redis_port"]
    backend_port = cfg["backend_port"]
    frontend_port = cfg["frontend_port"]
    is_celery = cfg["celery_mode"] == "celery"

    services = {
        "redis": {
            "cmd": [str(REDIS_SERVER_EXE)],
            "cwd": str(REDIS_SERVER_EXE.parent),
            "port": redis_port,
            "verify": "redis_ping",
            "depends_on": [],
            "delay": 2.0,
            "env": {},
        },
        "backend": {
            "cmd": [
                str(PYTHON_EXE), "-m", "daphne",
                "config.asgi:application",
                "-b", "0.0.0.0",
                "-p", str(backend_port),
                "--verbosity", "1",
            ],
            "cwd": str(BACKEND_DIR),
            "port": backend_port,
            "verify": "port_listen",
            "depends_on": ["redis"],
            "delay": 5.0,
            "env": {
                "GAF_ALLOW_LOCALHOST_BYPASS": "1",
                "PYTHONUNBUFFERED": "1",
            },
        },
        "agent": {
            "cmd": [str(PYTHON_EXE), "-m", "src", "--log-level", "INFO"],
            "cwd": str(AGENT_DIR),
            "port": None,
            "verify": "process",
            "depends_on": ["backend"],
            "delay": 5.0,
            "env": {},
        },
        "frontend": {
            "cmd": [NPM_EXE, "run", "dev"],
            "cwd": str(FRONTEND_DIR),
            "port": frontend_port,
            "verify": "port_listen",
            "depends_on": ["backend"],
            "delay": 3.0,
            "env": {},
        },
    }

    if is_celery:
        # 按依赖顺序插入: celery_worker 在 backend 之后, celery_beat 在 worker 之后
        services["celery_worker"] = {
            "cmd": [
                str(PYTHON_EXE), "-m", "celery", "-A", "config", "worker",
                "--loglevel=INFO", "--pool=threads", "--concurrency=4",
            ],
            "cwd": str(BACKEND_DIR),
            "port": None,
            "verify": "process",
            "depends_on": ["redis", "backend"],
            "delay": 3.0,
            "env": {},
        }
        services["celery_beat"] = {
            "cmd": [
                str(PYTHON_EXE), "-m", "celery", "-A", "config", "beat",
                "--loglevel=INFO",
            ],
            "cwd": str(BACKEND_DIR),
            "port": None,
            "verify": "process",
            "depends_on": ["redis", "backend"],
            "delay": 1.0,
            "env": {},
        }

    return services


# =============================================================================
# 启动顺序 (按依赖拓扑排序)
# =============================================================================

def startup_order(services: dict) -> list[str]:
    """按依赖关系拓扑排序."""
    sorted_names: list[str] = []
    visited = set()

    def visit(name: str):
        if name in visited:
            return
        visited.add(name)
        svc = services.get(name)
        if svc:
            for dep in svc.get("depends_on", []):
                visit(dep)
        sorted_names.append(name)

    for name in services:
        visit(name)
    return sorted_names


# =============================================================================
# 验证工具
# =============================================================================

def _port_listening(port: int, host: str = "127.0.0.1") -> bool:
    """检查端口是否在监听."""
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except (OSError, socket.timeout):
        return False


def _redis_ping(port: int) -> bool:
    """检查 Redis 是否响应 PING."""
    try:
        result = subprocess.run(
            [str(REDIS_CLI_EXE), "-p", str(port), "ping"],
            capture_output=True, timeout=5,
            creationflags=_no_console_flags(),
        )
        return (result.stdout or b"").strip() == b"PONG"
    except (subprocess.TimeoutExpired, OSError):
        return False


def verify_service(service_name: str, svc: dict) -> bool:
    """验证服务是否正常运行的通用方法."""
    verify = svc.get("verify", "process")
    port = svc.get("port")

    if verify == "redis_ping":
        return _redis_ping(port or DEFAULT_REDIS_PORT)
    elif verify == "port_listen" and port:
        return _port_listening(port)
    else:
        # process 类型: 进程存活即视为正常 (由 poll() 检查)
        return True


# =============================================================================
# ServiceManager — 进程管理
# =============================================================================

class ServiceInfo:
    """单个服务的运行时信息."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.restart_times: list[float] = []  # 重启时间戳列表
        self.restart_count = 0  # 当前窗口内重启次数
        self.log_fh: Optional[BinaryIO] = None  # 服务终端输出文件句柄 (P1)

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def pid(self) -> Optional[int]:
        return self.process.pid if self.process else None

    @property
    def returncode(self) -> Optional[int]:
        return self.process.poll() if self.process else None

    def close_log(self):
        """关闭终端输出句柄 (停止/进程退出时调用)."""
        if self.log_fh is not None:
            try:
                self.log_fh.close()
            except OSError:
                pass
            self.log_fh = None

    def clean_restart_history(self):
        """清理超过窗口期的重启记录."""
        now = time.time()
        self.restart_times = [t for t in self.restart_times if now - t < RESTART_WINDOW]
        self.restart_count = len(self.restart_times)

    def can_restart(self) -> bool:
        """检查是否还能重启 (窗口内不超过 MAX_RESTART_COUNT)."""
        self.clean_restart_history()
        return self.restart_count < MAX_RESTART_COUNT

    def record_restart(self):
        """记录一次重启."""
        self.clean_restart_history()
        self.restart_times.append(time.time())
        self.restart_count = len(self.restart_times)


class ServiceManager:
    """管理所有服务进程的启动/停止/状态."""

    def __init__(self, services: dict):
        self.services = {name: ServiceInfo(name, cfg) for name, cfg in services.items()}
        self._startup_order = startup_order(services)
        self._shutdown_order = list(reversed(self._startup_order))

    # ── 启动 ──────────────────────────────────────────────────────────

    def start_service(self, name: str) -> bool:
        """启动单个服务. 返回 True 表示启动成功."""
        info = self.services.get(name)
        if not info:
            logger.error("未知服务: %s", name)
            return False

        if info.is_running:
            logger.info("  [%s] 已在运行 (PID=%s)", name, info.pid)
            return True

        # 清理旧死进程引用
        if info.process is not None and info.process.poll() is not None:
            logger.info("  [%s] 清理旧死进程 (PID=%s, exit=%s)", name, info.pid, info.returncode)
            info.process = None
            info.close_log()

        svc = info.config
        cmd = svc["cmd"]
        cwd = svc["cwd"]
        delay = svc.get("delay", 1.0)
        env = os.environ.copy()
        env.update(svc.get("env", {}))

        logger.info("  [%s] 启动中... cmd=%s", name, os.path.basename(cmd[0] if cmd else ""))

        # spec 2026-08-29-services-management-monitor P1:
        # 服务终端输出 (stdout+stderr) 落盘到 debug/system/services/<name>.log,
        # 替代原有 DEVNULL 丢弃 — 保留报错痕迹供服务管理页统一查看.
        info.close_log()
        log_fh = _open_service_log(name)
        out_target = log_fh if log_fh is not None else subprocess.DEVNULL

        try:
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=out_target,
                stderr=out_target,
                creationflags=creationflags,
            )
            info.process = proc
            info.log_fh = log_fh
        except OSError as exc:
            logger.error("  [%s] 启动失败: %s", name, exc)
            info.close_log()
            return False

        # 等待 + 验证
        time.sleep(delay)
        if verify_service(name, svc):
            logger.info("  [%s] 启动成功 (PID=%s)", name, proc.pid)
            return True
        else:
            logger.warning("  [%s] 启动但验证未通过 (PID=%s)", name, proc.pid)
            return True  # 不阻塞后续服务启动

    def start_all(self) -> bool:
        """按依赖顺序启动所有服务."""
        logger.info("=" * 48)
        logger.info("  启动所有服务 (%d 个)", len(self.services))
        logger.info("=" * 48)

        for i, name in enumerate(self._startup_order, 1):
            logger.info("[%d/%d] 启动 %s...", i, len(self._startup_order), name)
            self.start_service(name)

        logger.info("")
        logger.info("=== 启动完成 ===")
        self.print_status()
        return True

    # ── 停止 ──────────────────────────────────────────────────────────

    def stop_service(self, name: str) -> bool:
        """停止单个服务."""
        info = self.services.get(name)
        if not info or not info.is_running:
            logger.info("  [%s] 未运行", name)
            return True

        proc = info.process
        logger.info("  [%s] 停止中... PID=%s", name, proc.pid)

        # 先 terminate
        proc.terminate()
        try:
            proc.wait(timeout=STOP_TIMEOUT)
            logger.info("  [%s] 已停止 (PID=%s)", name, proc.pid)
        except subprocess.TimeoutExpired:
            logger.warning("  [%s] 超时未退出, 强制终止 (PID=%s)", name, proc.pid)
            proc.kill()
            proc.wait(timeout=2)

        info.process = None
        info.close_log()
        return True

    def stop_all(self) -> bool:
        """按反向顺序停止所有服务."""
        logger.info("=" * 48)
        logger.info("  停止所有服务")
        logger.info("=" * 48)

        for i, name in enumerate(self._shutdown_order, 1):
            if name in self.services:
                logger.info("[%d/%d] 停止 %s...", i, len(self._shutdown_order), name)
                self.stop_service(name)

        logger.info("")
        logger.info("=== 停止完成 ===")
        return True

    # ── 状态 ──────────────────────────────────────────────────────────

    def print_status(self):
        """打印所有服务状态."""
        logger.info("服务状态:")
        any_running = False
        for name, info in self.services.items():
            if info.is_running:
                any_running = True
                port = info.config.get("port")
                port_str = f" Port={port}" if port else ""
                logger.info("  [%s] PID=%s%s", name, info.pid, port_str)
            else:
                rc = info.returncode
                rc_str = f" (exit={rc})" if rc is not None else ""
                logger.info("  [%s] 已停止%s", name, rc_str)

        if not any_running:
            logger.info("  所有服务已停止")

    def get_status(self) -> dict:
        """返回各服务状态字典."""
        return {
            name: {
                "running": info.is_running,
                "pid": info.pid,
                "port": info.config.get("port"),
                "returncode": info.returncode,
                "restart_count": info.restart_count,
            }
            for name, info in self.services.items()
        }

    # ── 重启 ──────────────────────────────────────────────────────────

    def restart_service(self, name: str) -> bool:
        """重启单个服务."""
        self.stop_service(name)
        # 短暂等待确保端口释放
        time.sleep(1)
        return self.start_service(name)

    def restart_all(self) -> bool:
        """重启所有服务."""
        logger.info("=" * 48)
        logger.info("  重启所有服务")
        logger.info("=" * 48)
        self.stop_all()
        logger.info("")
        logger.info("--- 等待 3 秒后启动 ---")
        logger.info("")
        time.sleep(3)
        return self.start_all()


# =============================================================================
# DaemonRunner — 看门狗循环
# =============================================================================

class DaemonRunner:
    """守护进程运行器: 看门狗循环 + 信号处理."""

    def __init__(self, manager: ServiceManager):
        self.manager = manager
        self._running = False
        self._shutdown_requested = False

        # 注册信号处理
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """信号处理: 设置关闭标志."""
        sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        if self._shutdown_requested:
            logger.warning("收到 %s, 强制退出...", sig_name)
            sys.exit(1)
        logger.info("收到 %s, 开始优雅关闭... (再次发送强制退出)", sig_name)
        self._shutdown_requested = True

    def _run_health_checks(self):
        """spec 2026-08-29 P2: 跑健康探针 → 写快照 → 对"进程在但应用假死"的服务触发重启.

        健康感知重启规则:
        - 服务进程存活 但 应用级探针 unhealthy → 视为假死 (如僵尸 consumer 假离线),
          走与进程退出相同的重启流程 (撞车保护不变).
        - 探针异常 (无法执行) 不重启, 仅记日志 — 避免误杀.
        """
        try:
            snapshot = check_all()
        except Exception as exc:
            logger.warning("健康探针执行失败 (跳过本轮): %s", exc)
            return

        # spec 2026-08-29-services-management-monitor P2:
        # 快照注入进程运行时信息 + 服务日志报错计数 (供服务管理 API/页面读取)
        extra: dict = {
            "processes": self.manager.get_status(),
            "log_errors": {name: scan_log_errors(name) for name in snapshot},
        }

        try:
            write_health_snapshot(snapshot, extra=extra)
        except Exception as exc:
            logger.warning("健康快照写入失败: %s", exc)

        unhealthy = {name: h for name, h in snapshot.items() if not h.healthy}
        if not unhealthy:
            return

        for name, h in unhealthy.items():
            info = self.manager.services.get(name)
            if not info or not info.is_running:
                continue  # 进程已不在 → 已有下方进程退出逻辑处理
            logger.warning(
                "  [%s] 进程存活但健康检查失败 (%s) → 触发健康感知重启",
                name, h.detail,
            )
            self.manager.restart_service(name)

    def run(self):
        """进入看门狗模式."""
        self._running = True
        _write_pid_file()
        logger.info("=" * 48)
        logger.info("  GAF 守护进程启动 (看门狗模式)")
        logger.info("  PID=%d | 检查周期: %ds | 最大重启: %d 次/%d 秒",
                     os.getpid(), WATCHDOG_INTERVAL, MAX_RESTART_COUNT, RESTART_WINDOW)
        logger.info("  Ctrl+C 优雅关闭")
        logger.info("=" * 48)

        # 启动所有服务
        self.manager.start_all()

        # 看门狗循环
        try:
            while self._running and not self._shutdown_requested:
                time.sleep(WATCHDOG_INTERVAL)

                if self._shutdown_requested:
                    break

                # spec 2026-08-29 P2: 每轮执行健康探针并写快照 (供 monitors/status 读取)
                self._run_health_checks()

                for name, info in self.manager.services.items():
                    if self._shutdown_requested:
                        break

                    if not info.is_running:
                        # 先检查端口是否仍在监听 (reconcile 僵尸状态)
                        svc = info.config
                        port = svc.get("port")
                        if port and _port_listening(port):
                            if info.process is not None:
                                logger.warning(
                                    "  [%s] 进程已退出 (PID=%s), 但端口 %d 仍在监听 → 清理旧进程引用",
                                    name, info.pid, port,
                                )
                            info.process = None
                            info.restart_times = []
                            info.restart_count = 0
                            info.close_log()
                            continue

                        rc = info.returncode
                        logger.warning(
                            "  [%s] 进程已退出 (PID=%s, exit=%s)",
                            name, info.pid, rc,
                        )
                        info.close_log()

                        if info.can_restart():
                            logger.info("  [%s] 自动重启中...", name)
                            self.manager.start_service(name)
                            info.record_restart()
                            if info.is_running:
                                logger.info(
                                    "  [%s] 重启成功 (新PID=%s, 已重启%d次)",
                                    name, info.pid, info.restart_count,
                                )
                            else:
                                logger.error("  [%s] 重启失败", name)
                        else:
                            logger.error(
                                "  [%s] 超过最大重启次数 (%d次/%d秒), 停止自动重启",
                                name, MAX_RESTART_COUNT, RESTART_WINDOW,
                            )
        finally:
            # 优雅关闭
            logger.info("")
            logger.info("守护进程退出中...")
            self.manager.stop_all()
            self._running = False
            _remove_pid_file()
            logger.info("守护进程已退出")


# =============================================================================
# detached 启动 (Windows 后台进程)
# =============================================================================

def launch_detached():
    """以 detached 方式启动 daemon 进程, 立即返回."""
    if sys.platform != "win32":
        logger.error("detached 启动仅支持 Windows")
        sys.exit(1)

    # 用 CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS 启动子进程
    # 这样子进程不会随父进程退出
    import ctypes
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200

    creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    cmd = [
        str(PYTHON_EXE), str(Path(__file__).resolve()),
        "__daemon__",
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=str(GAF_ROOT),
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )
    return proc.pid


def stop_daemon_process(pid: int):
    """停止指定 PID 的 daemon 进程及其子进程."""
    logger.info("终止 daemon 进程 PID=%d ...", pid)

    if sys.platform == "win32":
        # Windows: 用 taskkill /T 杀进程树
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, timeout=10,
                creationflags=_no_console_flags(),
            )
            out = result.stdout or b""
            # taskkill 成功输出可能为中文本地化 (GBK), bytes 匹配两种编码的"成功"
            if b"SUCCESS" in out or "成功".encode("utf-8") in out or "成功".encode("gbk") in out:
                logger.info("daemon 进程树已终止 (PID=%d)", pid)
                return True
            else:
                logger.warning("taskkill 输出: %s", result.stdout.strip())
                # 即使 taskkill 没找到, 也继续清理 PID 文件
                return True
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.error("终止 daemon 失败: %s", exc)
            return False
    else:
        # Unix: 发 SIGTERM 然后 SIGKILL
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(3)
            if _is_process_alive(pid):
                os.kill(pid, signal.SIGKILL)
            return True
        except OSError:
            return True  # 进程已不存在


def print_daemon_status(with_health: bool = False):
    """打印 daemon 状态 + 服务状态."""
    daemon_pid = check_daemon_running()

    if daemon_pid:
        logger.info("Daemon: 运行中 (PID=%d)", daemon_pid)
    else:
        pid = _read_pid_file()
        if pid:
            logger.info("Daemon: 已停止 (PID 文件残留 PID=%d, 进程已死)", pid)
        else:
            logger.info("Daemon: 未运行")

    # 检测各服务端口
    cfg = load_config()
    redis_ok = _redis_ping(cfg["redis_port"])
    backend_ok = _port_listening(cfg["backend_port"])
    frontend_ok = _port_listening(cfg["frontend_port"])

    logger.info("  [redis]    Port=%d %s", cfg["redis_port"], "✓" if redis_ok else "✗")
    logger.info("  [backend]  Port=%d %s", cfg["backend_port"], "✓" if backend_ok else "✗")
    logger.info("  [frontend] Port=%d %s", cfg["frontend_port"], "✓" if frontend_ok else "✗")

    # spec 2026-08-29 P2: 应用级健康探针（可选 --health）
    health_detail = None
    if with_health:
        try:
            snapshot = check_all()
            for name, h in snapshot.items():
                flag = "OK " if h.healthy else "FAIL"
                logger.info("  [%s] 健康 %s (%s)", name, flag.strip(), h.detail)
            health_detail = {name: h.to_dict() for name, h in snapshot.items()}
        except Exception as exc:
            logger.warning("健康探针执行失败: %s", exc)

    result = {
        "daemon_running": daemon_pid is not None,
        "daemon_pid": daemon_pid,
        "redis": redis_ok,
        "backend": backend_ok,
        "frontend": frontend_ok,
    }
    if health_detail is not None:
        result["health"] = health_detail
    return result


# =============================================================================
# CLI 入口
# =============================================================================

def main():
    """CLI 入口."""
    setup_logging()

    if len(sys.argv) < 2:
        print("用法: python scripts/gaf_daemon.py <command>")
        print("命令: start, stop, restart, status, daemon, monitor")
        print("  start   - detached 启动所有服务 + 看门狗 (立即返回)")
        print("  stop    - 停止所有服务 + 终止 daemon")
        print("  restart - stop + start")
        print("  status  - 显示 daemon + 服务状态")
        print("  daemon  - 前台模式启动 (调试用, Ctrl+C 退出)")
        print("  monitor - 仅看门狗模式 (不启动服务)")
        sys.exit(1)

    command = sys.argv[1]

    # ── 内部命令: __daemon__ (detached 启动的子进程) ──────────────
    if command == "__daemon__":
        cfg = load_config()
        services = build_services(cfg)
        manager = ServiceManager(services)
        runner = DaemonRunner(manager)
        runner.run()
        return

    # ── start: detached 启动, 立即返回 ────────────────────────────
    if command == "start":
        existing = check_daemon_running()
        if existing:
            logger.info("Daemon 已在运行 (PID=%d), 无需重复启动", existing)
            print(f"Daemon 已在运行 (PID={existing})")
            sys.exit(0)

        logger.info("启动 GAF daemon (detached 模式)...")
        print("启动 GAF 服务 (后台模式)...")
        try:
            pid = launch_detached()
            logger.info("Daemon 已启动 (PID=%d)", pid)
            print(f"Daemon 已启动 (PID={pid})")
            print(f"日志: {DEBUG_DIR / 'daemon.log'}")
            sys.exit(0)
        except Exception as exc:
            logger.error("启动失败: %s", exc)
            print(f"启动失败: {exc}")
            sys.exit(1)

    # ── stop: 停止 daemon + 所有服务 ────────────────────────────────
    if command == "stop":
        daemon_pid = _read_pid_file()
        if daemon_pid:
            logger.info("找到 daemon PID=%d, 终止进程树...", daemon_pid)
            stopped = stop_daemon_process(daemon_pid)
            if stopped:
                _remove_pid_file()
                logger.info("Daemon 已终止")
                print(f"Daemon (PID={daemon_pid}) 已终止")
            else:
                print(f"终止 daemon (PID={daemon_pid}) 失败")
                sys.exit(1)
        else:
            logger.info("无运行中的 daemon")
            print("无运行中的 daemon")
        sys.exit(0)

    # ── restart ────────────────────────────────────────────────────
    if command == "restart":
        existing = check_daemon_running()
        if existing:
            print(f"停止 daemon (PID={existing})...")
            stop_daemon_process(existing)
            _remove_pid_file()
            time.sleep(2)
        print("重新启动 daemon...")
        pid = launch_detached()
        print(f"Daemon 已启动 (PID={pid})")
        sys.exit(0)

    # ── status ────────────────────────────────────────────────────
    if command == "status":
        # spec 2026-08-29 P2: --health / --json 输出应用级健康详情
        want_health = any(a in sys.argv[2:] for a in ("--health", "-h", "--json"))
        if "--json" in sys.argv:
            result = print_daemon_status(with_health=want_health)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print_daemon_status(with_health=want_health)
        sys.exit(0)

    # ── daemon: 前台模式 (调试) ───────────────────────────────────
    if command == "daemon":
        existing = check_daemon_running()
        if existing:
            print(f"Daemon 已在运行 (PID={existing}), 拒绝重复启动")
            print("如需强制重启, 请先执行: python scripts/gaf_daemon.py stop")
            sys.exit(1)

        cfg = load_config()
        services = build_services(cfg)
        manager = ServiceManager(services)
        runner = DaemonRunner(manager)
        runner.run()
        return

    # ── monitor: 仅看门狗 ─────────────────────────────────────────
    if command == "monitor":
        cfg = load_config()
        services = build_services(cfg)
        manager = ServiceManager(services)
        runner = DaemonRunner(manager)
        runner._running = True
        _write_pid_file()
        logger.info("=" * 48)
        logger.info("  GAF 守护进程 (monitor 模式)")
        logger.info("  不启动服务, 仅监控已有进程")
        logger.info("  Ctrl+C 退出")
        logger.info("=" * 48)
        try:
            while not runner._shutdown_requested:
                time.sleep(WATCHDOG_INTERVAL)
                for name, info in manager.services.items():
                    if not info.is_running and info.pid is not None:
                        logger.warning(
                            "  [%s] 进程已退出 (exit=%s)",
                            name, info.returncode,
                        )
        except KeyboardInterrupt:
            logger.info("monitor 模式退出")
        finally:
            _remove_pid_file()
        return

    # ── start (兼容旧命令, 直接启动服务不进看门狗) ───────────────
    if command == "old_start":
        cfg = load_config()
        services = build_services(cfg)
        manager = ServiceManager(services)
        manager.start_all()
        return

    print(f"未知命令: {command}")
    print("支持的命令: start, stop, restart, status, daemon, monitor")
    sys.exit(1)


if __name__ == "__main__":
    main()
