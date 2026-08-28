"""Unified per-execution debug directory layout — backend mirror (N194, 2026-07-28; 嵌套结构 2026-07-29).

Mirror of ``agent/src/utils/debug_path.py``. Backend cannot import agent
package, so the logic is duplicated here. Keep the two copies in sync.

Directory layout (嵌套结构, 2026-07-29)::

    <DEBUG_DIR>/<YYYYMMDD>/<safe_task_name>/<HHMMSS>_<exec_id_suffix8>/
    ├── meta.json            # 用户可读元信息 (视角 B)
    ├── run.log              # backend FileLogHandler
    ├── structured.jsonl     # agent StructuredLogger
    └── screenshots/{annotated,raw}/  # agent DebugImageSaver

    <DEBUG_DIR>/_global/<YYYYMMDD>/run.log   # 无 execution_id 的日志 (CLI/Celery, 按日期分目录)

双视角:
  - 视角 A (AI): 拿 execution_id 后 8 字符 → 两层扫描 ``debug/<date>/<pipeline>/*<suffix>/``
  - 视角 B (用户): 浏览 ``debug/<date>/<pipeline>/`` 按时间找
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_MAX_TASK_NAME_LEN = 40
_EXEC_ID_SUFFIX_LEN = 8


def _sanitize_task_name(name: str) -> str:
    """Make task_name safe for use in a directory name.

    Mirror of agent.utils.debug_path._sanitize_task_name.
    """
    if not name:
        return "unnamed"
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    safe = safe.replace(" ", "_")
    safe = safe.strip("._")
    if not safe:
        return "unnamed"
    return safe[:_MAX_TASK_NAME_LEN]


def _extract_exec_id_suffix(execution_id: str) -> str:
    """Extract the last N chars of execution_id for directory naming.

    Mirror of agent.utils.debug_path._extract_exec_id_suffix.
    """
    if not execution_id:
        return ""
    if execution_id.startswith("exec-"):
        hex_part = execution_id[5:]
        return hex_part[-_EXEC_ID_SUFFIX_LEN:] if len(hex_part) >= _EXEC_ID_SUFFIX_LEN else hex_part
    return execution_id[-_EXEC_ID_SUFFIX_LEN:]


def _is_unified_exec_dir(debug_dir: str) -> bool:
    """Detect if ``debug_dir`` is a complete per-execution directory.

    Mirror of agent.utils.debug_path._is_unified_exec_dir.
    嵌套结构 (2026-07-29): basename = ``HHMMSS_<suffix>`` (6 位时间 + _).
    向后兼容: 旧扁平格式 ``YYYYMMDD_HHMMSS_<name>_<suffix>``.
    """
    if not debug_dir:
        return False
    base = os.path.basename(os.path.normpath(debug_dir))
    if re.match(r"^\d{6}_", base):
        return True
    return bool(re.match(r"^\d{8}_\d{6}_", base))


def build_execution_debug_dir(
    debug_dir_root: str,
    execution_id: str,
    task_name: str,
    start_time: datetime | None = None,
) -> str:
    """Build the per-execution debug directory path.

    Output (嵌套结构, 2026-07-29):
        ``<debug_dir_root>/<YYYYMMDD>/<safe_task_name>/<HHMMSS>_<exec_id_suffix>``

    The directory is NOT created here — callers create it lazily.

    Mirror of agent.utils.debug_path.build_execution_debug_dir.
    """
    root = debug_dir_root or "./debug"
    now = start_time or datetime.now()
    date_part = now.strftime("%Y%m%d")     # 日期目录: 20260728
    time_part = now.strftime("%H%M%S")     # 执行目录前缀: 153000
    safe_name = _sanitize_task_name(task_name)
    suffix = _extract_exec_id_suffix(execution_id)

    exec_dir_name = f"{time_part}_{suffix}" if suffix else time_part

    return os.path.join(root, date_part, safe_name, exec_dir_name)


def write_meta_json(
    exec_debug_dir: str,
    *,
    execution_id: str,
    task_id: str | int = "",
    task_name: str = "",
    pipeline_name: str = "",
    start_time: datetime | None = None,
    status: str = "running",
    device_info: dict[str, Any] | None = None,
    agent_id: str = "",
    trace_id: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Write ``meta.json`` to the per-execution debug directory.

    视角 B (用户调试) 核心: 用户打开目录第一眼就能确认"这是不是我要找的那次执行".

    B3-4 (spec 2026-07-30-debug-directory-restructure): 新增 ``trace_id`` 显式参数,
    由 dispatch_task / views.execute 从 ``current_trace_id`` ContextVar 取后传入.
    meta.json 含 trace_id 后, 用户/AI 拿 trace_id 可反查 meta.json 定位执行上下文,
    实现 HTTP → DB → meta.json → agent log 全链路贯穿.

    Idempotent: 每次调用都覆盖原 ``meta.json`` (用于 status 更新: running → completed).
    Failures are best-effort — meta.json 写失败不阻塞 pipeline.

    Mirror of agent.utils.debug_path.write_meta_json (agent 侧待 F 段同步加 trace_id).
    """
    try:
        os.makedirs(exec_debug_dir, exist_ok=True)
        meta_path = os.path.join(exec_debug_dir, "meta.json")

        start_iso = (start_time or datetime.now()).isoformat()
        meta: dict[str, Any] = {
            "execution_id": execution_id,
            "task_id": str(task_id) if task_id != "" else "",
            "task_name": task_name,
            "pipeline_name": pipeline_name,
            "start_time": start_iso,
            "status": status,
            "agent_id": agent_id,
            # B3-4: trace_id 字段始终存在 (空字符串表示无 HTTP 请求上下文,
            # 如 CLI / Celery 无请求 scope 触发的执行).
            "trace_id": trace_id,
        }
        if device_info:
            meta["device_info"] = device_info
        if extra:
            meta.update(extra)

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.warning(
            "debug_path: write_meta_json failed for %s: %s",
            exec_debug_dir, exc,
        )


def find_exec_dir_by_id(
    debug_dir_root: str,
    execution_id: str,
) -> str | None:
    """Find the per-execution directory by execution_id (视角 A AI 调试).

    Mirror of agent.utils.debug_path.find_exec_dir_by_id.
    嵌套结构 (2026-07-29): 两层扫描 <root>/<date>/<pipeline>/<HHMMSS_suffix>/.
    向后兼容: 旧扁平格式 <root>/YYYYMMDD_HHMMSS_*_<suffix>/.
    """
    if not execution_id or not debug_dir_root:
        return None
    suffix = _extract_exec_id_suffix(execution_id)
    if not suffix:
        return None

    try:
        root_entries = os.listdir(debug_dir_root)
    except OSError:
        return None

    matches: list[tuple[str, float]] = []

    # --- 1. 新嵌套格式: <root>/<YYYYMMDD>/<pipeline>/<HHMMSS_suffix>/ ---
    date_pattern = re.compile(r"^\d{8}$")
    exec_pattern = re.compile(r"^\d{6}_")
    for date_entry in root_entries:
        if not date_pattern.match(date_entry):
            continue
        date_dir = os.path.join(debug_dir_root, date_entry)
        if not os.path.isdir(date_dir):
            continue
        try:
            pipeline_entries = os.listdir(date_dir)
        except OSError:
            continue
        for pipeline_entry in pipeline_entries:
            pipeline_dir = os.path.join(date_dir, pipeline_entry)
            if not os.path.isdir(pipeline_dir):
                continue
            try:
                exec_entries = os.listdir(pipeline_dir)
            except OSError:
                continue
            for exec_entry in exec_entries:
                if not exec_entry.endswith(suffix):
                    continue
                if not exec_pattern.match(exec_entry):
                    continue
                full_path = os.path.join(pipeline_dir, exec_entry)
                if not os.path.isdir(full_path):
                    continue
                try:
                    mtime = os.path.getmtime(full_path)
                except OSError:
                    mtime = 0.0
                matches.append((full_path, mtime))

    # --- 2. 旧扁平格式兼容: <root>/YYYYMMDD_HHMMSS_*_<suffix>/ ---
    legacy_pattern = re.compile(r"^\d{8}_\d{6}_")
    for entry in root_entries:
        if not entry.endswith(suffix):
            continue
        if not legacy_pattern.match(entry):
            continue
        full_path = os.path.join(debug_dir_root, entry)
        if not os.path.isdir(full_path):
            continue
        try:
            mtime = os.path.getmtime(full_path)
        except OSError:
            mtime = 0.0
        matches.append((full_path, mtime))

    if not matches:
        return None
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[0][0]
