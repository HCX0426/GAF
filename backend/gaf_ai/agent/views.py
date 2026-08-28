"""Agent views — POST endpoint to dispatch LangGraph ReAct analysis, plus
GET endpoint for the frontend to poll session status.

POST /api/v2/ai/agent/analyze/         -> dispatch Celery task, return pending
GET  /api/v2/ai/agent/sessions/<id>/   -> poll session status + result

The reasoning-chain parsing helpers (_run_agent_analysis,
_extract_reasoning_steps, _serialize_messages, _parse_agent_result)
were moved to ai/tasks.py so the async Celery task owns the full
analysis pipeline; this module stays a thin HTTP layer.
"""
import logging

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status as http_status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import RoleBasedPermission, require_permission

from .models import AgentSession

logger = logging.getLogger(__name__)


@extend_schema(
    tags=['ai', 'agent'],
    summary='Dispatch deep analysis via LangGraph ReAct agent (async)',
    description=(
        'Creates an AgentSession in PENDING status and dispatches the '
        'LangGraph ReAct analysis task to Celery. Returns immediately '
        'with the session_id so the client can poll '
        'GET /api/v2/ai/agent/sessions/<id>/ for the final result. '
        'The agent autonomously calls tools (get_execution_detail, '
        'get_execution_steps, search_similar_errors, get_task_config) '
        'to diagnose a failed execution.'
    ),
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'execution_id': {'type': 'integer', 'description': 'TaskExecution ID to analyze'},
            },
            'required': ['execution_id'],
        },
    },
    responses={
        202: {
            'type': 'object',
            'properties': {
                'session_id': {'type': 'integer'},
                'status': {'type': 'string', 'enum': ['pending']},
                'message': {'type': 'string'},
            },
        },
        400: {'description': 'Missing execution_id'},
        403: {'description': 'Permission denied'},
        404: {'description': 'Execution not found'},
    },
    examples=[
        OpenApiExample(
            'Dispatched',
            value={
                'session_id': 42,
                'status': 'pending',
                'message': 'Analysis dispatched. Poll GET /api/v2/ai/agent/sessions/42/ for results.',
            },
            status_codes=['202'],
        ),
    ],
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission('view')
def agent_analyze_view(request):
    """POST /api/v2/ai/agent/analyze/ — dispatch async ReAct analysis.

    Request body: {"execution_id": int}
    Response 202: {
        "session_id": int,
        "status": "pending",
        "message": "Analysis dispatched. Poll GET .../sessions/<id>/ for results."
    }
    """
    # @api_view allowed: Agent orchestration over multiple data sources, not model CRUD
    execution_id = request.data.get('execution_id')
    if not execution_id:
        return Response(
            {'error': 'execution_id is required'},
            status=http_status.HTTP_400_BAD_REQUEST,
        )

    # Verify the execution exists and user has access
    try:
        from tasks.models import TaskExecution

        execution = TaskExecution.objects.get(pk=execution_id)
    except TaskExecution.DoesNotExist:
        return Response(
            {'error': f'Execution #{execution_id} not found'},
            status=http_status.HTTP_404_NOT_FOUND,
        )

    if request.user.role != 'admin' and execution.triggered_by_id != request.user.id:
        return Response(
            {'error': 'Permission denied'},
            status=http_status.HTTP_403_FORBIDDEN,
        )

    # Create the session record in PENDING state — the Celery task will
    # transition it to RUNNING -> COMPLETED | FAILED.
    session = AgentSession.objects.create(
        user=request.user,
        session_type=AgentSession.SessionType.LOG_ANALYSIS,
        target_id=execution_id,
        status=AgentSession.Status.PENDING,
    )

    # Dispatch the async task
    from gaf_ai.tasks import run_agent_analysis_task

    run_agent_analysis_task.delay(session.id, execution_id)

    return Response(
        {
            'session_id': session.id,
            'status': 'pending',
            'message': (
                f'Analysis dispatched. Poll GET /api/v2/ai/agent/sessions/'
                f'{session.id}/ for results.'
            ),
        },
        status=http_status.HTTP_202_ACCEPTED,
    )


@extend_schema(
    tags=['ai', 'agent'],
    summary='Poll AgentSession status + result',
    description=(
        'Returns the current status of an AgentSession. When status is '
        '"completed" or "failed", the full reasoning chain, summary, '
        'and suggestions are included. Used by the frontend to poll '
        'after POST /api/v2/ai/agent/analyze/ returns a session_id.'
    ),
    responses={
        200: {
            'type': 'object',
            'properties': {
                'session_id': {'type': 'integer'},
                'status': {'type': 'string', 'enum': ['pending', 'running', 'completed', 'failed']},
                'model_used': {'type': 'string'},
                'reasoning_steps': {'type': 'array'},
                'summary': {'type': 'string'},
                'suggestions': {'type': 'array'},
                'total_tokens': {'type': 'integer'},
                'error': {'type': 'string', 'nullable': True},
            },
        },
        404: {'description': 'Session not found'},
    },
    examples=[
        OpenApiExample(
            'Completed',
            value={
                'session_id': 42,
                'status': 'completed',
                'model_used': 'deepseek-chat',
                'reasoning_steps': [
                    {
                        'thought': 'Getting execution detail first',
                        'action': 'get_execution_detail',
                        'action_input': {'execution_id': 42},
                        'observation': '{"execution_id": 42, "status": "failed", ...}',
                    },
                ],
                'summary': '执行 #42 在第 3 步模板匹配失败...',
                'suggestions': ['更新模板 X', '检查设备分辨率'],
                'total_tokens': 1500,
                'error': None,
            },
        ),
        OpenApiExample(
            'Pending',
            value={
                'session_id': 42,
                'status': 'pending',
                'model_used': '',
                'reasoning_steps': [],
                'summary': '',
                'suggestions': [],
                'total_tokens': 0,
                'error': None,
            },
        ),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission('view')
def agent_session_status_view(request, session_id: int):
    """GET /api/v2/ai/agent/sessions/<session_id>/ — poll session status.

    Returns the current state of the AgentSession. The frontend polls
    this endpoint every few seconds after dispatching analysis until
    status becomes 'completed' or 'failed'.
    """
    try:
        session = AgentSession.objects.get(pk=session_id)
    except AgentSession.DoesNotExist:
        return Response(
            {'error': f'Session #{session_id} not found'},
            status=http_status.HTTP_404_NOT_FOUND,
        )

    # Permission: only the session owner or admin can view
    if request.user.role != 'admin' and session.user_id != request.user.id:
        return Response(
            {'error': 'Permission denied'},
            status=http_status.HTTP_403_FORBIDDEN,
        )

    return Response(
        {
            'session_id': session.id,
            'status': session.status,
            'model_used': session.model_used,
            'reasoning_steps': session.reasoning_steps or [],
            'summary': session.final_summary or '',
            'suggestions': session.final_suggestions or [],
            'evidence': session.evidence or [],
            'evidence_check': session.evidence_check or None,
            'total_tokens': session.total_tokens,
            'error': session.error_message or None,
        },
        status=http_status.HTTP_200_OK,
    )
