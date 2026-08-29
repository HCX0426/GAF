"""Tests for GameProfile detail sub-resource APIs (Stage 2)."""
from django.test import TestCase
from pipeline.models import TaskChain
from rest_framework.test import APIClient

from accounts.models import User
from gamestate.models import GameProfile


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _unwrap_json(r):
    """适配 unified_response 信封 (json 版)。优先取 ['data'], 降级到裸响应。"""
    body = r.json()
    if isinstance(body, dict) and 'data' in body and 'code' in body and 'message' in body:
        return body['data']
    return body


def _extract_results(resp):
    """Extract results list from a possibly-paginated response.

    TD-336 #6: shared helper so sub-resource tests assert response body
    structure (list or paginated dict) in addition to status_code.
    """
    data = _unwrap(resp)
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    return data


class GameProfileSubResourceAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_superuser('admin', 'admin@test.com', 'admin123')
        self.client.force_authenticate(user=self.user)
        self.profile = GameProfile.objects.create(game_name='BD2')

    def test_get_tasks_subresource(self):
        url = f'/api/v2/gamestate/game-profiles/{self.profile.id}/tasks/'
        r = self.client.get(url)
        assert r.status_code == 200
        # TD-336 #6: assert response body is a list (empty for fresh profile)
        results = _extract_results(r)
        assert isinstance(results, list)
        assert results == []

    def test_get_task_chains_subresource(self):
        url = f'/api/v2/gamestate/game-profiles/{self.profile.id}/task_chains/'
        r = self.client.get(url)
        assert r.status_code == 200
        results = _extract_results(r)
        assert isinstance(results, list)
        assert results == []

    def test_get_devices_subresource(self):
        url = f'/api/v2/gamestate/game-profiles/{self.profile.id}/devices/'
        r = self.client.get(url)
        assert r.status_code == 200
        results = _extract_results(r)
        assert isinstance(results, list)
        assert results == []

    def test_get_accounts_subresource(self):
        url = f'/api/v2/gamestate/game-profiles/{self.profile.id}/accounts/'
        r = self.client.get(url)
        assert r.status_code == 200
        results = _extract_results(r)
        assert isinstance(results, list)
        assert results == []

    def test_get_resource_packs_subresource(self):
        url = f'/api/v2/gamestate/game-profiles/{self.profile.id}/resource_packs/'
        r = self.client.get(url)
        assert r.status_code == 200
        results = _extract_results(r)
        assert isinstance(results, list)
        assert results == []


class GameProfileDefaultRoutineAPITest(TestCase):
    """Tests for PATCH /api/v2/gamestate/game-profiles/{id}/default-task-chain/ (spec 2.3)."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_superuser('admin', 'admin@test.com', 'admin123')
        # create_superuser does not set User.role; default_task_chain needs
        # 'manage' permission, so we must explicitly grant admin role.
        self.user.role = 'admin'
        self.user.save(update_fields=['role'])
        self.client.force_authenticate(user=self.user)
        self.profile = GameProfile.objects.create(game_name='BD2')
        self.chain = TaskChain.objects.create(
            name='chain-1',
            game_profile=self.profile,
            created_by=self.user,
        )

    def test_set_default_task_chain_success(self):
        url = f'/api/v2/gamestate/game-profiles/{self.profile.id}/default-task-chain/'
        r = self.client.patch(url, {'task_chain_id': self.chain.id}, format='json')
        assert r.status_code == 200
        # TD-336 #6: assert response body confirms the new default chain
        assert _unwrap(r)['default_task_chain_id'] == self.chain.id
        self.profile.refresh_from_db()
        assert self.profile.default_task_chain_id == self.chain.id
        self.chain.refresh_from_db()
        assert self.chain.is_default is True

    def test_set_default_task_chain_missing_task_chain_id(self):
        url = f'/api/v2/gamestate/game-profiles/{self.profile.id}/default-task-chain/'
        r = self.client.patch(url, {}, format='json')
        assert r.status_code == 400

    def test_set_default_task_chain_chain_not_found(self):
        url = f'/api/v2/gamestate/game-profiles/{self.profile.id}/default-task-chain/'
        r = self.client.patch(url, {'task_chain_id': 999999}, format='json')
        assert r.status_code == 404

    def test_set_default_task_chain_chain_belongs_to_other_profile(self):
        other_profile = GameProfile.objects.create(game_name='OtherGame')
        other_chain = TaskChain.objects.create(
            name='other-chain',
            game_profile=other_profile,
            created_by=self.user,
        )
        url = f'/api/v2/gamestate/game-profiles/{self.profile.id}/default-task-chain/'
        r = self.client.patch(url, {'task_chain_id': other_chain.id}, format='json')
        assert r.status_code == 400
        # Source profile should not have been mutated.
        self.profile.refresh_from_db()
        assert self.profile.default_task_chain_id is None

    def test_set_default_task_chain_clears_previous_default(self):
        """Setting a new default should clear is_default on the previous chain."""
        chain2 = TaskChain.objects.create(
            name='chain-2',
            game_profile=self.profile,
            is_default=True,
            created_by=self.user,
        )
        self.profile.default_task_chain = chain2
        self.profile.save(update_fields=['default_task_chain'])

        url = f'/api/v2/gamestate/game-profiles/{self.profile.id}/default-task-chain/'
        r = self.client.patch(url, {'task_chain_id': self.chain.id}, format='json')
        assert r.status_code == 200

        chain2.refresh_from_db()
        self.chain.refresh_from_db()
        assert chain2.is_default is False
        assert self.chain.is_default is True
        self.profile.refresh_from_db()
        assert self.profile.default_task_chain_id == self.chain.id


class GameProfileDispatchRoutineAPITest(TestCase):
    """Tests for POST /api/v2/gamestate/game-profiles/{id}/dispatch-routine/ (spec 2.3).

    The success path calls ``create_chain_execution_and_dispatch`` which
    triggers ``dispatch_chain_node.delay`` (Celery). To keep these tests
    hermetic, we only exercise error paths + skip paths here; the
    end-to-end dispatch flow is covered by ``pipeline/tests/test_chain_executor.py``.
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_superuser('admin', 'admin@test.com', 'admin123')
        # dispatch_routine needs 'execute' permission; admin role grants it.
        self.user.role = 'admin'
        self.user.save(update_fields=['role'])
        self.client.force_authenticate(user=self.user)
        self.profile = GameProfile.objects.create(game_name='BD2')

    def test_dispatch_routine_no_default_task_chain_returns_400(self):
        url = f'/api/v2/gamestate/game-profiles/{self.profile.id}/dispatch-routine/'
        r = self.client.post(url, {}, format='json')
        assert r.status_code == 400
        # unified_response 信封下, 400 错误信息在 message 或 data.error
        body = r.json()
        msg = body.get('message', '') if isinstance(body, dict) else ''
        err_data = body.get('data') if isinstance(body, dict) else None
        if isinstance(err_data, dict) and 'error' in err_data:
            assert 'default_task_chain' in err_data['error']
        else:
            assert 'default_task_chain' in msg or 'default_task_chain' in str(body)

    def test_dispatch_routine_disabled_chain_returns_400(self):
        chain = TaskChain.objects.create(
            name='disabled-chain',
            game_profile=self.profile,
            is_enabled=False,
            is_default=True,
            created_by=self.user,
        )
        self.profile.default_task_chain = chain
        self.profile.save(update_fields=['default_task_chain'])
        url = f'/api/v2/gamestate/game-profiles/{self.profile.id}/dispatch-routine/'
        r = self.client.post(url, {}, format='json')
        assert r.status_code == 400
        body = r.json()
        msg = body.get('message', '') if isinstance(body, dict) else ''
        err_data = body.get('data') if isinstance(body, dict) else None
        if isinstance(err_data, dict) and 'error' in err_data:
            assert 'disabled' in err_data['error']
        else:
            assert 'disabled' in msg or 'disabled' in str(body)

    def test_dispatch_routine_skips_devices_without_online_agent(self):
        """Devices without a bound Agent should be skipped, not failed."""
        from agents.models import Device

        chain = TaskChain.objects.create(
            name='active-chain',
            game_profile=self.profile,
            is_enabled=True,
            is_default=True,
            created_by=self.user,
        )
        self.profile.default_task_chain = chain
        self.profile.save(update_fields=['default_task_chain'])

        # Device bound to this profile but with no Agent — must be skipped.
        Device.objects.create(
            name='orphan-window',
            device_type='windows',
            game_profile=self.profile,
        )

        url = f'/api/v2/gamestate/game-profiles/{self.profile.id}/dispatch-routine/'
        r = self.client.post(url, {}, format='json')
        assert r.status_code == 200
        body = _unwrap_json(r)
        assert body['dispatched_count'] == 0
        assert body['skipped_count'] == 1
        assert body['skipped'][0]['reason'] == 'no_agent_bound'
