"""
Anomaly detection API for AI Lab
Discovers recurring failure patterns from execution logs
"""
import json
import logging
import re
from collections import Counter

from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from gaf_ai.llm_service import call_llm
from gaf_ai.services import count_user_executions_since, get_user_failed_executions_qs

logger = logging.getLogger(__name__)


@extend_schema(
    tags=['ai'],
    summary='Detect anomaly patterns from failed executions with LLM',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def anomaly_detection_view(request):
    """
    Detect anomaly patterns from failed task executions.

    POST /api/ai/anomaly-detection/
    Body: { days?: number (default 7), min_occurrences?: number (default 2) }
    Returns pattern analysis with LLM-generated suggestions.
    """
    # @api_view allowed: pattern extraction + external LLM analysis, not model CRUD
    days = int(request.data.get('days', 7))
    min_occurrences = int(request.data.get('min_occurrences', 2))

    cutoff = timezone.now() - timezone.timedelta(days=days)
    failed_executions = get_user_failed_executions_qs(request.user, cutoff)

    if not failed_executions.exists():
        return Response({
            'patterns': [],
            'summary': f'近 {days} 天无失败记录，系统运行正常',
            'total_analyzed': 0,
            'stats': {'failed_count': 0, 'total_count': 0},
        })

    total_executions = count_user_executions_since(request.user, cutoff)

    error_messages = []
    for ex in failed_executions:
        if ex.error_message:
            error_messages.append(ex.error_message)

    patterns = _extract_patterns(error_messages, min_occurrences)
    stats = {
        'failed_count': failed_executions.count(),
        'total_count': total_executions,
        'failure_rate': round(failed_executions.count() / max(total_executions, 1) * 100, 1),
        'unique_errors': len(set(error_messages)),
    }

    summary = (
        f'近 {days} 天共分析 {total_executions} 次执行，'
        f'发现 {len(patterns)} 个重复失败模式（共 {stats["failed_count"]} 次失败）'
    )

    llm_suggestions = None
    if patterns:
        try:
            context = json.dumps({
                'patterns': patterns,
                'stats': stats,
                'sample_errors': error_messages[:10],
            }, ensure_ascii=False, indent=2)

            messages = [
                {
                    'role': 'system',
                    'content': (
                        '你是 GAF 自动化框架的异常分析专家。'
                        '根据以下执行失败模式数据，给出：'
                        '1. 根因分析（最可能的根本原因）\n'
                        '2. 优先级排序（按影响面和修复难度）\n'
                        '3. 具体修复建议（可操作的步骤）\n'
                        '用中文回复，保持简洁专业。'
                    ),
                },
                {
                    'role': 'user',
                    'content': f'分析以下异常模式并给出修复建议：\n{context}',
                },
            ]

            result = call_llm(messages, model='gpt-4o-mini')
            if not result.get('error'):
                llm_suggestions = result['content']
        except Exception as e:
            logger.warning(f"Anomaly detection LLM analysis failed: {e}")

    return Response({
        'patterns': patterns,
        'summary': summary,
        'llm_analysis': llm_suggestions,
        'stats': stats,
        'total_analyzed': len(error_messages),
    })


def _extract_patterns(error_messages: list[str], min_occurrences: int) -> list[dict]:
    """Extract recurring error patterns using regex and string similarity"""
    normalized = []
    for msg in error_messages:
        clean = msg.strip()
        # Order matters: paths → hashes → numbers. If numbers run first,
        # they break up hex strings so the hash regex never matches; if
        # the path regex requires a leading backslash, forward-slash
        # Unix paths are not matched.
        clean = re.sub(r'[/\\][\w/.\\-]+', '<PATH>', clean)
        clean = re.sub(r'[a-f0-9]{8,}', '<HASH>', clean)
        clean = re.sub(r'[0-9]+', '<NUM>', clean)
        normalized.append(clean)

    counter = Counter(normalized)
    patterns = []
    for text, count in counter.most_common(20):
        if count < min_occurrences:
            continue
        original_msgs = [m for m, n in zip(error_messages, normalized, strict=False) if n == text]
        category = _categorize_error(text)
        patterns.append({
            'pattern_text': text[:200],
            'occurrence_count': count,
            'severity': _estimate_severity(count, category),
            'category': category,
            'sample_messages': original_msgs[:3],
            'first_seen': original_msgs[0] if original_msgs else '',
        })

    return patterns


def _categorize_error(error_text: str) -> str:
    """Categorize error type by keyword matching"""
    error_lower = error_text.lower()
    if any(kw in error_lower for kw in ['timeout', 'timed out']):
        return 'timeout'
    if any(kw in error_lower for kw in ['template', 'match', 'not found', 'threshold']):
        return 'recognition'
    if any(kw in error_lower for kw in ['connection', 'network', 'adb', 'device']):
        return 'device'
    if any(kw in error_lower for kw in ['permission', 'access denied', 'forbidden']):
        return 'permission'
    if any(kw in error_lower for kw in ['memory', 'oom', 'out of memory']):
        return 'resource'
    return 'unknown'


def _estimate_severity(count: int, category: str) -> str:
    """Estimate severity based on occurrence count and category"""
    if count >= 10 or category in ('device', 'permission'):
        return 'critical'
    if count >= 5 or category == 'resource':
        return 'high'
    if count >= 3:
        return 'medium'
    return 'low'


def _extract_patterns_from_jsonl(
    executions, min_occurrences: int, max_executions: int = 500,
) -> list[dict]:
    """从历史 JSONL 文件提取失败模式 (spec §7.4.1).

    遍历 executions, 读取每个 execution 的 JSONL 结构化日志,
    提取 success=False 的节点 error_msg, 复用 _extract_patterns
    做归一化 (路径/哈希/数字替换) + 计数.

    优势: 比从 TaskExecution.error_message 提取更精准, 因为 JSONL
    包含每个失败节点的 node_id/node_type/error_code, 能区分同一执行
    中多个步骤的失败.

    Args:
        executions: TaskExecution queryset/list (已过滤为 failed).
        min_occurrences: 最小出现次数阈值.
        max_executions: 扫描 executions 数量上限 (默认 500). 防止
            24h 内千次失败 × 千行 JSONL 的病态扫描. 超出部分静默
            跳过 — 异常检测只取最最近的样本已足够代表性.

    Returns:
        patterns 列表, 结构同 _extract_patterns 返回值.
    """
    import json as _json
    import os as _os

    error_messages: list[str] = []
    scanned = 0
    for ex in executions:
        if scanned >= max_executions:
            logger.info(
                '_extract_patterns_from_jsonl: 达到 max_executions=%d, '
                '跳过剩余 executions', max_executions,
            )
            break
        scanned += 1
        snapshot = ex.execution_snapshot if isinstance(
            ex.execution_snapshot, dict,
        ) else {}
        log_path = snapshot.get('structured_log_path', '')
        if not log_path or not _os.path.exists(log_path):
            continue
        try:
            with open(log_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = _json.loads(line)
                    except _json.JSONDecodeError:
                        continue
                    # 只收集失败节点的 error_msg
                    if evt.get('success') is False:
                        msg = evt.get('error_msg', '')
                        if msg:
                            error_messages.append(msg)
        except Exception:
            # 读文件失败时跳过该执行 (日志已记录)
            logger.warning(
                "读取 JSONL 失败 (execution_id=%s, path=%s)",
                getattr(ex, 'id', '?'), log_path,
            )
            continue

    return _extract_patterns(error_messages, min_occurrences)


def write_anomaly_report(patterns: list[dict], date=None) -> str:
    """写异常模式报告到 anomaly_reports/ 目录 (spec §7.4.2).

    Args:
        patterns: _extract_patterns_from_jsonl 返回的模式列表.
        date: 报告日期, 默认今天.

    Returns:
        报告文件的绝对路径.
    """
    import datetime as _dt
    import os as _os

    from django.conf import settings

    debug_dir = getattr(settings, 'DEBUG_DIR', './debug')
    reports_dir = _os.path.join(debug_dir, 'anomaly_reports')
    _os.makedirs(reports_dir, exist_ok=True)

    if date is None:
        date = _dt.date.today()
    report_path = _os.path.join(reports_dir, f'{date}.md')

    lines = [f'# 异常检测报告 {date}', '']
    lines.append(f'共发现 {len(patterns)} 个失败模式:')
    lines.append('')
    for i, p in enumerate(patterns, 1):
        lines.append(
            f"## {i}. {p['pattern_text'][:100]} "
            f"(出现 {p['occurrence_count']} 次, "
            f"严重度: {p['severity']})",
        )
        lines.append(f"- 类别: {p['category']}")
        if p.get('sample_messages'):
            lines.append('- 示例:')
            for msg in p['sample_messages'][:3]:
                lines.append(f'  - {msg[:200]}')
        lines.append('')

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return report_path
