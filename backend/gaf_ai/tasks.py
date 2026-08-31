"""Celery tasks for the AI app.

Currently hosts the async wrapper around the LangGraph ReAct log-analysis
agent. The HTTP view (ai.agent.views.agent_analyze_view) creates an
AgentSession in PENDING state, dispatches this task, and returns
immediately. The frontend polls GET /api/v2/ai/agent/sessions/<id>/
until status becomes COMPLETED or FAILED.

The reasoning-chain parsing helpers (_extract_reasoning_steps,
_serialize_messages, _parse_agent_result) live here rather than in
views.py because they are only invoked from the async task path.
"""
import json
import logging

from celery import shared_task
from django.utils import timezone

from .agent.models import AgentSession
from .models import QASession

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0, default_retry_delay=0, acks_late=True)
def run_agent_analysis_task(self, session_id: int, execution_id: int) -> dict:
    """Run the LangGraph ReAct agent to analyze an execution.

    Args:
        session_id: AgentSession PK to update with results.
        execution_id: TaskExecution PK to analyze.

    Returns:
        Dict mirror of AgentSession fields (session_id, status,
        model_used, reasoning_steps, summary, suggestions,
        total_tokens, error). On failure, status='failed' and
        error_message is set on the session.
    """
    try:
        session = AgentSession.objects.get(pk=session_id)
    except AgentSession.DoesNotExist:
        logger.error(
            'run_agent_analysis_task: AgentSession #%s not found',
            session_id,
        )
        return {
            'session_id': session_id,
            'status': 'failed',
            'error': f'AgentSession #{session_id} not found',
        }

    session.status = AgentSession.Status.RUNNING
    session.save(update_fields=['status'])

    try:
        result = _run_agent_analysis(session, execution_id)
        return result
    except Exception as exc:
        logger.exception(
            'run_agent_analysis_task failed for session #%s (execution #%s): %s',
            session_id, execution_id, exc,
        )
        session.status = AgentSession.Status.FAILED
        session.error_message = str(exc)
        session.completed_at = timezone.now()
        session.save(update_fields=['status', 'error_message', 'completed_at'])
        return {
            'session_id': session.id,
            'status': 'failed',
            'model_used': '',
            'reasoning_steps': [],
            'summary': '',
            'suggestions': [],
            'evidence': [],
            'total_tokens': 0,
            'error': str(exc),
        }


def _run_agent_analysis(session: AgentSession, execution_id: int) -> dict:
    """Build and invoke the ReAct agent, extract reasoning chain, save to session."""
    from .agent.graph import build_log_analysis_agent

    # Pass session.user so per-user CustomSkill tools are injected into
    # the agent's toolset (S6 / P2-4). Global SkillDefinitions are
    # injected regardless of user.
    agent = build_log_analysis_agent(user=session.user)

    user_message = (
        f'Please analyze execution #{execution_id}. '
        f'Use the tools to gather information about this execution, '
        f'identify any failures, search for similar past errors, '
        f'and provide a comprehensive diagnosis with actionable suggestions.'
    )

    # Invoke the agent — this runs the full ReAct loop
    agent_result = agent.invoke({
        'messages': [{'role': 'user', 'content': user_message}],
    })

    # Extract reasoning steps from the message history
    messages = agent_result.get('messages', [])
    reasoning_steps = _extract_reasoning_steps(messages)

    # Phase 2: persist the LangGraph observability trail (nodes/tools/tokens)
    # for the frontend trajectory timeline.
    trajectory = agent_result.get('trajectory', []) or []

    # Get the final AI message (last AIMessage with content)
    final_content = ''
    model_used = ''
    total_tokens = 0
    for msg in reversed(messages):
        msg_type = type(msg).__name__
        if msg_type == 'AIMessage' and msg.content and not getattr(msg, 'tool_calls', None):
            final_content = msg.content
            response_metadata = getattr(msg, 'response_metadata', {})
            model_used = response_metadata.get('model_name', '') or response_metadata.get('model', '')
            token_usage = response_metadata.get('token_usage', {})
            total_tokens = (
                token_usage.get('total_tokens', 0)
                or (token_usage.get('prompt_tokens', 0) + token_usage.get('completion_tokens', 0))
            )
            break
        elif msg_type == 'AIMessage' and msg.content and not getattr(msg, 'tool_calls', []):
            # Some LLMs return final answer without tool_calls
            final_content = msg.content
            response_metadata = getattr(msg, 'response_metadata', {})
            model_used = response_metadata.get('model_name', '') or response_metadata.get('model', '')
            token_usage = response_metadata.get('token_usage', {})
            total_tokens = (
                token_usage.get('total_tokens', 0)
                or (token_usage.get('prompt_tokens', 0) + token_usage.get('completion_tokens', 0))
            )
            break

    # Parse the final answer JSON
    summary, suggestions, evidence = _parse_agent_result(final_content)

    # P2 (2026-08-17): 幻觉防线强校验 — evidence 条目与 ReAct 工具观测比对.
    # 未找到观测支撑的 evidence 标记 unverified 并附注 (从"有无证据"升级到
    # "证据是否被工具观测支撑").
    observations = [
        step.get('observation', '')
        for step in reasoning_steps
        if step.get('observation')
    ]
    evidence_check = _verify_evidence(evidence, observations)
    if evidence_check['unverified']:
        unverified_preview = evidence_check['unverified'][:2]
        summary = summary.rstrip() + (
            '\n\n[强校验未通过] 以下证据条目与工具观测不符: '
            + '; '.join(unverified_preview)
            + '. 请人工复核.'
        )

    # S3 P5: 幻觉防线基础版 — 无 evidence 时弱校验提示 (不阻塞).
    if not evidence:
        summary = summary.rstrip() + (
            '\n\n[请人工复核] 本次诊断未提供证据条目 (evidence 为空), '
            '结论可能缺少工具观测支撑.'
        )

    # Save to session
    session.messages = _serialize_messages(messages)
    session.reasoning_steps = reasoning_steps
    session.trajectory = trajectory
    session.final_summary = summary
    session.final_suggestions = suggestions
    session.evidence = evidence
    session.evidence_check = evidence_check
    session.status = AgentSession.Status.COMPLETED
    session.model_used = model_used
    session.total_tokens = total_tokens
    session.completed_at = timezone.now()
    session.save()

    return {
        'session_id': session.id,
        'status': 'completed',
        'model_used': model_used,
        'reasoning_steps': reasoning_steps,
        'trajectory': trajectory,
        'summary': summary,
        'suggestions': suggestions,
        'evidence': evidence,
        'evidence_check': evidence_check,
        'total_tokens': total_tokens,
    }


def _extract_reasoning_steps(messages: list) -> list[dict]:
    """Extract ReAct reasoning steps from the LangGraph message history.

    A ReAct step is: AIMessage(tool_calls=[...]) → ToolMessage(result)
    We pair each tool call with its tool message response.
    """
    steps = []
    pending_tool_calls = []  # list of (tool_name, tool_args)

    for msg in messages:
        msg_type = type(msg).__name__

        if msg_type == 'AIMessage':
            tool_calls = getattr(msg, 'tool_calls', None) or []
            if tool_calls:
                for tc in tool_calls:
                    tool_name = tc.get('name', 'unknown')
                    tool_args = tc.get('args', {})
                    pending_tool_calls.append((tool_name, tool_args, msg.content or ''))
            elif msg.content and not pending_tool_calls:
                # Final answer without any tool use
                steps.append({
                    'thought': msg.content[:500],
                    'action': None,
                    'action_input': None,
                    'observation': None,
                })

        elif msg_type == 'ToolMessage':
            if pending_tool_calls:
                tool_name, tool_args, thought = pending_tool_calls.pop(0)
                observation = msg.content if isinstance(msg.content, str) else str(msg.content)
                steps.append({
                    'thought': thought or f'Calling {tool_name}',
                    'action': tool_name,
                    'action_input': tool_args,
                    'observation': observation[:2000],  # Truncate long tool results
                })

    return steps


def _serialize_messages(messages: list) -> list[dict]:
    """Serialize LangGraph messages to JSON-safe dicts for storage."""
    serialized = []
    for msg in messages:
        msg_type = type(msg).__name__
        entry = {
            'type': msg_type,
            'content': '',
            'tool_calls': [],
            'tool_call_id': '',
        }
        content = getattr(msg, 'content', '')
        if isinstance(content, str):
            entry['content'] = content
        elif isinstance(content, list):
            # Some providers return content as list of blocks
            entry['content'] = json.dumps(content, ensure_ascii=False, default=str)
        else:
            entry['content'] = str(content)

        tool_calls = getattr(msg, 'tool_calls', None)
        if tool_calls:
            entry['tool_calls'] = [
                {'name': tc.get('name'), 'args': tc.get('args', {})}
                for tc in tool_calls
            ]

        tool_call_id = getattr(msg, 'tool_call_id', None)
        if tool_call_id:
            entry['tool_call_id'] = tool_call_id

        serialized.append(entry)
    return serialized


def _parse_agent_result(content: str) -> tuple[str, list[str], list[str]]:
    """Parse the agent's final JSON answer into (summary, suggestions, evidence).

    Falls back gracefully if the LLM didn't return valid JSON. S3 P5:
    the ``evidence`` array is extracted for the hallucination guard
    (empty list = no evidence provided → weak-check annotation).
    """
    if not content:
        return 'Agent completed but returned no summary.', [], []

    text = content.strip()

    # Strip markdown fences if present
    if text.startswith('```'):
        first_newline = text.find('\n')
        if first_newline != -1:
            text = text[first_newline + 1:]
        if text.rstrip().endswith('```'):
            text = text.rstrip()[:-3].rstrip()

    try:
        parsed = json.loads(text)
        summary = str(parsed.get('summary', '')).strip()
        suggestions_raw = parsed.get('suggestions', [])
        if isinstance(suggestions_raw, list):
            suggestions = [str(s) for s in suggestions_raw]
        elif isinstance(suggestions_raw, str):
            suggestions = [suggestions_raw]
        else:
            suggestions = []

        evidence_raw = parsed.get('evidence', [])
        if isinstance(evidence_raw, list):
            evidence = [str(e) for e in evidence_raw]
        elif isinstance(evidence_raw, str):
            evidence = [evidence_raw]
        else:
            evidence = []

        return summary or 'Analysis completed.', suggestions, evidence
    except (json.JSONDecodeError, TypeError):
        logger.warning('Agent final answer was not valid JSON, using raw content as summary')
        return text[:1000], [], []


# P2 (2026-08-17): 幻觉防线强校验 — evidence ↔ 工具观测比对.
STRONG_CHECK_THRESHOLD = 0.3


def _verify_evidence(
    evidence: list[str], observations: list[str],
) -> dict[str, list[str]]:
    """Check each evidence item against the tool observations seen in the
    ReAct loop.

    An evidence item is ``verified`` when its text_similarity to at least
    one observation reaches ``STRONG_CHECK_THRESHOLD`` (0.3). Evidence is
    the LLM's paraphrase of observations, so the threshold is deliberately
    below the JSONL retrieval threshold (0.5).

    Returns ``{"verified": [...], "unverified": [...]}``. An empty
    evidence list yields empty lists (weak-check annotation unchanged).
    """
    from .agent.tools import text_similarity

    verified: list[str] = []
    unverified: list[str] = []
    for item in evidence:
        best = 0.0
        for observation in observations:
            score = text_similarity(item, observation)
            if score > best:
                best = score
            if best >= STRONG_CHECK_THRESHOLD:
                break
        if best >= STRONG_CHECK_THRESHOLD:
            verified.append(item)
        else:
            unverified.append(item)
    return {'verified': verified, 'unverified': unverified}


# Ensure Celery also discovers RAG tasks in the separate tasks_rag module.
# autodiscover_tasks() only loads tasks.py, so we import tasks_rag here to
# register its @shared_task decorators when this module is loaded.
from . import tasks_rag  # noqa: E402,F401

# ============================================================
# spec 阶段 4 — 任务 4.2: 异常检测定时任务
# ============================================================


@shared_task(bind=True, max_retries=0, acks_late=True)
def daily_anomaly_scan(self) -> dict:
    """每天扫描最近 24h 失败的执行, 从 JSONL 提取异常模式 (spec §7.4.2).

    流程:
    1. 查询最近 1 天 status=FAILED 的 TaskExecution
    2. 调用 _extract_patterns_from_jsonl 从 JSONL 提取失败模式
    3. 写异常报告到 anomaly_reports/<date>.md
    4. 返回扫描结果摘要

    Returns:
        dict: {"status": "ok", "patterns_count": int, "report_path": str}
        或 {"status": "ok", "patterns_count": 0} (无失败时)
    """
    from datetime import timedelta

    from tasks.models import TaskExecution

    from .views_anomaly import _extract_patterns_from_jsonl, write_anomaly_report

    cutoff = timezone.now() - timedelta(days=1)
    failed_executions = TaskExecution.objects.filter(
        status=TaskExecution.Status.FAILED,
        started_at__gte=cutoff,
    )

    if not failed_executions.exists():
        logger.info('daily_anomaly_scan: 最近 24h 无失败执行')
        return {'status': 'ok', 'patterns_count': 0}

    patterns = _extract_patterns_from_jsonl(
        failed_executions, min_occurrences=1,
    )

    if not patterns:
        logger.info(
            'daily_anomaly_scan: %d 个失败执行但无 JSONL 可分析',
            failed_executions.count(),
        )
        return {
            'status': 'ok',
            'patterns_count': 0,
            'failed_count': failed_executions.count(),
        }

    report_path = write_anomaly_report(patterns, date=timezone.now().date())
    logger.info(
        'daily_anomaly_scan: 发现 %d 个模式, 报告: %s',
        len(patterns), report_path,
    )

    return {
        'status': 'ok',
        'patterns_count': len(patterns),
        'report_path': report_path,
        'failed_count': failed_executions.count(),
    }


# ============================================================
# S3 P4 (2026-08-16): 过期 session 清理
# ============================================================

# Stale-session thresholds (S3 P4).
STALE_RUNNING_HOURS = 1        # RUNNING AgentSession older than this → FAILED
STALE_PENDING_HOURS = 24       # PENDING AgentSession older than this → FAILED
STALE_QA_DAYS = 30             # QASession without messages older than this → deleted


@shared_task(bind=True, max_retries=0, acks_late=True)
def cleanup_stale_sessions(self) -> dict:
    """Clean up stale AI sessions (daily beat, S3 P4).

    - AgentSession RUNNING 超 STALE_RUNNING_HOURS → 标记 FAILED
      (含 error_message, 否则前端轮询永远 pending)
    - AgentSession PENDING 超 STALE_PENDING_HOURS → 标记 FAILED
      (任务分发丢失 / worker 未启动的兜底)
    - QASession 无消息且超 STALE_QA_DAYS → 删除
      (有消息的会话保留 — 可能是知识来源)

    Returns:
        dict: 各清理类别的计数.
    """
    from datetime import timedelta

    from .agent.models import AgentSession

    now = timezone.now()
    stats = {'running_failed': 0, 'pending_failed': 0, 'qa_deleted': 0}

    running_cutoff = now - timedelta(hours=STALE_RUNNING_HOURS)
    stale_running = AgentSession.objects.filter(
        status=AgentSession.Status.RUNNING,
        created_at__lt=running_cutoff,
    )
    for session in stale_running:
        session.status = AgentSession.Status.FAILED
        session.error_message = (
            'Stale RUNNING session cleaned up by cleanup_stale_sessions '
            f'(created {session.created_at.isoformat()}, >{STALE_RUNNING_HOURS}h)'
        )
        session.completed_at = now
        session.save(update_fields=['status', 'error_message', 'completed_at'])
        stats['running_failed'] += 1

    pending_cutoff = now - timedelta(hours=STALE_PENDING_HOURS)
    stale_pending = AgentSession.objects.filter(
        status=AgentSession.Status.PENDING,
        created_at__lt=pending_cutoff,
    )
    for session in stale_pending:
        session.status = AgentSession.Status.FAILED
        session.error_message = (
            'Stale PENDING session cleaned up by cleanup_stale_sessions '
            f'(created {session.created_at.isoformat()}, >{STALE_PENDING_HOURS}h)'
        )
        session.completed_at = now
        session.save(update_fields=['status', 'error_message', 'completed_at'])
        stats['pending_failed'] += 1

    qa_cutoff = now - timedelta(days=STALE_QA_DAYS)
    stale_qa = QASession.objects.filter(
        created_at__lt=qa_cutoff,
    ).exclude(messages__isnull=False)
    stats['qa_deleted'], _ = stale_qa.delete()

    logger.info(
        'cleanup_stale_sessions: %s', stats,
    )
    return stats
