"""Unified per-execution debug directory layout (N194, 2026-07-28; 嵌套结构 2026-07-29).

归一化前 (问题): 一次执行的调试文件散落在 5+ 个目录:
  - ``<debug_dir>/structured/<exec_id>.jsonl``       (agent StructuredLogger)
  - ``<debug_dir>/template_match/screenshots/...``   (template_match 节点)
  - ``<debug_dir>/ocr/screenshots/...``              (ocr 节点)
  - ``<debug_dir>/action/screenshots/...``           (click/swipe/wait/key_press 节点)
  - ``<debug_dir>/logs/<exec_id>/run.log``           (backend FileLogHandler)

用户调试时无法"一起看"日志和图片 — 必须跨 5 个目录翻找, 而且不按 execution_id
归集, 多次执行的图片全堆在 ``template_match/screenshots/annotated/`` 下无法区分。

归一化后 (本模块): 每次执行一个目录, **嵌套结构** (2026-07-29 改版, 替代原扁平
``YYYYMMDD_HHMMSS_<name>_<suffix>`` 单层目录), 按 日期 → pipeline → 执行 三级分组::

    d:/code/GAF/debug/
    ├── 20260728/                              # YYYYMMDD (日期目录)
    │   ├── Get_Email/                         # safe_task_name (pipeline 目录)
    │   │   ├── 153000_a1b2c3d4/               # HHMMSS_<exec_id_suffix> (单次执行)
    │   │   │   ├── meta.json                  # 用户可读的执行元信息 (视角 B)
    │   │   │   ├── run.log                    # backend 文本日志 (FileLogHandler)
    │   │   │   ├── structured.jsonl           # agent 结构化日志 (StructuredLogger)
    │   │   │   └── screenshots/
    │   │   │       ├── annotated/             # 所有节点标注图 PNG
    │   │   │       └── raw/                   # 识别类节点原图 JPEG
    │   │   └── 160500_e5f6g7h8/               # 同一 pipeline 当天第二次执行
    │   └── Login_Test/
    │       └── 103000_9a8b7c6d/
    ├── archives/                              # 归档 tar.gz (pack_execution_logs, 跟着嵌套)
    │   └── 20260728/
    │       └── Get_Email/
    │           └── <exec_id>.tar.gz
    └── _global/
        └── run.log                            # backend 无 exec 上下文的日志 (CLI/Celery)

嵌套结构优势 (相比扁平 ``YYYYMMDD_HHMMSS_<name>_<suffix>``):
  - 同一 pipeline 当天多次执行聚拢在同一子目录, 方便对比
  - 单级目录名更短, Windows MAX_PATH=260 友好
  - 按日期→pipeline 浏览符合直觉

双视角设计:
  - 视角 A (AI 调试): 拿到 ``execution_id=exec-abc123456789a`` → 取后 8 字符 ``a1b2c3d4``
    → 两层扫描 ``debug/<date>/<pipeline>/*a1b2c3d4`` → 命中目录
  - 视角 B (用户调试): 用户在前端只看到"任务失败", 知道"下午 3 点跑的 get_email"
    → 浏览 ``debug/20260728/Get_Email/`` → 看 meta.json 确认
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# 目录名中 task_name 的最大保留长度. 太长会让目录名难读, 太短会同名任务无法区分.
_MAX_TASK_NAME_LEN = 40
# execution_id 后缀长度. 8 位足够区分同分钟内同任务多次执行 (16^8 = 4.3B 种可能).
_EXEC_ID_SUFFIX_LEN = 8


def _sanitize_task_name(name: str) -> str:
    """Make task_name safe for use in a directory name.

    - 替换路径分隔符 / 空格 / 冒号 / 其他 Windows 不允许的字符为 ``_``
    - 保留中文 (Unicode-safe, 文件系统支持)
    - 截断到 ``_MAX_TASK_NAME_LEN`` 字符
    - 空字符串返回 ``"unnamed"``
    """
    if not name:
        return "unnamed"
    # Windows 文件系统禁止的字符: < > : " / \\ | ? * 以及控制字符
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    safe = safe.replace(" ", "_")
    safe = safe.strip("._")  # 去掉首尾的 . 和 _
    if not safe:
        return "unnamed"
    return safe[:_MAX_TASK_NAME_LEN]


def _is_unified_exec_dir(debug_dir: str) -> bool:
    """N194 归一化 (2026-07-28; 嵌套结构 2026-07-29): detect if ``debug_dir`` is a
    complete per-execution directory vs a legacy root (``./debug``).

    嵌套结构检测 (2026-07-29): 路径形如
    ``<root>/<YYYYMMDD>/<safe_task_name>/<HHMMSS>_<exec_id_suffix>/``.
    basename 匹配 ``HHMMSS_<suffix>`` (6 位时间 + 下划线 + 后缀),
    且 parent 目录存在 (说明是嵌套结构的叶子层).

    向后兼容: 也接受旧扁平格式 ``YYYYMMDD_HHMMSS_<name>_<suffix>`` (历史目录未迁移,
    cleanup 时仍需识别). 但新生成的目录都是嵌套格式.

    Used by StructuredLogger / orchestrator to decide:
    - Whether to write ``<debug_dir>/structured.jsonl`` (unified) or
      ``<debug_dir>/structured/<exec_id>.jsonl`` (legacy)
    - Whether to update ``meta.json`` (only exists in unified dir)
    - Whether to mirror to agent-local ``<cwd>/debug/<rel_path>/`` (unified only)
    """
    if not debug_dir:
        return False
    base = os.path.basename(os.path.normpath(debug_dir))
    # 新嵌套格式: basename = HHMMSS_<suffix>, 6 位数字 + _ + 后缀
    if re.match(r"^\d{6}_", base):
        return True
    # 旧扁平格式兼容: basename = YYYYMMDD_HHMMSS_<name>_<suffix>
    return bool(re.match(r"^\d{8}_\d{6}_", base))


def _extract_exec_id_suffix(execution_id: str) -> str:
    """Extract the last N chars of execution_id for directory naming.

    Accepts both ``"exec-abc123456789a"`` (agent-generated) and ``"123"`` (backend
    TaskExecution.pk). For numeric IDs, uses the whole string (no need to truncate
    — they're already short and unique). For ``exec-`` prefixed UUIDs, takes the
    last 8 hex chars.

    Args:
        execution_id: ``"exec-<uuid12>"`` or ``"<int>"`` or empty string.

    Returns:
        8-char (or shorter) suffix safe for directory naming. Empty string when
        ``execution_id`` is empty (CLI mode, no server connection).
    """
    if not execution_id:
        return ""
    # Strip "exec-" prefix if present
    if execution_id.startswith("exec-"):
        hex_part = execution_id[5:]
        return hex_part[-_EXEC_ID_SUFFIX_LEN:] if len(hex_part) >= _EXEC_ID_SUFFIX_LEN else hex_part
    # Numeric ID (backend TaskExecution.pk) — use as-is, already short
    return execution_id[-_EXEC_ID_SUFFIX_LEN:]


def build_execution_debug_dir(
    debug_dir_root: str,
    execution_id: str,
    task_name: str,
    start_time: datetime | None = None,
) -> str:
    """Build the per-execution debug directory path.

    Output format (嵌套结构, 2026-07-29):
        ``<debug_dir_root>/<YYYYMMDD>/<safe_task_name>/<HHMMSS>_<exec_id_suffix>``

    嵌套层级:
        - 第 1 层 ``YYYYMMDD``: 按日期分组, 同一天的所有执行聚在一起
        - 第 2 层 ``safe_task_name``: 按 pipeline/task 分组, 同一 pipeline 当天多次执行聚在一起
        - 第 3 层 ``HHMMSS_<suffix>``: 单次执行目录, 含 meta.json + run.log + structured.jsonl + screenshots/

    The directory is NOT created here — callers (orchestrator / FileLogHandler)
    create it lazily when they write the first file. This avoids leaving empty
    directories when a task assignment fails before any log is emitted.

    Args:
        debug_dir_root: Debug root directory (e.g. ``"d:/code/GAF/debug"``).
            Empty string falls back to ``"./debug"`` for backward compat.
        execution_id: Execution identifier (``"exec-<uuid12>"`` or backend pk).
            Empty string → suffix is empty (CLI mode, dir name has no suffix).
        task_name: Task name for human readability. Empty → ``"unnamed"``.
        start_time: Execution start time. None → use current UTC time.
            拆为 ``YYYYMMDD`` (日期目录) + ``HHMMSS`` (执行目录前缀) 两部分.

    Returns:
        Absolute path to the per-execution directory (not yet created).

    Examples:
        >>> build_execution_debug_dir("d:/code/GAF/debug", "exec-abc123456789a", "Get Email")
        'd:/code/GAF/debug/20260728/Get_Email/153000_a1b2c3d4'

        >>> build_execution_debug_dir("d:/code/GAF/debug", "123", "Login")
        'd:/code/GAF/debug/20260728/Login/153000_123'

        >>> build_execution_debug_dir("d:/code/GAF/debug", "", "")
        'd:/code/GAF/debug/20260728/unnamed/153000'
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
    extra: dict[str, Any] | None = None,
) -> None:
    """Write ``meta.json`` to the per-execution debug directory.

    视角 B (用户调试) 核心: 用户打开目录第一眼就能确认"这是不是我要找的那次执行",
    不用翻日志. 包含 execution_id / task_id / task_name / start_time / status /
    device_info / agent_id, 都是用户在前端能看到的概念.

    Idempotent: 每次调用都覆盖原 ``meta.json`` (用于 status 更新: running → completed).
    Failures are best-effort — meta.json 写失败不阻塞 pipeline.

    Args:
        exec_debug_dir: Per-execution directory (created if missing).
        execution_id: Execution identifier.
        task_id: Task ID (backend TaskExecution.pk or task.pk).
        task_name: Task name (user-visible).
        pipeline_name: Pipeline name from metadata.pipeline_name (may differ
            from task_name when same task runs different pipelines).
        start_time: Execution start time. None → use current UTC time.
        status: Execution status (``"running"`` / ``"completed"`` /
            ``"failed"`` / ``"cancelled"``).
        device_info: Device metadata dict (device_id / device_type / window_title /
            adb_serial). None → omitted from meta.json.
        agent_id: Agent identifier.
        extra: Optional extra fields merged into meta.json (e.g. end_time /
            elapsed_ms / error_msg when status != "running").
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

    嵌套结构 (2026-07-29): 两层扫描
        1. listdir ``<debug_dir_root>`` 找日期目录 (``YYYYMMDD`` 格式)
        2. 对每个日期目录, listdir 找 pipeline 目录
        3. 对每个 pipeline 目录, listdir 找以 ``<suffix>`` 结尾的执行目录

    AI 调试时拿到 ``execution_id=exec-abc123456789a``, 取后 8 字符 ``a1b2c3d4``,
    两层扫描 ``debug/<date>/<pipeline>/*a1b2c3d4`` → 命中目录. 当多个目录匹配
    (极少见, 后 8 位碰撞) 时返回最新的 (按 mtime 排序).

    向后兼容: 也扫描旧扁平格式 ``<debug_dir_root>/YYYYMMDD_HHMMSS_*_<suffix>/``
    (历史目录未迁移, 仍需能查到).

    Args:
        debug_dir_root: Debug root directory.
        execution_id: Execution identifier (``"exec-<uuid12>"`` or backend pk).

    Returns:
        Absolute path to the per-execution directory, or None when not found.
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

    # --- 1. 扫描新嵌套格式: <root>/<YYYYMMDD>/<pipeline>/<HHMMSS_suffix>/ ---
    date_pattern = re.compile(r"^\d{8}$")  # 8 位纯数字日期
    exec_pattern = re.compile(r"^\d{6}_")  # 6 位时间 + _ + suffix
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

    # --- 2. 向后兼容: 扫描旧扁平格式 <root>/YYYYMMDD_HHMMSS_*_<suffix>/ ---
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
    # Return the most recently modified match (handles suffix collisions by
    # assuming the latest one is the active execution).
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[0][0]
