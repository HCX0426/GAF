"""Structured JSONL logger for pipeline node execution events.

Outputs one JSON object per line to ``<debug_dir>/structured/<execution_id>.jsonl``
for LLM diagnosis. Does NOT replace the existing ``logging.getLogger`` text
logs — those remain for human readability. This module adds a parallel
JSONL stream carrying structured fields (node_id, confidence,
screenshot_path, etc.) that are hard to extract from free-form text.

Why JSONL?
- Each line is a complete JSON object — LLM can parse line-by-line without
  loading the whole file.
- Easy to grep / filter by node_id or event type.
- Naturally append-only (consecutive appends don't break earlier entries).

Thread-safety: PipelineEngine wraps node execution in a worker thread via
``ThreadPoolExecutor`` (spec 阶段 2.2). All public methods here are
thread-safe via a per-file lock.

Schema (spec 阶段 3.1):
    {
      "timestamp": "2026-07-12T10:30:45.123Z",
      "execution_id": "exec-abc123",
      "node_id": "click_start_game",
      "node_type": "template_match",
      "step_index": 3,
      "event": "node.execute.complete",
      "success": true,
      "elapsed_ms": 450,
      "retry_count": 0,
      "confidence": 0.95,                          # optional
      "threshold": 0.8,                            # optional
      "match_location": {"x": 960, "y": 540},      # optional
      "roi_base": [100, 100, 800, 600],             # optional; base 坐标
      "screenshot_path": "debug/.../match_...png", # optional
      "error_msg": "",                             # empty when success
      "variables_snapshot": {...},                 # only when non-empty
      "auto_heal_attempts": []                     # list of method names
    }
"""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import logging
import os
import re
import threading
import uuid
from typing import Any

from core.constants import NodeType

logger = logging.getLogger(__name__)


# Module-level registry of StructuredLogger instances by file path so that
# multiple callers logging to the same execution_id share one file handle
# and one lock. Key: absolute path to JSONL file.
_INSTANCES: dict[str, StructuredLogger] = {}
_INSTANCES_LOCK = threading.Lock()


def new_execution_id() -> str:
    """Generate a fresh execution_id for one Pipeline.execute() call.

    Returns:
        ``exec-<uuid4_hex_12chars>`` — short enough for filenames, unique
        enough to avoid collisions across concurrent pipeline runs.
    """
    return f"exec-{uuid.uuid4().hex[:12]}"


# N192 A6 P3: 字符串字段统一截断上限. 防止大堆栈 / 长 OCR 结果 / 大 detections
# 列表的 str 表示撑爆 JSONL 单行, 导致 LLM 诊断时上下文超限或 jq 解析慢.
# 2000 字符约等于 500-700 中文字符 / 2000 英文字符, 足够定位绝大多数错误.
MAX_STR_FIELD_LEN = 2000


def _truncate_str(s: Any, max_len: int = MAX_STR_FIELD_LEN) -> str:
    """截断字符串字段到 max_len, 超长时返回 prefix + _truncated 标记.

    N192 A6 P3: error_msg / comment / rationale 等字符串字段统一截断.
    超长时返回 ``原字符串[:max_len] + "..._truncated:original_len=N"``,
    让 AI 知道字段被截断且原始长度, 必要时可去 result_data 或日志其他
    字段补全上下文.

    Args:
        s: 待截断的值. 非字符串会先 str() 归一 (None → "").
        max_len: 最大保留长度 (含截断标记). 默认 MAX_STR_FIELD_LEN.

    Returns:
        截断后的字符串. 原长度 ≤ max_len 时原样返回 (str 归一后).
    """
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    if len(s) <= max_len:
        return s
    # 预留截断标记的空间 (约 40 字符), 避免最终长度远超 max_len.
    prefix_len = max(0, max_len - 40)
    return f"{s[:prefix_len]}..._truncated:original_len={len(s)}"


def _is_unified_exec_dir(debug_dir: str) -> bool:
    """N194 归一化 (2026-07-28): detect if ``debug_dir`` is a complete
    per-execution directory (e.g. ``d:/code/GAF/debug/20260728_103045_get_email_a1b2c3d4``)
    vs a legacy root (``./debug``).

    Thin wrapper around ``utils.debug_path._is_unified_exec_dir`` so callers
    in structured_logger don't need a second import. See that function for
    the detection rationale.
    """
    # Local import to avoid circular dependency at module load time.
    from utils.debug_path import _is_unified_exec_dir as _impl
    return _impl(debug_dir)


def _resolve_mirror_path(main_path: str) -> str | None:
    """Compute the agent-local mirror path for dual-write (N194 双写).

    Mirror layout (嵌套结构, 2026-07-29):
        ``<agent_cwd>/debug/<YYYYMMDD>/<safe_task_name>/<HHMMSS_suffix>/structured.jsonl``
    — 保留归一化目录的三层嵌套结构, 让 agent 本地镜像与归一化目录布局一致,
      用户在 worker/debug/ 下浏览也能按日期→pipeline 分组.

    旧扁平格式兼容: ``<agent_cwd>/debug/<exec_dir_basename>/structured.jsonl``.

    Returns None when mirroring isn't applicable (main_path is not in a
    unified exec dir, or cwd cannot be determined).
    """
    try:
        exec_dir = os.path.dirname(main_path)
        base = os.path.basename(os.path.normpath(exec_dir))
        if not _is_unified_exec_dir(exec_dir):
            return None
        agent_cwd = os.getcwd()
        # 嵌套结构: basename = HHMMSS_<suffix>, 需要取 date/pipeline/HHMMSS_suffix 三层
        # 旧扁平: basename = YYYYMMDD_HHMMSS_<name>_<suffix>, 只用 basename 一层
        if re.match(r"^\d{6}_", base):
            # 嵌套: parent = pipeline_dir, grandparent = date_dir
            pipeline_dir = os.path.dirname(exec_dir)
            date_dir = os.path.dirname(pipeline_dir)
            rel_path = os.path.join(
                os.path.basename(date_dir),
                os.path.basename(pipeline_dir),
                base,
            )
        else:
            # 旧扁平格式: 只用 basename
            rel_path = base
        mirror_dir = os.path.join(agent_cwd, "debug", rel_path)
        return os.path.join(mirror_dir, "structured.jsonl")
    except OSError:
        return None


def _now_local() -> datetime.datetime:
    """Local now (用于小时桶路径分桶)."""
    return datetime.datetime.now()


def _sanitize_path_segment(name: str) -> str:
    """Sanitize a path segment: replace non-alphanumeric chars with ``_``."""
    if not name:
        return "unknown"
    # Replace anything that's not letter/digit/dash/underscore/dot with _
    safe = re.sub(r"[^A-Za-z0-9_\-.]+", "_", name)
    # Collapse multiple underscores
    safe = re.sub(r"_+", "_", safe).strip("_.")
    return safe or "unknown"


def _resolve_hour_bucket_path(
    debug_dir: str, pipeline_name: str,
) -> str:
    """A1: 生成新结构路径 ``<debug_dir>/<YYYYMMDD>/agent/<pipeline>/HH/structured.jsonl``.

    按本地时区分桶 (与 screenshots 同源), 让日志按日期 + 小时归集,
    便于 AI 按时间窗口定位问题.

    Args:
        debug_dir: Debug 根目录 (e.g. ``./debug`` 或 backend 传入的 exec dir).
        pipeline_name: Pipeline 名称 (从 ``pipeline_json.metadata.pipeline_name``
            取). 空时用 ``"unknown"`` 兜底.

    Returns:
        Absolute path to JSONL file.
    """
    now = _now_local()
    date_part = now.strftime("%Y%m%d")
    hour_part = now.strftime("%H")
    safe_pipeline = _sanitize_path_segment(pipeline_name)
    return os.path.join(
        debug_dir, date_part, "agent", safe_pipeline, hour_part, "structured.jsonl",
    )


def get_logger(
    execution_id: str,
    debug_dir: str = "./debug",
    pipeline_name: str = "",
    trace_id: str = "",
) -> StructuredLogger:
    """Get (or create) the StructuredLogger for a given execution_id.

    A1 (spec 2026-07-30-debug-directory-restructure): 新增 ``pipeline_name``
    和 ``trace_id`` 参数. 当任一非空时走新结构路径
    ``<debug_dir>/<YYYYMMDD>/agent/<pipeline>/HH/structured.jsonl`` (小时桶),
    否则走 legacy 路径 (兼容现有测试 / CLI 模式).

    N194 归一化 + 双写 (2026-07-28):
    - When ``debug_dir`` is a complete exec dir (basename matches
      ``YYYYMMDD_HHMMSS_*``, as dispatched by backend), JSONL goes to
      ``<debug_dir>/structured.jsonl`` AND a mirror copy goes to
      ``<agent_cwd>/debug/<exec_dir_basename>/structured.jsonl``.
    - When ``debug_dir`` is a legacy root (e.g. ``./debug``, CLI mode or
      pre-N194 backend), JSONL goes to
      ``<debug_dir>/structured/<execution_id>.jsonl`` with no mirror.

    Args:
        execution_id: Execution identifier (from ``new_execution_id()``).
        debug_dir: Either a complete per-execution directory (N194 unified)
            or a debug root (legacy). Auto-detected via ``_is_unified_exec_dir``.
        pipeline_name: A1 新增. Pipeline 名称, 触发新结构路径 + JSONL 字段.
        trace_id: A1 新增. HTTP 请求级 trace_id, 注入每行 JSONL.

    Returns:
        A thread-safe StructuredLogger instance.
    """
    # A1: pipeline_name 或 trace_id 任一非空 → 走新结构路径 (小时桶)
    use_hour_bucket = bool(pipeline_name or trace_id)
    if use_hour_bucket and not _is_unified_exec_dir(debug_dir):
        file_path = _resolve_hour_bucket_path(debug_dir, pipeline_name)
    elif _is_unified_exec_dir(debug_dir):
        # N194 归一化: debug_dir 已经是 <root>/<exec_dir>/
        file_path = os.path.join(debug_dir, "structured.jsonl")
    else:
        # Legacy root: <debug_dir>/structured/<execution_id>.jsonl
        file_path = os.path.join(debug_dir, "structured", f"{execution_id}.jsonl")
    abs_path = os.path.abspath(file_path)
    mirror_path = _resolve_mirror_path(abs_path)

    with _INSTANCES_LOCK:
        instance = _INSTANCES.get(abs_path)
        if instance is None:
            instance = StructuredLogger(
                abs_path,
                execution_id=execution_id,
                mirror_path=mirror_path,
                pipeline_name=pipeline_name,
                trace_id=trace_id,
                # A1: 传 debug_dir 作为 debug_dir_root, 让 _maybe_rotate_for_hour
                # 在小时切换时能重新解析路径. 仅 hour_bucket 模式需要.
                debug_dir_root=debug_dir if use_hour_bucket else "",
            )
            _INSTANCES[abs_path] = instance
        return instance


class StructuredLogger:
    """Thread-safe JSONL logger for one execution.

    Do not instantiate directly — use ``get_logger(execution_id, debug_dir)``
    so concurrent writes to the same file share one lock.

    All write failures are best-effort: a warning is emitted via the
    regular ``logging`` module, but no exception is raised. The pipeline
    must never be blocked by debug-log write failures.
    """

    def __init__(
        self,
        file_path: str,
        execution_id: str,
        mirror_path: str | None = None,
        pipeline_name: str = "",
        trace_id: str = "",
        debug_dir_root: str = "",
    ) -> None:
        """Initialize the logger.

        Args:
            file_path: Absolute path to the JSONL file (unified dir).
            execution_id: Execution identifier (used in each log line).
            mirror_path: N194 双写. Absolute path to the agent-local mirror
                JSONL file, or None for legacy mode (no mirror). When set,
                every write goes to both ``file_path`` and ``mirror_path``.
                Mirror failures are best-effort (warning only).
            pipeline_name: A1 新增. Pipeline 名称, 注入每行 JSONL payload.
            trace_id: A1 新增. HTTP 请求级 trace_id, 注入每行 JSONL payload.
            debug_dir_root: A1 新增. Debug 根目录, 用于小时切换时重新解析
                路径. 空时表示不启用小时切换检查 (legacy 模式).
        """
        self._file_path = file_path
        self._execution_id = execution_id
        self._mirror_path = mirror_path
        self._pipeline_name = pipeline_name or ""
        self._trace_id = trace_id or ""
        self._debug_dir_root = debug_dir_root or ""
        self._current_hour = _now_local().strftime("%H")
        self._lock = threading.Lock()
        self._closed = False
        # 缓存的文件句柄 (P0 优化 2026-08-02: 避免每次写入 open/close)
        self._file: io.TextIOWrapper | None = None
        # Pre-create the directory. makedirs failures are non-fatal — the
        # first log_node_event call will simply emit a warning.
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
        except OSError as exc:
            logger.warning(
                "structured_logger: makedirs failed for %s: %s",
                os.path.dirname(file_path), exc,
            )
        # 预打开文件句柄 (P0 优化)
        try:
            self._file = open(file_path, "a", encoding="utf-8")  # noqa: SIM115 - cached handle in self._file, closed in close()
        except OSError as exc:
            logger.warning(
                "structured_logger: open failed for %s: %s", file_path, exc,
            )
        # N194 双写: also pre-create mirror dir so first write doesn't fail.
        if mirror_path:
            try:
                os.makedirs(os.path.dirname(mirror_path), exist_ok=True)
            except OSError as exc:
                logger.warning(
                    "structured_logger: mirror makedirs failed for %s: %s",
                    os.path.dirname(mirror_path), exc,
                )
                # Disable mirror on dir creation failure to avoid repeated warnings.
                self._mirror_path = None

    def _maybe_rotate_for_hour(self) -> None:
        """A1: 检查当前小时, 若与打开文件的小时不一致则重新解析路径.

        小时切换后, 旧文件不再追加, 新事件写到新小时桶的文件中.
        仅在 ``_debug_dir_root`` 和 ``_pipeline_name`` 都非空时启用
        (即 A1 新结构模式). legacy 模式跳过.
        """
        if not self._debug_dir_root or not self._pipeline_name:
            return
        new_hour = _now_local().strftime("%H")
        if new_hour == self._current_hour:
            return
        # 小时切换: 重新解析路径, 更新 _file_path, 让后续写入落到新文件.
        new_path = _resolve_hour_bucket_path(self._debug_dir_root, self._pipeline_name)
        new_abs = os.path.abspath(new_path)
        if new_abs == self._file_path:
            # 同一路径 (理论上不会发生, 但兜底)
            return
        try:
            os.makedirs(os.path.dirname(new_abs), exist_ok=True)
        except OSError as exc:
            logger.warning(
                "structured_logger: hour rotation makedirs failed for %s: %s",
                os.path.dirname(new_abs), exc,
            )
            return
        # 关闭旧文件句柄 (P0 优化 2026-08-02: 保持 handle 打开避免 open/close)
        if self._file is not None:
            with contextlib.suppress(OSError):
                self._file.close()
            self._file = None
        # 更新实例注册表: 旧路径移除, 新路径注册
        with _INSTANCES_LOCK:
            _INSTANCES.pop(self._file_path, None)
            _INSTANCES[new_abs] = self
        self._file_path = new_abs
        self._current_hour = new_hour
        # mirror_path 是按旧 file_path 计算的, 小时切换后不再有效,
        # 禁用 mirror 避免写到旧镜像目录.
        self._mirror_path = None

    @property
    def file_path(self) -> str:
        """Absolute path to the JSONL file."""
        return self._file_path

    @property
    def execution_id(self) -> str:
        """Execution identifier."""
        return self._execution_id

    def _write_line(self, line: str, *, event_hint: str = "") -> None:
        """Append one line to the JSONL file (and mirror if configured).

        N194 双写 (2026-07-28): 主写归一化目录, 镜像写 agent 本地目录.
        Mirror failures are best-effort — main write success is what matters.

        A1 (2026-07-30): 每次写入前检查小时切换, 切换后写到新小时桶.

        P0 优化 (2026-08-02): 使用缓存的文件句柄, 避免每次 open/close.
        __init__ 时预打开句柄, 小时切换时关闭旧句柄重新打开. 句柄失效
        (如文件被删除/权限变更) 时降级为 open/close 模式, 下次再试.

        Args:
            line: Pre-formatted JSON line (already ends with ``\\n``).
            event_hint: Event name for warning context (e.g. ``"node"`` /
                ``"orchestrator"`` / ``"coord_trace"``).
        """
        # A1: 小时切换检查 (仅在新结构模式下生效)
        self._maybe_rotate_for_hour()
        with self._lock:
            try:
                # P0 优化: 使用缓存句柄, 失效时重新打开
                if self._file is None:
                    self._file = open(self._file_path, "a", encoding="utf-8")  # noqa: SIM115 - cached handle in self._file, closed in close()
                self._file.write(line)
                self._file.flush()
            except OSError as exc:
                # 句柄失效: 关闭并清空, 下次写入重新打开
                if self._file is not None:
                    with contextlib.suppress(OSError):
                        self._file.close()
                    self._file = None
                logger.warning(
                    "structured_logger: %s write failed for %s: %s",
                    event_hint or "event", self._file_path, exc,
                )
                # Main write failed — skip mirror, nothing to mirror.
                return

        if not self._mirror_path:
            return
        try:
            with self._lock, open(self._mirror_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError as exc:
            logger.warning(
                "structured_logger: %s mirror write failed for %s: %s",
                event_hint or "event", self._mirror_path, exc,
            )
            # Disable mirror after first failure to avoid log spam on every event.
            self._mirror_path = None

    def _inject_trace_fields(self, payload: dict[str, Any]) -> None:
        """A1: 注入 trace_id 和 pipeline_name 字段到 payload (非空时).

        Args:
            payload: 待写入的 JSON payload (会被原地修改).
        """
        if self._trace_id:
            payload["trace_id"] = self._trace_id
        if self._pipeline_name:
            payload["pipeline_name"] = self._pipeline_name

    def log_node_event(
        self,
        *,
        event: str,
        node_id: str,
        node_type: str,
        step_index: int,
        success: bool,
        elapsed_ms: float = 0.0,
        retry_count: int = 0,
        confidence: float | None = None,
        threshold: float | None = None,
        match_location: dict[str, int] | None = None,
        roi_base: list[int] | None = None,
        screenshot_path: str | None = None,
        raw_screenshot_path: str | None = None,
        error_msg: str = "",
        error_code: str = "",
        variables_snapshot: dict[str, Any] | None = None,
        auto_heal_attempts: list[str] | None = None,
        comment: str = "",
        rationale: str = "",
        coord_system: str = "",
        device_type: str = "",
        transformer_id: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Append one structured event line to the JSONL file.

        Args:
            event: Event name (e.g. ``"node.execute.complete"``,
                ``"node.execute.timeout"``, ``"node.execute.exception"``).
            node_id: Pipeline node ID.
            node_type: Pipeline node type (``template_match`` / ``click`` ...).
            step_index: Step index in the pipeline (iteration counter).
            success: Whether the node succeeded.
            elapsed_ms: Elapsed milliseconds for this node's execution.
            retry_count: How many retries were attempted.
            confidence: Match confidence (template_match only).
            threshold: Match threshold (template_match only).
            match_location: Match center as ``{"x": int, "y": int}``.
            roi_base: ROI as ``[x, y, w, h]`` in base (reference) coordinates.
            screenshot_path: Path to debug screenshot (when debug_mode).
            raw_screenshot_path: Path to raw JPEG screenshot (spec §6.5).
                Set only for recognition nodes (template_match/ocr/etc.).
                None for action nodes.
            error_msg: Error message (empty string on success).
            error_code: Node error code (spec 阶段 5 — 任务 1.8). Accepts
                ``NodeErrorCode`` enum (StrEnum) or plain string. Empty
                string on success; omitted from JSONL when empty so the
                file stays compact. Lets AI classify failures without
                parsing error_msg.
            variables_snapshot: Snapshot of context variables (only
                non-empty ones are written).
            auto_heal_attempts: List of auto-heal methods tried.
            comment: Node human-readable comment (spec 阶段 4.3) — describes
                what this node does. Included in JSONL so LLM diagnosis can
                understand node intent without reading the pipeline JSON.
            rationale: Node design rationale (spec 阶段 4.3) — describes why
                the node was designed this way.
            coord_system: N191 §10.7 P1-1 (架构层归一化, 2026-07-27). 当前
                pipeline 流转的坐标系标签 (``"logical"`` / ``"physical"`` /
                ``""`` legacy). 取自 ``PipelineContext.coord_system``, 让
                AI 分析 JSONL 时能判断 ``match_location`` / ``roi_base``
                / ``variables_snapshot._last_match_pos`` 等坐标字段的语义,
                避免 logical / physical 混淆导致的诊断错误。空字符串时
                省略字段 (legacy 兼容, JSONL 紧凑)。
            device_type: N191 §10.10 决策点 6 (AI 可调试性, 2026-07-27).
                设备类型标签 (``"windows"`` / ``"adb"`` / ``""``)。
                AI 跨设备对比时按此字段分组, 保证 Windows/ADB 两份
                log_node_event 字段集一致 (D3 跨设备对比能力)。
            transformer_id: N191 §10.10 决策点 6. transformer 实例标识,
                如 ``"win_1920x1080_dpi2.0"``。AI 按此分组对比同一
                transformer 的所有节点事件。空字符串时省略字段。
            extra: Optional extra fields to merge into the JSON object.

        Writes are best-effort: failures emit a warning via the regular
        logger but never raise.
        """
        if self._closed:
            return

        # Build the JSON payload. Optional fields are omitted when None so
        # the JSONL stays compact — LLM context budget matters.
        # N192 A6 P3: 字符串字段 (error_msg / comment / rationale) 统一截断
        # 到 MAX_STR_FIELD_LEN, 防止大堆栈撑爆 JSONL 单行.
        # N193 Task 5.1: node.execute.start 事件省略 success / error_msg /
        # error_code 字段 — start 事件语义是"节点开始执行", 尚无成功/失败
        # 概念, 写 success=True 会让 AI 误判为"成功完成". 这些字段是
        # complete 事件专属.
        is_start_event = event == "node.execute.start"
        payload: dict[str, Any] = {
            "timestamp": _utc_iso_now(),
            "execution_id": self._execution_id,
            "node_id": node_id,
            "node_type": node_type,
            "step_index": step_index,
            "event": event,
            "elapsed_ms": round(float(elapsed_ms), 2),
            "retry_count": int(retry_count),
        }
        # A1: 注入 trace_id 和 pipeline_name (非空时)
        self._inject_trace_fields(payload)
        if not is_start_event:
            payload["success"] = bool(success)
            payload["error_msg"] = _truncate_str(error_msg or "")
            # Normalize error_code: StrEnum → str, empty → omit.
            # NodeErrorCode.SCREEN_UNCHANGED.value == "SCREEN_UNCHANGED", and
            # str(NodeErrorCode.SCREEN_UNCHANGED) also == "SCREEN_UNCHANGED"
            # (StrEnum behavior), so str() is a safe normalizer for both
            # plain strings and enum values.
            normalized_error_code = str(error_code) if error_code else ""
            if normalized_error_code:
                payload["error_code"] = normalized_error_code
        if confidence is not None:
            payload["confidence"] = round(float(confidence), 4)
        if threshold is not None:
            payload["threshold"] = float(threshold)
        if match_location is not None:
            payload["match_location"] = dict(match_location)
        if roi_base is not None:
            payload["roi_base"] = list(roi_base)
        if screenshot_path:
            payload["screenshot_path"] = screenshot_path
        if raw_screenshot_path:
            payload["raw_screenshot_path"] = raw_screenshot_path
        if comment:
            payload["comment"] = _truncate_str(comment)
        if rationale:
            payload["rationale"] = _truncate_str(rationale)
        # N191 §10.7 P1-1: coord_system 仅在非空时写入, 让 AI 分析 JSONL
        # 时能判断坐标字段语义 (logical / physical)。空字符串 = legacy
        # 模式 (orchestrator 未注入 transformer), 省略保持 JSONL 紧凑。
        if coord_system:
            payload["coord_system"] = coord_system
        # N191 §10.10 决策点 6 (AI 可调试性, 2026-07-27):
        # device_type + transformer_id 强制写入 (空字符串也写, 保证
        # Windows/ADB 字段集一致), AI 跨设备对比时按此分组。空字符串
        # 表示 legacy 模式或未注入 transformer, 仍写字段让 AI 能识别。
        payload["device_type"] = device_type or ""
        if transformer_id:
            payload["transformer_id"] = transformer_id
        if variables_snapshot:
            # Only snapshot small, JSON-serializable variables. The caller
            # is responsible for filtering out large/binary values.
            try:
                json.dumps(variables_snapshot, default=str, ensure_ascii=False)
                payload["variables_snapshot"] = variables_snapshot
            except (TypeError, ValueError):
                payload["variables_snapshot"] = "<non-serializable>"
        if auto_heal_attempts:
            payload["auto_heal_attempts"] = list(auto_heal_attempts)
        if extra:
            payload.update(extra)

        line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"

        self._write_line(line, event_hint="node")

    def close(self) -> None:
        """Mark this logger as closed. Future log_node_event calls are no-ops.

        P0 优化 (2026-08-02): 关闭缓存的文件句柄, 确保所有数据写入磁盘.
        __init__ 时预打开句柄, 在 close() 中关闭.
        """
        with _INSTANCES_LOCK:
            self._closed = True
            _INSTANCES.pop(os.path.abspath(self._file_path), None)
        # P0 优化: 关闭缓存的文件句柄
        if self._file is not None:
            with contextlib.suppress(OSError):
                self._file.close()
            self._file = None

    # ------------------------------------------------------------------
    # P0-4 fix (AI 可调试性, 2026-07-27): orchestrator-level trace events.
    # 之前 orchestrator 的 task 状态机转换 (start/complete/failed/cancel/
    # pause/resume) 只写 logger.info 文本日志, 不入 JSONL。AI 调试时无法
    # 从结构化日志反推任务级决策 (何时取消/为何失败/暂停多久), 只能看节点
    # 级事件。本方法补 orchestrator 级 trace, 与 node 事件同文件同 execution_id,
    # AI 用 jq 'select(.event|startswith("orchestrator."))' 即可过滤。
    # ------------------------------------------------------------------
    def log_orchestrator_event(
        self,
        *,
        event: str,
        task_state: str = "",
        success: bool | None = None,
        elapsed_ms: float = 0.0,
        device_id: str = "",
        pipeline_name: str = "",
        error_msg: str = "",
        error_code: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Append one orchestrator-level trace event to the JSONL file.

        与 ``log_node_event`` 平行, 但用于任务级状态机转换 (非节点级)。
        ``node_id`` 固定为 ``"_orchestrator"``, ``node_type`` 固定为
        ``"orchestrator"``, ``step_index`` 固定为 ``-1`` (区分于真实节点)。

        Args:
            event: 事件名, 取值:
                ``"orchestrator.task.start"`` /
                ``"orchestrator.task.complete"`` /
                ``"orchestrator.task.failed"`` /
                ``"orchestrator.task.cancelled"`` /
                ``"orchestrator.task.paused"`` /
                ``"orchestrator.task.resumed"`` /
                ``"orchestrator.coord_transformer.error"`` /
                ``"orchestrator.llm_diagnosis.attached"`` 等。
            task_state: TaskState 值 (``"running"`` / ``"completed"`` /
                ``"failed"`` / ``"cancelled"`` / ``"paused"``)。
            success: 任务是否成功 (None 表示中间状态如 paused/resumed)。
            elapsed_ms: 任务总耗时 (start→end)。
            device_id: 目标设备 ID。
            pipeline_name: pipeline 名称 (来自 metadata.pipeline_name)。
            error_msg: 失败时的错误消息。
            error_code: 失败时的错误码 (NodeErrorCode 或字符串)。
            extra: 额外字段 (如 cancel_reason / pause_reason /
                coord_transformer_root_cause 等)。
        """
        if self._closed:
            return

        payload: dict[str, Any] = {
            "timestamp": _utc_iso_now(),
            "execution_id": self._execution_id,
            "node_id": "_orchestrator",
            "node_type": "orchestrator",
            "step_index": -1,
            "event": event,
        }
        # A1: 注入 trace_id (pipeline_name 已在下方按参数处理)
        if self._trace_id:
            payload["trace_id"] = self._trace_id
        if success is not None:
            payload["success"] = bool(success)
        if task_state:
            payload["task_state"] = task_state
        if elapsed_ms:
            payload["elapsed_ms"] = round(float(elapsed_ms), 2)
        if device_id:
            payload["device_id"] = device_id
        if pipeline_name:
            payload["pipeline_name"] = pipeline_name
        if error_msg:
            # N192 A6 P3: orchestrator 级 error_msg 也截断, 与 node 级一致.
            payload["error_msg"] = _truncate_str(error_msg)
        normalized_error_code = str(error_code) if error_code else ""
        if normalized_error_code:
            payload["error_code"] = normalized_error_code
        if extra:
            payload.update(extra)

        line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"

        self._write_line(line, event_hint="orchestrator")

    # ------------------------------------------------------------------
    # N191 §10.10 决策点 5 (AI 可调试性基础设施, 2026-07-27):
    # CoordTraceEvent — 统一的坐标转换 trace 日志。每次 publish_match_pos
    # / resolve_target / device.click / sub_image_to_full / template_scale
    # 等坐标转换发生时, 都调本方法记一行 trace。AI 调试时:
    #   grep "coord_transform" run.log | jq 'select(.node_id=="ocr_1")'
    # 即可看到该节点所有坐标转换的完整链路 (raw → formula → converted)。
    #
    # 4 条 AI 可调试性总原则之 1: 转换必观测。
    # 4 条 AI 可调试性总原则之 4: bug 现场可重建 (不重跑就能算点击位置)。
    # ------------------------------------------------------------------
    def emit_coord_trace(
        self,
        *,
        node_id: str,
        step: str,
        device_type: str,
        raw: dict[str, Any] | tuple[int, int] | list[int] | None,
        converted: dict[str, Any] | tuple[int, int] | list[int] | None,
        formula: str,
        transformer_id: str = "",
        coord_system_in: str = "",
        coord_system_out: str = "",
        task_id: str = "",
        trace_id: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Append one coord_transform trace event to the JSONL file.

        AI 调试黄金标准 §1 (N191 §10.10): 每次坐标转换必记 trace。

        Args:
            node_id: 节点 ID (与 log_node_event 的 node_id 一致, AI 可关联)。
            step: 转换发生的位置, 取值:
                ``"publish_match_pos"`` / ``"resolve_target"`` /
                ``"device_click"`` / ``"device_swipe"`` /
                ``"roi_crop"`` / ``"template_scale"`` /
                ``"sub_image_to_full"`` / ``"base_to_physical"`` 等。
            device_type: ``"windows"`` / ``"adb"`` / ``""`` (未知/通用)。
                AI 跨设备对比时按此字段分组 (D3 跨设备对比能力)。
            raw: 转换前坐标。dict 形式 ``{"x": 1920, "y": 1080}`` 或
                tuple/list ``[1920, 1080]``。None 表示无原始值 (如 publish
                首次写入)。
            converted: 转换后坐标。同 raw 格式。
            formula: 转换公式描述, 如 ``"logical = physical / dpi_scale(2.0)"``
                或 ``"full = sub_image + roi_offset(100, 50)"``。AI 反推链路
                时按此字段判断转换类型 (D6 AI 反推能力)。
            transformer_id: transformer 实例标识, 如
                ``"win_1920x1080_dpi2.0"`` / ``"adb_1920x1080_to_2560x1440"``。
                AI 可按此分组对比同一 transformer 的所有转换。
            coord_system_in: 输入坐标系标签 (``"physical"`` / ``"logical"``
                / ``"base"`` / ``"sub_image"``)。空字符串表示未标记。
            coord_system_out: 输出坐标系标签, 同上。
            task_id: 任务 ID (可选, 用于跨任务关联)。
            trace_id: 执行 trace ID (可选, 等同 execution_id)。
            extra: 额外字段 (如 roi_offset / dpi_scale 数值)。

        Writes are best-effort: 失败时仅 warning, 不阻塞 pipeline。
        """
        if self._closed:
            return

        payload: dict[str, Any] = {
            "timestamp": _utc_iso_now(),
            "execution_id": self._execution_id,
            "event": "coord_transform",
            "node_id": node_id,
            "step": step,
            "device_type": device_type or "",
            "raw": _normalize_coord_value(raw),
            "converted": _normalize_coord_value(converted),
            "formula": formula,
        }
        if transformer_id:
            payload["transformer_id"] = transformer_id
        if coord_system_in:
            payload["coord_system_in"] = coord_system_in
        if coord_system_out:
            payload["coord_system_out"] = coord_system_out
        if task_id:
            payload["task_id"] = task_id
        if trace_id:
            payload["trace_id"] = trace_id
        if extra:
            payload.update(extra)

        line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"

        self._write_line(line, event_hint="coord_trace")


def _normalize_coord_value(
    value: dict[str, Any] | tuple[int, int] | list[int] | None,
) -> dict[str, Any] | None:
    """Normalize a coordinate value to a JSON-serializable dict.

    - None → None (kept out of payload for compactness)
    - dict → returned as-is (assumed already has x/y or similar keys)
    - tuple/list of 2 ints → ``{"x": int, "y": int}``
    - tuple/list of 4 ints → ``{"x": int, "y": int, "w": int, "h": int}``
      (for ROI / box values)
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (list, tuple)):
        try:
            ints = [int(v) for v in value]
        except (TypeError, ValueError):
            return {"raw": list(value)}
        if len(ints) == 2:
            return {"x": ints[0], "y": ints[1]}
        if len(ints) == 4:
            return {"x": ints[0], "y": ints[1], "w": ints[2], "h": ints[3]}
        return {"raw": ints}
    # Scalar or other — wrap for traceability.
    return {"value": value}


def extract_result_fields(
    node_type: str,
    result_data: Any,
    node_config: dict[str, Any],
) -> dict[str, Any]:
    """Extract structured-loggable fields from a node's AutoResult.data.

    Centralizes the field-extraction logic so engine.py doesn't need to
    know the schema of every node type. Returns only fields that are
    present in ``result_data`` — absent fields are omitted from the
    returned dict.

    Args:
        node_type: Node type string (``template_match`` / ``click`` ...).
        result_data: The ``AutoResult.data`` dict (may be None).
        node_config: The node's config dict (for threshold / ROI).

    Returns:
        Dict with any of: ``confidence``, ``threshold``, ``match_location``,
        ``roi_base``, ``screenshot_path``, ``auto_heal_attempts``.
    """
    out: dict[str, Any] = {}
    if not isinstance(result_data, dict):
        return out

    # screenshot_path is set by all nodes when debug_mode saves a screenshot
    sp = result_data.get("screenshot_path")
    if isinstance(sp, str) and sp:
        out["screenshot_path"] = sp

    # raw_screenshot_path is set by recognition nodes (template_match/ocr/
    # feature_match/color_detect) when debug_mode saves the original JPEG
    # alongside the annotated PNG (spec §6.5).
    rsp = result_data.get("raw_screenshot_path")
    if isinstance(rsp, str) and rsp:
        out["raw_screenshot_path"] = rsp

    # auto_heal_method is set by template_match._auto_heal_and_retry
    ah = result_data.get("auto_heal_method")
    if isinstance(ah, str) and ah:
        out["auto_heal_attempts"] = [ah]

    if node_type == NodeType.TEMPLATE_MATCH:
        conf = result_data.get("confidence")
        if isinstance(conf, (int, float)):
            out["confidence"] = float(conf)
        thr = node_config.get("threshold")
        if isinstance(thr, (int, float)):
            out["threshold"] = float(thr)
        # match_location: prefer explicit "match_loc", fall back to "x"/"y"
        loc = result_data.get("match_loc")
        if isinstance(loc, dict) and "x" in loc and "y" in loc:
            out["match_location"] = {"x": int(loc["x"]), "y": int(loc["y"])}
        elif "x" in result_data and "y" in result_data:
            with contextlib.suppress(TypeError, ValueError):
                out["match_location"] = {
                    "x": int(result_data["x"]),
                    "y": int(result_data["y"]),
                }
        # roi_base: from node_config["roi"] (x, y, w, h) — 原始 base 坐标.
        # 字段名含 "base" 而非 "physical" 避免误导 (N196, 2026-08-01).
        # 实际物理 ROI 需经 coord_transformer 转换, 记录在 coord_transform 事件中.
        roi = node_config.get("roi")
        if isinstance(roi, (list, tuple)) and len(roi) == 4:
            out["roi_base"] = [int(v) for v in roi]
    elif node_type == "click":
        # click 节点坐标（spec 阶段 3.1.1）——之前完全丢失，导致 AI 无法
        # 诊断"点错位置"。这里把 x/y 转成 match_location 复用既有字段，
        # 同时保留 click_input (x_in/y_in) 记录原始输入坐标（变换前）。
        cx = result_data.get("x")
        cy = result_data.get("y")
        if isinstance(cx, (int, float)) and isinstance(cy, (int, float)):
            out["match_location"] = {"x": int(cx), "y": int(cy)}
        # 点击参数原样保留
        for key in ("button", "clicks", "interval", "coord_type", "normalization_applied"):
            val = result_data.get(key)
            if val is not None:
                out[key] = val
        # 原始输入坐标（与最终 match_location 不同时记录，便于排查坐标变换问题）
        x_in = result_data.get("x_in")
        y_in = result_data.get("y_in")
        if isinstance(x_in, (int, float)) and isinstance(y_in, (int, float)):
            out["click_input"] = {"x": int(x_in), "y": int(y_in)}
        # 竞态防护结果（spec 阶段 4.2 — wait_for_change_lightweight 产出）
        if "expect_screen_change" in result_data:
            out["expect_screen_change"] = result_data["expect_screen_change"]
        if "screen_change_outcome" in result_data:
            out["screen_change_outcome"] = result_data["screen_change_outcome"]
    elif node_type == "ocr":
        # OCR 文本入 JSONL（spec 阶段 3.1.2 + AI 诊断盲区修复）
        # —— 之前 OCR 结果完全不入日志，AI 无法看到识别内容。
        texts = result_data.get("texts", [])
        if texts:
            # 前 10 条，每条截断 200 字符防止 JSONL 膨胀
            out["texts"] = [str(t)[:200] for t in texts[:10]]
            out["text_count"] = len(texts)
        confidences = result_data.get("confidences", [])
        if confidences:
            out["confidences_top10"] = [round(float(c), 4) for c in confidences[:10]]
        boxes = result_data.get("boxes", [])
        if boxes:
            out["boxes_top10"] = [[int(v) for v in b[:4]] for b in boxes[:10]]
        # expected_text 用于失败诊断（OCR 没识别到预期文字的场景）
        expected = result_data.get("expected_text")
        if expected:
            out["expected_text"] = str(expected)[:200]
    elif node_type == "wait":
        # wait 节点模式与超时（spec 阶段 3.1.3）
        for key in ("mode", "max_wait"):
            val = result_data.get(key)
            if val is not None:
                out[key] = val
        # 检查历史最近 3 条（精简快照，便于 AI 判断等待过程）
        check_history = result_data.get("check_history", [])
        if check_history:
            out["check_history"] = [
                {
                    "check_index": h.get("check_index"),
                    "elapsed_s": round(h.get("elapsed_s", 0), 3),
                    "confidence": round(h.get("confidence", 0), 4) if h.get("confidence") else None,
                    "screenshot": h.get("screenshot"),
                }
                for h in check_history[-3:]
            ]
    elif node_type == "swipe_until":
        # swipe_until 节点尝试次数（spec 阶段 3.1.4）
        for key in ("attempts", "swipes_performed"):
            val = result_data.get(key)
            if val is not None:
                out[key] = val

    return out


def _utc_iso_now() -> str:
    """Return current UTC time as ISO 8601 string with millisecond precision.

    Format: ``2026-07-12T10:30:45.123Z`` (trailing Z, dots between date/time).
    """
    now = datetime.datetime.now(datetime.UTC)
    # isoformat() gives "2026-07-12T10:30:45.123456+00:00"
    # Truncate microseconds to milliseconds and replace +00:00 with Z.
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
