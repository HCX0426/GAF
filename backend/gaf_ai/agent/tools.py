"""Agent tools — LangChain @tool functions wrapping GAF backend data.

These tools let the ReAct agent query execution data on demand:
  - get_execution_detail: overview of one execution
  - get_execution_steps: step list with status/errors
  - search_similar_errors: search past errors via RAG + JSONL archives
  - get_task_config: task pipeline config

P2-3 (S5 Task A2): every @tool body is wrapped in a top-level
``try/except Exception`` that returns a JSON error string. This guarantees
an unexpected DB error, model attribute change, or RAG stack trace never
propagates into the ReAct loop — the agent always sees a tool result it
can reason about, even if that result is an error envelope.

spec §7.3.2 (阶段 4 — 任务 4.6, 2026-07-26 修正):
search_similar_errors SQL fallback replaced by JSONL log scan. The old
_sql_search_errors() (icontains on TaskExecution.error_message) violated
spec §2.2 数据库边界收敛. The new _search_similar_errors_via_jsonl()
queries TaskExecution.execution_snapshot['structured_log_path'] for
failed executions and reads the structured JSONL log at that path
(aligned with gaf_ai.views_anomaly._extract_patterns_from_jsonl data
flow), ranking matches by text_similarity (difflib.SequenceMatcher).
"""
import difflib
import json
import logging
import os
from collections.abc import Iterable

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def get_execution_detail(execution_id: int) -> str:
    """Get execution overview: task name, status, duration, start/end time, error.

    Args:
        execution_id: The TaskExecution ID to look up.

    Returns:
        JSON string with execution details, or error message.
    """
    try:
        from tasks.models import TaskExecution

        try:
            ex = TaskExecution.objects.select_related('task', 'agent').get(pk=execution_id)
        except TaskExecution.DoesNotExist:
            return f"Execution #{execution_id} not found."

        result = {
            'execution_id': ex.id,
            'task_name': ex.task.name if ex.task else 'Unknown',
            'status': ex.status,
            'started_at': ex.started_at.isoformat() if ex.started_at else None,
            'completed_at': ex.completed_at.isoformat() if ex.completed_at else None,
            'duration_seconds': ex.duration.total_seconds() if ex.duration else None,
            'agent': ex.agent.hostname if ex.agent else None,
            'last_error': ex.error_message or None,
            'recovery_attempts': ex.recovery_attempts,
            'recovery_layer': ex.recovery_layer,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.exception('get_execution_detail failed for execution_id=%s', execution_id)
        return json.dumps({
            'error': f'Tool execution failed: {exc}',
            'tool': 'get_execution_detail',
        }, ensure_ascii=False)


@tool
def get_execution_steps(execution_id: int) -> str:
    """Get execution step list with status, duration, errors, and retry count.

    Args:
        execution_id: The TaskExecution ID whose steps to retrieve.

    Returns:
        JSON string with step list, or error message.
    """
    try:
        from tasks.models import TaskStep

        steps = TaskStep.objects.filter(execution_id=execution_id).order_by('step_index')
        if not steps.exists():
            return f"Execution #{execution_id} has no steps."

        result = []
        for s in steps:
            result.append({
                'index': s.step_index,
                'name': s.step_name,
                'status': s.status,
                'duration_seconds': s.duration.total_seconds() if s.duration else None,
                'error': s.error_message or None,
                'retry_count': s.retry_count,
                'screenshot_path': s.screenshot_path or None,
            })
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.exception('get_execution_steps failed for execution_id=%s', execution_id)
        return json.dumps({
            'error': f'Tool execution failed: {exc}',
            'tool': 'get_execution_steps',
        }, ensure_ascii=False)


@tool
def search_similar_errors(error_text: str) -> str:
    """Search past execution errors similar to the given text.

    Uses RAG (ChromaDB vector search) as the primary retrieval path,
    falling back to JSONL log scan (spec §7.3.2 — 任务 4.6, 2026-07-26
    修正) when RAG is unavailable or returns no results. The JSONL
    fallback queries ``TaskExecution.execution_snapshot['structured_log_path']``
    for failed executions (default last 30 days) and reads the
    structured JSONL log at that path, ranking matches by
    text_similarity (difflib.SequenceMatcher, threshold > 0.5).

    RAG indexed documents (code files, QA history, technical docs) are
    returned with their filepath + content snippet. JSONL fallback
    returns matching execution records from structured logs.

    Args:
        error_text: The error text to search for (can be a partial match).

    Returns:
        JSON string with one of:
          - {"source": "rag", "matches": [{content, filepath, score}, ...]}
          - {"source": "jsonl_fallback", "matches": [{execution_id, error, similarity, ...}, ...]}
          - {"source": "none", "matches": [], "message": "..."}
    """
    try:
        if not error_text or len(error_text.strip()) < 3:
            return "Error text too short for search (min 3 chars)."

        # --- Primary path: RAG vector retrieval ---
        rag_matches = _rag_search_errors(error_text, top_k=10)
        if rag_matches:
            result = {
                'source': 'rag',
                'matches': rag_matches,
                'message': f'Found {len(rag_matches)} RAG matches.',
            }
            return json.dumps(result, ensure_ascii=False, indent=2)

        # --- Fallback path: JSONL archive scan (spec §7.3.2 — 任务 4.6) ---
        # Replaces the old SQL icontains fallback (violated spec §2.2
        # 数据库边界收敛). Scans archived structured.jsonl files and
        # ranks by text_similarity.
        jsonl_matches = _search_similar_errors_via_jsonl(error_text, top_k=10)
        if jsonl_matches:
            result = {
                'source': 'jsonl_fallback',
                'matches': jsonl_matches,
                'message': (
                    'RAG returned no matches; showing JSONL archive fallback '
                    '(text_similarity > 0.5).'
                ),
            }
            return json.dumps(result, ensure_ascii=False, indent=2)

        return json.dumps(
            {
                'source': 'none',
                'matches': [],
                'message': (
                    f"No similar errors found for '{error_text}' in RAG index "
                    f"or JSONL archives."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        logger.exception('search_similar_errors failed for error_text=%r', error_text)
        return json.dumps({
            'error': f'Tool execution failed: {exc}',
            'tool': 'search_similar_errors',
        }, ensure_ascii=False)


def _rag_search_errors(error_text: str, top_k: int = 10) -> list[dict]:
    """Query the RAG retriever for documents similar to error_text.

    Returns an empty list when ChromaDB is unavailable, the retriever
    fails, or no documents match — letting the caller fall back to SQL.
    Each match dict has: content, filepath, filename, type, score.
    """
    try:
        from gaf_ai.rag import get_rag_retriever

        retriever = get_rag_retriever()
        docs = retriever.search(error_text, top_k=top_k)
    except Exception as exc:  # RAG must never block the agent
        logger.warning('RAG search failed, falling back to SQL: %s', exc)
        return []

    matches = []
    for doc in docs:
        matches.append({
            'content': doc.get('content', '')[:500],
            'filepath': doc.get('filepath', ''),
            'filename': doc.get('filename', ''),
            'type': doc.get('type', ''),
            'score': doc.get('score', 0),
        })
    return matches


def _sql_search_errors(error_text: str, days: int = 30, limit: int = 10) -> list[dict]:
    """SQL icontains fallback on TaskExecution.error_message.

    .. deprecated:: spec §7.3.2 — 任务 4.6 (2026-07-26)
        Replaced by :func:`_search_similar_errors_via_jsonl`. Retained
        only for backward-compat imports / tests that may still call it
        directly. The ``search_similar_errors`` @tool no longer invokes
        this function — it violates spec §2.2 数据库边界收敛.
    """
    from datetime import timedelta

    from django.db.models import Q
    from django.utils import timezone

    from tasks.models import TaskExecution

    threshold = timezone.now() - timedelta(days=days)
    qs = TaskExecution.objects.filter(
        Q(error_message__icontains=error_text),
        created_at__gte=threshold,
    ).order_by('-created_at')[:limit]

    matches = []
    for ex in qs:
        matches.append({
            'execution_id': ex.id,
            'task_name': ex.task.name if ex.task else 'Unknown',
            'status': ex.status,
            'error': ex.error_message or '',
            'created_at': ex.created_at.isoformat(),
        })
    return matches


# ── spec §7.3.2 — 任务 4.6: JSONL archive fallback ──────────────


def text_similarity(a: str, b: str) -> float:
    """Compute text similarity between two strings using difflib.

    Uses :class:`difflib.SequenceMatcher` with case-insensitive
    comparison and whitespace stripping. Returns a float in [0.0, 1.0]:

    - 1.0 = identical (after normalization)
    - 0.0 = completely different (no common subsequences)

    Rationale: spec §7.3.2 requires ``text_similarity(error_text,
    error_msg)`` for JSONL fallback ranking. We use SequenceMatcher
    (Python stdlib, no new dependencies) rather than token Jaccard
    or fuzzy match — SequenceMatcher handles partial substring
    matches naturally, which is what we want for error messages
    that often share long common substrings (e.g. "Template match
    failed: btn.png not found" vs "Template match failed: icon.png").

    Args:
        a: First string (typically the query error_text).
        b: Second string (typically a JSONL line's error_msg).

    Returns:
        Similarity ratio in [0.0, 1.0].
    """
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(
        None,
        a.strip().lower(),
        b.strip().lower(),
    ).ratio()


def _search_similar_errors_via_jsonl(
    error_text: str,
    top_k: int = 5,
    similarity_threshold: float = 0.5,
    days: int = 30,
    max_executions: int = 200,
    executions: Iterable = None,
) -> list[dict]:
    """Scan failed executions' structured JSONL logs for similar errors.

    spec §7.3.2 — 任务 4.6 (2026-07-26 修正): replaces the old SQL
    icontains fallback (violated spec §2.2 数据库边界收敛). Reads each
    failed execution's structured JSONL log via the path stored in
    ``TaskExecution.execution_snapshot['structured_log_path']``, parses
    every ``success=False`` event, and ranks by
    :func:`text_similarity` against ``error_msg``.

    Data flow (修正前 vs 修正后):
        - 修正前 (bug): ``glob <DEBUG_ARCHIVE_DIR>/**/structured.jsonl``
          — JSONL 实际在 ``<DEBUG_DIR>/<YYYYMMDD>/<pipeline>/<HHMMSS_suffix>/structured.jsonl``
          (嵌套结构, 2026-07-29) 而非 ``<DEBUG_ARCHIVE_DIR>/**/structured.jsonl``,
          扫描永远返回 [].
        - 修正后: 查 DB 拿 ``structured_log_path`` → 读文件 (对齐
          :func:`gaf_ai.views_anomaly._extract_patterns_from_jsonl`
          的数据流模式).

    Args:
        error_text: The error text to search for.
        top_k: Maximum number of matches to return (sorted by
            similarity descending).
        similarity_threshold: Minimum similarity to include a match
            (default 0.5, per spec §7.3.2).
        days: Look back N days for failed executions (default 30).
            Ignored when ``executions`` is provided.
        max_executions: Cap on number of executions to scan (default 200).
            Guards against pathological 30-day windows with thousands of
            failed executions — each JSONL may have thousands of lines,
            so unbounded scan = millions of SequenceMatcher calls.
        executions: Optional pre-filtered TaskExecution iterable. When
            provided, ``days`` and ``max_executions`` are ignored. Used
            by callers that already have a queryset (e.g. anomaly
            detection).

    Returns:
        List of match dicts (sorted by similarity desc, top_k max).
        ``execution_id`` is always the TaskExecution.pk (int) — the
        JSONL's internal agent execution_id (UUID12 string) is NOT
        exposed because callers (e.g. get_execution_detail) expect the
        DB pk. ``jsonl_path`` is included for traceability.

    Files that fail to read or parse are silently skipped (best-effort
    scan — a single corrupted JSONL should never block the agent).
    """
    from datetime import timedelta

    from django.utils import timezone

    from tasks.models import TaskExecution

    if executions is None:
        cutoff = timezone.now() - timedelta(days=days)
        executions = TaskExecution.objects.filter(
            status=TaskExecution.Status.FAILED,
            started_at__gte=cutoff,
        ).order_by('-started_at')[:max_executions]

    candidates: list[tuple[float, dict]] = []

    for ex in executions:
        snapshot = (
            ex.execution_snapshot
            if isinstance(ex.execution_snapshot, dict) else {}
        )
        jsonl_path = snapshot.get('structured_log_path', '')
        if not jsonl_path or not os.path.isfile(jsonl_path):
            continue
        try:
            with open(jsonl_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if evt.get('success') is not False:
                        continue
                    msg = evt.get('error_msg', '')
                    if not msg:
                        continue
                    sim = text_similarity(error_text, msg)
                    if sim <= similarity_threshold:
                        continue
                    # Always use TaskExecution.pk (int) — the JSONL's
                    # execution_id is the agent's UUID12 string (e.g.
                    # "exec-abc123def456"), which callers cannot use to
                    # query TaskExecution (get_execution_detail expects int).
                    # jsonl_path is included for traceability instead.
                    candidates.append((sim, {
                        'execution_id': ex.id,
                        'error': msg,
                        'similarity': round(sim, 3),
                        'jsonl_path': jsonl_path,
                        'node_id': evt.get('node_id'),
                        'node_type': evt.get('node_type'),
                        'error_code': evt.get('error_code'),
                        'timestamp': evt.get('timestamp'),
                    }))
        except (OSError, UnicodeDecodeError):
            # Single-file failure should not block the whole scan.
            logger.warning(
                'JSONL fallback: failed to read %s, skipping', jsonl_path,
            )
            continue

    # Sort by similarity descending, take top_k.
    candidates.sort(key=lambda x: -x[0])
    return [c[1] for c in candidates[:top_k]]


@tool
def get_task_config(task_id: int) -> str:
    """Get task configuration: pipeline JSON, enabled status, execution mode.

    Args:
        task_id: The Task ID to look up.

    Returns:
        JSON string with task config, or error message.
    """
    try:
        from tasks.models import Task

        try:
            task = Task.objects.get(pk=task_id)
        except Task.DoesNotExist:
            return f"Task #{task_id} not found."

        result = {
            'task_id': task.id,
            'task_name': task.name,
            'execution_mode': getattr(task, 'execution_mode', 'pipeline'),
            'is_enabled': getattr(task, 'is_enabled', True),
            'task_definition': getattr(task, 'task_definition', None),
            'params_config': getattr(task, 'params_config', None),
            'description': getattr(task, 'description', ''),
        }
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.exception('get_task_config failed for task_id=%s', task_id)
        return json.dumps({
            'error': f'Tool execution failed: {exc}',
            'tool': 'get_task_config',
        }, ensure_ascii=False)


@tool
def get_screenshot_base64(execution_id: int, step_index: int = None, raw: bool = True) -> str:
    """Get a screenshot as base64 for a given execution step (spec §7.2.1).

    Lets the ReAct agent visually inspect what happened at a specific
    step. Two modes:
      - raw=True  → original JPEG (recognition nodes only: template_match
                    / ocr / feature_match / color_detect). Read from the
                    JSONL ``raw_screenshot_path`` field.
      - raw=False → annotated PNG (all nodes). Read from
                    ``TaskStep.screenshot_path``.

    When ``step_index`` is omitted, the first failed step is selected
    automatically. When ``raw=True`` but no raw image exists for that
    step (action nodes don't save raw), the tool returns an error
    envelope with ``fallback_hint='call again with raw=False'`` so the
    agent can self-correct.

    Args:
        execution_id: The TaskExecution ID to look up.
        step_index: Optional step index. If omitted, the first failed
            step is used.
        raw: True for the original JPEG (recognition nodes only),
            False for the annotated PNG (all nodes). Default True.

    Returns:
        JSON string with ``{base64, format, path, size_bytes}`` on
        success, or ``{error, tool, ...}`` on failure.
    """
    try:
        import base64
        import os

        from tasks.models import TaskExecution, TaskStep

        try:
            ex = TaskExecution.objects.get(pk=execution_id)
        except TaskExecution.DoesNotExist:
            return json.dumps({
                'error': f'Execution #{execution_id} not found.',
                'tool': 'get_screenshot_base64',
            }, ensure_ascii=False)

        # 1. Locate the TaskStep
        if step_index is not None:
            try:
                step = TaskStep.objects.get(
                    execution_id=execution_id, step_index=step_index,
                )
            except TaskStep.DoesNotExist:
                return json.dumps({
                    'error': (
                        f'Step #{step_index} not found in execution '
                        f'#{execution_id}.'
                    ),
                    'tool': 'get_screenshot_base64',
                }, ensure_ascii=False)
        else:
            step = (
                TaskStep.objects.filter(
                    execution_id=execution_id, status='failed',
                ).order_by('step_index').first()
            )
            if step is None:
                return json.dumps({
                    'error': (
                        f'No failed step in execution #{execution_id} '
                        f'(specify step_index explicitly).'
                    ),
                    'tool': 'get_screenshot_base64',
                }, ensure_ascii=False)

        # 2. Resolve screenshot path
        if raw:
            screenshot_path = _read_raw_screenshot_path(ex, step.step_index)
            if not screenshot_path:
                return json.dumps({
                    'error': (
                        f'No raw_screenshot_path for step {step.step_index} '
                        f'(raw images are saved only by recognition nodes: '
                        f'template_match/ocr/feature_match/color_detect).'
                    ),
                    'tool': 'get_screenshot_base64',
                    'fallback_hint': 'call again with raw=False to get annotated PNG',
                    'step_index': step.step_index,
                    'step_name': step.step_name,
                }, ensure_ascii=False)
            fmt = 'jpeg'
        else:
            screenshot_path = step.screenshot_path or ''
            if not screenshot_path:
                return json.dumps({
                    'error': (
                        f'No screenshot_path recorded for step '
                        f'{step.step_index} ({step.step_name}).'
                    ),
                    'tool': 'get_screenshot_base64',
                    'step_index': step.step_index,
                    'step_name': step.step_name,
                }, ensure_ascii=False)
            ext = os.path.splitext(screenshot_path)[1].lower()
            fmt = 'jpeg' if ext in ('.jpg', '.jpeg') else 'png'

        # 3. Read file + base64 encode (with 5MB safety cap)
        if not os.path.isfile(screenshot_path):
            return json.dumps({
                'error': f'Screenshot file not found: {screenshot_path}',
                'tool': 'get_screenshot_base64',
                'path': screenshot_path,
            }, ensure_ascii=False)

        try:
            with open(screenshot_path, 'rb') as f:
                img_data = f.read()
        except OSError as exc:
            return json.dumps({
                'error': f'Failed to read screenshot: {exc}',
                'tool': 'get_screenshot_base64',
                'path': screenshot_path,
            }, ensure_ascii=False)

        size_limit = 5 * 1024 * 1024  # 5MB cap to keep LLM context sane
        if len(img_data) > size_limit:
            return json.dumps({
                'error': (
                    f'Screenshot too large ({len(img_data)} bytes, '
                    f'max {size_limit}). Consider downscaling before re-run.'
                ),
                'tool': 'get_screenshot_base64',
                'path': screenshot_path,
                'size_bytes': len(img_data),
            }, ensure_ascii=False)

        b64 = base64.b64encode(img_data).decode('ascii')
        return json.dumps({
            'base64': b64,
            'format': fmt,
            'path': screenshot_path,
            'size_bytes': len(img_data),
            'step_index': step.step_index,
            'step_name': step.step_name,
        }, ensure_ascii=False)
    except Exception as exc:
        logger.exception(
            'get_screenshot_base64 failed for execution_id=%s step_index=%s',
            execution_id, step_index,
        )
        return json.dumps({
            'error': f'Tool execution failed: {exc}',
            'tool': 'get_screenshot_base64',
        }, ensure_ascii=False)


def _read_raw_screenshot_path(execution, step_index: int) -> str:
    """Look up ``raw_screenshot_path`` for a step from the JSONL log.

    The JSONL is a sequence of one-event-per-line JSON objects written
    by ``agent/src/utils/structured_logger.py``. Its path is stored in
    ``TaskExecution.execution_snapshot['structured_log_path']`` when the
    agent reports results (only readable when agent + backend share a
    filesystem — local dev scenario, same as spec 阶段 3.4).

    Args:
        execution: TaskExecution instance.
        step_index: Step index to look up.

    Returns:
        The raw_screenshot_path string, or '' if not found / file
        unreadable / field absent.
    """
    import json
    import os

    snapshot = (
        execution.execution_snapshot
        if isinstance(execution.execution_snapshot, dict) else {}
    )
    jsonl_path = snapshot.get('structured_log_path', '')
    if not jsonl_path or not os.path.isfile(jsonl_path):
        return ''

    try:
        with open(jsonl_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get('step_index') == step_index:
                    rsp = entry.get('raw_screenshot_path')
                    if isinstance(rsp, str) and rsp:
                        return rsp
    except OSError as exc:
        logger.warning('_read_raw_screenshot_path read failed: %s', exc)
    return ''


@tool
def get_structured_log(execution_id: int) -> str:
    """Get a structured summary of the JSONL log for an execution (spec §7.3.1).

    Parses the structured JSONL written by the agent's
    ``StructuredLogger`` and returns a compact, LLM-friendly summary:
    failed steps get full detail (confidence/threshold/roi/error_code/
    error_msg); successful steps get a one-liner. The agent uses this
    to reason about *why* a step failed without parsing raw text logs.

    The JSONL path is read from
    ``TaskExecution.execution_snapshot['structured_log_path']``. When
    the file is missing (e.g. agent and backend on different hosts),
    the tool returns an error envelope with hints instead of crashing.

    Args:
        execution_id: The TaskExecution ID to look up.

    Returns:
        JSON string with ``{total_steps, failed_count, success_count,
        failed_steps: [...], successful_summary: str, failed_detail: str,
        raw_log_path: str}`` on success, or ``{error, tool, ...}`` on
        failure.
    """
    try:
        import json
        import os

        from tasks.models import TaskExecution

        try:
            ex = TaskExecution.objects.get(pk=execution_id)
        except TaskExecution.DoesNotExist:
            return json.dumps({
                'error': f'Execution #{execution_id} not found.',
                'tool': 'get_structured_log',
            }, ensure_ascii=False)

        snapshot = (
            ex.execution_snapshot
            if isinstance(ex.execution_snapshot, dict) else {}
        )
        jsonl_path = snapshot.get('structured_log_path', '')

        if not jsonl_path:
            return json.dumps({
                'error': (
                    f'Execution #{execution_id} has no '
                    f'execution_snapshot.structured_log_path — agent '
                    f'likely did not report one.'
                ),
                'tool': 'get_structured_log',
                'hint': 'fall back to get_execution_steps for SQL-based step data',
            }, ensure_ascii=False)

        if not os.path.isfile(jsonl_path):
            return json.dumps({
                'error': (
                    f'JSONL file not found: {jsonl_path} (agent and '
                    f'backend may be on different hosts).'
                ),
                'tool': 'get_structured_log',
                'raw_log_path': jsonl_path,
                'hint': 'fall back to get_execution_steps for SQL-based step data',
            }, ensure_ascii=False)

        entries: list[dict] = []
        try:
            with open(jsonl_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError as exc:
            return json.dumps({
                'error': f'Failed to read JSONL: {exc}',
                'tool': 'get_structured_log',
                'raw_log_path': jsonl_path,
            }, ensure_ascii=False)

        if not entries:
            return json.dumps({
                'error': f'JSONL file is empty: {jsonl_path}',
                'tool': 'get_structured_log',
                'raw_log_path': jsonl_path,
            }, ensure_ascii=False)

        # Sort by step_index for stable output
        entries.sort(key=lambda e: e.get('step_index', 0))

        failed_steps: list[dict] = []
        success_lines: list[str] = []
        failed_detail_lines: list[str] = []
        for entry in entries:
            step_idx = entry.get('step_index', '?')
            node_id = entry.get('node_id', '?')
            node_type = entry.get('node_type', '?')
            elapsed_ms = entry.get('elapsed_ms', 0)
            success = bool(entry.get('success', False))

            if success:
                success_lines.append(
                    f"step={step_idx} ✅ {node_type}({node_id}) {elapsed_ms}ms"
                )
                continue

            # Failed step — collect structured fields
            fail_record: dict = {
                'step_index': step_idx,
                'node_id': node_id,
                'node_type': node_type,
                'elapsed_ms': elapsed_ms,
                'error_msg': entry.get('error_msg', ''),
                'error_code': entry.get('error_code', ''),
                'retry_count': entry.get('retry_count', 0),
            }
            # Optional diagnostic fields
            for k in ('confidence', 'threshold', 'match_location',
                      'roi_physical', 'auto_heal_attempts',
                      'screenshot_path', 'raw_screenshot_path',
                      'comment', 'rationale'):
                v = entry.get(k)
                if v not in (None, '', [], {}):
                    fail_record[k] = v
            failed_steps.append(fail_record)

            # Build human-readable failed_detail line
            detail = f"step={step_idx} ❌ {node_type}({node_id}) {elapsed_ms}ms"
            if fail_record.get('confidence') is not None:
                detail += f" confidence={fail_record['confidence']}"
            if fail_record.get('threshold') is not None:
                detail += f" threshold={fail_record['threshold']}"
            if fail_record.get('roi_physical'):
                detail += f" roi={fail_record['roi_physical']}"
            if fail_record.get('error_code'):
                detail += f" error_code={fail_record['error_code']}"
            if fail_record.get('auto_heal_attempts'):
                detail += f" auto_heal={fail_record['auto_heal_attempts']}"
            if fail_record.get('screenshot_path'):
                detail += f" screenshot={fail_record['screenshot_path']}"
            if fail_record.get('raw_screenshot_path'):
                detail += f" raw_screenshot={fail_record['raw_screenshot_path']}"
            if fail_record['error_msg']:
                # cap error_msg inline to keep summary readable
                detail += f"\n    error: {fail_record['error_msg'][:500]}"
            failed_detail_lines.append(detail)

        return json.dumps({
            'total_steps': len(entries),
            'failed_count': len(failed_steps),
            'success_count': len(success_lines),
            'failed_steps': failed_steps,
            'successful_summary': ' | '.join(success_lines),
            'failed_detail': '\n'.join(failed_detail_lines),
            'raw_log_path': jsonl_path,
        }, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.exception(
            'get_structured_log failed for execution_id=%s', execution_id,
        )
        return json.dumps({
            'error': f'Tool execution failed: {exc}',
            'tool': 'get_structured_log',
        }, ensure_ascii=False)
