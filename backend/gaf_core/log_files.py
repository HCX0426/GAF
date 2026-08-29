"""统一文件日志检索 — 服务终端日志 + 各服务原生日志 (spec 2026-08-29-logging-system-consolidation P2-1).

AI 可调试性: 前端日志中心/服务管理/AI 通过一个检索层访问**文件层**日志
(服务终端捕获 + 原生日志), 与 DB 层业务事件 (AuditLog 等) 互补.

布局:
- 服务终端捕获: ``debug/system/services/<name>.log`` (+ .log.1 轮转备份, daemon 写)
- 原生日志:      ``debug/<YYYYMMDD>/<app>/system/...`` (django.log / agent.log / daemon.log)

本模块被两处消费:
- ``gaf_core.views.FileLogQueryView`` (GET /api/v2/logs/files/)
- ``monitors.views`` 服务管理日志 (保证同一套定位/报错过滤逻辑, 无双份漂移)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# backend/gaf_core/log_files.py → parents[2] = 仓库根
_DEBUG_ROOT = Path(__file__).resolve().parents[2] / "debug"
_SERVICE_LOG_DIR = _DEBUG_ROOT / "system" / "services"

# 报错行匹配 (与 scripts/services/health.py _ERROR_PATTERNS 保持语义一致)
ERROR_PATTERNS = (
    re.compile(r"\b(ERROR|CRITICAL|FATAL)\b"),
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"(?:Exception|Error)[:(]"),
)

SERVICE_ORDER = ["redis", "backend", "agent", "frontend", "daemon"]


def latest_day_dir(debug_root: Path | None = None) -> Path | None:
    """返回 debug/ 下日期最大的目录 (YYYYMMDD)."""
    debug_root = debug_root or _DEBUG_ROOT
    if not debug_root.is_dir():
        return None
    for entry in sorted(debug_root.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        try:
            datetime.strptime(entry.name, "%Y%m%d")
        except ValueError:
            logger.debug("跳过非日期目录: %s", entry.name)
            continue
        return entry
    return None


def _day_dir_for(date: str | None) -> Path | None:
    """把 'YYYY-MM-DD' 解析为 debug/<YYYYMMDD>; None 时取最新一天."""
    if date:
        try:
            compact = date.replace("-", "")
            datetime.strptime(compact, "%Y%m%d")
        except ValueError:
            return None
        cand = _DEBUG_ROOT / compact
        return cand if cand.is_dir() else None
    return latest_day_dir()


def resolve_service_log_files(name: str, date: str | None = None) -> list[Path]:
    """定位服务日志文件列表 (终端捕获优先, 原生日志 fallback).

    Args:
        name: 服务名 (redis/backend/agent/frontend/daemon, 或追加自定义)
        date: 'YYYY-MM-DD' 指定日期 (None = 最新一天, 仅原生日志生效)
    """
    candidates = [
        _SERVICE_LOG_DIR / f"{name}.log",
        _SERVICE_LOG_DIR / f"{name}.log.1",
    ]
    day = _day_dir_for(date)
    if day is not None:
        if name == "backend":
            system_dir = day / "backend" / "system"
            if system_dir.is_dir():
                logs = sorted(
                    system_dir.rglob("*.log"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )[:4]
                candidates.extend(logs)
        elif name == "agent":
            candidates.append(day / "agent" / "system" / "agent.log")
        elif name == "daemon":
            candidates.append(day / "backend" / "system" / "daemon.log")
    return [p for p in candidates if p.exists()]


def read_log_tail(files: list[Path], max_lines: int) -> list[str]:
    """读取列表首个存在文件的尾部 max_lines 行 (主捕获文件即为最新输出)."""
    if not files:
        return []
    path = files[0]
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError as exc:
        logger.debug("读取日志文件失败 %s: %s", path, exc)
        return []
    return [ln.rstrip("\r\n") for ln in lines[-max_lines:]]


def collect_error_lines(files: list[Path], max_lines: int) -> list[str]:
    """跨所有候选文件收集报错行 (含原生日志历史错误, 便于统一排查)."""
    error_lines: list[str] = []
    for path in files:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for ln in fh.readlines()[-(max_lines * 2):]:
                    if any(p.search(ln) for p in ERROR_PATTERNS):
                        error_lines.append(ln.rstrip("\r\n"))
        except OSError as exc:
            logger.debug("读取日志文件失败 %s: %s", path, exc)
            continue
        if len(error_lines) >= max_lines:
            break
    return error_lines[:max_lines]
