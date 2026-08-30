"""Task execution service — wraps execute_task into a class-based service.

Phase 1 (2026-08-08): Introduces TaskService class for cleaner
view-layer separation. The module-level ``execute_task`` function
is kept for backward compatibility.
"""

import logging

from django.db import transaction
from django.db.models import F
from django.utils.timezone import now as django_now

from tasks.services.exceptions import TaskBindingError
from tasks.services.monitor_service import _release_concurrency_slot, _restore_device_status

logger = logging.getLogger(__name__)


def _get_or_create_default_account(user, resource_pack):
    """查找或创建默认 GameAccount, 用于「已登录, 直接测试资源包」场景.

    当用户已登录游戏, 不需要真实账号密码, 只需一个携带 resource_pack 的
    GameAccount 占位记录, 让 dispatch_task 能正确转发资源包给 agent.

    Args:
        user: 请求用户 (作为 GameAccount.owner)
        resource_pack: ResourcePack 实例

    Returns:
        GameAccount 实例 (已绑定 resource_pack)
    """
    from accounts.models import GameAccount  # cross-app import isolated

    game_profile = resource_pack.game_profile
    game_name = game_profile.game_name if game_profile else resource_pack.name

    # 尝试查找已有的默认账号: 同 profile + 同资源包 + 同 owner (P3: game_name 字符串已退)
    existing = GameAccount.objects.filter(
        owner=user,
        game_profile=game_profile,
        resource_pack=resource_pack,
    ).first()
    if existing:
        return existing

    # 创建默认账号 — 无真实密码, 仅作为 resource_pack 载体
    username = f"{game_name} 默认测试账号"
    return GameAccount.objects.create(
        owner=user,
        game_profile=game_profile,
        username=username,
        encrypted_password="",  # 无密码, 用户已登录
        resource_pack=resource_pack,
    )


def execute_task(task, agent_id, user, device_id=None, game_account_id=None,
                 resource_pack_id=None):
    """Execute a task: create TaskExecution + update game_accounts + dispatch.

    Wraps the cross-app ``Agent`` / ``Device`` lookups (TD-265) so views.py
    no longer needs ``from workers.models import Worker``.

    Window-centric (R37): ``TaskExecution.device`` 是单 FK, 记录本次执行
    具体在哪台设备上跑。``dispatch_task`` 通过 ``execution.device`` 构造
    ``device_info`` 派发给 agent; 若为 None, agent 会 fallback 到当前活跃
    设备 (可能是 LDPlayer 而非用户预期的 BD2 窗口)。

    N194 fix (2026-07-28, BD2 选错窗口 + 资源包没绑定根因):
    ``TaskExecution.game_account`` 必须绑定, 否则 ``dispatch_task`` 无法
    从 ``execution.game_account.resource_pack`` 取到 resource_pack 派发
    给 agent, 导致 agent 用错资源包 / 模板找不到窗口。优先级:
        1. 显式传入的 ``game_account_id`` (前端用户选择)
        2. ``task.game_accounts`` 第一条 (任务默认绑定账号)
        3. None (legacy: 任务未绑定账号, dispatch_task 派发 resource_pack=None)

    N197 (2026-08-01): 新增 ``resource_pack_id`` 参数, 支持「已登录, 直接测试
    资源包」场景。当传入时:
        - 覆盖 game_account 携带的 resource_pack (若 game_account 已存在)
        - 若 game_account_id 未传, 自动创建默认 GameAccount 绑定此资源包
        - 校验 ResourcePack.game_profile 与 Task.game_profile 一致

    device_id 解析优先级:
        1. 显式传入的 ``device_id`` (前端用户选择)
        2. ``task.device_mappings`` 第一条 (任务默认绑定设备)
        3. None (legacy: 任务未绑定设备, 由 agent fallback)

    Args:
        task: ``Task`` instance (already fetched / permission-checked by view).
        agent_id: Optional ``Agent.agent_id`` string. If provided but no
            Agent matches, raises ``TaskBindingError`` with status 400.
        user: Request user (set as ``triggered_by`` on the new execution).
        device_id: Optional ``Device.id``. If provided but no Device matches
            or 不属于 task.device_mappings, raises ``TaskBindingError`` (400).
            If None, falls back to ``task.device_mappings`` 第一条.
        game_account_id: Optional ``GameAccount.id``. If provided but no
            GameAccount matches or 不属于 task.game_accounts, raises
            ``TaskBindingError`` (400). If None, falls back to
            ``task.game_accounts`` 第一条.
        resource_pack_id: Optional ``ResourcePack.id``. 直接指定资源包,
            用于「已登录, 直接测试资源包」场景。

    Returns:
        Newly created ``TaskExecution`` (status=PENDING, agent + device +
        game_account set; game_account may still be None if task has no
        bound accounts for backwards compat).

    Raises:
        TaskBindingError: If ``agent_id`` / ``device_id`` / ``game_account_id``
            provided but no match, or device_id 不属于 task.device_mappings,
            or game_account_id 不属于 task.game_accounts.
    """
    from workers.models import Device, Worker  # cross-app import isolated (TD-265)

    from resources.models import ResourcePack  # cross-app import isolated
    from tasks.models import TaskExecution
    from tasks.services.agent_resolver import resolve_online_agent
    from tasks.tasks import dispatch_task

    agent = None
    if agent_id:
        try:
            agent = Worker.objects.get(agent_id=agent_id)
        except Worker.DoesNotExist:
            raise TaskBindingError(f"Agent {agent_id} 不存在", status_code=400) from None
    else:
        # 用户默认 agent (2026-08-26): 调用方未显式指定 agent 时, 默认
        # 用「最新心跳的在线 agent」代替 None。单 agent 部署下即是唯一
        # agent, 避免 execution.agent 为 null 导致派发链路语义不清
        # (dispatch_task 侧仍会二次校验 / 覆盖为实际可分配 agent)。
        agent = resolve_online_agent()
        if agent is None:
            raise TaskBindingError(
                "无可用在线 Agent, 无法派发执行", status_code=400
            )

    # Resolve target device: explicit > task default binding > None.
    device = None
    if device_id:
        device = Device.objects.filter(id=device_id).first()
        if device is None:
            raise TaskBindingError(f"Device {device_id} 不存在", status_code=400)
        if not task.device_mappings.filter(device_id=device_id).exists():
            raise TaskBindingError(
                f"Device {device_id} 未绑定到任务 {task.id}",
                status_code=400,
            )
    else:
        first_mapping = task.device_mappings.select_related("device").first()
        if first_mapping is not None:
            device = first_mapping.device

    # N197: resolve resource pack when resource_pack_id is provided.
    _explicit_resource_pack = None
    if resource_pack_id is not None:
        _explicit_resource_pack = (
            ResourcePack.objects.filter(id=resource_pack_id)
            .select_related("game_profile")
            .first()
        )
        if _explicit_resource_pack is None:
            raise TaskBindingError(
                f"ResourcePack {resource_pack_id} 不存在", status_code=400
            )
        if (
            _explicit_resource_pack.game_profile_id
            and task.game_profile_id
            and _explicit_resource_pack.game_profile_id != task.game_profile_id
        ):
            raise TaskBindingError(
                f"资源包 \"{_explicit_resource_pack.name}\" 的游戏档案 "
                f"(id={_explicit_resource_pack.game_profile_id}) 与任务 "
                f"\"{task.name}\" 的游戏档案 (id={task.game_profile_id}) 不一致",
                status_code=400,
            )

    # N194 fix: resolve target game_account.
    game_account = None
    if game_account_id:
        from accounts.models import GameAccount  # cross-app import isolated (TD-265)

        game_account = GameAccount.objects.filter(id=game_account_id).first()
        if game_account is None:
            raise TaskBindingError(
                f"GameAccount {game_account_id} 不存在", status_code=400
            )
        if not task.game_accounts.filter(id=game_account_id).exists():
            raise TaskBindingError(
                f"GameAccount {game_account_id} 未绑定到任务 {task.id}",
                status_code=400,
            )
        if (
            _explicit_resource_pack is not None
            and game_account.resource_pack_id
            and game_account.resource_pack_id != _explicit_resource_pack.id
        ):
            raise TaskBindingError(
                f"GameAccount {game_account_id} 已绑定资源包 "
                f"id={game_account.resource_pack_id}, "
                f"与传入的 resource_pack_id={resource_pack_id} 冲突",
                status_code=400,
            )
    elif _explicit_resource_pack is not None:
        game_account = _get_or_create_default_account(user, _explicit_resource_pack)
    else:
        game_account = task.game_accounts.select_related("resource_pack").first()

    # Atomic so TaskExecution.create + game_accounts.update either both
    # commit or both roll back; dispatch_task is deferred until commit so
    # the Celery worker never reads a stale execution row.
    with transaction.atomic():
        execution = TaskExecution.objects.create(
            task=task,
            agent=agent,
            device=device,
            game_account=game_account,
            triggered_by=user,
            status=TaskExecution.Status.PENDING,
        )
        game_accounts = task.game_accounts.all()
        if game_accounts.exists():
            game_accounts.update(
                execution_count=F("execution_count") + 1,
                last_execution_time=django_now(),
            )

    # F39: 捕获当前线程的 trace_id, 传给 Celery 边界.
    from gaf_core.tracing.context import current_trace_id

    _trace_id = current_trace_id.get() or ""

    transaction.on_commit(lambda: dispatch_task.delay(execution.id, trace_id=_trace_id))
    return execution


class TaskService:
    """Task execution service — encapsulates task dispatch and execution logic.

    Phase 1 (2026-08-08): Wraps the module-level ``execute_task`` function
    into a class so views can use dependency injection / constructor-based
    configuration in the future.
    """

    def dispatch(self, task, agent_id, user, device_id=None, game_account_id=None,
                 resource_pack_id=None):
        """Create a TaskExecution and dispatch it to the Celery worker.

        All arguments are forwarded to :func:`execute_task`.
        See :func:`execute_task` for full parameter documentation.

        Returns:
            Newly created ``TaskExecution`` instance.

        Raises:
            TaskBindingError: On validation/lookup failures.
        """
        return execute_task(
            task=task,
            agent_id=agent_id,
            user=user,
            device_id=device_id,
            game_account_id=game_account_id,
            resource_pack_id=resource_pack_id,
        )

    def cancel(self, execution, reason="用户手动取消"):
        """Cancel a running/pending execution.

        Sets status to CANCELLED, notifies the agent via WebSocket,
        and releases concurrency slot + device.

        Args:
            execution: ``TaskExecution`` instance (must be RUNNING or PENDING).
            reason: Optional cancel reason string.

        Returns:
            The updated ``TaskExecution`` instance.
        """
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        from tasks.models import TaskExecution

        execution.status = TaskExecution.Status.CANCELLED
        execution.cancel_reason = reason
        execution.save(update_fields=["status", "cancel_reason", "updated_at"])

        # Notify agent via WebSocket
        if execution.agent:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"agent_{execution.agent.agent_id}",
                {
                    "type": "task.cancel",
                    "payload": {
                        "execution_id": str(execution.id),
                        "reason": reason,
                    },
                },
            )

        # Release resources
        _release_concurrency_slot(
            execution.agent.agent_id if execution.agent else None,
            execution.id,
        )
        _restore_device_status(execution)

        return execution
