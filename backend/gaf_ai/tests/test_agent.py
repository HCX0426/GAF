# Merged from test_agent_async.py, test_agent_tools.py, test_agent_reasoning.py - 2026-08-04

import json
import os
import shutil
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gaf_ai.agent.models import AgentSession
from gaf_ai.agent.tools import (
    _search_similar_errors_via_jsonl,
    get_execution_detail,
    get_execution_steps,
    get_screenshot_base64,
    get_structured_log,
    get_task_config,
    search_similar_errors,
    text_similarity,
)
from gaf_ai.tasks import (
    _extract_reasoning_steps,
    _parse_agent_result,
    _serialize_messages,
    _verify_evidence,
    run_agent_analysis_task,
)
from tasks.models import Task, TaskExecution, ExecutionStep

User = get_user_model()

pytestmark = pytest.mark.unit

# ── Helper functions from test_agent_tools.py ────────────────────

def _make_task(name='Test Task', **kwargs):
    """Create a minimal Task with only required fields."""
    defaults = {
        'name': name,
        'description': 'Test description',
        'execution_mode': Task.ExecutionMode.PIPELINE,
        'task_definition': {'nodes': []},
    }
    defaults.update(kwargs)
    return Task.objects.create(**defaults)


def _make_execution(task, status='failed', **kwargs):
    """Create a minimal TaskExecution."""
    defaults = {
        'task': task,
        'status': status,
        'started_at': timezone.now() - timedelta(minutes=5),
        'completed_at': timezone.now(),
        'duration': timedelta(seconds=300),
        'error_message': 'Template match failed',
        'recovery_attempts': 0,
        'recovery_layer': 0,
    }
    defaults.update(kwargs)
    return TaskExecution.objects.create(**defaults)


def _make_step(execution, index=0, name='screenshot', status='success', **kwargs):
    """Create a minimal ExecutionStep."""
    defaults = {
        'execution': execution,
        'step_index': index,
        'step_name': name,
        'step_type': 'action',
        'status': status,
        'duration': timedelta(seconds=2),
        'started_at': timezone.now() - timedelta(minutes=4),
        'completed_at': timezone.now() - timedelta(minutes=3),
    }
    defaults.update(kwargs)
    return ExecutionStep.objects.create(**defaults)


# ── Helper functions from test_agent_async.py ────────────────────

def _make_user(username='admin', role='admin', password='admin123'):
    user = User.objects.create_user(username=username, password=password)
    user.role = role
    user.save(update_fields=['role'])
    return user


def _make_ai_message(content='', model_name='', total_tokens=0):
    """Create a mock AIMessage whose type name is 'AIMessage'.

    The extraction logic uses ``type(msg).__name__ == 'AIMessage'``, so we
    build a class named 'AIMessage' and instantiate it (the class itself
    would have type 'type', not 'AIMessage').
    """
    cls = type('AIMessage', (object,), {})
    obj = cls()
    obj.content = content
    obj.tool_calls = []
    obj.response_metadata = {
        'model_name': model_name,
        'token_usage': {'total_tokens': total_tokens},
    }
    return obj


# ── Helper functions from test_agent_reasoning.py ────────────────

def _ai_message(content='', tool_calls=None):
    """Mock a LangChain AIMessage.

    Args:
        content: The text content of the message.
        tool_calls: Optional list of {'name': str, 'args': dict, 'id': str}.
    """
    return SimpleNamespace(
        __class__=type('AIMessage', (), {}),
        content=content,
        tool_calls=tool_calls or [],
    )


def _tool_message(content='', tool_call_id=''):
    """Mock a LangChain ToolMessage (the result of a tool call)."""
    return SimpleNamespace(
        __class__=type('ToolMessage', (), {}),
        content=content,
        tool_call_id=tool_call_id,
        tool_calls=[],
    )


def _make_reasoning_ai_message(content='', tool_calls=None):
    """Create a mock AIMessage whose type name is 'AIMessage'.

    The extraction logic uses ``type(msg).__name__ == 'AIMessage'``, so we
    need the mock's class to be named 'AIMessage'.
    """
    cls = type('AIMessage', (object,), {})
    obj = cls()
    obj.content = content
    obj.tool_calls = tool_calls or []
    return obj


def _make_reasoning_tool_message(content='', tool_call_id=''):
    """Create a mock ToolMessage whose type name is 'ToolMessage'."""
    cls = type('ToolMessage', (object,), {})
    obj = cls()
    obj.content = content
    obj.tool_call_id = tool_call_id
    obj.tool_calls = []
    return obj


# ══════════════════════════════════════════════════════════════════
#  Test classes from test_agent_tools.py
# ══════════════════════════════════════════════════════════════════

# ── get_execution_detail tests ──────────────────────────────────
class GetExecutionDetailTest(TestCase):
    """Tests for get_execution_detail @tool."""

    def test_existing_execution_returns_json(self):
        task = _make_task(name='MyTask')
        ex = _make_execution(task, status='failed', error_message='boom')

        # @tool wraps the function in a StructuredTool; .invoke() calls it.
        result_str = get_execution_detail.invoke({'execution_id': ex.id})
        result = json.loads(result_str)

        self.assertEqual(result['execution_id'], ex.id)
        self.assertEqual(result['task_name'], 'MyTask')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['last_error'], 'boom')
        self.assertEqual(result['duration_seconds'], 300.0)

    def test_nonexistent_execution_returns_error_message(self):
        result = get_execution_detail.invoke({'execution_id': 999999})

        self.assertIn('not found', result)
        self.assertIn('999999', result)

    def test_execution_without_task_shows_unknown(self):
        """If task FK is null, task_name should be 'Unknown'."""
        ex = _make_execution(task=None, status='success')

        result_str = get_execution_detail.invoke({'execution_id': ex.id})
        result = json.loads(result_str)

        self.assertEqual(result['task_name'], 'Unknown')

    def test_execution_without_error_shows_none(self):
        """error_message null → 'last_error': None."""
        task = _make_task()
        ex = _make_execution(task, error_message='')

        result_str = get_execution_detail.invoke({'execution_id': ex.id})
        result = json.loads(result_str)

        self.assertIsNone(result['last_error'])


# ── get_execution_steps tests ───────────────────────────────────
class GetExecutionStepsTest(TestCase):
    """Tests for get_execution_steps @tool."""

    def test_execution_with_multiple_steps_returns_list(self):
        task = _make_task()
        ex = _make_execution(task)
        _make_step(ex, index=0, name='screenshot', status='success')
        _make_step(ex, index=1, name='template_match', status='failed',
                   error_message='not found')
        _make_step(ex, index=2, name='click', status='skipped')

        result_str = get_execution_steps.invoke({'execution_id': ex.id})
        result = json.loads(result_str)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['index'], 0)
        self.assertEqual(result[0]['name'], 'screenshot')
        self.assertEqual(result[1]['status'], 'failed')
        self.assertEqual(result[1]['error'], 'not found')
        self.assertEqual(result[2]['status'], 'skipped')

    def test_execution_with_no_steps_returns_message(self):
        task = _make_task()
        ex = _make_execution(task)

        result = get_execution_steps.invoke({'execution_id': ex.id})

        self.assertIn('no steps', result)
        self.assertIn(str(ex.id), result)

    def test_nonexistent_execution_returns_no_steps_message(self):
        """An execution that doesn't exist will have no steps (queryset empty)."""
        result = get_execution_steps.invoke({'execution_id': 999999})

        self.assertIn('no steps', result)

    def test_steps_ordered_by_step_index(self):
        """Steps should be returned in step_index order, not creation order."""
        task = _make_task()
        ex = _make_execution(task)
        # Create out of order
        _make_step(ex, index=2, name='third')
        _make_step(ex, index=0, name='first')
        _make_step(ex, index=1, name='second')

        result_str = get_execution_steps.invoke({'execution_id': ex.id})
        result = json.loads(result_str)

        self.assertEqual(result[0]['name'], 'first')
        self.assertEqual(result[1]['name'], 'second')
        self.assertEqual(result[2]['name'], 'third')

    def test_step_with_retry_count(self):
        task = _make_task()
        ex = _make_execution(task)
        _make_step(ex, index=0, name='retry_step', status='failed', retry_count=3)

        result_str = get_execution_steps.invoke({'execution_id': ex.id})
        result = json.loads(result_str)

        self.assertEqual(result[0]['retry_count'], 3)


# ── search_similar_errors tests (JSONL fallback path) ──────────
class SearchSimilarErrorsTest(TestCase):
    """Tests for search_similar_errors @tool — JSONL fallback path.

    spec §7.3.2 (任务 4.6, 2026-07-26 修正): SQL fallback replaced by
    JSONL log scan. The fallback queries
    ``TaskExecution.execution_snapshot['structured_log_path']`` for
    failed executions (default last 30 days) and reads the structured
    JSONL log at that path. Tests create real TaskExecution rows (with
    execution_snapshot.structured_log_path) + real JSONL files on disk,
    exercising the full data flow.

    These tests mock RAG to return [] so the JSONL fallback path is
    exercised in isolation. The RAG-primary path is covered by
    SearchSimilarErrorsRAGTest below.
    """

    def setUp(self):
        """Mock RAG to return empty + create temp dir for JSONL files."""
        fake_retriever = MagicMock()
        fake_retriever.search.return_value = []
        self._rag_patch = patch('gaf_ai.rag.get_rag_retriever', return_value=fake_retriever)
        self._rag_patch.start()

        # Temp dir for JSONL files (one per execution). The path is
        # stored in TaskExecution.execution_snapshot['structured_log_path']
        # — the fallback scans DB, not the filesystem, so we just need
        # a writable location.
        self._jsonl_dir = tempfile.mkdtemp(prefix='gaf_test_jsonl_')

    def tearDown(self):
        self._rag_patch.stop()
        shutil.rmtree(self._jsonl_dir, ignore_errors=True)

    def _make_failed_execution_with_jsonl(
        self, exec_id: int, events: list[dict], **exec_kwargs,
    ) -> TaskExecution:
        """Create a failed TaskExecution + write its structured.jsonl.

        Args:
            exec_id: Used as TaskExecution pk (must not clash with other
                tests in the same DB fixture — use unique values).
            events: List of dicts to serialize as JSONL lines.
            **exec_kwargs: Override default TaskExecution fields.

        Returns:
            The saved TaskExecution instance.
        """
        task = _make_task(name=f'Task for exec {exec_id}')
        # Write JSONL file: <jsonl_dir>/<exec_id>.jsonl
        jsonl_path = os.path.join(self._jsonl_dir, f'{exec_id}.jsonl')
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for evt in events:
                f.write(json.dumps(evt) + '\n')
        defaults = {
            'status': TaskExecution.Status.FAILED,
            'started_at': timezone.now() - timedelta(minutes=10),
            'completed_at': timezone.now() - timedelta(minutes=5),
            'duration': timedelta(seconds=300),
            'error_message': 'Template match failed',
            'execution_snapshot': {'structured_log_path': jsonl_path},
        }
        defaults.update(exec_kwargs)
        return _make_execution(task, **defaults)

    def test_finds_matching_errors_via_jsonl_fallback(self):
        """When RAG returns nothing, JSONL fallback finds matches."""
        self._make_failed_execution_with_jsonl(1001, [
            {'execution_id': 1001, 'success': False,
             'error_msg': 'Template match failed: btn.png not found',
             'node_id': 'match_btn', 'node_type': 'template_match',
             'error_code': 'TEMPLATE_NOT_FOUND', 'timestamp': '2026-07-26T10:00:00+08:00'},
        ])
        self._make_failed_execution_with_jsonl(1002, [
            {'execution_id': 1002, 'success': False,
             'error_msg': 'Template match failed: icon.png not found',
             'node_id': 'match_icon', 'node_type': 'template_match',
             'error_code': 'TEMPLATE_NOT_FOUND', 'timestamp': '2026-07-26T11:00:00+08:00'},
        ])

        result_str = search_similar_errors.invoke({'error_text': 'Template match failed'})
        result = json.loads(result_str)

        self.assertEqual(result['source'], 'jsonl_fallback')
        self.assertEqual(len(result['matches']), 2)
        for m in result['matches']:
            self.assertIn('Template match failed', m['error'])
            self.assertGreater(m['similarity'], 0.5)
            self.assertIn('jsonl_path', m)
            self.assertIn('node_type', m)

    def test_too_short_error_text_returns_message(self):
        result = search_similar_errors.invoke({'error_text': 'ab'})

        self.assertIn('too short', result)

    def test_empty_error_text_returns_message(self):
        result = search_similar_errors.invoke({'error_text': ''})

        self.assertIn('too short', result)

    def test_no_matches_returns_none_source(self):
        """When neither RAG nor JSONL finds matches, source is 'none'."""
        # Failed execution exists, but its error_msg is unrelated.
        self._make_failed_execution_with_jsonl(1001, [
            {'execution_id': 1001, 'success': False,
             'error_msg': 'completely unrelated error text xyz',
             'node_id': 's1', 'node_type': 'click'},
        ])

        result_str = search_similar_errors.invoke({'error_text': 'nonexistent_error_xyz123'})
        result = json.loads(result_str)

        self.assertEqual(result['source'], 'none')
        self.assertEqual(result['matches'], [])
        self.assertIn('No similar errors', result['message'])

    def test_searches_error_msg_field_in_jsonl(self):
        """The JSONL fallback scans error_msg field of failed events."""
        self._make_failed_execution_with_jsonl(2001, [
            {'execution_id': 2001, 'success': False,
             'error_msg': 'DB connection lost at startup',
             'node_id': 's1', 'node_type': 'init'},
        ])

        result_str = search_similar_errors.invoke({'error_text': 'DB connection'})
        result = json.loads(result_str)

        self.assertEqual(result['source'], 'jsonl_fallback')
        self.assertEqual(len(result['matches']), 1)
        self.assertIn('DB connection', result['matches'][0]['error'])

    def test_returns_at_most_10_results(self):
        """JSONL fallback caps matches at top_k=10."""
        # 15 failed executions each with one matching error.
        for i in range(15):
            self._make_failed_execution_with_jsonl(3000 + i, [
                {'execution_id': 3000 + i, 'success': False,
                 'error_msg': f'Template match failed #{i}',
                 'node_id': 's1', 'node_type': 'template_match'},
            ])

        result_str = search_similar_errors.invoke({'error_text': 'Template match failed'})
        result = json.loads(result_str)

        self.assertEqual(len(result['matches']), 10)
        # Verify sorted by similarity descending.
        sims = [m['similarity'] for m in result['matches']]
        self.assertEqual(sims, sorted(sims, reverse=True))

    def test_skips_successful_events(self):
        """JSONL fallback must only scan success=False events."""
        self._make_failed_execution_with_jsonl(4001, [
            {'execution_id': 4001, 'success': True,
             'error_msg': 'Template match failed',  # would match if scanned
             'node_id': 's1', 'node_type': 'template_match'},
        ])

        result_str = search_similar_errors.invoke({'error_text': 'Template match failed'})
        result = json.loads(result_str)

        self.assertEqual(result['source'], 'none')

    def test_corrupted_jsonl_lines_are_skipped(self):
        """Malformed JSON lines in JSONL must not crash the scan."""
        # Write a JSONL file with corrupted + valid lines.
        exec_id = 5001
        jsonl_path = os.path.join(self._jsonl_dir, f'{exec_id}.jsonl')
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            f.write('this is not json\n')
            f.write('  \n')  # blank line
            f.write(json.dumps({
                'execution_id': exec_id, 'success': False,
                'error_msg': 'Template match failed after corruption',
                'node_id': 's1', 'node_type': 'template_match',
            }) + '\n')
        task = _make_task(name=f'Task for exec {exec_id}')
        _make_execution(
            task, status=TaskExecution.Status.FAILED,
            started_at=timezone.now() - timedelta(minutes=10),
            completed_at=timezone.now() - timedelta(minutes=5),
            duration=timedelta(seconds=300),
            error_message='Template match failed',
            execution_snapshot={'structured_log_path': jsonl_path},
        )

        result_str = search_similar_errors.invoke({'error_text': 'Template match failed'})
        result = json.loads(result_str)

        self.assertEqual(result['source'], 'jsonl_fallback')
        self.assertEqual(len(result['matches']), 1)
        self.assertIn('Template match failed', result['matches'][0]['error'])

    def test_skips_executions_without_structured_log_path(self):
        """Failed executions with no structured_log_path are skipped silently."""
        # Execution 1: no execution_snapshot.structured_log_path.
        task = _make_task(name='No snapshot task')
        _make_execution(
            task, status=TaskExecution.Status.FAILED,
            error_message='Template match failed',
            execution_snapshot={},  # no structured_log_path
        )
        # Execution 2: has structured_log_path, will be scanned.
        ex2 = self._make_failed_execution_with_jsonl(6002, [
            {'execution_id': 6002, 'success': False,
             'error_msg': 'Template match failed in second exec',
             'node_id': 's1', 'node_type': 'template_match'},
        ])

        result_str = search_similar_errors.invoke({'error_text': 'Template match failed'})
        result = json.loads(result_str)

        self.assertEqual(result['source'], 'jsonl_fallback')
        self.assertEqual(len(result['matches']), 1)
        # execution_id is TaskExecution.pk (DB auto-increment), not the
        # helper's exec_id arg (which is only used for file naming).
        self.assertEqual(result['matches'][0]['execution_id'], ex2.pk)

    def test_skips_executions_with_missing_jsonl_file(self):
        """Failed executions whose JSONL file is gone are skipped silently."""
        # Point structured_log_path at a path that does not exist.
        task = _make_task(name='Missing file task')
        _make_execution(
            task, status=TaskExecution.Status.FAILED,
            error_message='Template match failed',
            execution_snapshot={
                'structured_log_path': '/nonexistent/path/missing.jsonl',
            },
        )
        # Add a real matching execution to ensure scan continues.
        ex2 = self._make_failed_execution_with_jsonl(6004, [
            {'execution_id': 6004, 'success': False,
             'error_msg': 'Template match failed in real exec',
             'node_id': 's1', 'node_type': 'template_match'},
        ])

        result_str = search_similar_errors.invoke({'error_text': 'Template match failed'})
        result = json.loads(result_str)

        self.assertEqual(result['source'], 'jsonl_fallback')
        self.assertEqual(len(result['matches']), 1)
        # execution_id is TaskExecution.pk (DB auto-increment), not the
        # helper's exec_id arg (which is only used for file naming).
        self.assertEqual(result['matches'][0]['execution_id'], ex2.pk)

    def test_skips_non_failed_executions(self):
        """Only status=FAILED executions are scanned by default queryset."""
        # Successful execution with a matching error_msg — should be skipped.
        self._make_failed_execution_with_jsonl(
            6005,
            [{'execution_id': 6005, 'success': False,
              'error_msg': 'Template match failed', 'node_id': 's1'}],
            status=TaskExecution.Status.SUCCESS,  # override to success
        )

        result_str = search_similar_errors.invoke({'error_text': 'Template match failed'})
        result = json.loads(result_str)

        self.assertEqual(result['source'], 'none')


# ── search_similar_errors RAG path tests ────────────────────────
class SearchSimilarErrorsRAGTest(TestCase):
    """Tests for the RAG-primary path of search_similar_errors.

    Mocks ai.rag.get_rag_retriever to control whether RAG returns
    matches, empty list, or raises — verifying the fallback contract.
    """

    def setUp(self):
        self._jsonl_dir = tempfile.mkdtemp(prefix='gaf_test_rag_jsonl_')

    def tearDown(self):
        shutil.rmtree(self._jsonl_dir, ignore_errors=True)

    def _mock_rag(self, docs):
        """Patch ai.rag.get_rag_retriever to return a fake retriever yielding `docs`."""
        fake_retriever = MagicMock()
        fake_retriever.search.return_value = docs
        return patch('gaf_ai.rag.get_rag_retriever', return_value=fake_retriever)

    def _make_failed_execution_with_jsonl(self, exec_id, events):
        """Create a failed TaskExecution + JSONL file (data flow helper)."""
        jsonl_path = os.path.join(self._jsonl_dir, f'{exec_id}.jsonl')
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for evt in events:
                f.write(json.dumps(evt) + '\n')
        task = _make_task(name=f'Task for exec {exec_id}')
        _make_execution(
            task, status=TaskExecution.Status.FAILED,
            started_at=timezone.now() - timedelta(minutes=10),
            completed_at=timezone.now() - timedelta(minutes=5),
            duration=timedelta(seconds=300),
            error_message='Template match failed',
            execution_snapshot={'structured_log_path': jsonl_path},
        )

    def test_rag_returns_matches_uses_rag_source(self):
        """When RAG returns matches, source='rag' and JSONL is not scanned."""
        docs = [
            {'content': 'def foo(): ...', 'filepath': '/a/b.py', 'filename': 'b.py', 'type': 'code', 'score': 0.1},
            {'content': 'Q: how to fix X', 'filepath': '', 'filename': '', 'type': 'qa_history', 'score': 0.3},
        ]

        with self._mock_rag(docs):
            result_str = search_similar_errors.invoke({'error_text': 'Template match failed'})
        result = json.loads(result_str)

        self.assertEqual(result['source'], 'rag')
        self.assertEqual(len(result['matches']), 2)
        self.assertEqual(result['matches'][0]['filepath'], '/a/b.py')
        self.assertEqual(result['matches'][1]['type'], 'qa_history')

    def test_rag_returns_empty_falls_back_to_jsonl(self):
        """When RAG returns [], source='jsonl_fallback' with archive matches."""
        self._make_failed_execution_with_jsonl(7001, [
            {'execution_id': 7001, 'success': False,
             'error_msg': 'Template match failed: btn.png not found',
             'node_id': 's1', 'node_type': 'template_match'},
        ])

        with self._mock_rag([]):
            result_str = search_similar_errors.invoke({'error_text': 'Template match failed'})
        result = json.loads(result_str)

        self.assertEqual(result['source'], 'jsonl_fallback')
        self.assertEqual(len(result['matches']), 1)
        self.assertIn('Template match failed', result['matches'][0]['error'])

    def test_rag_raises_falls_back_to_jsonl(self):
        """When RAG raises an exception, source='jsonl_fallback' (never block)."""
        self._make_failed_execution_with_jsonl(8001, [
            {'execution_id': 8001, 'success': False,
             'error_msg': 'Template match failed: icon.png',
             'node_id': 's1', 'node_type': 'template_match'},
        ])
        fake_retriever = MagicMock()
        fake_retriever.search.side_effect = RuntimeError('chromadb down')
        with patch('gaf_ai.rag.get_rag_retriever', return_value=fake_retriever):
            result_str = search_similar_errors.invoke({'error_text': 'Template match failed'})
        result = json.loads(result_str)

        self.assertEqual(result['source'], 'jsonl_fallback')
        self.assertEqual(len(result['matches']), 1)

    def test_rag_empty_and_jsonl_empty_returns_none_source(self):
        """When both RAG and JSONL return nothing, source='none'."""
        with self._mock_rag([]):
            result_str = search_similar_errors.invoke({'error_text': 'unique_error_xyz'})
        result = json.loads(result_str)

        self.assertEqual(result['source'], 'none')
        self.assertEqual(result['matches'], [])


# ── get_task_config tests ───────────────────────────────────────
class GetTaskConfigTest(TestCase):
    """Tests for get_task_config @tool."""

    def test_existing_task_returns_json(self):
        task = _make_task(
            name='MyPipeline',
            description='A test pipeline',
            execution_mode='pipeline',
            params_config={'retry': True},
            # spec-2026-07-27-execution-path-unification: task_definition
            # 使用 pipeline schema ({nodes: [{node_type, ...}]}), chain schema
            # ({steps: [{action, ...}]}) 已废弃.
            task_definition={'nodes': [{'id': 'step1', 'name': 'step1', 'node_type': 'click'}]},
        )

        result_str = get_task_config.invoke({'task_id': task.id})
        result = json.loads(result_str)

        self.assertEqual(result['task_id'], task.id)
        self.assertEqual(result['task_name'], 'MyPipeline')
        self.assertEqual(result['description'], 'A test pipeline')
        # S3 P3: use real Task fields (execution_mode / task_definition /
        # params_config) instead of nonexistent task_type / pipeline_config
        self.assertEqual(result['execution_mode'], 'pipeline')
        self.assertEqual(result['params_config'], {'retry': True})
        self.assertEqual(
            result['task_definition'],
            {'nodes': [{'id': 'step1', 'name': 'step1', 'node_type': 'click'}]},
        )

    def test_nonexistent_task_returns_error_message(self):
        result = get_task_config.invoke({'task_id': 999999})

        self.assertIn('not found', result)
        self.assertIn('999999', result)

    def test_disabled_task_shows_is_enabled_false(self):
        task = _make_task(name='Disabled', is_enabled=False)

        result_str = get_task_config.invoke({'task_id': task.id})
        result = json.loads(result_str)

        self.assertFalse(result['is_enabled'])


# ── Tool decorator interface tests ──────────────────────────────
class ToolDecoratorInterfaceTest(TestCase):
    """Verify the @tool decorator metadata is correctly set up.

    LangChain @tool decorator wraps functions in StructuredTool objects
    with .name, .description, .args_schema properties. These tests verify
    the wrapping didn't break anything.
    """

    def test_all_tools_have_names(self):
        for tool_obj in [get_execution_detail, get_execution_steps,
                         search_similar_errors, get_task_config,
                         get_screenshot_base64, get_structured_log]:
            self.assertIsNotNone(tool_obj.name, f'{tool_obj} has no name')
            self.assertIsInstance(tool_obj.name, str)

    def test_all_tools_have_descriptions(self):
        for tool_obj in [get_execution_detail, get_execution_steps,
                         search_similar_errors, get_task_config,
                         get_screenshot_base64, get_structured_log]:
            self.assertIsNotNone(tool_obj.description)
            self.assertIsInstance(tool_obj.description, str)
            self.assertTrue(len(tool_obj.description) > 10,
                            f'{tool_obj.name} description too short')

    def test_tool_names_match_function_names(self):
        """The @tool decorator should use the function name as the tool name."""
        self.assertEqual(get_execution_detail.name, 'get_execution_detail')
        self.assertEqual(get_execution_steps.name, 'get_execution_steps')
        self.assertEqual(search_similar_errors.name, 'search_similar_errors')
        self.assertEqual(get_task_config.name, 'get_task_config')
        self.assertEqual(get_screenshot_base64.name, 'get_screenshot_base64')
        self.assertEqual(get_structured_log.name, 'get_structured_log')

    def test_tools_are_callable_via_invoke(self):
        """Each tool should be callable via .invoke() with dict args."""
        task = _make_task()
        ex = _make_execution(task)

        # Should not raise
        result = get_execution_detail.invoke({'execution_id': ex.id})
        self.assertIsInstance(result, str)

        result = get_execution_steps.invoke({'execution_id': ex.id})
        self.assertIsInstance(result, str)

        result = search_similar_errors.invoke({'error_text': 'test error xyz'})
        self.assertIsInstance(result, str)

        result = get_task_config.invoke({'task_id': task.id})
        self.assertIsInstance(result, str)

        result = get_screenshot_base64.invoke({
            'execution_id': ex.id, 'raw': False,
        })
        self.assertIsInstance(result, str)

        result = get_structured_log.invoke({'execution_id': ex.id})
        self.assertIsInstance(result, str)


# ── Exception isolation tests (S5 Task A2 / P2-3) ──────────────
class ToolExceptionIsolationTest(TestCase):
    """Verify each @tool returns a JSON error envelope on unexpected exceptions.

    P2-3 contract: a tool that raises an unhandled exception would crash the
    ReAct loop. Each @tool is wrapped in a top-level try/except that returns
    ``{"error": "...", "tool": "<name>"}`` instead. These tests force the
    underlying DB query to raise OperationalError and assert the tool result
    is a JSON error string — never a propagated exception.
    """

    def _assert_error_envelope(self, result_str: str, expected_tool: str):
        """Helper: parse the tool result and assert it is an error envelope.

        Args:
            result_str: The string returned by the @tool.
            expected_tool: The expected ``tool`` field in the error envelope.
        """
        self.assertIsInstance(result_str, str)
        result = json.loads(result_str)
        self.assertIn('error', result)
        self.assertIn('Tool execution failed', result['error'])
        self.assertEqual(result.get('tool'), expected_tool)

    def test_get_execution_detail_returns_error_on_db_failure(self):
        """Mock TaskExecution.objects.get to raise OperationalError → JSON error."""
        with patch('tasks.models.TaskExecution.objects') as mock_objects:
            mock_objects.select_related.return_value.get.side_effect = OperationalError(
                'DB connection lost'
            )
            result = get_execution_detail.invoke({'execution_id': 1})
        self._assert_error_envelope(result, 'get_execution_detail')

    def test_get_execution_steps_returns_error_on_db_failure(self):
        """Mock ExecutionStep.objects.filter to raise OperationalError → JSON error."""
        with patch('tasks.models.ExecutionStep.objects') as mock_objects:
            mock_objects.filter.side_effect = OperationalError('DB connection lost')
            result = get_execution_steps.invoke({'execution_id': 1})
        self._assert_error_envelope(result, 'get_execution_steps')

    def test_search_similar_errors_returns_error_on_unexpected_failure(self):
        """Force _rag_search_errors AND _search_similar_errors_via_jsonl to raise → JSON error.

        The RAG helper already swallows its own exceptions internally (returns
        []), so to exercise the outer isolation we patch the JSONL fallback
        helper to raise. The outer try/except must catch it and return an
        error envelope.
        """
        with patch('gaf_ai.agent.tools._rag_search_errors', return_value=[]), \
             patch(
                 'gaf_ai.agent.tools._search_similar_errors_via_jsonl',
                 side_effect=OperationalError('archive read failure'),
             ):
            result = search_similar_errors.invoke({'error_text': 'some error text'})
        self._assert_error_envelope(result, 'search_similar_errors')

    def test_get_task_config_returns_error_on_db_failure(self):
        """Mock Task.objects.get to raise OperationalError → JSON error."""
        with patch('tasks.models.Task.objects') as mock_objects:
            mock_objects.get.side_effect = OperationalError('DB connection lost')
            result = get_task_config.invoke({'task_id': 1})
        self._assert_error_envelope(result, 'get_task_config')


# ── get_screenshot_base64 tests (spec §7.2.1) ──────────────────
class GetScreenshotBase64Test(TestCase):
    """Tests for get_screenshot_base64 @tool.

    Verifies:
      - execution/step lookup (incl. auto-pick first failed step)
      - raw=True path: reads raw_screenshot_path from JSONL
      - raw=False path: reads ExecutionStep.screenshot_path
      - 5MB cap + missing-file handling
      - error envelopes never crash the ReAct loop
    """

    def test_nonexistent_execution_returns_error(self):
        result_str = get_screenshot_base64.invoke({'execution_id': 999999})
        result = json.loads(result_str)
        self.assertIn('error', result)
        self.assertIn('not found', result['error'])
        self.assertEqual(result['tool'], 'get_screenshot_base64')

    def test_explicit_step_not_found_returns_error(self):
        task = _make_task()
        ex = _make_execution(task)
        result_str = get_screenshot_base64.invoke({
            'execution_id': ex.id, 'step_index': 42, 'raw': False,
        })
        result = json.loads(result_str)
        self.assertIn('error', result)
        self.assertIn('Step #42', result['error'])

    def test_no_failed_step_returns_error_with_hint(self):
        """When step_index omitted and no failed step exists, surface a clear error."""
        task = _make_task()
        ex = _make_execution(task, status='success')
        _make_step(ex, index=0, status='success')

        result_str = get_screenshot_base64.invoke({'execution_id': ex.id})
        result = json.loads(result_str)
        self.assertIn('error', result)
        self.assertIn('No failed step', result['error'])
        self.assertIn('step_index', result['error'])

    def test_raw_false_reads_annotated_png_from_step(self):
        """raw=False should read ExecutionStep.screenshot_path and return base64."""
        task = _make_task()
        ex = _make_execution(task)
        # Create a small PNG file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
            png_path = f.name
        try:
            _make_step(
                ex, index=0, status='failed',
                screenshot_path=png_path, error_message='no match',
            )
            result_str = get_screenshot_base64.invoke({
                'execution_id': ex.id, 'raw': False,
            })
            result = json.loads(result_str)
            self.assertNotIn('error', result, f'got error: {result}')
            self.assertEqual(result['format'], 'png')
            self.assertEqual(result['path'], png_path)
            self.assertEqual(result['size_bytes'], 108)
            # base64 should decode back to the original bytes
            import base64 as b64
            decoded = b64.b64decode(result['base64'])
            self.assertTrue(decoded.startswith(b'\x89PNG'))
        finally:
            os.unlink(png_path)

    def test_raw_false_missing_screenshot_path_returns_error(self):
        """raw=False with empty screenshot_path → error envelope."""
        task = _make_task()
        ex = _make_execution(task)
        _make_step(ex, index=0, status='failed', screenshot_path='')
        result_str = get_screenshot_base64.invoke({
            'execution_id': ex.id, 'raw': False,
        })
        result = json.loads(result_str)
        self.assertIn('error', result)
        self.assertIn('No screenshot_path', result['error'])

    def test_raw_false_file_not_found_returns_error(self):
        """screenshot_path points to missing file → error envelope with path."""
        task = _make_task()
        ex = _make_execution(task)
        _make_step(
            ex, index=0, status='failed',
            screenshot_path='/nonexistent/path.png',
        )
        result_str = get_screenshot_base64.invoke({
            'execution_id': ex.id, 'raw': False,
        })
        result = json.loads(result_str)
        self.assertIn('error', result)
        self.assertIn('not found', result['error'])
        self.assertEqual(result['path'], '/nonexistent/path.png')

    def test_raw_true_no_snapshot_returns_error_with_fallback_hint(self):
        """raw=True but execution_snapshot has no structured_log_path → fallback hint."""
        task = _make_task()
        ex = _make_execution(task, status='failed')
        _make_step(ex, index=0, status='failed', screenshot_path='/x.png')

        result_str = get_screenshot_base64.invoke({
            'execution_id': ex.id, 'raw': True,
        })
        result = json.loads(result_str)
        # No JSONL available → raw_screenshot_path lookup returns ''
        # → tool returns error with fallback_hint
        self.assertIn('error', result)
        self.assertEqual(
            result.get('fallback_hint'),
            'call again with raw=False to get annotated PNG',
        )

    def test_raw_true_reads_raw_screenshot_path_from_jsonl(self):
        """raw=True should parse JSONL and return the raw_screenshot_path file."""
        task = _make_task()
        ex = _make_execution(task, status='failed')

        # Create raw JPEG + JSONL file
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            f.write(b'\xff\xd8\xff\xe0' + b'\x00' * 50)
            jpg_path = f.name
        with tempfile.NamedTemporaryFile(
            suffix='.jsonl', delete=False, mode='w', encoding='utf-8',
        ) as f:
            f.write(json.dumps({
                'step_index': 0,
                'node_type': 'template_match',
                'raw_screenshot_path': jpg_path,
                'screenshot_path': '/annotated.png',
                'success': False,
            }) + '\n')
            jsonl_path = f.name
        try:
            ex.execution_snapshot = {'structured_log_path': jsonl_path}
            ex.save()
            _make_step(ex, index=0, status='failed', screenshot_path='/annotated.png')

            result_str = get_screenshot_base64.invoke({
                'execution_id': ex.id, 'raw': True,
            })
            result = json.loads(result_str)
            self.assertNotIn('error', result, f'got error: {result}')
            self.assertEqual(result['format'], 'jpeg')
            self.assertEqual(result['path'], jpg_path)
            self.assertEqual(result['size_bytes'], 54)
        finally:
            os.unlink(jpg_path)
            os.unlink(jsonl_path)

    def test_raw_true_step_without_raw_in_jsonl_returns_fallback_hint(self):
        """raw=True but JSONL has no raw_screenshot_path for this step → hint."""
        task = _make_task()
        ex = _make_execution(task, status='failed')
        with tempfile.NamedTemporaryFile(
            suffix='.jsonl', delete=False, mode='w', encoding='utf-8',
        ) as f:
            # Entry has no raw_screenshot_path (action node, e.g. click)
            f.write(json.dumps({
                'step_index': 0,
                'node_type': 'click',
                'screenshot_path': '/annotated.png',
                'success': False,
            }) + '\n')
            jsonl_path = f.name
        try:
            ex.execution_snapshot = {'structured_log_path': jsonl_path}
            ex.save()
            _make_step(ex, index=0, status='failed', screenshot_path='/annotated.png')

            result_str = get_screenshot_base64.invoke({
                'execution_id': ex.id, 'raw': True,
            })
            result = json.loads(result_str)
            self.assertIn('error', result)
            self.assertIn('raw_screenshot_path', result['error'])
            self.assertEqual(
                result.get('fallback_hint'),
                'call again with raw=False to get annotated PNG',
            )
        finally:
            os.unlink(jsonl_path)

    def test_file_over_5mb_returns_too_large_error(self):
        """Files >5MB should be rejected to protect LLM context."""
        task = _make_task()
        ex = _make_execution(task)
        # 6MB of zeros
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * (6 * 1024 * 1024))
            big_path = f.name
        try:
            _make_step(
                ex, index=0, status='failed',
                screenshot_path=big_path, error_message='fail',
            )
            result_str = get_screenshot_base64.invoke({
                'execution_id': ex.id, 'raw': False,
            })
            result = json.loads(result_str)
            self.assertIn('error', result)
            self.assertIn('too large', result['error'])
            self.assertGreater(result['size_bytes'], 5 * 1024 * 1024)
        finally:
            os.unlink(big_path)

    def test_auto_picks_first_failed_step_when_step_index_omitted(self):
        """When step_index omitted, tool auto-selects the first failed step."""
        task = _make_task()
        ex = _make_execution(task)
        # Step 0 success, step 1 failed (target), step 2 failed (later)
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
            png_path = f.name
        try:
            _make_step(ex, index=0, status='success', screenshot_path='')
            _make_step(
                ex, index=1, status='failed',
                screenshot_path=png_path, error_message='fail-1',
                step_name='template_match_step',
            )
            _make_step(
                ex, index=2, status='failed',
                screenshot_path='/other.png', error_message='fail-2',
            )
            result_str = get_screenshot_base64.invoke({
                'execution_id': ex.id, 'raw': False,
            })
            result = json.loads(result_str)
            self.assertNotIn('error', result, f'got error: {result}')
            self.assertEqual(result['step_index'], 1)
            self.assertEqual(result['step_name'], 'template_match_step')
        finally:
            os.unlink(png_path)


# ── get_structured_log tests (spec §7.3.1) ─────────────────────
class GetStructuredLogTest(TestCase):
    """Tests for get_structured_log @tool.

    Verifies JSONL parsing, failed/successful step separation,
    optional field extraction (confidence/threshold/error_code/
    raw_screenshot_path), and graceful degradation when the JSONL
    file is missing/unreachable.
    """

    def test_nonexistent_execution_returns_error(self):
        result_str = get_structured_log.invoke({'execution_id': 999999})
        result = json.loads(result_str)
        self.assertIn('error', result)
        self.assertIn('not found', result['error'])
        self.assertEqual(result['tool'], 'get_structured_log')

    def test_no_structured_log_path_returns_error_with_hint(self):
        """When execution_snapshot lacks structured_log_path → hint to fall back."""
        task = _make_task()
        ex = _make_execution(task)
        ex.execution_snapshot = {}
        ex.save()

        result_str = get_structured_log.invoke({'execution_id': ex.id})
        result = json.loads(result_str)
        self.assertIn('error', result)
        self.assertIn('structured_log_path', result['error'])
        self.assertEqual(
            result.get('hint'),
            'fall back to get_execution_steps for SQL-based step data',
        )

    def test_jsonl_file_missing_returns_error_with_hint(self):
        """structured_log_path set but file does not exist → error + hint."""
        task = _make_task()
        ex = _make_execution(task)
        ex.execution_snapshot = {
            'structured_log_path': '/nonexistent/path.jsonl',
        }
        ex.save()

        result_str = get_structured_log.invoke({'execution_id': ex.id})
        result = json.loads(result_str)
        self.assertIn('error', result)
        self.assertIn('not found', result['error'])
        self.assertEqual(result['raw_log_path'], '/nonexistent/path.jsonl')
        self.assertIn('hint', result)

    def test_empty_jsonl_returns_error(self):
        """Empty JSONL file → error envelope (not a crash)."""
        task = _make_task()
        ex = _make_execution(task)
        with tempfile.NamedTemporaryFile(
            suffix='.jsonl', delete=False, mode='w', encoding='utf-8',
        ) as f:
            f.write('')  # empty
            jsonl_path = f.name
        try:
            ex.execution_snapshot = {'structured_log_path': jsonl_path}
            ex.save()

            result_str = get_structured_log.invoke({'execution_id': ex.id})
            result = json.loads(result_str)
            self.assertIn('error', result)
            self.assertIn('empty', result['error'])
        finally:
            os.unlink(jsonl_path)

    def test_parses_failed_and_successful_steps(self):
        """JSONL with mixed success/failure → structured summary."""
        task = _make_task()
        ex = _make_execution(task)
        with tempfile.NamedTemporaryFile(
            suffix='.jsonl', delete=False, mode='w', encoding='utf-8',
        ) as f:
            f.write(json.dumps({
                'step_index': 0, 'node_id': 'screenshot', 'node_type': 'screenshot',
                'success': True, 'elapsed_ms': 100.0,
            }) + '\n')
            f.write(json.dumps({
                'step_index': 1, 'node_id': 'match_btn', 'node_type': 'template_match',
                'success': True, 'elapsed_ms': 200.0,
                'confidence': 0.95, 'threshold': 0.8,
            }) + '\n')
            f.write(json.dumps({
                'step_index': 2, 'node_id': 'click_btn', 'node_type': 'click',
                'success': False, 'elapsed_ms': 50.0,
                'error_msg': 'SCREEN_UNCHANGED: click did not navigate',
                'error_code': 'SCREEN_UNCHANGED',
                'screenshot_path': '/debug/click_btn.png',
                'retry_count': 1,
            }) + '\n')
            jsonl_path = f.name
        try:
            ex.execution_snapshot = {'structured_log_path': jsonl_path}
            ex.save()

            result_str = get_structured_log.invoke({'execution_id': ex.id})
            result = json.loads(result_str)

            self.assertEqual(result['total_steps'], 3)
            self.assertEqual(result['failed_count'], 1)
            self.assertEqual(result['success_count'], 2)
            self.assertEqual(result['raw_log_path'], jsonl_path)

            # failed_steps has structured fields
            self.assertEqual(len(result['failed_steps']), 1)
            failed = result['failed_steps'][0]
            self.assertEqual(failed['step_index'], 2)
            self.assertEqual(failed['node_type'], 'click')
            self.assertEqual(failed['error_code'], 'SCREEN_UNCHANGED')
            self.assertEqual(failed['retry_count'], 1)
            self.assertEqual(failed['screenshot_path'], '/debug/click_btn.png')
            self.assertIn('SCREEN_UNCHANGED', failed['error_msg'])

            # successful_summary has both successful steps
            self.assertIn('step=0', result['successful_summary'])
            self.assertIn('screenshot', result['successful_summary'])
            self.assertIn('step=1', result['successful_summary'])
            self.assertIn('template_match', result['successful_summary'])

            # failed_detail is a non-empty human-readable string
            self.assertIn('step=2', result['failed_detail'])
            self.assertIn('click', result['failed_detail'])
            self.assertIn('error_code=SCREEN_UNCHANGED', result['failed_detail'])
        finally:
            os.unlink(jsonl_path)

    def test_failed_step_includes_optional_fields_when_present(self):
        """confidence/threshold/roi_physical/raw_screenshot_path in JSONL → in failed_steps."""
        task = _make_task()
        ex = _make_execution(task)
        with tempfile.NamedTemporaryFile(
            suffix='.jsonl', delete=False, mode='w', encoding='utf-8',
        ) as f:
            f.write(json.dumps({
                'step_index': 0, 'node_id': 'match', 'node_type': 'template_match',
                'success': False, 'elapsed_ms': 300.0,
                'confidence': 0.42, 'threshold': 0.8,
                'match_location': {'x': 960, 'y': 540},
                'roi_physical': [100, 100, 800, 600],
                'raw_screenshot_path': '/raw/match.jpg',
                'screenshot_path': '/ann/match.png',
                'error_code': 'LOW_CONFIDENCE',
                'error_msg': 'confidence 0.42 < threshold 0.8',
                'auto_heal_attempts': ['retry_with_threshold'],
            }) + '\n')
            jsonl_path = f.name
        try:
            ex.execution_snapshot = {'structured_log_path': jsonl_path}
            ex.save()

            result_str = get_structured_log.invoke({'execution_id': ex.id})
            result = json.loads(result_str)
            failed = result['failed_steps'][0]
            self.assertEqual(failed['confidence'], 0.42)
            self.assertEqual(failed['threshold'], 0.8)
            self.assertEqual(failed['match_location'], {'x': 960, 'y': 540})
            self.assertEqual(failed['roi_physical'], [100, 100, 800, 600])
            self.assertEqual(failed['raw_screenshot_path'], '/raw/match.jpg')
            self.assertEqual(failed['error_code'], 'LOW_CONFIDENCE')
            self.assertEqual(failed['auto_heal_attempts'], ['retry_with_threshold'])

            # failed_detail mentions confidence/threshold
            self.assertIn('confidence=0.42', result['failed_detail'])
            self.assertIn('threshold=0.8', result['failed_detail'])
            self.assertIn('error_code=LOW_CONFIDENCE', result['failed_detail'])
            self.assertIn('raw_screenshot=/raw/match.jpg', result['failed_detail'])
        finally:
            os.unlink(jsonl_path)

    def test_skips_invalid_json_lines(self):
        """Malformed JSON lines should be silently skipped, not crash."""
        task = _make_task()
        ex = _make_execution(task)
        with tempfile.NamedTemporaryFile(
            suffix='.jsonl', delete=False, mode='w', encoding='utf-8',
        ) as f:
            f.write('this is not json\n')
            f.write(json.dumps({
                'step_index': 0, 'node_id': 'ok', 'node_type': 'wait',
                'success': True, 'elapsed_ms': 100.0,
            }) + '\n')
            f.write('  \n')  # blank line
            jsonl_path = f.name
        try:
            ex.execution_snapshot = {'structured_log_path': jsonl_path}
            ex.save()

            result_str = get_structured_log.invoke({'execution_id': ex.id})
            result = json.loads(result_str)
            self.assertEqual(result['total_steps'], 1)
            self.assertEqual(result['success_count'], 1)
        finally:
            os.unlink(jsonl_path)


# ── text_similarity unit tests (spec §7.3.2 — 任务 4.6) ────────
class TextSimilarityTest(TestCase):
    """Pure-function tests for text_similarity (difflib-based).

    No Django DB, no settings, no I/O — just the SequenceMatcher
    wrapper. Verifies case-insensitivity, whitespace stripping,
    empty-string handling, and the [0.0, 1.0] range contract.
    """

    def test_identical_strings_return_1(self):
        self.assertEqual(text_similarity('hello', 'hello'), 1.0)

    def test_identical_after_normalization_returns_1(self):
        """Case-insensitive + whitespace-stripped identical → 1.0."""
        self.assertEqual(text_similarity('  Hello  ', 'HELLO'), 1.0)
        self.assertEqual(text_similarity('Template Match Failed',
                                        'template match failed'), 1.0)

    def test_completely_different_returns_low_score(self):
        """No common subsequences → ratio near 0.0."""
        sim = text_similarity('abc', 'xyz')
        self.assertLess(sim, 0.3)

    def test_empty_string_returns_zero(self):
        self.assertEqual(text_similarity('', 'something'), 0.0)
        self.assertEqual(text_similarity('something', ''), 0.0)
        self.assertEqual(text_similarity('', ''), 0.0)

    def test_none_like_input_returns_zero(self):
        """None should be treated like empty (defensive)."""
        self.assertEqual(text_similarity(None, 'x'), 0.0)
        self.assertEqual(text_similarity('x', None), 0.0)

    def test_partial_match_returns_intermediate_score(self):
        """Shared substrings should produce 0 < sim < 1."""
        sim = text_similarity(
            'Template match failed: btn.png not found',
            'Template match failed: icon.png not found',
        )
        self.assertGreater(sim, 0.5)
        self.assertLess(sim, 1.0)

    def test_returns_float_in_zero_one_range(self):
        """All similarities must be clamped to [0.0, 1.0]."""
        sim = text_similarity('a quick brown fox', 'a slow blue turtle')
        self.assertGreaterEqual(sim, 0.0)
        self.assertLessEqual(sim, 1.0)


# ── _search_similar_errors_via_jsonl unit tests (任务 4.6, 2026-07-26 修正) ─────
class JsonlArchiveScanTest(TestCase):
    """Direct tests for _search_similar_errors_via_jsonl.

    These tests bypass the @tool layer and call the helper directly,
    isolating the JSONL scan + similarity ranking logic from RAG.
    Each test creates a temp dir for JSONL files and passes a list of
    mock execution objects (with .id and .execution_snapshot attrs)
    via the ``executions`` parameter — no DB queryset is queried.

    This isolates the file-scan + ranking logic from the DB layer,
    while still exercising the real data flow:
    execution.execution_snapshot['structured_log_path'] → read file → rank.
    """

    def setUp(self):
        self._jsonl_dir = tempfile.mkdtemp(prefix='gaf_test_scan_')

    def tearDown(self):
        shutil.rmtree(self._jsonl_dir, ignore_errors=True)

    def _make_mock_execution(self, exec_id: int, events: list[dict]):
        """Build a mock TaskExecution-like object with a JSONL file on disk.

        Returns an object with ``.id`` and ``.execution_snapshot`` attrs
        that point at a real JSONL file under self._jsonl_dir.
        """
        jsonl_path = os.path.join(self._jsonl_dir, f'{exec_id}.jsonl')
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for evt in events:
                f.write(json.dumps(evt) + '\n')
        mock_ex = MagicMock()
        mock_ex.id = exec_id
        mock_ex.execution_snapshot = {'structured_log_path': jsonl_path}
        return mock_ex

    def test_empty_executions_returns_empty(self):
        """When executions=[] is passed, scan returns [] without DB hit."""
        self.assertEqual(
            _search_similar_errors_via_jsonl('any error', executions=[]),
            [],
        )

    def test_skips_executions_without_structured_log_path(self):
        """Executions whose snapshot has no structured_log_path are skipped."""
        mock_ex = MagicMock()
        mock_ex.id = 9001
        mock_ex.execution_snapshot = {}  # no structured_log_path
        # Plus a real one to verify scan continues past the bad one.
        good_ex = self._make_mock_execution(9002, [
            {'execution_id': 9002, 'success': False,
             'error_msg': 'Template match failed in good exec',
             'node_id': 's1', 'node_type': 'template_match'},
        ])

        matches = _search_similar_errors_via_jsonl(
            'Template match failed', executions=[mock_ex, good_ex],
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['execution_id'], 9002)

    def test_skips_executions_with_missing_jsonl_file(self):
        """Executions whose JSONL file is gone are skipped silently."""
        mock_ex = MagicMock()
        mock_ex.id = 9003
        mock_ex.execution_snapshot = {
            'structured_log_path': '/nonexistent/path/missing.jsonl',
        }
        good_ex = self._make_mock_execution(9004, [
            {'execution_id': 9004, 'success': False,
             'error_msg': 'Template match failed in good exec',
             'node_id': 's1'},
        ])

        matches = _search_similar_errors_via_jsonl(
            'Template match failed', executions=[mock_ex, good_ex],
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['execution_id'], 9004)

    def test_only_success_false_events_included(self):
        """success=True events with matching error_msg must be skipped."""
        mock_ex = self._make_mock_execution(10001, [
            {'execution_id': 10001, 'success': True,
             'error_msg': 'Template match failed',  # would match but skipped
             'node_id': 's1', 'node_type': 'template_match'},
            {'execution_id': 10001, 'success': False,
             'error_msg': 'Template match failed real error',
             'node_id': 's2', 'node_type': 'template_match'},
        ])

        matches = _search_similar_errors_via_jsonl(
            'Template match failed', executions=[mock_ex],
        )
        self.assertEqual(len(matches), 1)
        self.assertIn('real error', matches[0]['error'])

    def test_events_without_error_msg_skipped(self):
        """Failed events with empty/missing error_msg must be skipped."""
        mock_ex = self._make_mock_execution(10002, [
            {'execution_id': 10002, 'success': False, 'node_id': 's1'},
            {'execution_id': 10002, 'success': False, 'error_msg': '',
             'node_id': 's2'},
            {'execution_id': 10002, 'success': False,
             'error_msg': 'Template match failed with msg',
             'node_id': 's3', 'node_type': 'template_match'},
        ])

        matches = _search_similar_errors_via_jsonl(
            'Template match failed', executions=[mock_ex],
        )
        self.assertEqual(len(matches), 1)

    def test_threshold_filters_low_similarity(self):
        """Matches below similarity_threshold must be excluded."""
        # 'abc' vs 'xyz' = ~0.0 similarity — below default 0.5 threshold.
        mock_ex = self._make_mock_execution(10003, [
            {'execution_id': 10003, 'success': False,
             'error_msg': 'xyz', 'node_id': 's1'},
        ])

        matches = _search_similar_errors_via_jsonl(
            'abc', executions=[mock_ex],
        )
        self.assertEqual(matches, [])

        # Identical string has similarity 1.0 — always included by
        # any reasonable threshold < 1.0. Use threshold=0.99 to prove
        # the filter is a strict greater-than comparison (sim > threshold).
        mock_ex2 = self._make_mock_execution(10003, [
            {'execution_id': 10003, 'success': False,
             'error_msg': 'abc', 'node_id': 's1'},
        ])
        matches = _search_similar_errors_via_jsonl(
            'abc', executions=[mock_ex2], similarity_threshold=0.99,
        )
        self.assertEqual(len(matches), 1)
        # threshold above max possible similarity excludes everything.
        matches = _search_similar_errors_via_jsonl(
            'abc', executions=[mock_ex2], similarity_threshold=2.0,
        )
        self.assertEqual(matches, [])

    def test_sorted_by_similarity_descending(self):
        """Top match should have the highest similarity."""
        ex_partial = self._make_mock_execution(10004, [
            {'execution_id': 10004, 'success': False,
             'error_msg': 'Template match failed partial', 'node_id': 's1'},
        ])
        ex_diff = self._make_mock_execution(10005, [
            {'execution_id': 10005, 'success': False,
             'error_msg': 'Template match failed completely different wording',
             'node_id': 's1'},
        ])
        ex_exact = self._make_mock_execution(10006, [
            {'execution_id': 10006, 'success': False,
             'error_msg': 'Template match failed', 'node_id': 's1'},
        ])

        matches = _search_similar_errors_via_jsonl(
            'Template match failed',
            executions=[ex_partial, ex_diff, ex_exact],
        )
        sims = [m['similarity'] for m in matches]
        self.assertEqual(sims, sorted(sims, reverse=True))
        # Exact match should be the top hit.
        self.assertEqual(matches[0]['error'], 'Template match failed')
        self.assertEqual(matches[0]['execution_id'], 10006)

    def test_top_k_caps_result_count(self):
        """top_k=2 must return at most 2 matches even if 5 exist."""
        executions = [
            self._make_mock_execution(10007 + i, [
                {'execution_id': 10007 + i, 'success': False,
                 'error_msg': 'Template match failed',
                 'node_id': 's1', 'node_type': 'template_match'},
            ])
            for i in range(5)
        ]

        matches = _search_similar_errors_via_jsonl(
            'Template match failed', executions=executions, top_k=2,
        )
        self.assertEqual(len(matches), 2)

    def test_match_dict_has_expected_fields(self):
        """Each match must include all fields spec §7.3.2 lists."""
        mock_ex = self._make_mock_execution(10010, [
            {'execution_id': 10010, 'success': False,
             'error_msg': 'Template match failed: btn.png',
             'node_id': 'match_btn', 'node_type': 'template_match',
             'error_code': 'TEMPLATE_NOT_FOUND',
             'timestamp': '2026-07-26T10:00:00+08:00'},
        ])

        matches = _search_similar_errors_via_jsonl(
            'Template match failed', executions=[mock_ex],
        )
        self.assertEqual(len(matches), 1)
        m = matches[0]
        for field in ('execution_id', 'error', 'similarity', 'jsonl_path',
                      'node_id', 'node_type', 'error_code', 'timestamp'):
            self.assertIn(field, m, f'missing field: {field}')
        self.assertEqual(m['execution_id'], 10010)
        self.assertEqual(m['node_id'], 'match_btn')
        self.assertEqual(m['node_type'], 'template_match')
        self.assertEqual(m['error_code'], 'TEMPLATE_NOT_FOUND')
        self.assertEqual(m['timestamp'], '2026-07-26T10:00:00+08:00')
        self.assertIsInstance(m['similarity'], float)
        self.assertGreater(m['similarity'], 0.5)

    def test_corrupted_jsonl_files_skipped(self):
        """One corrupted JSONL file should not block scanning others."""
        # File 1: corrupted (not JSON at all).
        bad_path = os.path.join(self._jsonl_dir, '10011.jsonl')
        with open(bad_path, 'w', encoding='utf-8') as f:
            f.write('this is not json\n')
        bad_ex = MagicMock()
        bad_ex.id = 10011
        bad_ex.execution_snapshot = {'structured_log_path': bad_path}

        # File 2: valid JSONL with a matching error.
        good_ex = self._make_mock_execution(10012, [
            {'execution_id': 10012, 'success': False,
             'error_msg': 'Template match failed in second file',
             'node_id': 's1'},
        ])

        matches = _search_similar_errors_via_jsonl(
            'Template match failed', executions=[bad_ex, good_ex],
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['execution_id'], 10012)

    def test_always_uses_taskexecution_pk_not_agent_uuid(self):
        """execution_id must be TaskExecution.pk (int), not the JSONL's agent UUID12.

        JSONL events contain ``execution_id`` = agent's UUID12 string (e.g.
        "exec-abc123def456"), but callers (get_execution_detail) expect the
        DB pk (int). Verify we always return ex.id, regardless of whether
        the JSONL event has an execution_id field.
        """
        # Event WITH agent UUID12 execution_id — must still return TaskExecution.pk.
        mock_ex = self._make_mock_execution(10014, [
            {'execution_id': 'exec-abc123def456', 'success': False,
             'error_msg': 'Template match failed with agent uuid',
             'node_id': 's1', 'node_type': 'template_match'},
        ])

        matches = _search_similar_errors_via_jsonl(
            'Template match failed', executions=[mock_ex],
        )
        self.assertEqual(len(matches), 1)
        # Must be int (TaskExecution.pk), not str (agent UUID12).
        self.assertEqual(matches[0]['execution_id'], 10014)
        self.assertIsInstance(matches[0]['execution_id'], int)

        # Event WITHOUT execution_id — also returns TaskExecution.pk.
        mock_ex2 = self._make_mock_execution(10015, [
            {'success': False,
             'error_msg': 'Template match failed no event id',
             'node_id': 's1', 'node_type': 'template_match'},
        ])
        matches2 = _search_similar_errors_via_jsonl(
            'Template match failed', executions=[mock_ex2],
        )
        self.assertEqual(matches2[0]['execution_id'], 10015)
        self.assertIsInstance(matches2[0]['execution_id'], int)

    def test_unicode_error_messages_handled(self):
        """Chinese / non-ASCII error_msg must round-trip correctly.

        Note: difflib.SequenceMatcher uses code-point-level matching,
        so a short Chinese query against a longer Chinese error_msg
        can fall below the default 0.5 threshold (e.g. '模板匹配失败'
        vs '模板匹配失败: 找不到 btn.png' = 0.48). Use a query long
        enough to clear the threshold.
        """
        mock_ex = self._make_mock_execution(10013, [
            {'execution_id': 10013, 'success': False,
             'error_msg': '模板匹配失败: 找不到 btn.png',
             'node_id': 's1', 'node_type': 'template_match'},
        ])

        # Use the full error_msg as query → similarity 1.0.
        matches = _search_similar_errors_via_jsonl(
            '模板匹配失败: 找不到 btn.png', executions=[mock_ex],
        )
        self.assertEqual(len(matches), 1)
        self.assertIn('btn.png', matches[0]['error'])

        # A longer partial query (12 chars vs 19) clears 0.5: ratio ≈ 0.69.
        matches = _search_similar_errors_via_jsonl(
            '模板匹配失败: 找不到', executions=[mock_ex],
        )
        self.assertEqual(len(matches), 1)


# ══════════════════════════════════════════════════════════════════
#  Test classes from test_agent_async.py
# ══════════════════════════════════════════════════════════════════

@override_settings(GAF_UNIFIED_RESPONSE_ENABLED=False)
class AgentAnalyzeDispatchTest(TestCase):
    """Tests for POST /api/v2/ai/agent/analyze/ dispatch behavior."""

    def setUp(self):
        self.client = APIClient()
        self.admin = _make_user('admin_user')
        self.client.force_authenticate(user=self.admin)
        self.task = _make_task()
        self.task_result = _make_execution(self.task, triggered_by=self.admin)

    def test_post_returns_202_with_session_id_and_pending_status(self):
        """POST creates a PENDING AgentSession and returns 202 immediately."""
        with patch('gaf_ai.tasks.run_agent_analysis_task.delay') as mock_delay:
            response = self.client.post(
                '/api/v2/ai/agent/analyze/',
                data=json.dumps({'execution_id': self.task_result.id}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['status'], 'pending')
        self.assertIn('session_id', response.data)
        # Celery delay() was called once with (session_id, execution_id)
        mock_delay.assert_called_once()
        session_id = response.data['session_id']
        self.assertEqual(mock_delay.call_args[0][0], session_id)
        self.assertEqual(mock_delay.call_args[0][1], self.task_result.id)

        # Session was persisted with PENDING status
        session = AgentSession.objects.get(pk=session_id)
        self.assertEqual(session.status, AgentSession.Status.PENDING)
        self.assertEqual(session.target_id, self.task_result.id)

    def test_post_missing_execution_id_returns_400(self):
        response = self.client.post(
            '/api/v2/ai/agent/analyze/',
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_post_nonexistent_execution_returns_404(self):
        response = self.client.post(
            '/api/v2/ai/agent/analyze/',
            data=json.dumps({'execution_id': 999999}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_post_dispatches_task_with_session_running_transition(self):
        """When delay() is called for real (no mock), the session is PENDING;
        the task will later transition it to RUNNING. We verify dispatch only.
        """
        # Use a mock that does nothing — we just want to verify the session
        # was created in PENDING and the task was dispatched.
        with patch('gaf_ai.tasks.run_agent_analysis_task.delay'):
            response = self.client.post(
                '/api/v2/ai/agent/analyze/',
                data=json.dumps({'execution_id': self.task_result.id}),
                content_type='application/json',
            )
        session_id = response.data['session_id']
        session = AgentSession.objects.get(pk=session_id)
        self.assertEqual(session.status, AgentSession.Status.PENDING)


@override_settings(GAF_UNIFIED_RESPONSE_ENABLED=False)
class AgentSessionStatusTest(TestCase):
    """Tests for GET /api/v2/ai/agent/sessions/<id>/ polling endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.admin = _make_user('admin_user')
        self.other_user = _make_user('other_user', role='viewer')
        self.client.force_authenticate(user=self.admin)
        self.session = AgentSession.objects.create(
            user=self.admin,
            session_type=AgentSession.SessionType.LOG_ANALYSIS,
            target_id=42,
            status=AgentSession.Status.PENDING,
        )

    def test_get_pending_session_returns_status(self):
        """GET on a PENDING session returns status='pending' with empty result."""
        response = self.client.get(f'/api/v2/ai/agent/sessions/{self.session.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(response.data['session_id'], self.session.id)
        self.assertEqual(response.data['reasoning_steps'], [])
        self.assertEqual(response.data['summary'], '')
        self.assertEqual(response.data['suggestions'], [])
        self.assertEqual(response.data['total_tokens'], 0)
        self.assertIsNone(response.data['error'])

    def test_get_completed_session_returns_full_result(self):
        """GET on a COMPLETED session returns reasoning chain + summary."""
        self.session.status = AgentSession.Status.COMPLETED
        self.session.model_used = 'deepseek-chat'
        self.session.reasoning_steps = [
            {'thought': 'checking', 'action': 'get_execution_detail',
             'action_input': {'execution_id': 42}, 'observation': '{}'},
        ]
        self.session.final_summary = '执行 #42 模板匹配失败'
        self.session.final_suggestions = ['更新模板 X']
        self.session.total_tokens = 1500
        self.session.save()

        response = self.client.get(f'/api/v2/ai/agent/sessions/{self.session.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'completed')
        self.assertEqual(response.data['model_used'], 'deepseek-chat')
        self.assertEqual(len(response.data['reasoning_steps']), 1)
        self.assertEqual(response.data['summary'], '执行 #42 模板匹配失败')
        self.assertEqual(response.data['suggestions'], ['更新模板 X'])
        self.assertEqual(response.data['total_tokens'], 1500)

    def test_get_failed_session_returns_error(self):
        """GET on a FAILED session surfaces the error_message."""
        self.session.status = AgentSession.Status.FAILED
        self.session.error_message = 'LLM provider timeout'
        self.session.save()

        response = self.client.get(f'/api/v2/ai/agent/sessions/{self.session.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'failed')
        self.assertEqual(response.data['error'], 'LLM provider timeout')

    def test_get_nonexistent_session_returns_404(self):
        response = self.client.get('/api/v2/ai/agent/sessions/999999/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_session_as_non_owner_non_admin_returns_403(self):
        """A regular user cannot view another user's session."""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(f'/api/v2/ai/agent/sessions/{self.session.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_session_as_owner_returns_200(self):
        """The session owner (non-admin) can view their own session."""
        self.session.user = self.other_user
        self.session.save()
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(f'/api/v2/ai/agent/sessions/{self.session.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['session_id'], self.session.id)

    def test_admin_can_view_other_users_session(self):
        """Admin can view any session regardless of owner."""
        self.session.user = self.other_user
        self.session.save()
        # self.admin is already authenticated
        response = self.client.get(f'/api/v2/ai/agent/sessions/{self.session.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_session_returns_evidence_check(self):
        """P2: 状态接口透出 evidence_check (旧数据默认 None)."""
        self.session.status = AgentSession.Status.COMPLETED
        self.session.evidence = ['tool get_error_log returned exit_code=1']
        self.session.evidence_check = {
            'verified': ['tool get_error_log returned exit_code=1'],
            'unverified': [],
        }
        self.session.save()

        response = self.client.get(f'/api/v2/ai/agent/sessions/{self.session.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['evidence_check'],
            {'verified': ['tool get_error_log returned exit_code=1'], 'unverified': []},
        )

    def test_get_session_evidence_check_defaults_none(self):
        """P2: 旧 session 无 evidence_check → 接口返回 None."""
        self.session.status = AgentSession.Status.COMPLETED
        self.session.save()

        response = self.client.get(f'/api/v2/ai/agent/sessions/{self.session.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['evidence_check'])


@override_settings(GAF_UNIFIED_RESPONSE_ENABLED=False)
class AgentAnalyzeEagerTest(TestCase):
    """End-to-end test with CELERY_TASK_ALWAYS_EAGER=True.

    In eager mode, .delay() runs the task synchronously, so by the time
    POST returns, the session should already be COMPLETED (or FAILED if
    the LLM call fails — we mock the agent to control the outcome).
    """

    def setUp(self):
        self.client = APIClient()
        self.admin = _make_user('admin_user')
        self.client.force_authenticate(user=self.admin)
        self.task = _make_task()
        self.task_result = _make_execution(self.task, triggered_by=self.admin)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    def test_eager_dispatch_runs_task_and_completes_session(self):
        """With eager mode + mocked LangGraph agent, POST → session COMPLETED."""
        # Mock the LangGraph agent to return a canned response
        fake_ai_message = _make_ai_message(
            content=json.dumps({'summary': 'Test summary', 'suggestions': ['Fix X']}),
            model_name='deepseek-chat',
            total_tokens=500,
        )
        fake_agent = patch('gaf_ai.agent.graph.build_log_analysis_agent')
        mock_build = fake_agent.start()
        mock_build.return_value.invoke.return_value = {
            'messages': [fake_ai_message],
        }
        try:
            response = self.client.post(
                '/api/v2/ai/agent/analyze/',
                data=json.dumps({'execution_id': self.task_result.id}),
                content_type='application/json',
            )
        finally:
            fake_agent.stop()

        # In eager mode, POST dispatches AND the task completes synchronously.
        # The POST response still returns 202 + 'pending' (because the view
        # returns before the session status is re-read), but the session in
        # the DB is now COMPLETED.
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        session_id = response.data['session_id']
        session = AgentSession.objects.get(pk=session_id)
        self.assertEqual(session.status, AgentSession.Status.COMPLETED)
        # S3 P5: 无 evidence → summary 附弱校验注记
        self.assertTrue(session.final_summary.startswith('Test summary'))
        self.assertIn('请人工复核', session.final_summary)
        self.assertEqual(session.final_suggestions, ['Fix X'])
        self.assertEqual(session.evidence, [])
        self.assertEqual(session.model_used, 'deepseek-chat')
        self.assertEqual(session.total_tokens, 500)

        # Subsequent GET returns the completed result
        get_response = self.client.get(f'/api/v2/ai/agent/sessions/{session_id}/')
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data['status'], 'completed')
        self.assertTrue(get_response.data['summary'].startswith('Test summary'))
        self.assertEqual(get_response.data['evidence'], [])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    def test_eager_dispatch_task_failure_marks_session_failed(self):
        """When the agent raises, the session is marked FAILED with error_message."""
        fake_agent = patch('gaf_ai.agent.graph.build_log_analysis_agent')
        mock_build = fake_agent.start()
        mock_build.return_value.invoke.side_effect = RuntimeError('LLM provider down')
        try:
            response = self.client.post(
                '/api/v2/ai/agent/analyze/',
                data=json.dumps({'execution_id': self.task_result.id}),
                content_type='application/json',
            )
        finally:
            fake_agent.stop()

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        session_id = response.data['session_id']
        session = AgentSession.objects.get(pk=session_id)
        self.assertEqual(session.status, AgentSession.Status.FAILED)
        self.assertIn('LLM provider down', session.error_message)


class RunAgentAnalysisTaskUnitTest(TestCase):
    """Unit tests for run_agent_analysis_task Celery function.

    These call the task function directly (not via .delay()) to verify
    the session lifecycle transitions without involving Celery.
    """

    def setUp(self):
        self.admin = _make_user('admin_user')
        self.session = AgentSession.objects.create(
            user=self.admin,
            session_type=AgentSession.SessionType.LOG_ANALYSIS,
            target_id=42,
            status=AgentSession.Status.PENDING,
        )

    def test_task_returns_failed_for_nonexistent_session(self):
        """Calling the task with a bad session_id returns failed dict."""
        result = run_agent_analysis_task.run(session_id=999999, task_result_id=42)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('not found', result['error'])

    def test_task_transitions_to_failed_on_agent_exception(self):
        """When the agent raises, the task marks the session FAILED."""
        with patch('gaf_ai.agent.graph.build_log_analysis_agent') as mock_build:
            mock_build.return_value.invoke.side_effect = RuntimeError('boom')
            result = run_agent_analysis_task.run(
                session_id=self.session.id, task_result_id=42,
            )
        self.assertEqual(result['status'], 'failed')
        self.assertIn('boom', result['error'])
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, AgentSession.Status.FAILED)
        self.assertIn('boom', self.session.error_message)
        self.assertIsNotNone(self.session.completed_at)

    def test_task_transitions_to_running_then_completed(self):
        """A successful task transitions session PENDING → RUNNING → COMPLETED."""
        fake_ai_message = _make_ai_message(
            content=json.dumps({'summary': 'OK', 'suggestions': []}),
            model_name='gpt-4o',
            total_tokens=100,
        )
        with patch('gaf_ai.agent.graph.build_log_analysis_agent') as mock_build:
            mock_build.return_value.invoke.return_value = {
                'messages': [fake_ai_message],
            }
            result = run_agent_analysis_task.run(
                session_id=self.session.id, task_result_id=42,
            )
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['model_used'], 'gpt-4o')
        self.assertEqual(result['total_tokens'], 100)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, AgentSession.Status.COMPLETED)
        self.assertEqual(self.session.model_used, 'gpt-4o')
        self.assertIsNotNone(self.session.completed_at)

    def test_task_weak_check_annotates_summary_without_evidence(self):
        """S3 P5: 无 evidence 的最终答案 → summary 附人工复核注记."""
        fake_ai_message = _make_ai_message(
            content=json.dumps({'summary': 'OK', 'suggestions': []}),
            model_name='gpt-4o',
        )
        with patch('gaf_ai.agent.graph.build_log_analysis_agent') as mock_build:
            mock_build.return_value.invoke.return_value = {
                'messages': [fake_ai_message],
            }
            result = run_agent_analysis_task.run(
                session_id=self.session.id, task_result_id=42,
            )
        self.assertEqual(result['evidence'], [])
        self.assertIn('请人工复核', result['summary'])
        self.session.refresh_from_db()
        self.assertEqual(self.session.evidence, [])
        self.assertIn('请人工复核', self.session.final_summary)

    def test_task_stores_evidence_on_session(self):
        """S3 P5: evidence 提取后存入 AgentSession 并随结果返回.

        P2 (2026-08-17): 无工具观测时 evidence 无法强校验通过 → 附强校验注记
        (行为变化: 单条 AI 消息无工具链, evidence 必然 unverified).
        """
        fake_ai_message = _make_ai_message(
            content=json.dumps({
                'summary': 'OCR node failed.',
                'suggestions': ['Retry'],
                'evidence': ['tool get_error_log returned exit_code=1'],
            }),
            model_name='gpt-4o',
        )
        with patch('gaf_ai.agent.graph.build_log_analysis_agent') as mock_build:
            mock_build.return_value.invoke.return_value = {
                'messages': [fake_ai_message],
            }
            result = run_agent_analysis_task.run(
                session_id=self.session.id, task_result_id=42,
            )
        self.assertEqual(result['evidence'], ['tool get_error_log returned exit_code=1'])
        # P2: 无工具观测 → 强校验未通过注记 (行为变化)
        self.assertIn('强校验未通过', result['summary'])
        self.assertEqual(
            result['evidence_check'],
            {
                'verified': [],
                'unverified': ['tool get_error_log returned exit_code=1'],
            },
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.evidence, ['tool get_error_log returned exit_code=1'])
        self.assertEqual(self.session.evidence_check['unverified'], [
            'tool get_error_log returned exit_code=1',
        ])

    # ── P2 (2026-08-17): 幻觉防线强校验 (evidence ↔ 工具观测比对) ──────

    def _run_with_steps(self, steps_messages: list, final_content: str):
        """Run the task with a canned ReAct message chain + final answer."""
        fake_ai_message = _make_ai_message(
            content=final_content,
            model_name='gpt-4o',
        )
        messages = list(steps_messages) + [fake_ai_message]
        with patch('gaf_ai.agent.graph.build_log_analysis_agent') as mock_build:
            mock_build.return_value.invoke.return_value = {
                'messages': messages,
            }
            return run_agent_analysis_task.run(
                session_id=self.session.id, task_result_id=42,
            )

    def test_strong_check_all_verified(self):
        """evidence 与工具观测高度相似 → 全部 verified, 无附注."""
        call_msg = _make_reasoning_ai_message(
            content='Calling get_error_log',
            tool_calls=[{'name': 'get_error_log', 'args': {}, 'id': 'c1'}],
        )
        obs = _make_reasoning_tool_message(
            'get_error_log returned exit_code=1 for execution 42', tool_call_id='c1',
        )
        result = self._run_with_steps(
            [call_msg, obs],
            json.dumps({
                'summary': 'OCR node failed.',
                'suggestions': ['Retry'],
                'evidence': ['get_error_log returned exit_code=1'],
            }),
        )
        self.assertEqual(
            result['evidence_check'],
            {'verified': ['get_error_log returned exit_code=1'], 'unverified': []},
        )
        self.assertNotIn('强校验未通过', result['summary'])
        self.session.refresh_from_db()
        self.assertEqual(
            self.session.evidence_check['verified'],
            ['get_error_log returned exit_code=1'],
        )

    def test_strong_check_partial_unverified(self):
        """一条 evidence 无观测支撑 → unverified + summary 附注."""
        call_msg = _make_reasoning_ai_message(
            content='Calling get_error_log',
            tool_calls=[{'name': 'get_error_log', 'args': {}, 'id': 'c1'}],
        )
        obs = _make_reasoning_tool_message(
            'get_error_log returned exit_code=1 for execution 42', tool_call_id='c1',
        )
        result = self._run_with_steps(
            [call_msg, obs],
            json.dumps({
                'summary': 'Diagnosis.',
                'suggestions': [],
                'evidence': [
                    'get_error_log returned exit_code=1',
                    'the database was completely wiped last night',
                ],
            }),
        )
        check = result['evidence_check']
        self.assertEqual(check['verified'], ['get_error_log returned exit_code=1'])
        self.assertEqual(
            check['unverified'], ['the database was completely wiped last night'],
        )
        self.assertIn('强校验未通过', result['summary'])
        self.assertIn('the database was completely wiped last night', result['summary'])

    def test_strong_check_all_unverified_no_observations(self):
        """无工具调用 (observations 空) → 全部 unverified + 附注."""
        result = self._run_with_steps(
            [],
            json.dumps({
                'summary': 'Guess without tools.',
                'suggestions': [],
                'evidence': ['claimed fact with no observation'],
            }),
        )
        check = result['evidence_check']
        self.assertEqual(check['verified'], [])
        self.assertEqual(check['unverified'], ['claimed fact with no observation'])
        self.assertIn('强校验未通过', result['summary'])

    def test_strong_check_empty_evidence_preserves_weak_check(self):
        """evidence 为空 → evidence_check 空 dict + 弱校验注记保留."""
        result = self._run_with_steps(
            [],
            json.dumps({'summary': 'OK', 'suggestions': []}),
        )
        self.assertEqual(result['evidence_check'], {'verified': [], 'unverified': []})
        self.assertIn('请人工复核', result['summary'])
        self.assertNotIn('强校验未通过', result['summary'])
        self.session.refresh_from_db()
        self.assertEqual(
            self.session.evidence_check, {'verified': [], 'unverified': []},
        )


# ══════════════════════════════════════════════════════════════════
#  Test classes from test_agent_reasoning.py
# ══════════════════════════════════════════════════════════════════

# ── _extract_reasoning_steps tests ──────────────────────────────
class ExtractReasoningStepsTest(SimpleTestCase):
    """Tests for _extract_reasoning_steps()."""

    def test_empty_messages_returns_empty_list(self):
        self.assertEqual(_extract_reasoning_steps([]), [])

    def test_final_answer_only(self):
        """AIMessage with no tool_calls and no pending → single thought step."""
        msg = _make_reasoning_ai_message(content='Final analysis: all good', tool_calls=[])
        steps = _extract_reasoning_steps([msg])

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]['thought'], 'Final analysis: all good')
        self.assertIsNone(steps[0]['action'])
        self.assertIsNone(steps[0]['action_input'])
        self.assertIsNone(steps[0]['observation'])

    def test_single_tool_call_paired_with_tool_message(self):
        """AIMessage(tool_calls=[X]) → ToolMessage → 1 step with action+observation."""
        ai = _make_reasoning_ai_message(
            content='I need to check the execution',
            tool_calls=[{'name': 'get_execution_detail', 'args': {'execution_id': 63}, 'id': 'call_1'}],
        )
        tool = _make_reasoning_tool_message(content='Execution 63: failed', tool_call_id='call_1')

        steps = _extract_reasoning_steps([ai, tool])

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]['thought'], 'I need to check the execution')
        self.assertEqual(steps[0]['action'], 'get_execution_detail')
        self.assertEqual(steps[0]['action_input'], {'execution_id': 63})
        self.assertEqual(steps[0]['observation'], 'Execution 63: failed')

    def test_multi_step_react_chain(self):
        """Full ReAct: AI(tool) → Tool → AI(tool) → Tool → AI(final) → 3 steps."""
        ai1 = _make_reasoning_ai_message(
            content='Step 1: get execution detail',
            tool_calls=[{'name': 'get_execution_detail', 'args': {'execution_id': 63}, 'id': 'c1'}],
        )
        tool1 = _make_reasoning_tool_message(content='detail result', tool_call_id='c1')
        ai2 = _make_reasoning_ai_message(
            content='Step 2: search similar errors',
            tool_calls=[{'name': 'search_similar_errors', 'args': {'error_text': 'fail'}, 'id': 'c2'}],
        )
        tool2 = _make_reasoning_tool_message(content='found 4 similar', tool_call_id='c2')
        ai3 = _make_reasoning_ai_message(content='Final summary here', tool_calls=[])

        steps = _extract_reasoning_steps([ai1, tool1, ai2, tool2, ai3])

        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0]['action'], 'get_execution_detail')
        self.assertEqual(steps[0]['observation'], 'detail result')
        self.assertEqual(steps[1]['action'], 'search_similar_errors')
        self.assertEqual(steps[1]['observation'], 'found 4 similar')
        # The final AI message (no tool_calls, no pending) becomes a thought-only step.
        self.assertEqual(steps[2]['thought'], 'Final summary here')
        self.assertIsNone(steps[2]['action'])

    def test_multiple_tool_calls_in_one_ai_message(self):
        """AIMessage with multiple tool_calls → multiple pending → paired in order."""
        ai = _make_reasoning_ai_message(content='Need both', tool_calls=[
            {'name': 'get_execution_detail', 'args': {'execution_id': 1}, 'id': 'c1'},
            {'name': 'get_execution_steps', 'args': {'execution_id': 1}, 'id': 'c2'},
        ])
        tool1 = _make_reasoning_tool_message(content='detail', tool_call_id='c1')
        tool2 = _make_reasoning_tool_message(content='steps', tool_call_id='c2')

        steps = _extract_reasoning_steps([ai, tool1, tool2])

        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]['action'], 'get_execution_detail')
        self.assertEqual(steps[0]['observation'], 'detail')
        self.assertEqual(steps[1]['action'], 'get_execution_steps')
        self.assertEqual(steps[1]['observation'], 'steps')

    def test_tool_message_without_preceding_ai_ignored(self):
        """A ToolMessage with no pending tool_calls is ignored (defensive)."""
        tool = _make_reasoning_tool_message(content='orphan result', tool_call_id='c1')

        steps = _extract_reasoning_steps([tool])

        self.assertEqual(steps, [])

    def test_long_observation_truncated_to_2000_chars(self):
        """Observations longer than 2000 chars are truncated."""
        long_obs = 'x' * 5000
        ai = _make_reasoning_ai_message(
            content='check',
            tool_calls=[{'name': 'tool', 'args': {}, 'id': 'c1'}],
        )
        tool = _make_reasoning_tool_message(content=long_obs, tool_call_id='c1')

        steps = _extract_reasoning_steps([ai, tool])

        self.assertEqual(len(steps[0]['observation']), 2000)

    def test_long_final_answer_thought_truncated_to_500_chars(self):
        """Final-answer thought (no tool_calls) is truncated to 500 chars."""
        long_thought = 'y' * 1000
        ai = _make_reasoning_ai_message(content=long_thought, tool_calls=[])

        steps = _extract_reasoning_steps([ai])

        self.assertEqual(len(steps[0]['thought']), 500)

    def test_empty_content_with_tool_calls_uses_fallback_thought(self):
        """When AI has tool_calls but empty content, thought defaults to 'Calling X'."""
        ai = _make_reasoning_ai_message(
            content='',
            tool_calls=[{'name': 'get_task_config', 'args': {}, 'id': 'c1'}],
        )
        tool = _make_reasoning_tool_message(content='result', tool_call_id='c1')

        steps = _extract_reasoning_steps([ai, tool])

        self.assertEqual(steps[0]['thought'], 'Calling get_task_config')

    def test_non_string_tool_message_content_stringified(self):
        """ToolMessage with non-str content (e.g. dict) is stringified."""
        ai = _make_reasoning_ai_message(
            content='check',
            tool_calls=[{'name': 'tool', 'args': {}, 'id': 'c1'}],
        )
        # Non-string content — e.g. a dict (some providers do this)
        tool = _make_reasoning_tool_message(content={'key': 'value'}, tool_call_id='c1')

        steps = _extract_reasoning_steps([ai, tool])

        # Should be stringified, not crash
        self.assertIsInstance(steps[0]['observation'], str)
        self.assertIn('key', steps[0]['observation'])


# ── _serialize_messages tests ───────────────────────────────────
class SerializeMessagesTest(SimpleTestCase):
    """Tests for _serialize_messages()."""

    def test_empty_list(self):
        self.assertEqual(_serialize_messages([]), [])

    def test_simple_ai_message(self):
        msg = _make_reasoning_ai_message(content='hello', tool_calls=[])
        result = _serialize_messages([msg])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['type'], 'AIMessage')
        self.assertEqual(result[0]['content'], 'hello')
        self.assertEqual(result[0]['tool_calls'], [])
        self.assertEqual(result[0]['tool_call_id'], '')

    def test_tool_message_with_id(self):
        msg = _make_reasoning_tool_message(content='result', tool_call_id='c1')
        result = _serialize_messages([msg])

        self.assertEqual(result[0]['type'], 'ToolMessage')
        self.assertEqual(result[0]['content'], 'result')
        self.assertEqual(result[0]['tool_call_id'], 'c1')

    def test_tool_calls_extracted(self):
        msg = _make_reasoning_ai_message(content='plan', tool_calls=[
            {'name': 'tool_a', 'args': {'x': 1}, 'id': 'c1'},
            {'name': 'tool_b', 'args': {'y': 2}, 'id': 'c2'},
        ])
        result = _serialize_messages([msg])

        self.assertEqual(len(result[0]['tool_calls']), 2)
        self.assertEqual(result[0]['tool_calls'][0], {'name': 'tool_a', 'args': {'x': 1}})
        self.assertEqual(result[0]['tool_calls'][1], {'name': 'tool_b', 'args': {'y': 2}})

    def test_list_content_json_dumped(self):
        """Content that is a list (block format) is JSON-dumped."""
        cls = type('AIMessage', (object,), {})
        obj = cls()
        obj.content = [{'type': 'text', 'text': 'hello'}]
        obj.tool_calls = []

        result = _serialize_messages([obj])

        self.assertIsInstance(result[0]['content'], str)
        # Should be valid JSON.
        parsed = json.loads(result[0]['content'])
        self.assertEqual(parsed[0]['text'], 'hello')

    def test_non_str_non_list_content_stringified(self):
        """Content that is neither str nor list is stringified."""
        cls = type('AIMessage', (object,), {})
        obj = cls()
        obj.content = 42  # int
        obj.tool_calls = []

        result = _serialize_messages([obj])

        self.assertEqual(result[0]['content'], '42')


# ── _parse_agent_result tests ───────────────────────────────────
class ParseAgentResultTest(SimpleTestCase):
    """Tests for _parse_agent_result() — the final-JSON parser with fallback."""

    def test_empty_content_returns_default(self):
        summary, suggestions, evidence = _parse_agent_result('')
        self.assertEqual(summary, 'Agent completed but returned no summary.')
        self.assertEqual(suggestions, [])
        self.assertEqual(evidence, [])

    def test_valid_json_with_summary_and_suggestions(self):
        content = json.dumps({
            'summary': 'The execution failed due to template mismatch.',
            'suggestions': ['Lower threshold to 0.7', 'Add retry logic'],
        })

        summary, suggestions, evidence = _parse_agent_result(content)

        self.assertEqual(summary, 'The execution failed due to template mismatch.')
        self.assertEqual(suggestions, ['Lower threshold to 0.7', 'Add retry logic'])
        # S3 P5: no evidence key → empty list
        self.assertEqual(evidence, [])

    def test_json_with_evidence(self):
        """S3 P5: evidence array is extracted from the final answer JSON."""
        content = json.dumps({
            'summary': 'OCR node failed.',
            'suggestions': ['Retry with higher resolution'],
            'evidence': [
                'tool get_error_log returned exit_code=1',
                'tool search_similar_errors returned 3 matches',
            ],
        })

        summary, suggestions, evidence = _parse_agent_result(content)

        self.assertEqual(summary, 'OCR node failed.')
        self.assertEqual(suggestions, ['Retry with higher resolution'])
        self.assertEqual(evidence, [
            'tool get_error_log returned exit_code=1',
            'tool search_similar_errors returned 3 matches',
        ])

    def test_json_with_string_evidence(self):
        """S3 P5: string evidence is wrapped in a list."""
        content = json.dumps({'summary': 'ok', 'evidence': 'single evidence string'})

        summary, suggestions, evidence = _parse_agent_result(content)

        self.assertEqual(evidence, ['single evidence string'])

    def test_markdown_fence_json(self):
        """JSON wrapped in ```json ... ``` fences is parsed correctly."""
        content = '```json\n{"summary": "fenced", "suggestions": ["a"]}\n```'

        summary, suggestions, evidence = _parse_agent_result(content)

        self.assertEqual(summary, 'fenced')
        self.assertEqual(suggestions, ['a'])
        self.assertEqual(evidence, [])

    def test_plain_markdown_fence(self):
        """Plain ``` fence (no json lang) also stripped."""
        content = '```\n{"summary": "plain", "suggestions": []}\n```'

        summary, suggestions, evidence = _parse_agent_result(content)

        self.assertEqual(summary, 'plain')
        self.assertEqual(evidence, [])

    def test_non_json_text_fallback(self):
        """Non-JSON text returns raw content (truncated to 1000) as summary, empty suggestions."""
        content = 'This is just plain text, not JSON.'

        summary, suggestions, evidence = _parse_agent_result(content)

        self.assertEqual(summary, 'This is just plain text, not JSON.')
        self.assertEqual(suggestions, [])
        self.assertEqual(evidence, [])

    def test_long_non_json_text_truncated_to_1000(self):
        """Plain-text fallback is truncated to 1000 chars."""
        long_text = 'a' * 2000

        summary, suggestions, evidence = _parse_agent_result(long_text)

        self.assertEqual(len(summary), 1000)
        self.assertEqual(evidence, [])

    def test_json_with_string_suggestion(self):
        """If 'suggestions' is a string instead of list, it's wrapped in a list."""
        content = json.dumps({'summary': 'ok', 'suggestions': 'single string suggestion'})

        summary, suggestions, evidence = _parse_agent_result(content)

        self.assertEqual(suggestions, ['single string suggestion'])
        self.assertEqual(evidence, [])

    def test_json_with_invalid_suggestions_type(self):
        """If 'suggestions' is int/dict/None, returns empty list."""
        content = json.dumps({'summary': 'ok', 'suggestions': 42})

        summary, suggestions, evidence = _parse_agent_result(content)

        self.assertEqual(suggestions, [])
        self.assertEqual(evidence, [])

    def test_json_with_empty_summary(self):
        """Empty summary string falls back to 'Analysis completed.'."""
        content = json.dumps({'summary': '', 'suggestions': []})

        summary, suggestions, evidence = _parse_agent_result(content)

        self.assertEqual(summary, 'Analysis completed.')
        self.assertEqual(evidence, [])

    def test_json_missing_summary_key(self):
        """Missing 'summary' key also falls back to 'Analysis completed.'."""
        content = json.dumps({'suggestions': []})

        summary, suggestions, evidence = _parse_agent_result(content)

        self.assertEqual(summary, 'Analysis completed.')
        self.assertEqual(evidence, [])


class VerifyEvidenceTest(SimpleTestCase):
    """P2 (2026-08-17): 幻觉防线强校验 — evidence ↔ 工具观测比对."""

    def test_all_verified(self):
        evidence = ['get_error_log returned exit_code=1']
        observations = ['tool get_error_log returned exit_code=1 for execution 42']
        result = _verify_evidence(evidence, observations)
        self.assertEqual(result['verified'], evidence)
        self.assertEqual(result['unverified'], [])

    def test_paraphrase_verified(self):
        """evidence 为观测的转述 (含关键 token) → 通过 (阈值 0.3)."""
        evidence = ['get_error_log shows exit_code=1 for execution 42']
        observations = [
            'tool get_error_log returned exit_code=1 for execution 42'
        ]
        result = _verify_evidence(evidence, observations)
        self.assertEqual(
            result['verified'], ['get_error_log shows exit_code=1 for execution 42'],
        )

    def test_unrelated_evidence_unverified(self):
        evidence = ['the database was completely wiped last night']
        observations = ['tool get_error_log returned exit_code=1']
        result = _verify_evidence(evidence, observations)
        self.assertEqual(result['verified'], [])
        self.assertEqual(result['unverified'], evidence)

    def test_empty_evidence_returns_empty_lists(self):
        result = _verify_evidence([], ['some observation'])
        self.assertEqual(result, {'verified': [], 'unverified': []})

    def test_no_observations_all_unverified(self):
        result = _verify_evidence(['claimed fact'], [])
        self.assertEqual(result['verified'], [])
        self.assertEqual(result['unverified'], ['claimed fact'])
