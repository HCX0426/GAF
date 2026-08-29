"""TD-400: UnattendedSession.loop_rotation tests.

Covers the loop-rotation behavior added for persistent multi-account
grinding (an account whose chain finished is returned to the rotation
pool so the same session keeps dispatching rounds):

- loop mode returns the finished account to dispatched_account_ids pool
- non-loop sessions keep the dispatch-once behavior (no return)
- loop mode disables the all_completed AutoStop (no premature stop)
- non-loop all_completed AutoStop still works (regression guard)
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from pipeline.models import TaskChain, TaskChainExecution

from accounts.models import GameAccount
from agents.models import Agent, Device
from gamestate.models import GameProfile
from scheduler.models import AutoStopCondition, UnattendedSession
from scheduler.tasks import on_chain_execution_completed

User = get_user_model()


@pytest.fixture
def base_data(db):
    """User + enabled chain + profile + online agent + online device."""
    user = User.objects.create_user(username='loop_user', password='Pass123!')
    chain = TaskChain.objects.create(name='Loop Chain', is_enabled=True)
    profile = GameProfile.objects.create(game_name='LoopGame', default_task_chain=chain)
    agent = Agent.objects.create(
        agent_id='loop-agent-1', hostname='h', status=Agent.Status.ONLINE,
    )
    device = Device.objects.create(
        name='loop-device', device_type=Device.DeviceType.WINDOWS,
        status=Device.Status.ONLINE, agent=agent, game_profile=profile,
    )
    return {'user': user, 'chain': chain, 'profile': profile, 'device': device}


@pytest.fixture
def loop_accounts(db, base_data):
    """Two GameAccounts owned by the session user."""
    accs = []
    for name in ('loop-acc-a', 'loop-acc-b'):
        accs.append(GameAccount.objects.create(
            owner=base_data['user'],
            game_profile=base_data['profile'],
            username=name,
            server_region='官服',
            login_method='password',
            status='ok',
        ))
    # Deterministic created_at (2026-08-27): auto_now_add records the same
    # microsecond for back-to-back creates, and sequential rotation ordering
    # (newest first) then ties on timestamp — the alternates test flaked
    # (dispatched b vs a depending on DB heap order). Force distinct times:
    # a is the OLDER account, b the newer one → ordered = [b, a] is stable.
    from datetime import timedelta as _td

    from django.utils import timezone as _tz

    GameAccount.objects.filter(pk=accs[0].pk).update(created_at=_tz.now() - _td(seconds=60))
    GameAccount.objects.filter(pk=accs[1].pk).update(created_at=_tz.now())
    return accs


def _make_chain_exec(base_data, account, status):
    return TaskChainExecution.objects.create(
        chain=base_data['chain'],
        triggered_by=base_data['user'],
        device=base_data['device'],
        game_account=account,
        status=status,
    )


def _run_completion(chain_exec, session):
    """Run the completion hook the same way the post_save signal does."""
    session.active_chain_executions.add(chain_exec)
    with patch('scheduler.engine.check_time_window', return_value=True):
        on_chain_execution_completed(chain_exec.id)


def _make_session(base_data, loop_rotation, dispatched):
    return UnattendedSession.objects.create(
        status=UnattendedSession.Status.RUNNING,
        started_at=timezone.now(),
        triggered_by=base_data['user'],
        loop_rotation=loop_rotation,
        dispatched_account_ids=dispatched,
        total_accounts=len(dispatched),
    )


@pytest.mark.django_db
def test_loop_rotation_returns_account_after_completion(base_data, loop_accounts):
    a, b = loop_accounts
    session = _make_session(base_data, loop_rotation=True, dispatched=[a.id, b.id])
    chain_exec = _make_chain_exec(base_data, a, TaskChainExecution.Status.SUCCESS)

    _run_completion(chain_exec, session)

    session.refresh_from_db()
    assert a.id not in session.dispatched_account_ids
    assert b.id in session.dispatched_account_ids


@pytest.mark.django_db
def test_non_loop_keeps_dispatch_once(base_data, loop_accounts):
    a, b = loop_accounts
    session = _make_session(base_data, loop_rotation=False, dispatched=[a.id, b.id])
    chain_exec = _make_chain_exec(base_data, a, TaskChainExecution.Status.SUCCESS)

    _run_completion(chain_exec, session)

    session.refresh_from_db()
    assert set(session.dispatched_account_ids) == {a.id, b.id}


@pytest.mark.django_db
def test_loop_mode_disables_all_completed_autostop(base_data, loop_accounts):
    a, _b = loop_accounts
    # all_completed condition armed + loop mode → a finished round must NOT stop.
    AutoStopCondition.objects.create(
        condition_type=AutoStopCondition.ConditionType.ALL_COMPLETED,
        action=AutoStopCondition.Action.STOP_ALL,
    )
    session = _make_session(
        base_data, loop_rotation=True, dispatched=[a.id],
    )
    session.completed_chain_count = 1
    session.save(update_fields=['completed_chain_count'])
    chain_exec = _make_chain_exec(base_data, a, TaskChainExecution.Status.SUCCESS)

    _run_completion(chain_exec, session)

    session.refresh_from_db()
    assert session.status == UnattendedSession.Status.RUNNING


@pytest.mark.django_db
def test_non_loop_all_completed_autostop_still_works(base_data, loop_accounts):
    a, _b = loop_accounts
    AutoStopCondition.objects.create(
        condition_type=AutoStopCondition.ConditionType.ALL_COMPLETED,
        action=AutoStopCondition.Action.STOP_ALL,
    )
    session = _make_session(
        base_data, loop_rotation=False, dispatched=[a.id],
    )
    session.completed_chain_count = 1
    session.save(update_fields=['completed_chain_count'])
    chain_exec = _make_chain_exec(base_data, a, TaskChainExecution.Status.SUCCESS)

    _run_completion(chain_exec, session)

    session.refresh_from_db()
    assert session.status == UnattendedSession.Status.STOPPED


@pytest.mark.django_db
def test_loop_rotation_alternates_accounts_via_cursor(base_data, loop_accounts):
    """Fair rotation (2026-08-27): the session cursor makes a single device
    cycle through ALL accounts instead of always picking the head, which
    previously stuck on ordered_accounts[0] once the pool was returned."""
    from pipeline.models import TaskChainNode

    from scheduler.models import GameAccountRotation
    from scheduler.tasks import tick_unattended_session
    from tasks.models import Task

    # dispatch_chain_node requires the chain to have at least one node
    TaskChainNode.objects.create(
        chain=base_data['chain'],
        task=Task.objects.create(name='fair-node'),
        order=1,
    )
    a, b = loop_accounts
    rule = GameAccountRotation.objects.create(
        name='fair', rotation_strategy='sequential',
    )
    rule.accounts.add(a, b)
    session = UnattendedSession.objects.create(
        status=UnattendedSession.Status.RUNNING,
        started_at=timezone.now(),
        triggered_by=base_data['user'],
        loop_rotation=True,
        rotation_rule=rule,
        rotation_index=0,
        total_accounts=2,
        game_profile=base_data['profile'],
    )

    def _tick_and_finish(expect_account):
        with patch('pipeline.tasks.dispatch_chain_node.delay'):
            tick_unattended_session()
        ce = (
            TaskChainExecution.objects.filter(game_account=expect_account)
            .order_by('-id').first()
        )
        assert ce is not None, f'account {expect_account.username} not dispatched'
        # Simulate a successful agent round-trip (dispatch is mocked, so the
        # chain would otherwise stay PENDING and block the device via has_active).
        ce.status = TaskChainExecution.Status.SUCCESS
        ce.save()
        _run_completion(ce, session)
        session.refresh_from_db()

    # ordered = [b, a] (sequential: newest account first, deterministic tie-break
    # on id); cursor 0 → b (cursor→1), then cursor 1 → a (cursor→2)
    _tick_and_finish(b)
    assert session.rotation_index == 1
    _tick_and_finish(a)
    assert session.rotation_index == 2
