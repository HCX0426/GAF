"""Tests for JSONL-based anomaly detection (spec 阶段 4 — 任务 4.2).

Covers:
- _extract_patterns_from_jsonl: 从历史 JSONL 文件提取失败模式
- daily_anomaly_scan: Celery 定时任务
- JSONL 文件缺失时优雅降级
"""
import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from gaf_ai.views_anomaly import _extract_patterns_from_jsonl
from tasks.models import Task, TaskExecution


def _make_task(name='JSONL Anomaly Task', **kwargs):
    defaults = {
        'name': name,
        'execution_mode': Task.ExecutionMode.PIPELINE,
        'task_definition': {'nodes': []},
    }
    defaults.update(kwargs)
    return Task.objects.create(**defaults)


def _make_execution(task, user, status='failed', error_message='',
                     days_ago=0, structured_log_path=None):
    started = timezone.now() - timedelta(days=days_ago)
    snapshot = {}
    if structured_log_path:
        snapshot['structured_log_path'] = structured_log_path
    return TaskExecution.objects.create(
        task=task,
        triggered_by=user,
        status=status,
        error_message=error_message,
        started_at=started,
        execution_snapshot=snapshot,
    )


def _write_jsonl(tmp_path, lines):
    """Write a JSONL file with one JSON object per line."""
    import os
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    with open(tmp_path, 'w', encoding='utf-8') as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + '\n')
    return tmp_path


class ExtractPatternsFromJsonlTest(TestCase):
    """_extract_patterns_from_jsonl: 从 JSONL 提取失败模式."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='tester', password='pass',
        )
        self.task = _make_task()

    def test_extracts_failed_nodes_from_jsonl(self, ):
        """JSONL 中 success=False 的节点应被提取为失败模式."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = f'{tmpdir}/structured.jsonl'
            _write_jsonl(jsonl_path, [
                {'node_id': 'step_1', 'node_type': 'click',
                 'success': True, 'error_msg': ''},
                {'node_id': 'step_2', 'node_type': 'template_match',
                 'success': False, 'error_msg': 'Template not found at /path/x.png',
                 'error_code': 'NO_MATCH'},
                {'node_id': 'step_3', 'node_type': 'template_match',
                 'success': False, 'error_msg': 'Template not found at /path/y.png',
                 'error_code': 'NO_MATCH'},
            ])
            ex = _make_execution(self.task, self.user,
                                  structured_log_path=jsonl_path)

            patterns = _extract_patterns_from_jsonl([ex], min_occurrences=1)

            assert len(patterns) >= 1
            # 两个 template_match 失败应合并为一个模式
            top = patterns[0]
            assert top['occurrence_count'] >= 2
            assert 'template' in top['pattern_text'].lower() or \
                   'not found' in top['pattern_text'].lower()

    def test_skips_executions_with_missing_jsonl_file(self):
        """JSONL 文件不存在时应跳过该执行, 不报错."""
        ex = _make_execution(self.task, self.user,
                              structured_log_path='/nonexistent/path.jsonl')

        patterns = _extract_patterns_from_jsonl([ex], min_occurrences=1)

        assert patterns == []

    def test_skips_executions_without_structured_log_path(self):
        """没有 structured_log_path 的执行应被跳过."""
        ex = _make_execution(self.task, self.user,
                              error_message='some error')

        patterns = _extract_patterns_from_jsonl([ex], min_occurrences=1)

        assert patterns == []

    def test_returns_empty_for_no_failed_nodes_in_jsonl(self):
        """JSONL 中没有失败节点时返回空列表."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = f'{tmpdir}/structured.jsonl'
            _write_jsonl(jsonl_path, [
                {'node_id': 'step_1', 'success': True},
                {'node_id': 'step_2', 'success': True},
            ])
            ex = _make_execution(self.task, self.user,
                                  structured_log_path=jsonl_path)

            patterns = _extract_patterns_from_jsonl([ex], min_occurrences=1)

            assert patterns == []

    def test_aggregates_across_multiple_executions(self):
        """多个执行的 JSONL 失败模式应聚合统计."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl1 = f'{tmpdir}/exec1.jsonl'
            jsonl2 = f'{tmpdir}/exec2.jsonl'
            # 两条消息归一化后相同 (8位十六进制 → <HASH>)
            _write_jsonl(jsonl1, [
                {'node_id': 's1', 'node_type': 'ocr',
                 'success': False, 'error_msg': 'OCR failed: text=abcd1234',
                 'error_code': 'OCR_MISMATCH'},
            ])
            _write_jsonl(jsonl2, [
                {'node_id': 's2', 'node_type': 'ocr',
                 'success': False, 'error_msg': 'OCR failed: text=abcd5678',
                 'error_code': 'OCR_MISMATCH'},
            ])
            ex1 = _make_execution(self.task, self.user,
                                   structured_log_path=jsonl1)
            ex2 = _make_execution(self.task, self.user,
                                   structured_log_path=jsonl2)

            patterns = _extract_patterns_from_jsonl(
                [ex1, ex2], min_occurrences=1,
            )

            assert len(patterns) >= 1
            # 两个 OCR 失败应合并 (归一化后都变成 "OCR failed: text=<HASH>")
            top = patterns[0]
            assert top['occurrence_count'] >= 2


class DailyAnomalyScanTaskTest(TestCase):
    """daily_anomaly_scan Celery 任务测试."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='scan_user', password='pass',
        )
        self.task = _make_task()

    def test_task_runs_without_error_when_no_executions(self):
        """没有失败执行时任务应正常完成, 不抛异常."""
        from gaf_ai.tasks import daily_anomaly_scan
        # 不创建任何 TaskExecution
        result = daily_anomaly_scan()
        assert result is not None
        assert 'patterns' in result or result.get('status') == 'ok'

    def test_task_processes_failed_executions(self):
        """有失败执行时任务应提取模式."""
        import tempfile

        from gaf_ai.tasks import daily_anomaly_scan
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = f'{tmpdir}/failed.jsonl'
            _write_jsonl(jsonl_path, [
                {'node_id': 's1', 'node_type': 'click',
                 'success': False, 'error_msg': 'Click at 100,200 failed',
                 'error_code': 'CLICK_FAILED'},
            ])
            _make_execution(
                self.task, self.user,
                structured_log_path=jsonl_path,
                days_ago=0,
            )

            with mock.patch('gaf_ai.views_anomaly.write_anomaly_report') as mock_write:
                mock_write.return_value = '/tmp/report.md'
                result = daily_anomaly_scan()

            # 任务应成功完成
            assert result is not None


class CleanupStaleSessionsTaskTest(TestCase):
    """cleanup_stale_sessions Celery 任务测试 (S3 P4)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='cleanup_user', password='pass',
        )

    def _make_agent_session(self, status='running', days_ago=0, hours_ago=0):
        from gaf_ai.agent.models import AgentSession
        session = AgentSession.objects.create(
            user=self.user,
            session_type=AgentSession.SessionType.LOG_ANALYSIS,
            status=status,
        )
        if days_ago or hours_ago:
            # auto_now_add 覆盖显式传入的 created_at — 用 queryset.update 绕过
            backdated = timezone.now() - timedelta(days=days_ago, hours=hours_ago)
            AgentSession.objects.filter(pk=session.pk).update(created_at=backdated)
        return session

    def test_stale_running_session_marked_failed(self):
        """RUNNING 超 1h 的 session 标记 FAILED 并带 error_message."""
        from gaf_ai.agent.models import AgentSession
        from gaf_ai.tasks import cleanup_stale_sessions

        session = self._make_agent_session(status='running', hours_ago=2)

        result = cleanup_stale_sessions()

        session.refresh_from_db()
        assert result['running_failed'] == 1
        assert session.status == AgentSession.Status.FAILED
        assert 'cleanup_stale_sessions' in session.error_message
        assert session.completed_at is not None

    def test_fresh_running_session_untouched(self):
        """RUNNING 未超时的 session 保留."""
        from gaf_ai.agent.models import AgentSession
        from gaf_ai.tasks import cleanup_stale_sessions

        session = self._make_agent_session(status='running')

        result = cleanup_stale_sessions()

        session.refresh_from_db()
        assert result['running_failed'] == 0
        assert session.status == AgentSession.Status.RUNNING

    def test_stale_pending_session_marked_failed(self):
        """PENDING 超 24h 的 session 标记 FAILED."""
        from gaf_ai.agent.models import AgentSession
        from gaf_ai.tasks import cleanup_stale_sessions

        session = self._make_agent_session(status='pending', days_ago=2)

        result = cleanup_stale_sessions()

        session.refresh_from_db()
        assert result['pending_failed'] == 1
        assert session.status == AgentSession.Status.FAILED

    def test_qa_session_without_messages_deleted(self):
        """无消息且超 30 天的 QASession 被删除."""
        from gaf_ai.models import QASession
        from gaf_ai.tasks import cleanup_stale_sessions

        stale = QASession.objects.create(
            question='old question', user=self.user,
        )
        # auto_now_add 覆盖显式 created_at — 用 queryset.update 绕过
        QASession.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(days=31),
        )
        QASession.objects.create(
            question='fresh question', user=self.user,
        )

        result = cleanup_stale_sessions()

        assert result['qa_deleted'] == 1
        assert not QASession.objects.filter(pk=stale.pk).exists()

    def test_qa_session_with_messages_kept(self):
        """有消息的旧 QASession 保留 (可能是知识来源)."""
        from gaf_ai.models import QAMessage, QASession
        from gaf_ai.tasks import cleanup_stale_sessions

        session = QASession.objects.create(
            question='knowledge question', user=self.user,
        )
        # auto_now_add 覆盖显式 created_at — 用 queryset.update 绕过
        QASession.objects.filter(pk=session.pk).update(
            created_at=timezone.now() - timedelta(days=40),
        )
        QAMessage.objects.create(
            session=session, role=QAMessage.Role.USER, content='hi',
        )

        result = cleanup_stale_sessions()

        assert result['qa_deleted'] == 0
        assert QASession.objects.filter(pk=session.pk).exists()
