"""Tests for qa API views: QASessionViewSet, LLMUsageLogViewSet, AskView.

Covers CRUD, permission matrix (admin/operator/viewer), URL existence,
filtering, and the mark-knowledge custom action.

(Migrated from qa app — 2026-08-04)
"""

from unittest import mock

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from gaf_ai.models import LLMUsageLog, QASession


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _extract_results(response_data):
    """Extract list from either paginated dict or plain list response."""
    if isinstance(response_data, dict) and 'results' in response_data:
        return response_data['results']
    return response_data


def _get_results(resp):
    """适配信封 + 分页。先解信封, 再取分页 results 字段。"""
    return _extract_results(_unwrap(resp))


class QAViewTestBase(TestCase):
    """Base setUp with admin / operator / viewer users and login helper."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='qa_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        self.operator = User.objects.create_user(
            username='qa_operator', password='OpPass123!', role=User.Role.OPERATOR,
        )
        self.viewer = User.objects.create_user(
            username='qa_viewer', password='ViewerPass123!', role=User.Role.VIEWER,
        )

    def _login(self, user):
        """Login as the given user and set Authorization header."""
        resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': user.username,
            'password': {
                self.admin: 'AdminPass123!',
                self.operator: 'OpPass123!',
                self.viewer: 'ViewerPass123!',
            }[user],
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        _token = resp.data.get('data', {}).get('access') or resp.data.get('access')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")


class QASessionListTests(QAViewTestBase):
    """QASessionViewSet list — GET /api/v2/qa/qa-sessions/ (required_permission='llm_use')."""

    def test_admin_sees_all_sessions(self):
        """Admin can see all QASessions regardless of owner."""
        QASession.objects.create(question='q1', user=self.operator)
        QASession.objects.create(question='q2', user=self.admin)
        QASession.objects.create(question='q3', user=None)
        self._login(self.admin)
        resp = self.client.get('/api/v2/qa/qa-sessions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = _get_results(resp)
        self.assertEqual(len(results), 3)

    def test_operator_sees_only_own(self):
        """Non-admin user sees only their own sessions."""
        QASession.objects.create(question='mine', user=self.operator)
        QASession.objects.create(question='theirs', user=self.admin)
        self._login(self.operator)
        resp = self.client.get('/api/v2/qa/qa-sessions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['question'], 'mine')

    def test_viewer_denied(self):
        """Viewer role lacks 'llm_use' permission and gets 403."""
        self._login(self.viewer)
        resp = self.client.get('/api/v2/qa/qa-sessions/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_denied(self):
        """Unauthenticated request gets 401."""
        resp = self.client.get('/api/v2/qa/qa-sessions/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_filter_by_is_knowledge_entry(self):
        """Filtering by is_knowledge_entry works."""
        QASession.objects.create(question='normal', user=self.admin, is_knowledge_entry=False)
        QASession.objects.create(question='knowledge', user=self.admin, is_knowledge_entry=True)
        self._login(self.admin)
        resp = self.client.get('/api/v2/qa/qa-sessions/?is_knowledge_entry=true')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['is_knowledge_entry'])


class QASessionCRUDTests(QAViewTestBase):
    """QASessionViewSet create / retrieve / delete."""

    def test_create_session(self):
        """POST creates a new QASession; perform_create sets user from request."""
        self._login(self.admin)
        resp = self.client.post('/api/v2/qa/qa-sessions/', {
            'question': 'What is GAF?',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(resp)['question'], 'What is GAF?')
        self.assertEqual(_unwrap(resp)['user'], self.admin.id)

    def test_retrieve_session(self):
        """Admin can retrieve any session by id."""
        session = QASession.objects.create(question='retrieve me', user=self.admin)
        self._login(self.admin)
        resp = self.client.get(f'/api/v2/qa/qa-sessions/{session.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(resp)['question'], 'retrieve me')

    def test_delete_session(self):
        """Admin can delete a session."""
        session = QASession.objects.create(question='delete me', user=self.admin)
        self._login(self.admin)
        resp = self.client.delete(f'/api/v2/qa/qa-sessions/{session.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(QASession.objects.filter(pk=session.pk).exists())

    def test_operator_cannot_retrieve_others(self):
        """Operator cannot retrieve a session owned by another user (404)."""
        session = QASession.objects.create(question='admin only', user=self.admin)
        self._login(self.operator)
        resp = self.client.get(f'/api/v2/qa/qa-sessions/{session.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class QASessionMarkKnowledgeTests(QAViewTestBase):
    """QASessionViewSet mark-knowledge custom action — POST /qa-sessions/<pk>/mark-knowledge/."""

    def test_toggle_to_true_by_default(self):
        """No body toggles is_knowledge_entry from False to True."""
        session = QASession.objects.create(question='q', user=self.admin, is_knowledge_entry=False)
        self._login(self.admin)
        resp = self.client.post(f'/api/v2/qa/qa-sessions/{session.pk}/mark-knowledge/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(_unwrap(resp)['is_knowledge_entry'])

    def test_toggle_to_false_by_default(self):
        """No body toggles is_knowledge_entry from True to False."""
        session = QASession.objects.create(question='q', user=self.admin, is_knowledge_entry=True)
        self._login(self.admin)
        resp = self.client.post(f'/api/v2/qa/qa-sessions/{session.pk}/mark-knowledge/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(_unwrap(resp)['is_knowledge_entry'])

    def test_explicit_true(self):
        """Explicit is_knowledge_entry=true sets it to True."""
        session = QASession.objects.create(question='q', user=self.admin, is_knowledge_entry=False)
        self._login(self.admin)
        resp = self.client.post(
            f'/api/v2/qa/qa-sessions/{session.pk}/mark-knowledge/',
            {'is_knowledge_entry': True}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(_unwrap(resp)['is_knowledge_entry'])

    def test_invalid_type_returns_400(self):
        """Non-boolean is_knowledge_entry returns 400."""
        session = QASession.objects.create(question='q', user=self.admin)
        self._login(self.admin)
        resp = self.client.post(
            f'/api/v2/qa/qa-sessions/{session.pk}/mark-knowledge/',
            {'is_knowledge_entry': 'yes'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_viewer_denied(self):
        """Viewer role gets 403 on mark-knowledge."""
        session = QASession.objects.create(question='q', user=self.admin)
        self._login(self.viewer)
        resp = self.client.post(f'/api/v2/qa/qa-sessions/{session.pk}/mark-knowledge/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class QASessionBudgetActionTests(QAViewTestBase):
    """QASessionViewSet budget custom action — GET /qa-sessions/budget/."""

    def test_budget_returns_info(self):
        """Budget action returns budget info for current user."""
        self._login(self.admin)
        resp = self.client.get('/api/v2/qa/qa-sessions/budget/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('status', _unwrap(resp))


class LLMUsageLogViewTests(QAViewTestBase):
    """LLMUsageLogViewSet — GET /api/v2/qa/llm-usage-logs/ (read-only)."""

    def test_admin_sees_all_logs(self):
        """Admin can see all LLMUsageLog entries."""
        LLMUsageLog.objects.create(user=self.admin, model_name='gpt-4o')
        LLMUsageLog.objects.create(user=self.operator, model_name='gpt-4o-mini')
        LLMUsageLog.objects.create(user=None, model_name='deepseek-chat')
        self._login(self.admin)
        resp = self.client.get('/api/v2/qa/llm-usage-logs/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = _get_results(resp)
        self.assertEqual(len(results), 3)

    def test_operator_sees_only_own(self):
        """Non-admin sees only their own logs."""
        LLMUsageLog.objects.create(user=self.operator, model_name='m1')
        LLMUsageLog.objects.create(user=self.admin, model_name='m2')
        self._login(self.operator)
        resp = self.client.get('/api/v2/qa/llm-usage-logs/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['model_name'], 'm1')

    def test_retrieve_single_log(self):
        """Admin can retrieve a single log by id."""
        log = LLMUsageLog.objects.create(user=self.admin, model_name='gpt-4o', input_tokens=100)
        self._login(self.admin)
        resp = self.client.get(f'/api/v2/qa/llm-usage-logs/{log.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(resp)['model_name'], 'gpt-4o')
        self.assertEqual(_unwrap(resp)['input_tokens'], 100)

    def test_viewer_denied(self):
        """Viewer role gets 403 on llm-usage-logs."""
        self._login(self.viewer)
        resp = self.client.get('/api/v2/qa/llm-usage-logs/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_denied(self):
        """Unauthenticated request gets 401."""
        resp = self.client.get('/api/v2/qa/llm-usage-logs/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_read_only_no_create(self):
        """POST (create) is not allowed on read-only viewset (405)."""
        self._login(self.admin)
        resp = self.client.post('/api/v2/qa/llm-usage-logs/', {
            'model_name': 'test',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_filter_by_model_name(self):
        """Filtering by model_name works."""
        LLMUsageLog.objects.create(user=self.admin, model_name='gpt-4o')
        LLMUsageLog.objects.create(user=self.admin, model_name='deepseek-chat')
        self._login(self.admin)
        resp = self.client.get('/api/v2/qa/llm-usage-logs/?model_name=gpt-4o')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['model_name'], 'gpt-4o')


class AskViewTests(QAViewTestBase):
    """AskView — POST /api/v2/qa/ask/ (required_permission='llm_use')."""

    @mock.patch('gaf_ai.llm_service.call_llm')
    def test_ask_returns_answer(self, mock_call_llm):
        """POST /api/v2/qa/ask/ returns a QASession with AI answer."""
        mock_call_llm.return_value = {
            'content': 'Use the Tasks page to create a task.',
            'input_tokens': 10,
            'output_tokens': 20,
            'model': 'gpt-4o-mini',
            'cost': 0.0,
            'route': 'preferred',
        }
        self._login(self.admin)
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'How to create a task?',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(resp)['question'], 'How to create a task?')
        self.assertEqual(_unwrap(resp)['answer'], 'Use the Tasks page to create a task.')
        self.assertEqual(_unwrap(resp)['user'], self.admin.id)
        self.assertEqual(
            LLMUsageLog.objects.filter(user=self.admin, call_type='qa').count(), 1
        )

    @mock.patch('gaf_ai.llm_service.call_llm')
    def test_ask_llm_failure_records_error(self, mock_call_llm):
        """When call_llm raises LLMAPIError, session.answer records the failure."""
        from gaf_ai.qa_llm_client import LLMAPIError

        mock_call_llm.side_effect = LLMAPIError('simulated 500')
        self._login(self.admin)
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'test question',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('[LLM 调用失败:', _unwrap(resp)['answer'])

    def test_viewer_denied(self):
        """Viewer role lacks 'llm_use' permission and gets 403."""
        self._login(self.viewer)
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'test',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_denied(self):
        """Unauthenticated request gets 401."""
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'test',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
