"""P-009 Phase 3: TaskChainExecution completion hook tests.

Covers the ``on_chain_execution_completed`` Celery task and the
``post_save`` signal that dispatches it:

- Chain not found / no session / session not RUNNING → no-op
- SUCCESS → failed_count reset, completed_chain_count incremented
- FAILED → failed_count incremented, recovery engine invoked
- CANCELLED → failed_count unchanged (neutral)
- Active chain removed from session.active_chain_executions
- AutoStop consecutive_failures threshold → session STOPPED
- AutoStop all_completed → session STOPPED
- AutoStop not triggered → session stays RUNNING
- Signal fires Celery task on terminal status change
- Signal ignores non-terminal status and creates

Mocks:
- ``scheduler.recovery_engine.handle_task_failure`` → avoid ActionChain
- ``scheduler.engine.check_time_window`` → control window gate for AutoStop
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from pipeline.models import TaskChain, TaskChainExecution

from agents.models import Agent, Device
from gamestate.models import GameProfile
from scheduler.models import (
    AutoStopCondition,
    UnattendedSession,
)
from scheduler.tasks import on_chain_execution_completed
from tasks.models import Task, TaskExecution

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def hook_user(db):
    """User that triggers the unattended session."""
    return User.objects.create_user(
        username='hook_user', password='Pass123!',
    )


@pytest.fixture
def game_chain(db):
    """An enabled TaskChain."""
    return TaskChain.objects.create(
        name='Hook Test Chain',
        is_enabled=True,
    )


@pytest.fixture
def game_profile(game_chain):
    """GameProfile with default_task_chain."""
    return GameProfile.objects.create(
        game_name='HookGame',
        default_task_chain=game_chain,
    )


@pytest.fixture
def online_agent(db):
    """Agent with status=ONLINE."""
    return Agent.objects.create(
        agent_id='hook-agent-001',
        hostname='hook-host',
        status=Agent.Status.ONLINE,
    )


@pytest.fixture
def idle_device(game_profile, online_agent):
    """Device bound to game_profile + online agent."""
    return Device.objects.create(
        name='hook-device',
        device_type=Device.DeviceType.WINDOWS,
        status=Device.Status.ONLINE,
        agent=online_agent,
        game_profile=game_profile,
    )


@pytest.fixture
def running_session(hook_user):
    """RUNNING UnattendedSession."""
    return UnattendedSession.objects.create(
        status=UnattendedSession.Status.RUNNING,
        started_at=timezone.now(),
        triggered_by=hook_user,
    )


@pytest.fixture
def chain_exec(game_chain, hook_user):
    """A RUNNING TaskChainExecution (default state for tests)."""
    return TaskChainExecution.objects.create(
        chain=game_chain,
        triggered_by=hook_user,
        status=TaskChainExecution.Status.RUNNING,
    )


@pytest.fixture
def clean_autostop(db):
    """Clear all AutoStopCondition records to isolate test scenarios."""
    AutoStopCondition.objects.all().delete()


def _make_chain_exec(chain, user, device=None, account=None, status=None):
    """Create a TaskChainExecution row."""
    return TaskChainExecution.objects.create(
        chain=chain,
        triggered_by=user,
        device=device,
        game_account=account,
        status=status or TaskChainExecution.Status.RUNNING,
    )


def _link(session, chain_exec):
    """Link a chain execution to a session's active_chain_executions."""
    session.active_chain_executions.add(chain_exec)


def _make_failed_task_exec(chain_exec):
    """Create a failed TaskExecution linked to the chain execution."""
    task = Task.objects.create(
        name='Hook Test Task',
        execution_mode=Task.ExecutionMode.PIPELINE,
        task_definition={'nodes': []},
    )
    return TaskExecution.objects.create(
        task=task,
        chain_execution=chain_exec,
        status=TaskExecution.Status.FAILED,
        started_at=timezone.now(),
    )


# ---------------------------------------------------------------------------
# No-op / guard tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_completion_chain_not_found():
    """Non-existent chain_execution_id → no-op (no exception)."""
    on_chain_execution_completed(999999)


@pytest.mark.django_db
def test_completion_no_session_tracking(chain_exec, running_session):
    """Chain not linked to any RUNNING session → no-op."""
    # chain_exec is not in running_session.active_chain_executions
    on_chain_execution_completed(chain_exec.id)
    running_session.refresh_from_db()
    assert running_session.status == UnattendedSession.Status.RUNNING
    assert running_session.failed_count == 0


@pytest.mark.django_db
def test_completion_session_not_running(chain_exec, hook_user):
    """PAUSED session → skipped (only RUNNING sessions are processed)."""
    session = UnattendedSession.objects.create(
        status=UnattendedSession.Status.PAUSED,
        started_at=timezone.now(),
        triggered_by=hook_user,
    )
    _link(session, chain_exec)
    chain_exec.status = TaskChainExecution.Status.SUCCESS
    chain_exec.save(update_fields=['status'])

    on_chain_execution_completed(chain_exec.id)

    session.refresh_from_db()
    assert session.status == UnattendedSession.Status.PAUSED
    assert session.failed_count == 0
    assert session.completed_chain_count == 0


# ---------------------------------------------------------------------------
# Counter update tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_completion_success_resets_failed_count(
    game_chain, hook_user, running_session, clean_autostop,
):
    """Chain SUCCESS → failed_count reset to 0, completed incremented."""
    chain_exec = _make_chain_exec(
        game_chain, hook_user,
        status=TaskChainExecution.Status.SUCCESS,
    )
    _link(running_session, chain_exec)
    running_session.failed_count = 2
    running_session.save(update_fields=['failed_count'])

    on_chain_execution_completed(chain_exec.id)

    running_session.refresh_from_db()
    assert running_session.failed_count == 0
    assert running_session.completed_chain_count == 1


@pytest.mark.django_db
def test_completion_failed_increments_count(
    game_chain, hook_user, running_session, clean_autostop,
):
    """Chain FAILED → failed_count incremented, completed incremented."""
    chain_exec = _make_chain_exec(
        game_chain, hook_user,
        status=TaskChainExecution.Status.FAILED,
    )
    _link(running_session, chain_exec)

    with patch(
        'scheduler.recovery_engine.handle_task_failure',
        return_value={'success': True, 'action': 'continue'},
    ):
        on_chain_execution_completed(chain_exec.id)

    running_session.refresh_from_db()
    assert running_session.failed_count == 1
    assert running_session.completed_chain_count == 1


@pytest.mark.django_db
def test_completion_cancelled_neutral(
    game_chain, hook_user, running_session, clean_autostop,
):
    """Chain CANCELLED → failed_count unchanged, completed incremented."""
    chain_exec = _make_chain_exec(
        game_chain, hook_user,
        status=TaskChainExecution.Status.CANCELLED,
    )
    _link(running_session, chain_exec)
    running_session.failed_count = 1
    running_session.save(update_fields=['failed_count'])

    on_chain_execution_completed(chain_exec.id)

    running_session.refresh_from_db()
    assert running_session.failed_count == 1  # unchanged
    assert running_session.completed_chain_count == 1


@pytest.mark.django_db
def test_completion_removes_from_active(
    game_chain, hook_user, running_session, clean_autostop,
):
    """Completed chain removed from session.active_chain_executions."""
    chain_exec = _make_chain_exec(
        game_chain, hook_user,
        status=TaskChainExecution.Status.SUCCESS,
    )
    _link(running_session, chain_exec)
    assert running_session.active_chain_executions.count() == 1

    on_chain_execution_completed(chain_exec.id)

    running_session.refresh_from_db()
    assert running_session.active_chain_executions.count() == 0


# ---------------------------------------------------------------------------
# Recovery engine tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_completion_failed_triggers_recovery(
    game_chain, hook_user, running_session, clean_autostop,
):
    """Chain FAILED with a failed TaskExecution → handle_task_failure called."""
    chain_exec = _make_chain_exec(
        game_chain, hook_user,
        status=TaskChainExecution.Status.FAILED,
    )
    _link(running_session, chain_exec)
    _make_failed_task_exec(chain_exec)

    with patch(
        'scheduler.recovery_engine.handle_task_failure',
        return_value={'success': True, 'action': 'continue'},
    ) as mock_recovery:
        on_chain_execution_completed(chain_exec.id)

    mock_recovery.assert_called_once()
    call_kwargs = mock_recovery.call_args
    assert call_kwargs[1]['consecutive_failures'] == 1


@pytest.mark.django_db
def test_completion_failed_no_task_exec_skips_recovery(
    game_chain, hook_user, running_session, clean_autostop,
):
    """Chain FAILED but no failed TaskExecution → recovery not called."""
    chain_exec = _make_chain_exec(
        game_chain, hook_user,
        status=TaskChainExecution.Status.FAILED,
    )
    _link(running_session, chain_exec)
    # No TaskExecution created

    with patch(
        'scheduler.recovery_engine.handle_task_failure',
    ) as mock_recovery:
        on_chain_execution_completed(chain_exec.id)

    mock_recovery.assert_not_called()


# ---------------------------------------------------------------------------
# AutoStop tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_autostop_consecutive_failures(
    game_chain, hook_user, running_session, clean_autostop,
):
    """3 consecutive failures → AutoStop triggers → session STOPPED."""
    AutoStopCondition.objects.create(
        condition_type='consecutive_failures',
        is_enabled=True,
        threshold=3,
        action='stop_all',
    )
    chain_exec = _make_chain_exec(
        game_chain, hook_user,
        status=TaskChainExecution.Status.FAILED,
    )
    _link(running_session, chain_exec)
    _make_failed_task_exec(chain_exec)
    running_session.failed_count = 2  # This failure will make it 3
    running_session.save(update_fields=['failed_count'])

    with patch('scheduler.engine.check_time_window', return_value=True), patch(
        'scheduler.recovery_engine.handle_task_failure',
        return_value={'success': True, 'action': 'continue'},
    ):
        on_chain_execution_completed(chain_exec.id)

    running_session.refresh_from_db()
    assert running_session.status == UnattendedSession.Status.STOPPED
    assert running_session.failed_count == 3
    assert '连续失败' in running_session.stop_reason


@pytest.mark.django_db
def test_autostop_all_completed(
    game_chain, hook_user, running_session, idle_device, clean_autostop,
):
    """All dispatched accounts completed → AutoStop(all_completed) → STOPPED."""
    AutoStopCondition.objects.create(
        condition_type='all_completed',
        is_enabled=True,
        action='stop_all',
    )
    chain_exec = _make_chain_exec(
        game_chain, hook_user, device=idle_device,
        status=TaskChainExecution.Status.SUCCESS,
    )
    _link(running_session, chain_exec)
    running_session.dispatched_account_ids = [101]  # 1 account dispatched
    running_session.save(update_fields=['dispatched_account_ids'])

    with patch('scheduler.engine.check_time_window', return_value=True):
        on_chain_execution_completed(chain_exec.id)

    running_session.refresh_from_db()
    assert running_session.status == UnattendedSession.Status.STOPPED
    assert 'all_completed' in running_session.stop_reason.lower() \
        or '所有账户' in running_session.stop_reason


@pytest.mark.django_db
def test_autostop_not_triggered(
    game_chain, hook_user, running_session, clean_autostop,
):
    """1 failure (below threshold) + not all completed → session stays RUNNING."""
    AutoStopCondition.objects.create(
        condition_type='consecutive_failures',
        is_enabled=True,
        threshold=5,
        action='stop_all',
    )
    chain_exec = _make_chain_exec(
        game_chain, hook_user,
        status=TaskChainExecution.Status.FAILED,
    )
    _link(running_session, chain_exec)
    _make_failed_task_exec(chain_exec)

    with patch('scheduler.engine.check_time_window', return_value=True), patch(
        'scheduler.recovery_engine.handle_task_failure',
        return_value={'success': True, 'action': 'continue'},
    ):
        on_chain_execution_completed(chain_exec.id)

    running_session.refresh_from_db()
    assert running_session.status == UnattendedSession.Status.RUNNING
    assert running_session.failed_count == 1


@pytest.mark.django_db
def test_autostop_window_end(
    game_chain, hook_user, running_session, clean_autostop,
):
    """Outside time window → AutoStop(window_end) → session STOPPED."""
    AutoStopCondition.objects.create(
        condition_type='window_end',
        is_enabled=True,
        action='stop_all',
    )
    chain_exec = _make_chain_exec(
        game_chain, hook_user,
        status=TaskChainExecution.Status.SUCCESS,
    )
    _link(running_session, chain_exec)

    with patch('scheduler.engine.check_time_window', return_value=False):
        on_chain_execution_completed(chain_exec.id)

    running_session.refresh_from_db()
    assert running_session.status == UnattendedSession.Status.STOPPED


# ---------------------------------------------------------------------------
# Signal wiring tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_signal_fires_task_on_terminal_status(
    game_chain, hook_user, running_session, clean_autostop,
):
    """TaskChainExecution status → SUCCESS triggers on_chain_execution_completed."""
    chain_exec = _make_chain_exec(
        game_chain, hook_user,
        status=TaskChainExecution.Status.RUNNING,
    )
    _link(running_session, chain_exec)

    # Patch on_commit to execute immediately (bypass transaction deferral)
    with patch('django.db.transaction.on_commit', side_effect=lambda f: f()), patch(
        'scheduler.tasks.on_chain_execution_completed.delay',
    ) as mock_delay:
        chain_exec.status = TaskChainExecution.Status.SUCCESS
        chain_exec.save(update_fields=['status'])

    mock_delay.assert_called_once_with(chain_exec.id)


@pytest.mark.django_db
def test_signal_ignores_non_terminal_status(game_chain, hook_user):
    """Status change to RUNNING (non-terminal) → no task dispatched."""
    chain_exec = _make_chain_exec(
        game_chain, hook_user,
        status=TaskChainExecution.Status.PENDING,
    )

    with patch('django.db.transaction.on_commit', side_effect=lambda f: f()), patch(
        'scheduler.tasks.on_chain_execution_completed.delay',
    ) as mock_delay:
        chain_exec.status = TaskChainExecution.Status.RUNNING
        chain_exec.save(update_fields=['status'])

    mock_delay.assert_not_called()


@pytest.mark.django_db
def test_signal_ignores_create(game_chain, hook_user):
    """New TaskChainExecution created → no task dispatched (created=True)."""
    with patch('django.db.transaction.on_commit', side_effect=lambda f: f()), patch(
        'scheduler.tasks.on_chain_execution_completed.delay',
    ) as mock_delay:
        _make_chain_exec(
            game_chain, hook_user,
            status=TaskChainExecution.Status.SUCCESS,
        )

    mock_delay.assert_not_called()
