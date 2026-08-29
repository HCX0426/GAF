"""A1-fix (2026-08-26): unattended start must register dispatched chains.

Verifies that ``unattended_start_view`` registers the start-round dispatches
on the created session — otherwise the completion hook cannot attribute the
chain: rotation never advances, loop_rotation never returns accounts, and
all_completed AutoStop never fires (TD-400 root gap).
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from pipeline.models import TaskChain, TaskChainExecution, TaskChainNode
from rest_framework.test import APIClient

from accounts.models import GameAccount
from agents.models import Agent, Device
from gamestate.models import GameProfile
from scheduler.models import GameAccountRotation, UnattendedSession
from scheduler.tasks import on_chain_execution_completed
from tasks.models import Task

User = get_user_model()
START_URL = '/api/v2/scheduler/unattended/start/'


@pytest.fixture
def start_user(db):
    return User.objects.create_user(username='start_user', password='Pass123!')


def _build_stack(start_user):
    """Profile + enabled chain (1 node) + online agent + online device."""
    profile = GameProfile.objects.create(game_name='StartGame')
    chain = TaskChain.objects.create(
        name='start-chain', game_profile=profile, is_enabled=True, is_default=True,
    )
    task = Task.objects.create(name='StartTask')
    TaskChainNode.objects.create(chain=chain, task=task, order=1)
    profile.default_routine = chain
    profile.save(update_fields=['default_routine'])
    agent = Agent.objects.create(
        agent_id='start-agent', hostname='h', status=Agent.Status.ONLINE,
    )
    device = Device.objects.create(
        name='start-device', device_type=Device.DeviceType.WINDOWS,
        game_profile=profile, agent=agent,
    )
    return profile, chain, device


def _make_account(start_user):
    return GameAccount.objects.create(
        owner=start_user,
        game_profile=GameProfile.objects.get_or_create(game_name='StartGame')[0],
        game_name='StartGame', username='acc-1',
        server_region='官服', login_method='password', status='ok',
    )


def _post_start(start_user, **extra):
    client = APIClient()
    client.force_authenticate(start_user)
    return client.post(START_URL, {'game_profile_id': extra['profile'].id, **extra['body']}, format='json')


@pytest.mark.django_db
def test_start_registers_chain_and_account_on_session(start_user):
    profile, _chain, _device = _build_stack(start_user)
    acc = _make_account(start_user)
    rule = GameAccountRotation.objects.create(name='rot', rotation_strategy='sequential')
    rule.accounts.add(acc)

    with patch('pipeline.tasks.dispatch_chain_node.delay'):
        res = _post_start(
            start_user, profile=profile,
            body={'rotation_rule_id': rule.id, 'loop_rotation': True},
        )

    assert res.status_code == 200
    session = UnattendedSession.objects.get(game_profile=profile)
    assert list(session.dispatched_account_ids) == [acc.id]
    assert session.active_chain_executions.count() == 1
    chain_exec = session.active_chain_executions.first()
    assert chain_exec.game_account_id == acc.id  # start fallback to rotation first


@pytest.mark.django_db
def test_start_uses_static_coordinates_without_account_bound(start_user):
    """Device without a bound account + no rotation rule → dispatched without
    game_account (chain still created), but still registered on the session."""
    profile, _chain, _device = _build_stack(start_user)

    with patch('pipeline.tasks.dispatch_chain_node.delay'):
        res = _post_start(start_user, profile=profile, body={})

    assert res.status_code == 200
    session = UnattendedSession.objects.get(game_profile=profile)
    assert session.active_chain_executions.count() == 1
    assert session.dispatched_account_ids == []


@pytest.mark.django_db
def test_start_registration_enables_loop_completion_return(start_user):
    """Once registered, a completed start-round chain is attributed to the
    session and loop_rotation returns the account for the next tick."""
    profile, _chain, _device = _build_stack(start_user)
    acc = _make_account(start_user)
    rule = GameAccountRotation.objects.create(name='rot', rotation_strategy='sequential')
    rule.accounts.add(acc)

    with patch('pipeline.tasks.dispatch_chain_node.delay'):
        res = _post_start(
            start_user, profile=profile,
            body={'rotation_rule_id': rule.id, 'loop_rotation': True},
        )

    assert res.status_code == 200
    session = UnattendedSession.objects.get(game_profile=profile)
    chain_exec = session.active_chain_executions.first()
    assert chain_exec.game_account_id == acc.id

    # Simulate terminal save (agent result path) — directly drive the hook
    # (the signal enqueues the same task; calling in-process keeps it deterministic).
    chain_exec.status = TaskChainExecution.Status.SUCCESS
    chain_exec.save()
    with patch('scheduler.engine.check_time_window', return_value=True):
        on_chain_execution_completed(chain_exec.id)

    session.refresh_from_db()
    assert session.active_chain_executions.count() == 0
    assert acc.id not in session.dispatched_account_ids  # returned to pool
