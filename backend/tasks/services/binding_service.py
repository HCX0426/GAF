"""Task binding services — account binding, pipeline cloning, pipeline lookup.

Phase 1 (2026-08-08): Extracted from the flat services.py.
"""

import logging

from tasks.services.exceptions import TaskBindingError

logger = logging.getLogger(__name__)


def bind_task_accounts(task, account_ids, rotation_rule_id, user):
    """Bind game accounts + rotation rule to a task.

    Wraps the cross-app ``GameAccount`` + ``GameAccountRotation`` lookups
    (TD-265) so execution_views.py no longer needs
    ``from accounts.models import GameAccount`` or
    ``from scheduler.models import GameAccountRotation``.

    Args:
        task: ``Task`` instance.
        account_ids: List of ``GameAccount`` IDs to bind.
        rotation_rule_id: Optional ``GameAccountRotation`` ID.
        user: Request user (for ownership validation).

    Returns:
        dict: ``{"rotation_rule_id": int|None, "account_ids": list}``.

    Raises:
        TaskBindingError: If any account_id doesn't exist / user lacks
            permission, or rotation_rule_id doesn't exist / user lacks
            permission.
    """
    from django.db import transaction
    from scheduler.models import GameAccountRotation  # cross-app import isolated (TD-265)

    from accounts.models import GameAccount  # cross-app import isolated (TD-265)

    for aid in account_ids:
        if not GameAccount.objects.filter(pk=aid, owner=user).exists():
            raise TaskBindingError(f"账户 {aid} 不存在或无权限", status_code=400)

    rotation_rule = None
    if rotation_rule_id:
        try:
            rotation_rule = GameAccountRotation.objects.get(
                pk=rotation_rule_id, owner=user,
            )
        except GameAccountRotation.DoesNotExist as exc:
            raise TaskBindingError("轮换规则不存在或无权限", status_code=400) from exc

    with transaction.atomic():
        task.game_accounts.set(account_ids)
        task.rotation_rule = rotation_rule
        task.save(update_fields=["rotation_rule", "updated_at"])

    return {"rotation_rule_id": rotation_rule_id, "account_ids": account_ids}


def clone_pipeline_for_user(source_pipeline, user):
    """Clone a Pipeline for a user (used by marketplace import).

    Wraps the cross-app ``Pipeline`` lookup (TD-265) so resource_views.py
    no longer needs ``from pipeline.models import Pipeline`` for the
    clone-on-import path.

    Args:
        source_pipeline: ``Pipeline`` instance to clone.
        user: Request user (owner of the new Pipeline).

    Returns:
        New ``Pipeline`` instance.

    Raises:
        TaskBindingError: If a Pipeline with the same name already exists
            for this user (status 409).
    """
    from pipeline.models import Pipeline  # cross-app import isolated (TD-265)

    existing = Pipeline.objects.filter(user=user, name=source_pipeline.name).first()
    if existing:
        raise TaskBindingError(
            f"已存在同名 Pipeline: {source_pipeline.name}",
            status_code=409,
            extra={"pipeline_id": existing.id},
        )

    return Pipeline.objects.create(
        user=user,
        name=source_pipeline.name,
        description=source_pipeline.description,
        graph_data=source_pipeline.graph_data,
        version=1,
    )


def get_user_pipeline(pipeline_id, user):
    """Get a Pipeline owned by user (used by marketplace publish).

    Wraps the cross-app ``Pipeline`` lookup (TD-265) so resource_views.py
    no longer needs ``from pipeline.models import Pipeline`` for the
    publish path.

    Args:
        pipeline_id: ``Pipeline`` ID.
        user: Request user.

    Returns:
        ``Pipeline`` instance.

    Raises:
        TaskBindingError: If pipeline doesn't exist or user doesn't own it
            (status 404).
    """
    from pipeline.models import Pipeline  # cross-app import isolated (TD-265)

    try:
        return Pipeline.objects.get(id=pipeline_id, user=user)
    except Pipeline.DoesNotExist as exc:
        raise TaskBindingError("Pipeline 不存在", status_code=404) from exc
