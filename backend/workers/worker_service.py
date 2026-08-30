"""Worker domain services — single source of truth for Worker lifecycle.

Extracted from accounts/views.py:WorkerTokenViewSet (spec-41 / TD-277) to
decouple the accounts app from the workers app. accounts.views now calls
these services instead of importing workers.models directly, removing the
top-level ``from workers.models import Worker`` cross-app import.

Functions:
- create_worker_token: create Worker + generate raw token (hash + preview stored)
- list_worker_tokens: list all workers with token preview
- revoke_worker_token: delete Worker by pk
- get_worker_for_device_check: get Worker for GameAccount login test
- is_worker_offline: status helper (replaces Worker.Status.OFFLINE ref in accounts)
"""
from __future__ import annotations

import secrets
from typing import Any

from gaf_core.utils.tokens import hash_token, make_token_preview

from workers.models import Worker


def create_worker_token(name: str, permissions: list[str]) -> tuple[Worker, str]:
    """Create a new Worker record with a generated token.

    Args:
        name: Human-readable worker name (stored as hostname).
        permissions: List of permission strings (stored in capabilities.permissions).

    Returns:
        Tuple of (Worker instance, raw_token). The raw_token is only available
        at creation time — only its SHA-256 hash + preview are persisted.
    """
    token = secrets.token_urlsafe(32)
    agent_id = f"agent-{secrets.token_hex(8)}"

    worker = Worker.objects.create(
        agent_id=agent_id,
        hostname=name,
        worker_token_hash=hash_token(token),
        worker_token_preview=make_token_preview(token),
        status=Worker.Status.OFFLINE,
        capabilities={'permissions': permissions},
    )
    return worker, token


def list_worker_tokens() -> list[dict[str, Any]]:
    """List all workers ordered by created_at desc, with token preview.

    Returns:
        List of dicts suitable for WorkerTokenListSerializer. Never includes
        raw token values — only the stored preview.
    """
    workers = Worker.objects.all().order_by('-created_at')
    return [
        {
            'id': worker.id,
            'agent_id': worker.agent_id,
            'name': worker.hostname,
            'status': worker.status,
            'token_preview': worker.worker_token_preview or '',
            'permissions': worker.capabilities.get('permissions', []),
            'created_at': worker.created_at,
        }
        for worker in workers
    ]


def revoke_worker_token(pk: int) -> Worker | None:
    """Delete a Worker by primary key.

    Args:
        pk: Worker.pk

    Returns:
        The deleted Worker instance, or None if not found. Caller is
        responsible for audit logging using the returned instance.
    """
    try:
        worker = Worker.objects.get(pk=pk)
    except Worker.DoesNotExist:
        return None
    worker.delete()
    return worker


def get_worker_for_device_check(device_id: int) -> Worker | None:
    """Get a Worker for GameAccount login test (device status check).

    Args:
        device_id: Worker.pk

    Returns:
        Worker instance, or None if not found.
    """
    try:
        return Worker.objects.get(pk=device_id)
    except Worker.DoesNotExist:
        return None


def is_worker_offline(worker: Worker) -> bool:
    """Return True if the worker's status is OFFLINE.

    Helper for callers (e.g. accounts.views.GameAccountViewSet.test_login)
    that need to check offline status without importing ``Worker.Status``.
    """
    return worker.status == Worker.Status.OFFLINE
