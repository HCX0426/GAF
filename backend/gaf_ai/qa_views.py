"""QA API views (migrated from qa app — 2026-08-04)."""

import logging

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiTypes, extend_schema
from gaf_core.audit_constants import AuditAction, AuditResourceType, get_client_ip
from gaf_core.mixins import AuditMixin, audit_action, build_diff_details
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import RoleBasedPermission
from gaf_ai.models import LLMUsageLog, QAMessage, QASession
from gaf_ai.qa_context_builder import build_qa_context
from gaf_ai.qa_cost_control import CostControlService
from gaf_ai.qa_llm_client import LLMAPIError, LLMTimeoutError
from gaf_ai.qa_serializers import (
    AskSerializer,
    LLMUsageLogSerializer,
    QAMessageSerializer,
    QASessionSerializer,
)

logger = logging.getLogger(__name__)

QA_HISTORY_LIMIT = 20


class QASessionViewSet(AuditMixin, viewsets.ModelViewSet):
    """问答会话视图集 (migrated from qa app)."""

    serializer_class = QASessionSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'llm_use'
    filterset_fields = ['is_knowledge_entry', 'user', 'model_name']
    search_fields = ['question', 'answer']
    audit_resource_type = AuditResourceType.QA_SESSION

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return QASession.objects.none()
        qs = QASession.objects.all().prefetch_related('messages')
        if self.request.user.role != 'admin':
            qs = qs.filter(user=self.request.user)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, serializer.instance)

    def _build_audit_details(self, action, instance, *, old_instance=None):
        snapshot_keys = ("title", "is_knowledge_entry", "model_name")
        sensitive = {"question", "answer", "context_snapshot"}
        if action == AuditAction.CREATE:
            return build_diff_details(before=None, after={k: getattr(instance, k, None) for k in snapshot_keys}, sensitive_extra=sensitive)
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k, None) for k in snapshot_keys},
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=sensitive,
            )
        if action == AuditAction.DELETE:
            return build_diff_details(before={k: getattr(instance, k, None) for k in snapshot_keys}, after=None, sensitive_extra=sensitive)
        return {}

    @action(detail=True, methods=['post'], url_path='mark-knowledge')
    @audit_action(AuditAction.UPDATE, AuditResourceType.QA_SESSION)
    def mark_knowledge(self, request, pk=None):
        session = self.get_object()
        is_knowledge = request.data.get('is_knowledge_entry', not session.is_knowledge_entry)
        if not isinstance(is_knowledge, bool):
            return Response({'detail': 'is_knowledge_entry 必须为布尔值'}, status=status.HTTP_400_BAD_REQUEST)
        session.is_knowledge_entry = is_knowledge
        session.save(update_fields=['is_knowledge_entry', 'updated_at'])
        return Response(QASessionSerializer(session).data)

    @action(detail=False, methods=['get'], url_path='budget')
    def budget(self, request):
        budget_info = CostControlService.check_budget(request.user.id)
        return Response(budget_info, status=status.HTTP_200_OK)


class AskView(APIView):
    """提问视图 (migrated from qa app)."""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'llm_use'

    @extend_schema(
        request=AskSerializer,
        responses={201: QASessionSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 429: OpenApiTypes.OBJECT, 503: OpenApiTypes.OBJECT},
        description="Submit a question to the LLM assistant.",
    )
    def post(self, request):
        serializer = AskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = serializer.validated_data['question']
        extra_context = serializer.validated_data.get('context', {})
        session_id = serializer.validated_data.get('session_id')

        from gaf_ai.feature_flags import is_ai_assistant_enabled
        if not is_ai_assistant_enabled():
            return Response({'error': 'AI assistant is disabled by feature flag'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if not CostControlService.check_rate_limit(request.user.id):
            return Response({'detail': '调用频率超限，请稍后再试'}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        budget_status = CostControlService.check_budget(request.user.id)
        if budget_status['status'] == 'exceeded':
            return Response({'detail': '月度 LLM 预算已超支，请联系管理员'}, status=status.HTTP_403_FORBIDDEN)

        context_result = build_qa_context(question, extra_context)
        context_text = context_result['context_text']
        model_name = request.data.get('model', 'gpt-4o-mini')

        if session_id:
            qs = QASession.objects.all()
            if request.user.role != 'admin':
                qs = qs.filter(user=request.user)
            session = get_object_or_404(qs, pk=session_id)
            history_qs = QAMessage.objects.filter(session_id=session.id).order_by('-created_at')[:QA_HISTORY_LIMIT]
            history_messages = [{'role': m.role, 'content': m.content} for m in reversed(list(history_qs))]
            is_new_session = False
        else:
            session = QASession.objects.create(
                question=question, title=question[:50],
                context_snapshot={'context_metadata': context_result['metadata']},
                answer='', user=request.user, model_name=model_name,
            )
            history_messages = []
            is_new_session = True

        QAMessage.objects.create(session=session, role=QAMessage.Role.USER, content=question)

        try:
            from gaf_ai.llm_service import call_llm
            messages = [{"role": "system", "content": f"你是 GAF 项目的智能助手，基于以下项目上下文回答用户问题。\n\n{context_text}"}]
            messages.extend(history_messages)
            messages.append({"role": "user", "content": question})

            result = call_llm(messages=messages, model=model_name)
            answer = result.get('content', '')
            model_used = result.get('model', model_name)
            input_tokens = result.get('input_tokens', 0)
            output_tokens = result.get('output_tokens', 0)

            session.answer = answer
            session.model_name = model_used
            if not is_new_session and not session.title:
                session.title = question[:50]
                session.save(update_fields=['answer', 'model_name', 'title', 'updated_at'])
            else:
                session.save(update_fields=['answer', 'model_name', 'updated_at'])

            QAMessage.objects.create(session=session, role=QAMessage.Role.ASSISTANT, content=answer)
            CostControlService.record_usage(
                user_id=request.user.id, model_name=model_used,
                input_tokens=input_tokens, output_tokens=output_tokens, call_type='qa',
            )
        except (LLMAPIError, LLMTimeoutError) as exc:
            logger.error("QA LLM 调用失败: %s", exc)
            session.answer = f"[LLM 调用失败: {exc}]"
            session.save(update_fields=['answer', 'updated_at'])
            QAMessage.objects.create(session=session, role=QAMessage.Role.ASSISTANT, content=session.answer)

        from accounts.audit import log_audit
        log_audit(
            user=request.user, action=AuditAction.EXECUTE,
            resource_type=AuditResourceType.QA_SESSION, resource_id=str(session.id),
            details={'question_length': len(question), 'session_id': session.id, 'model_name': model_name, 'is_new_session': is_new_session},
            ip_address=get_client_ip(request),
        )
        return Response(QASessionSerializer(session).data, status=status.HTTP_201_CREATED)


class QAMessageViewSet(AuditMixin, viewsets.ModelViewSet):
    """问答消息视图集 (migrated from qa app)."""

    queryset = QAMessage.objects.all()
    serializer_class = QAMessageSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'llm_use'
    filterset_fields = ['session', 'role']
    audit_resource_type = AuditResourceType.QA_MESSAGE

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return QAMessage.objects.none()
        user = self.request.user
        qs = QAMessage.objects.select_related('session')
        if user.role != 'admin':
            qs = qs.filter(session__user=user)
        session_id = self.request.query_params.get('session')
        if session_id:
            qs = qs.filter(session_id=session_id)
        return qs

    def perform_create(self, serializer):
        session = serializer.validated_data['session']
        user = self.request.user
        if user.role != 'admin' and session.user_id != user.id:
            from django.http import Http404
            raise Http404()
        serializer.save()
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, serializer.instance)

    def _build_audit_details(self, action, instance, *, old_instance=None):
        sensitive = {"content", "context", "answer"}
        def _snapshot(obj):
            data = {"role": getattr(obj, "role", None)}
            content = getattr(obj, "content", "") or ""
            data["content_length"] = len(content)
            return data
        if action == AuditAction.CREATE:
            return build_diff_details(before=None, after=_snapshot(instance), sensitive_extra=sensitive)
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(before=_snapshot(old_instance), after=_snapshot(instance), sensitive_extra=sensitive)
        if action == AuditAction.DELETE:
            return build_diff_details(before=_snapshot(instance), after=None, sensitive_extra=sensitive)
        return {}

    @action(detail=False, methods=['get'])
    def by_session(self, request):
        session_id = request.query_params.get('session')
        if not session_id:
            return Response({'error': 'session parameter required'}, status=status.HTTP_400_BAD_REQUEST)
        messages = self.get_queryset().filter(session_id=session_id).order_by('created_at')
        serializer = self.get_serializer(messages, many=True)
        return Response(serializer.data)


class LLMUsageLogViewSet(viewsets.ReadOnlyModelViewSet):
    """LLM 用量日志只读视图集 (migrated from qa app)."""

    queryset = LLMUsageLog.objects.all()
    serializer_class = LLMUsageLogSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'llm_use'
    filterset_fields = ['user', 'model_name', 'call_type']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return LLMUsageLog.objects.none()
        qs = super().get_queryset()
        if self.request.user.role != 'admin':
            qs = qs.filter(user=self.request.user)
        return qs
