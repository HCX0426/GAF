"""Agent domain services — single source of truth for Agent lifecycle.

Extracted from accounts/views.py:AgentTokenViewSet (spec-41 / TD-277) to
decouple the accounts app from the agents app. accounts.views now calls
these services instead of importing agents.models directly, removing the
top-level ``from workers.models import Worker`` cross-app import.

Functions:
- create_agent_token: create Agent + generate raw token (hash + preview stored)
- list_agent_tokens: list all agents with token preview
- revoke_agent_token: delete Agent by pk
- get_agent_for_device_check: get Agent for GameAccount login test
- is_agent_offline: status helper (replaces Worker.Status.OFFLINE ref in accounts)
"""
from __future__ import annotations

import secrets
from typing import Any

from gaf_core.utils.tokens import hash_token, make_token_preview

from workers.models import Worker


def create_agent_token(name: str, permissions: list[str]) -> tuple[Worker, str]:
    """Create a new Agent record with a generated token.

    Args:
        name: Human-readable agent name (stored as hostname).
        permissions: List of permission strings (stored in capabilities.permissions).

    Returns:
        Tuple of (Agent instance, raw_token). The raw_token is only available
        at creation time — only its SHA-256 hash + preview are persisted.
    """
    token = secrets.token_urlsafe(32)
    agent_id = f"agent-{secrets.token_hex(8)}"

    agent = Worker.objects.create(
        agent_id=agent_id,
        hostname=name,
        agent_token_hash=hash_token(token),
        agent_token_preview=make_token_preview(token),
        status=Worker.Status.OFFLINE,
        capabilities={'permissions': permissions},
    )
    return agent, token


def list_agent_tokens() -> list[dict[str, Any]]:
    """List all agents ordered by created_at desc, with token preview.

    Returns:
        List of dicts suitable for AgentTokenListSerializer. Never includes
        raw token values — only the stored preview.
    """
    agents = Worker.objects.all().order_by('-created_at')
    return [
        {
            'id': agent.id,
            'agent_id': agent.agent_id,
            'name': agent.hostname,
            'status': agent.status,
            'token_preview': agent.agent_token_preview or '',
            'permissions': agent.capabilities.get('permissions', []),
            'created_at': agent.created_at,
        }
        for agent in agents
    ]


def revoke_agent_token(pk: int) -> Worker | None:
    """Delete an Agent by primary key.

    Args:
        pk: Worker.pk

    Returns:
        The deleted Agent instance, or None if not found. Caller is
        responsible for audit logging using the returned instance.
    """
    try:
        agent = Worker.objects.get(pk=pk)
    except Worker.DoesNotExist:
        return None
    agent.delete()
    return agent


def get_agent_for_device_check(device_id: int) -> Worker | None:
    """Get an Agent for GameAccount login test (device status check).

    Args:
        device_id: Worker.pk

    Returns:
        Agent instance, or None if not found.
    """
    try:
        return Worker.objects.get(pk=device_id)
    except Worker.DoesNotExist:
        return None


def is_agent_offline(agent: Worker) -> bool:
    """Return True if the agent's status is OFFLINE.

    Helper for callers (e.g. accounts.views.GameAccountViewSet.test_login)
    that need to check offline status without importing ``Worker.Status``.
    """
    return agent.status == Worker.Status.OFFLINE
