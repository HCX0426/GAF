"""pytest global configuration and shared fixtures."""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from django.conf import settings
from workers.factories import (
    DeviceFactory,
    DeviceGroupFactory,
    WindowsDeviceFactory,
    WorkerFactory,
)

from accounts.factories import AdminUserFactory, OperatorUserFactory, UserFactory
from tasks.factories import TaskExecutionFactory, TaskFactory


def pytest_configure():
    """Configure Django settings before pytest collects tests."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
    settings.DEBUG = False

    import django

    django.setup()


@pytest.fixture(autouse=True)
def _mock_channel_layer(monkeypatch):
    """Replace Channels' channel_layer with an in-memory AsyncMock.

    Why: ``tasks/signals.py::broadcast_execution_status`` fires on every
    ``TaskExecution.save()`` and calls ``channel_layer.group_send`` via
    ``broadcast_notification``. In tests without a running Redis, the real
    ``RedisChannelLayer`` raises ``redis.exceptions.ConnectionError`` and
    fails 16+ tests that save executions (dispatch tests, retry tests, etc.).

    Patching ``get_channel_layer()`` to return a MagicMock whose
    ``group_send`` is an AsyncMock keeps the production code path intact
    (signals still fire, broadcast_notification still runs) while ensuring
    no real Redis connection is attempted. Tests that explicitly assert
    ``group_send`` was called can still do so via the mock.
    """
    mock_layer = MagicMock(name="mock_channel_layer")
    mock_layer.group_send = AsyncMock(name="mock_group_send")
    monkeypatch.setattr(
        "channels.layers.get_channel_layer",
        lambda *args, **kwargs: mock_layer,
    )
    yield mock_layer


@pytest.fixture
def api_client():
    """Return an unauthenticated DRF APIClient."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def user(db):
    """Return a generic viewer user."""
    return UserFactory()


@pytest.fixture
def operator(db):
    """Return an operator user."""
    return OperatorUserFactory()


@pytest.fixture
def admin(db):
    """Return an admin user."""
    return AdminUserFactory()


@pytest.fixture
def agent(db):
    """Return an online agent (worker)."""
    return WorkerFactory()


@pytest.fixture
def device(db):
    """Return an online emulator device."""
    return DeviceFactory()


@pytest.fixture
def windows_device(db):
    """Return an online Windows device."""
    return WindowsDeviceFactory()


@pytest.fixture
def device_group(db):
    """Return a device group owned by an operator."""
    return DeviceGroupFactory()


@pytest.fixture
def task(db):
    """Return a chain-mode task."""
    return TaskFactory()


@pytest.fixture
def task_execution(db):
    """Return a pending task execution."""
    return TaskExecutionFactory()
