"""
调度引擎核心逻辑

负责时间窗口检查、账户轮换策略计算、设备可用资源解析、
执行计划生成和自动停止条件检测。
"""

import logging
import random
from datetime import datetime

from django.utils import timezone

from scheduler.models import (
    AutoStopCondition,
    GameAccountRotation,
    TimeWindow,
)

logger = logging.getLogger(__name__)


def check_time_window(dt: datetime | None = None) -> bool:
    """
    检查给定时间是否在已配置的时间窗口内。

    Args:
        dt: 要检查的时间，默认为当前时间

    Returns:
        True 表示在窗口内，False 表示不在任何窗口内
    """
    if dt is None:
        dt = timezone.now()

    windows = TimeWindow.objects.filter(is_enabled=True)
    if not windows.exists():
        return True

    current_time = dt.time()
    current_weekday = dt.weekday()
    sunday_mapped = (current_weekday + 1) % 7

    for window in windows:
        if not window.is_enabled:
            continue

        active_days = window.days_of_week if window.days_of_week else list(range(7))
        if sunday_mapped not in active_days:
            continue

        if window.start_time <= current_time <= window.end_time:
            return True

        if window.start_time > window.end_time and (
            current_time >= window.start_time or current_time <= window.end_time
        ):
            return True

    return False


def calculate_account_order(rotation_rule: GameAccountRotation, accounts: list) -> list:
    """
    根据轮换策略计算账户执行顺序。

    Args:
        rotation_rule: 轮换规则对象
        accounts: 账户查询集或列表

    Returns:
        排序后的账户列表
    """
    accounts_list = list(accounts)

    if not accounts_list:
        return []

    if rotation_rule.auto_skip_blocked:
        accounts_list = [a for a in accounts_list if getattr(a, 'status', 'ok') != 'error']

    strategy = rotation_rule.rotation_strategy

    if strategy == 'sequential':
        # TD-111: sequential strategy prefers newest-created account first
        # (matches GameAccount.Meta.ordering = ['-created_at']).
        # 2026-08-27: add a deterministic tie-breaker on (created_at, id) —
        # two accounts created within the same timestamp (SQLite microsecond
        # precision / bulk fixtures) previously yielded an unstable order
        # (test_loop_rotation alternates flaked, dispatched b instead of a).
        # Sorting on (created_at, id) with reverse keeps "newest first" and
        # makes equal timestamps fall back to the larger id deterministically.
        return sorted(
            accounts_list,
            key=lambda a: (
                getattr(a, 'created_at', None)
                or datetime.min.replace(tzinfo=timezone.utc),
                a.id or 0,
            ),
            reverse=True,
        )

    elif strategy == 'random':
        shuffled = list(accounts_list)
        random.shuffle(shuffled)
        return shuffled

    elif strategy == 'by_stamina':
        return sorted(
            accounts_list,
            key=lambda a: getattr(a, 'stamina', 0) or 0,
            reverse=True,
        )

    elif strategy == 'by_last_executed':
        return sorted(
            accounts_list,
            key=lambda a: (
                getattr(a, 'last_login_at', None) or
                datetime.min.replace(tzinfo=timezone.utc)
            ),
        )

    return accounts_list



def execute_warmup(device_id: int, warmup_config) -> bool:
    """
    执行设备预热流程。

    Args:
        device_id: 设备 ID
        warmup_config: WarmupConfig 实例

    Returns:
        预热是否成功
    """
    steps = warmup_config.steps if warmup_config.steps else []
    if not steps:
        return True

    for step in steps:
        if not step.get('is_enabled', True):
            continue

        step_type = step.get('type', '')
        timeout = step.get('timeout_seconds', 60)
        retry_count = step.get('retry_count', 1)

        for attempt in range(retry_count):
            success = _execute_warmup_step(device_id, step_type, timeout, step)
            if success:
                break
            if attempt == retry_count - 1 and (
                warmup_config.failure_strategy == 'abort_all'
                or warmup_config.failure_strategy == 'skip_device'
            ):
                return False

    return True


def _execute_warmup_step(device_id: int, step_type: str, timeout: int, step_config: dict) -> bool:
    """
    执行单个预热步骤的内部实现。

    Args:
        device_id: 设备 ID
        step_type: 步骤类型
        timeout: 超时时间（秒）
        step_config: 步骤配置字典

    Returns:
        步骤执行是否成功
    """
    try:
        if step_type == 'start_emulator' or step_type == 'start_game':
            return True
        elif step_type == 'wait_loading':
            import time
            wait_seconds = step_config.get('wait_seconds', timeout)
            time.sleep(min(wait_seconds, 30))
            return True
        elif step_type == 'auto_login':
            if step_config.get('auto_login', False):
                return True
            return True
        else:
            return True
    except Exception:
        logger.warning("scheduler: _execute_warmup_step failed (device_id=%s, step_type=%s)", device_id, step_type, exc_info=True)
        return False


def check_auto_stop_conditions(
    consecutive_failures: int = 0,
    device_offline_minutes: float = 0,
    all_accounts_completed: bool = False,
    in_time_window: bool = True,
    resource_sufficient: bool = True,
) -> list:
    """
    检查当前是否满足任何自动停止条件。

    Args:
        consecutive_failures: 当前连续失败次数
        device_offline_minutes: 设备离线分钟数
        all_accounts_completed: 所有账户是否已完成
        in_time_window: 是否在时间窗口内
        resource_sufficient: 资源包是否充足

    Returns:
        被触发的 AutoStopCondition 列表
    """
    conditions = AutoStopCondition.objects.filter(is_enabled=True)
    triggered = []

    for cond in conditions:
        if cond.condition_type == 'consecutive_failures':
            threshold = cond.threshold or 5
            if consecutive_failures >= threshold:
                triggered.append(cond)

        elif cond.condition_type == 'device_offline':
            threshold = cond.threshold or 10
            if device_offline_minutes >= threshold:
                triggered.append(cond)

        elif cond.condition_type == 'all_completed':
            if all_accounts_completed:
                triggered.append(cond)

        elif cond.condition_type == 'window_end':
            if not in_time_window:
                triggered.append(cond)

        elif cond.condition_type == 'manual_stop':
            pass

        elif cond.condition_type == 'resource_insufficient':
            if not resource_sufficient:
                triggered.append(cond)

    return triggered


def generate_execution_plan(days: int = 7) -> list:
    """Generate execution plan for the next N days based on Device + GameProfile.default_task_chain.

    Per spec §2.4.2 (window-centric task binding v3): the plan is derived
    from each Device's bound GameProfile.default_task_chain (TaskChain). This
    replaces the legacy Task-centric + GameAccount/Device fallback logic
    (TD-097 — empty_fallback path removed; plan can now be empty if no
    device has a default_task_chain configured).

    Args:
        days: number of future days to plan, default 7

    Returns:
        List of plan items. Each item has:
            - device_id / device_name
            - account_id / account_name (from device.game_account runtime binding)
            - task_chain_id / task_chain_name (from game_profile.default_task_chain)
            - day_offset (0 = today)
    """
    from agents.models import Device

    devices = Device.objects.filter(
        game_profile__default_task_chain__isnull=False,
    ).select_related('game_profile__default_task_chain', 'game_account')

    plans = []
    for day_offset in range(days):
        for device in devices:
            # Type narrowing for mypy: the queryset above filtered
            # game_profile__default_task_chain__isnull=False, so both
            # device.game_profile and device.game_profile.default_task_chain
            # are guaranteed non-None at runtime.
            assert device.game_profile is not None
            assert device.game_profile.default_task_chain is not None
            chain = device.game_profile.default_task_chain
            plans.append({
                'device_id': device.id,
                'device_name': device.name or device.adb_serial or '',
                'account_id': device.game_account_id,
                'account_name': (
                    device.game_account.username
                    if device.game_account else None
                ),
                'task_chain_id': chain.id,
                'task_chain_name': chain.name,
                'day_offset': day_offset,
            })

    return plans
