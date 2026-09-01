"""
AI 实验室 API 视图
"""
import json
import logging

from django.http import StreamingHttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from gaf_ai.llm_service import SYSTEM_PROMPT_OPTIMIZE, SYSTEM_PROMPT_PIPELINE, call_llm, estimate_cost
from gaf_ai.models import LLMUsageLog
from gaf_ai.pipeline_guard import validate_and_score
from gaf_ai.services import get_pipeline_for_user, get_user_execution_history

logger = logging.getLogger(__name__)


def _log_usage(user, model: str, input_tokens: int, output_tokens: int, cost: float, call_type: str):
    """记录 LLM 用量"""
    LLMUsageLog.objects.create(
        user=user,
        model_name=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_estimate=cost,
        call_type=call_type,
    )


@extend_schema(
    tags=['ai'],
    summary='Generate pipeline from natural language via LLM',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_pipeline(request):
    """自然语言 → Pipeline JSON"""
    # @api_view allowed: external LLM service wrapper, not model CRUD
    description = request.data.get('description', '')
    model = request.data.get('model', 'gpt-4o-mini')

    if not description:
        return Response({'error': '请输入任务描述'}, status=400)

    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT_PIPELINE},
        {'role': 'user', 'content': f'请生成以下任务的 Pipeline: {description}'},
    ]

    result = call_llm(messages, model=model)
    if result.get('error'):
        return Response({'error': result['error']}, status=500)

    _log_usage(
        request.user,
        model,
        result['input_tokens'],
        result['output_tokens'],
        result['cost'],
        'generate_pipeline',
    )

    content = result['content']
    graph_data = None
    try:
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            graph_data = json.loads(content[json_start:json_end])
    except (json.JSONDecodeError, ValueError):
        pass

    if not graph_data or 'nodes' not in graph_data:
        return Response({
            'raw_content': content,
            'graph_data': None,
            'warning': 'LLM 返回了非标准 JSON，请尝试重新生成',
        })

    return Response({
        'graph_data': graph_data,
        'validation': validate_and_score(graph_data),
        'raw_content': content,
        'usage': {
            'input_tokens': result['input_tokens'],
            'output_tokens': result['output_tokens'],
            'cost': result['cost'],
            'model': model,
        },
    })


@extend_schema(
    tags=['ai'],
    summary='Optimize pipeline via LLM with execution history',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def optimize_pipeline(request):
    """AI 优化 Pipeline"""
    # @api_view allowed: external LLM service wrapper reading Pipeline + TaskExecution history
    pipeline_id = request.data.get('pipeline_id')
    model = request.data.get('model', 'gpt-4o-mini')

    if not pipeline_id:
        return Response({'error': '需要 pipeline_id'}, status=400)

    try:
        pipeline = get_pipeline_for_user(pipeline_id, request.user)
        if pipeline is None:
            return Response({'error': 'Pipeline 不存在'}, status=404)
    except Exception:
        logger.warning("optimize_pipeline: get_pipeline_for_user failed", exc_info=True)
        return Response({'error': 'Pipeline 查询失败'}, status=500)

    pipeline_json = pipeline.graph_data
    execution_stats = get_user_execution_history(request.user)

    context = json.dumps({
        'pipeline': pipeline_json,
        'execution_history': execution_stats,
    }, ensure_ascii=False, indent=2)

    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT_OPTIMIZE},
        {'role': 'user', 'content': f'分析以下 Pipeline 和执行历史，给出优化建议：\n{context}'},
    ]

    result = call_llm(messages, model=model)
    if result.get('error'):
        return Response({'error': result['error']}, status=500)

    _log_usage(
        request.user,
        model,
        result['input_tokens'],
        result['output_tokens'],
        result['cost'],
        'optimize_pipeline',
    )

    suggestions = None
    try:
        content = result['content']
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            suggestions = json.loads(content[json_start:json_end])
    except (json.JSONDecodeError, ValueError):
        pass

    return Response({
        'suggestions': suggestions or {'suggestions': []},
        'raw_content': result['content'],
        'usage': {
            'input_tokens': result['input_tokens'],
            'output_tokens': result['output_tokens'],
            'cost': result['cost'],
            'model': model,
        },
    })


@extend_schema(
    tags=['ai'],
    summary='Generate pipeline from natural language (SSE streaming)',
    request=OpenApiTypes.OBJECT,
    responses={(200, 'text/event-stream'): OpenApiTypes.STR, 400: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_pipeline_stream(request):
    """自然语言 → Pipeline JSON（SSE 流式响应）"""
    # @api_view allowed: SSE streaming response wrapping LLM stream, not model CRUD
    description = request.data.get('description', '')
    model = request.data.get('model', 'gpt-4o-mini')

    if not description:
        return Response({'error': '请输入任务描述'}, status=400)

    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT_PIPELINE},
        {'role': 'user', 'content': f'请生成以下任务的 Pipeline: {description}'},
    ]

    def event_stream():
        full_content = ''
        try:
            generator = call_llm(messages, model=model, stream=True)
            if isinstance(generator, dict) and generator.get('error'):
                yield f"data: {json.dumps({'error': generator['error']})}\n\n"
                return

            for chunk in generator:
                full_content += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"

            graph_data = None
            try:
                json_start = full_content.find('{')
                json_end = full_content.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    graph_data = json.loads(full_content[json_start:json_end])
            except (json.JSONDecodeError, ValueError):
                pass

            yield f"data: {json.dumps({'done': True, 'graph_data': graph_data, 'validation': validate_and_score(graph_data), 'raw_content': full_content})}\n\n"
        except Exception as e:
            logger.warning("event_stream: failed: %s", e, exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


@extend_schema(
    tags=['ai'],
    summary='AI usage statistics aggregation',
    responses={200: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter('days', OpenApiTypes.INT, description='Aggregation window in days (default 30).'),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ai_usage_stats_view(request):
    """
    AI 使用统计 API。

    GET /api/ai/usage-stats/?days=30
    返回指定时间窗口内的 AI 使用统计摘要，从 LLMUsageLog 表实时聚合。
    """
    # @api_view allowed: analytics aggregation over LLMUsageLog (custom report, not CRUD)
    from collections import defaultdict
    from datetime import timedelta

    from django.db.models import Count, Sum
    from django.utils import timezone as tz

    days = int(request.query_params.get('days', 30))
    cutoff = tz.now() - timedelta(days=days)

    logs = LLMUsageLog.objects.filter(created_at__gte=cutoff)

    total_requests = logs.count()
    if total_requests == 0:
        return Response({
            'period_days': days,
            'total_requests': 0,
            'success_rate': 0,
            'avg_tokens_per_request': 0,
            'total_tokens': 0,
            'cost_estimate_usd': 0,
            'by_model': [],
            'daily_trend': [],
        })

    model_stats = logs.values('model_name').annotate(
        requests=Count('id'),
        input_tokens=Sum('input_tokens'),
        output_tokens=Sum('output_tokens'),
    ).order_by('-requests')
    by_model = []
    for s in model_stats:
        input_tokens = s['input_tokens'] or 0
        output_tokens = s['output_tokens'] or 0
        by_model.append({
            'model': s['model_name'],
            'requests': s['requests'],
            'tokens': input_tokens + output_tokens,
            # Per-model cost (custom provider price or built-in pricing table).
            'cost_usd': estimate_cost(s['model_name'], input_tokens, output_tokens),
        })

    total_tokens = sum(s['tokens'] for s in by_model)
    avg_tokens = round(total_tokens / total_requests) if total_requests else 0
    total_cost = sum(logs.values_list('cost_estimate', flat=True))

    success_rate = round(
        (total_requests / max(total_requests, 1)) * 100, 1
    )

    daily_data = defaultdict(int)
    for log in logs.values('created_at__date').annotate(cnt=Count('id')):
        d = (log['created_at__date']).strftime('%Y-%m-%d') if isinstance(log['created_at__date'], tz.datetime) else str(log['created_at__date'])
        daily_data[d] = log['cnt']

    today = tz.now().date()
    daily_trend = []
    for i in range(min(days, 14) - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        daily_trend.append([d, daily_data.get(d, 0)])

    return Response({
        'period_days': days,
        'total_requests': total_requests,
        'success_rate': success_rate,
        'avg_tokens_per_request': avg_tokens,
        'total_tokens': total_tokens,
        'cost_estimate_usd': round(total_cost, 4),
        'by_model': by_model,
        'daily_trend': daily_trend,
    })


@extend_schema(
    tags=['ai'],
    summary='Agent evaluation metrics (completion/latency/tokens/tool usage)',
    parameters=[OpenApiParameter('days', int, OpenApiParameter.QUERY, description='window days (default 30)')],
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def agent_evaluation_view(request):
    """Agent evaluation metrics from AgentSession trajectory (Phase 3).

    GET /api/ai/agent-evaluation/?days=30
    """
    from gaf_ai.evaluation import evaluate_agent_sessions

    days = int(request.query_params.get('days', 30))
    return Response(evaluate_agent_sessions(days=days))


@extend_schema(
    tags=['ai'],
    summary='AI chat with LLM',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ai_chat_view(request):
    """
    AI 对话 API。

    POST /api/ai/chat/
    接收用户消息和对话历史，调用 LLM 返回真实回复。
    若 LLM 未配置或未启用，返回提示信息。
    """
    # @api_view allowed: external LLM service wrapper with conversation history
    from django.utils import timezone
    from settings.models import LLMConfig as LLMConfigModel

    message = request.data.get('message', '')
    model = request.data.get('model', 'gpt-4o-mini')
    history = request.data.get('history', [])

    if not message:
        return Response({'error': '请输入消息内容'}, status=400)

    llm_config = LLMConfigModel.objects.first()
    if not llm_config or not llm_config.is_active or not llm_config.api_key:
        return Response({
            'reply': 'LLM 未配置或未启用。请在系统设置中配置 LLM API Key 后重试。',
            'model': model,
            'tokens_used': 0,
            'timestamp': timezone.now().isoformat(),
            'config_missing': True,
        })

    messages = [
        {'role': 'system', 'content': '你是 GAF 游戏自动化框架的 AI 助手。你可以帮助用户分析执行日志、优化 Pipeline 配置、诊断任务失败原因、提供自动化脚本建议。请用中文回复，保持专业、简洁。'},
    ]
    for h in history:
        messages.append(h)
    messages.append({'role': 'user', 'content': message})

    result = call_llm(messages, model=model)
    if result.get('error'):
        logger.error(f"AI chat LLM error: {result['error']}")
        return Response({
            'reply': f'LLM 调用失败: {result["error"]}',
            'model': model,
            'tokens_used': 0,
            'timestamp': timezone.now().isoformat(),
            'error': True,
        })

    return Response({
        'reply': result['content'],
        'model': result['model'],
        'tokens_used': result['input_tokens'] + result['output_tokens'],
        'input_tokens': result['input_tokens'],
        'output_tokens': result['output_tokens'],
        'cost': result['cost'],
        'timestamp': timezone.now().isoformat(),
    })
