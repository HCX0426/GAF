"""Tests for S4 multi-turn QA: QAMessage model, AskView multi-turn, QAMessageViewSet.

Covers:
- QAMessage model: creation, role choices, CASCADE delete, ordering, __str__.
- AskView with session_id: history passed to call_llm, QAMessage persistence,
  title backfill, new-session creation, history limit (last 20), ownership.
- QAMessageViewSet: list/create/by_session, ownership filtering, admin access.

(Migrated from qa app — 2026-08-04)
"""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from gaf_ai.models import QAMessage, QASession


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


class MultiTurnTestBase(TestCase):
    """Base setUp with admin / operator users and login helper."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='mt_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        self.operator = User.objects.create_user(
            username='mt_operator', password='OpPass123!', role=User.Role.OPERATOR,
        )

    def _login(self, user):
        """Login as the given user and set Authorization header."""
        password = {
            self.admin: 'AdminPass123!',
            self.operator: 'OpPass123!',
        }[user]
        resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': user.username,
            'password': password,
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        _token = resp.data.get('data', {}).get('access') or resp.data.get('access')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")

    def _make_message(self, session, role, content, offset_seconds=0):
        """Create a QAMessage with an explicit created_at timestamp."""
        msg = QAMessage.objects.create(session=session, role=role, content=content)
        if offset_seconds:
            new_ts = timezone.now() - timedelta(seconds=offset_seconds)
            QAMessage.objects.filter(pk=msg.pk).update(created_at=new_ts)
            msg.refresh_from_db()
        return msg


class QAMessageModelTests(MultiTurnTestBase):
    """QAMessage model creation, role choices, CASCADE, ordering, __str__."""

    def test_create_message(self):
        """QAMessage created with session/role/content gets defaults."""
        session = QASession.objects.create(question='q', user=self.admin)
        msg = QAMessage.objects.create(
            session=session,
            role=QAMessage.Role.USER,
            content='Hello',
        )
        self.assertEqual(msg.role, 'user')
        self.assertEqual(msg.content, 'Hello')
        self.assertIsNotNone(msg.created_at)
        self.assertEqual(msg.session, session)

    def test_role_choices(self):
        """All three role choices (user/assistant/system) are accepted."""
        session = QASession.objects.create(question='q', user=self.admin)
        for role_value, role_enum in [
            ('user', QAMessage.Role.USER),
            ('assistant', QAMessage.Role.ASSISTANT),
            ('system', QAMessage.Role.SYSTEM),
        ]:
            msg = QAMessage.objects.create(
                session=session, role=role_enum, content=f'msg-{role_value}',
            )
            self.assertEqual(msg.role, role_value)

    def test_cascade_delete_session_deletes_messages(self):
        """Deleting a QASession CASCADE-deletes all its QAMessage rows."""
        session = QASession.objects.create(question='q', user=self.admin)
        QAMessage.objects.create(session=session, role='user', content='m1')
        QAMessage.objects.create(session=session, role='assistant', content='m2')
        self.assertEqual(QAMessage.objects.filter(session=session).count(), 2)
        session.delete()
        self.assertEqual(QAMessage.objects.count(), 0)

    def test_ordering_by_created_at_asc(self):
        """QAMessage Meta ordering is +created_at (oldest first)."""
        session = QASession.objects.create(question='q', user=self.admin)
        old = self._make_message(session, 'user', 'old', offset_seconds=20)
        new = self._make_message(session, 'user', 'new', offset_seconds=0)
        msgs = list(QAMessage.objects.filter(session=session))
        self.assertEqual(msgs[0], old)
        self.assertEqual(msgs[1], new)

    def test_str_representation(self):
        """__str__ returns 'role: content[:50]'."""
        session = QASession.objects.create(question='q', user=self.admin)
        msg = QAMessage.objects.create(
            session=session, role='assistant', content='Short answer',
        )
        self.assertEqual(str(msg), 'assistant: Short answer')

    def test_str_truncates_long_content(self):
        """__str__ truncates content to 50 chars."""
        session = QASession.objects.create(question='q', user=self.admin)
        long_content = 'X' * 100
        msg = QAMessage.objects.create(
            session=session, role='user', content=long_content,
        )
        self.assertEqual(str(msg), f'user: {"X" * 50}')

    def test_related_name_messages(self):
        """related_name='messages' allows session.messages access."""
        session = QASession.objects.create(question='q', user=self.admin)
        QAMessage.objects.create(session=session, role='user', content='m1')
        QAMessage.objects.create(session=session, role='assistant', content='m2')
        self.assertEqual(session.messages.count(), 2)

    def test_qasession_title_field_default(self):
        """QASession.title defaults to empty string."""
        session = QASession.objects.create(question='q')
        self.assertEqual(session.title, '')


class AskViewMultiturnTests(MultiTurnTestBase):
    """AskView multi-turn behavior — POST /api/v2/qa/ask/ with session_id."""

    @mock.patch('gaf_ai.llm_service.call_llm')
    def test_ask_with_session_id_creates_two_messages(self, mock_call_llm):
        """POST /ask/ with session_id → 201, creates user+assistant QAMessages."""
        mock_call_llm.return_value = {
            'content': 'Answer to follow-up',
            'input_tokens': 10,
            'output_tokens': 20,
            'model': 'gpt-4o-mini',
            'cost': 0.0,
            'route': 'preferred',
        }
        session = QASession.objects.create(
            question='first question', title='first', user=self.admin,
        )
        self._login(self.admin)
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'follow-up question',
            'session_id': session.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(QAMessage.objects.filter(session=session).count(), 2)
        msgs = list(QAMessage.objects.filter(session=session).order_by('created_at'))
        self.assertEqual(msgs[0].role, 'user')
        self.assertEqual(msgs[0].content, 'follow-up question')
        self.assertEqual(msgs[1].role, 'assistant')
        self.assertEqual(msgs[1].content, 'Answer to follow-up')

    @mock.patch('gaf_ai.llm_service.call_llm')
    def test_ask_with_session_id_passes_history_to_llm(self, mock_call_llm):
        """call_llm receives system + history messages + new user question."""
        mock_call_llm.return_value = {
            'content': 'ans', 'input_tokens': 1, 'output_tokens': 1,
            'model': 'gpt-4o-mini', 'cost': 0.0, 'route': 'preferred',
        }
        session = QASession.objects.create(
            question='q1', title='t1', user=self.admin,
        )
        self._make_message(session, 'user', 'hist-q1', offset_seconds=40)
        self._make_message(session, 'assistant', 'hist-a1', offset_seconds=30)
        self._make_message(session, 'user', 'hist-q2', offset_seconds=20)
        self._make_message(session, 'assistant', 'hist-a2', offset_seconds=10)

        self._login(self.admin)
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'new question',
            'session_id': session.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        mock_call_llm.assert_called_once()
        kwargs = mock_call_llm.call_args.kwargs
        messages = kwargs['messages']
        self.assertEqual(len(messages), 6)
        self.assertEqual(messages[0]['role'], 'system')
        self.assertEqual(messages[1]['content'], 'hist-q1')
        self.assertEqual(messages[2]['content'], 'hist-a1')
        self.assertEqual(messages[3]['content'], 'hist-q2')
        self.assertEqual(messages[4]['content'], 'hist-a2')
        self.assertEqual(messages[5]['role'], 'user')
        self.assertEqual(messages[5]['content'], 'new question')

    @mock.patch('gaf_ai.llm_service.call_llm')
    def test_ask_without_session_id_creates_new_session(self, mock_call_llm):
        """POST /ask/ without session_id → 201, new QASession + 2 QAMessages."""
        mock_call_llm.return_value = {
            'content': 'fresh answer', 'input_tokens': 1, 'output_tokens': 1,
            'model': 'gpt-4o-mini', 'cost': 0.0, 'route': 'preferred',
        }
        self._login(self.admin)
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'How to use GAF?',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        session = QASession.objects.get(pk=_unwrap(resp)['id'])
        self.assertEqual(session.title, 'How to use GAF?')
        self.assertEqual(session.user, self.admin)
        self.assertEqual(QAMessage.objects.filter(session=session).count(), 2)
        self.assertEqual(_unwrap(resp)['message_count'], 2)
        self.assertIsNotNone(_unwrap(resp)['last_message_at'])

    @mock.patch('gaf_ai.llm_service.call_llm')
    def test_history_limit_last_20_messages(self, mock_call_llm):
        """When 25 prior messages exist, call_llm receives only the last 20."""
        mock_call_llm.return_value = {
            'content': 'ans', 'input_tokens': 1, 'output_tokens': 1,
            'model': 'gpt-4o-mini', 'cost': 0.0, 'route': 'preferred',
        }
        session = QASession.objects.create(
            question='q', title='t', user=self.admin,
        )
        for i in range(25):
            offset = (25 - i) * 10
            self._make_message(
                session, 'user' if i % 2 == 0 else 'assistant',
                f'hist-{i + 1}', offset_seconds=offset,
            )

        self._login(self.admin)
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'new',
            'session_id': session.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        mock_call_llm.assert_called_once()
        messages = mock_call_llm.call_args.kwargs['messages']
        self.assertEqual(len(messages), 22)
        history = messages[1:21]
        self.assertEqual(history[0]['content'], 'hist-6')
        self.assertEqual(history[-1]['content'], 'hist-25')
        self.assertEqual(messages[21]['content'], 'new')

    @mock.patch('gaf_ai.llm_service.call_llm')
    def test_session_id_not_owned_by_non_admin_returns_404(self, mock_call_llm):
        """Non-admin user passing another user's session_id → 404."""
        mock_call_llm.return_value = {
            'content': 'ans', 'input_tokens': 1, 'output_tokens': 1,
            'model': 'gpt-4o-mini', 'cost': 0.0, 'route': 'preferred',
        }
        admin_session = QASession.objects.create(
            question='admin q', title='t', user=self.admin,
        )
        self._login(self.operator)
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'intrusion',
            'session_id': admin_session.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        mock_call_llm.assert_not_called()

    @mock.patch('gaf_ai.llm_service.call_llm')
    def test_admin_can_continue_other_users_session(self, mock_call_llm):
        """Admin passing another user's session_id → 201."""
        mock_call_llm.return_value = {
            'content': 'admin ans', 'input_tokens': 1, 'output_tokens': 1,
            'model': 'gpt-4o-mini', 'cost': 0.0, 'route': 'preferred',
        }
        operator_session = QASession.objects.create(
            question='op q', title='t', user=self.operator,
        )
        self._login(self.admin)
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'admin follow-up',
            'session_id': operator_session.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(resp)['id'], operator_session.id)

    @mock.patch('gaf_ai.llm_service.call_llm')
    def test_title_backfill_on_empty_title(self, mock_call_llm):
        """Continued session with empty title gets title from new question."""
        mock_call_llm.return_value = {
            'content': 'ans', 'input_tokens': 1, 'output_tokens': 1,
            'model': 'gpt-4o-mini', 'cost': 0.0, 'route': 'preferred',
        }
        session = QASession.objects.create(
            question='orig q', title='', user=self.admin,
        )
        self._login(self.admin)
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'A new question that becomes the title',
            'session_id': session.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        session.refresh_from_db()
        self.assertEqual(session.title, 'A new question that becomes the title')

    @mock.patch('gaf_ai.llm_service.call_llm')
    def test_existing_title_not_overwritten(self, mock_call_llm):
        """Continued session with existing title keeps the original title."""
        mock_call_llm.return_value = {
            'content': 'ans', 'input_tokens': 1, 'output_tokens': 1,
            'model': 'gpt-4o-mini', 'cost': 0.0, 'route': 'preferred',
        }
        session = QASession.objects.create(
            question='orig q', title='Original Title', user=self.admin,
        )
        self._login(self.admin)
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'different question',
            'session_id': session.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        session.refresh_from_db()
        self.assertEqual(session.title, 'Original Title')

    @mock.patch('gaf_ai.llm_service.call_llm')
    def test_llm_failure_still_persists_messages(self, mock_call_llm):
        """When call_llm raises LLMAPIError, user+assistant messages are still saved."""
        from gaf_ai.qa_llm_client import LLMAPIError

        mock_call_llm.side_effect = LLMAPIError('simulated 500')
        session = QASession.objects.create(
            question='q', title='t', user=self.admin,
        )
        self._login(self.admin)
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'will fail',
            'session_id': session.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        msgs = list(QAMessage.objects.filter(session=session).order_by('created_at'))
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0].role, 'user')
        self.assertEqual(msgs[0].content, 'will fail')
        self.assertEqual(msgs[1].role, 'assistant')
        self.assertIn('[LLM 调用失败:', msgs[1].content)


class QAMessageViewSetTests(MultiTurnTestBase):
    """QAMessageViewSet — list / create / by_session / ownership filtering."""

    def test_list_filtered_by_user(self):
        """Non-admin user sees only messages from own sessions."""
        own_session = QASession.objects.create(question='own', user=self.operator)
        other_session = QASession.objects.create(question='other', user=self.admin)
        QAMessage.objects.create(session=own_session, role='user', content='mine')
        QAMessage.objects.create(session=other_session, role='user', content='theirs')
        self._login(self.operator)
        resp = self.client.get('/api/v2/qa/messages/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['content'], 'mine')

    def test_admin_sees_all_messages(self):
        """Admin sees messages from all sessions."""
        s1 = QASession.objects.create(question='q1', user=self.admin)
        s2 = QASession.objects.create(question='q2', user=self.operator)
        QAMessage.objects.create(session=s1, role='user', content='admin msg')
        QAMessage.objects.create(session=s2, role='user', content='op msg')
        self._login(self.admin)
        resp = self.client.get('/api/v2/qa/messages/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = _get_results(resp)
        self.assertEqual(len(results), 2)

    def test_list_filter_by_session_param(self):
        """GET /messages/?session=<id> filters to that session only."""
        s1 = QASession.objects.create(question='q1', user=self.admin)
        s2 = QASession.objects.create(question='q2', user=self.admin)
        QAMessage.objects.create(session=s1, role='user', content='m1')
        QAMessage.objects.create(session=s1, role='assistant', content='m2')
        QAMessage.objects.create(session=s2, role='user', content='m3')
        self._login(self.admin)
        resp = self.client.get(f'/api/v2/qa/messages/?session={s1.id}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = _get_results(resp)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r['session'], s1.id)

    def test_by_session_returns_ordered_messages(self):
        """GET /messages/by_session/?session=<id> returns messages in asc order."""
        session = QASession.objects.create(question='q', user=self.admin)
        self._make_message(session, 'user', 'first', offset_seconds=20)
        self._make_message(session, 'assistant', 'second', offset_seconds=10)
        self._make_message(session, 'user', 'third', offset_seconds=0)
        self._login(self.admin)
        resp = self.client.get(f'/api/v2/qa/messages/by_session/?session={session.id}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = _unwrap(resp)
        self.assertEqual(len(body), 3)
        self.assertEqual(body[0]['content'], 'first')
        self.assertEqual(body[1]['content'], 'second')
        self.assertEqual(body[2]['content'], 'third')

    def test_by_session_missing_param_returns_400(self):
        """GET /messages/by_session/ without session param → 400."""
        self._login(self.admin)
        resp = self.client.get('/api/v2/qa/messages/by_session/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_message_on_own_session(self):
        """POST /messages/ creates a QAMessage on user's own session."""
        session = QASession.objects.create(question='q', user=self.operator)
        self._login(self.operator)
        resp = self.client.post('/api/v2/qa/messages/', {
            'session': session.id,
            'role': 'user',
            'content': 'manual message',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(resp)['content'], 'manual message')
        self.assertEqual(_unwrap(resp)['role'], 'user')
        self.assertEqual(_unwrap(resp)['session'], session.id)

    def test_create_message_on_other_session_denied(self):
        """Non-admin cannot create a message on another user's session (404)."""
        admin_session = QASession.objects.create(question='q', user=self.admin)
        self._login(self.operator)
        resp = self.client.post('/api/v2/qa/messages/', {
            'session': admin_session.id,
            'role': 'user',
            'content': 'intrusion',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_other_users_message_404(self):
        """Non-admin retrieving a message from another user's session → 404."""
        admin_session = QASession.objects.create(question='q', user=self.admin)
        msg = QAMessage.objects.create(
            session=admin_session, role='user', content='admin msg',
        )
        self._login(self.operator)
        resp = self.client.get(f'/api/v2/qa/messages/{msg.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_own_message(self):
        """User can retrieve a message from their own session."""
        session = QASession.objects.create(question='q', user=self.operator)
        msg = QAMessage.objects.create(
            session=session, role='user', content='my msg',
        )
        self._login(self.operator)
        resp = self.client.get(f'/api/v2/qa/messages/{msg.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(resp)['content'], 'my msg')

    def test_unauthenticated_denied(self):
        """Unauthenticated request gets 401."""
        resp = self.client.get('/api/v2/qa/messages/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
