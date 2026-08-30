"""
恢复策略执行引擎 (P-020-B ActionChain 重构版)

监听任务执行状态变更，当检测到异常时按预设的 5 层恢复策略逐级触发恢复动作。
恢复层级：步骤级 → 任务级 → 应用级 → 设备级 → 系统级
每次恢复动作记录到 RecoveryLog。

P-020-B 重构要点:
- 新增 ActionSpec 数据类 + RecoveryActionChain 类
- 每个 handler 默认从 UnattendedStrategy.recovery_config 读取 action 序列
- 支持 action 失败时的 on_failure 策略 (abort / continue / skip)
- 现有 5 个 handle_* 函数保留为薄包装, 内部委托给 RecoveryActionChain
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from scheduler.models import RecoveryLog

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# P-020-B: ActionChain 数据模型
# ─────────────────────────────────────────────


class OnFailurePolicy(str, Enum):  # noqa: UP042 - 兼容 Python <3.11
    """Action 失败时后续 action 的处理策略

    - abort: 中止整个 chain (默认)
    - continue: 继续执行下一 action (不视为 chain 失败)
    - skip: 跳过剩余 action, 但 chain 仍记为成功
    """

    ABORT = 'abort'
    CONTINUE = 'continue'
    SKIP = 'skip'


@dataclass
class ActionSpec:
    """单个恢复动作的规格说明

    Fields:
    - type: 动作类型 (retry / skip / restart / restart_app / notify / ...)
    - target: 动作目标 (步骤ID/任务ID/设备ID/Agent ID, 字符串或数字)
    - params: 动作附加参数 (dict, 可选)
    - on_failure: 失败策略 (默认 abort)
    - max_retries: 单动作内部重试次数 (默认 1, 不重试)
    - timeout_seconds: 单动作超时 (默认 30s)
    - description: 人类可读描述 (写入 RecoveryLog)
    """

    type: str
    target: Any = None
    params: dict[str, Any] = field(default_factory=dict)
    on_failure: str = OnFailurePolicy.ABORT.value
    max_retries: int = 1
    timeout_seconds: int = 30
    description: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {
            'type': self.type,
            'target': self.target,
            'params': self.params,
            'on_failure': self.on_failure,
            'max_retries': self.max_retries,
            'timeout_seconds': self.timeout_seconds,
            'description': self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ActionSpec':
        return cls(
            type=data['type'],
            target=data.get('target'),
            params=data.get('params') or {},
            on_failure=data.get('on_failure', OnFailurePolicy.ABORT.value),
            max_retries=data.get('max_retries', 1),
            timeout_seconds=data.get('timeout_seconds', 30),
            description=data.get('description', ''),
        )


@dataclass
class ChainStepResult:
    """ActionChain 单步执行结果"""

    action_type: str
    success: bool
    attempts: int = 1
    error: str | None = None
    duration_ms: int = 0
    output: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'action_type': self.action_type,
            'success': self.success,
            'attempts': self.attempts,
            'error': self.error,
            'duration_ms': self.duration_ms,
            'output': self.output,
        }


class RecoveryActionChain:
    """可配置动作序列执行器 (P-020-B)

    接受有序的 ActionSpec 列表, 按顺序执行。
    每步结果累积到 results, 最终返回 chain 总结果。

    Usage:
        chain = RecoveryActionChain([
            ActionSpec(type='retry', target=1, max_retries=3),
            ActionSpec(type='notify', target='admin', on_failure='continue'),
        ])
        result = chain.execute(context={'error': 'timeout'})
    """

    def __init__(self, actions: list[ActionSpec], level: str = 'custom'):
        self.actions = actions
        self.level = level
        self.results: list[ChainStepResult] = []

    def execute(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        按顺序执行 action 序列。

        Args:
            context: 共享上下文 (e.g. error message / device id), 每个 action 可读取

        Returns:
            {
                'success': bool,                  # chain 整体是否成功
                'completed': int,                 # 完成的 action 数
                'total': int,                     # 总 action 数
                'aborted_at': int | None,         # 在哪一步中止 (-1 表示未中止)
                'results': [ChainStepResult, ...]
            }
        """
        context = context or {}
        self.results = []
        aborted_at: int | None = None
        chain_success = True

        for idx, action in enumerate(self.actions):
            step_result = self._execute_single_action(action, context)
            self.results.append(step_result)

            if not step_result.success:
                policy = action.on_failure
                if policy == OnFailurePolicy.ABORT.value:
                    logger.warning(
                        'RecoveryActionChain level=%s abort at step %s (%s): %s',
                        self.level, idx, action.type, step_result.error,
                    )
                    aborted_at = idx
                    chain_success = False
                    break
                elif policy == OnFailurePolicy.SKIP.value:
                    logger.info(
                        'RecoveryActionChain level=%s skip remaining at step %s (%s)',
                        self.level, idx, action.type,
                    )
                    aborted_at = idx
                    chain_success = True
                    break
                else:  # 'continue'
                    logger.info(
                        'RecoveryActionChain level=%s continue after step %s failure (%s)',
                        self.level, idx, action.type,
                    )
                    chain_success = False  # 单步失败但继续, 整体仍标失败 (P-020-B 语义)

        return {
            'success': chain_success,
            'completed': len(self.results),
            'total': len(self.actions),
            'aborted_at': aborted_at if aborted_at is not None else -1,
            'results': [r.to_dict() for r in self.results],
        }

    def _execute_single_action(
        self, action: ActionSpec, context: dict[str, Any],
    ) -> ChainStepResult:
        """执行单个 action, 内部重试到 max_retries 次

        S2 (2026-08-16): 实现 ActionSpec.timeout_seconds — 每个 attempt
        内用 time.monotonic 检查超时。同步阻塞型动作 (ADB 命令等) 无法
        被强制中断, 但超时检查兜底保证慢动作不会无限拖住恢复链。
        """
        attempts = 0
        last_error: str | None = None
        start = time.monotonic()
        timeout_seconds = max(0, action.timeout_seconds)

        for attempt in range(1, max(1, action.max_retries) + 1):
            attempts = attempt
            attempt_start = time.monotonic()
            try:
                output = self._run_action_body(action, context)
            except Exception as exc:
                last_error = str(exc)[:200]
                logger.warning(
                    'Action %s attempt %s/%s failed: %s',
                    action.type, attempt, action.max_retries, last_error,
                )
                continue

            elapsed = time.monotonic() - attempt_start
            if timeout_seconds > 0 and elapsed > timeout_seconds:
                # S2: per-attempt timeout guard — 动作体执行超过
                # timeout_seconds 时终止该 attempt (同步阻塞无法中断,
                # 但避免"超时后仍被当作成功").
                last_error = (
                    f'timeout after {elapsed:.1f}s '
                    f'(limit {timeout_seconds}s)'
                )
                logger.warning(
                    'Action %s attempt %s timed out after %.1fs (limit %ss)',
                    action.type, attempt, elapsed, timeout_seconds,
                )
                break

            duration_ms = int((time.monotonic() - start) * 1000)
            return ChainStepResult(
                action_type=action.type,
                success=True,
                attempts=attempts,
                duration_ms=duration_ms,
                output=output,
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        return ChainStepResult(
            action_type=action.type,
            success=False,
            attempts=attempts,
            error=last_error,
            duration_ms=duration_ms,
        )

    def _run_action_body(
        self, action: ActionSpec, context: dict[str, Any],
    ) -> Any:
        """实际执行动作体 (MVP: 按 type 路由到 execute_recovery_action)

        后续 Phase 可替换为真实命令执行 (ADB / Celery task / WebSocket notify)
        """
        return execute_recovery_action(
            action_type=action.type,
            target_id=action.target,
            config=action.params,
        )


def _build_default_actions_for_level(level: str, target_id: Any, config: dict) -> list[ActionSpec]:
    """根据 level 从 strategy config 构造默认 action 序列

    Args:
        level: step / task / app / device / system
        target_id: 目标 ID
        config: strategy config (来自 get_strategy_config)

    Returns:
        ActionSpec 列表
    """
    if level == 'step':
        step_cfg = config.get('stepLevel', {})
        max_retries = step_cfg.get('maxRetries', 3)
        return [
            ActionSpec(
                type='retry',
                target=target_id,
                params={'max_retries': max_retries},
                on_failure=OnFailurePolicy.ABORT.value,
                description=f'重试步骤 {target_id} (最多 {max_retries} 次)',
            ),
        ]
    if level == 'task':
        task_cfg = config.get('taskLevel', {})
        action = task_cfg.get('failureAction', 'skip')
        return [
            ActionSpec(
                type=action,
                target=target_id,
                params={'consecutive_failures_threshold': task_cfg.get('consecutiveFailureThreshold', 3)},
                on_failure=OnFailurePolicy.SKIP.value,
                description=f'任务失败处理: {action}',
            ),
        ]
    if level == 'app':
        app_cfg = config.get('appLevel', {})
        freeze_action = app_cfg.get('freezeAction', 'restart_app')
        return [
            ActionSpec(
                type=freeze_action,
                target=target_id,
                params={'freeze_timeout_seconds': app_cfg.get('freezeTimeoutSeconds', 120)},
                on_failure=OnFailurePolicy.CONTINUE.value,
                description=f'应用卡死处理: {freeze_action}',
            ),
            ActionSpec(
                type='notify',
                target='admin',
                on_failure=OnFailurePolicy.CONTINUE.value,
                description='通知管理员',
            ),
        ]
    if level == 'device':
        device_cfg = config.get('deviceLevel', {})
        crash_action = device_cfg.get('crashAction', 'restart_emulator')
        return [
            ActionSpec(
                type=crash_action,
                target=target_id,
                params={'backup_device_id': device_cfg.get('backupDeviceId')},
                on_failure=OnFailurePolicy.ABORT.value,
                description=f'设备崩溃处理: {crash_action}',
            ),
        ]
    if level == 'system':
        system_cfg = config.get('systemLevel', {})
        timeout_actions = system_cfg.get('timeoutActions', ['notify', 'mark_offline', 'reassign'])
        return [
            ActionSpec(
                type=a,
                target=target_id,
                on_failure=OnFailurePolicy.CONTINUE.value,
                description=f'系统级动作: {a}',
            )
            for a in timeout_actions
        ]
    return []


# ─────────────────────────────────────────────
# 兼容层: 现有 5 个 handle_* 函数 (P-020-B 薄包装)
# ─────────────────────────────────────────────


def get_strategy_config() -> dict:
    """
    获取当前无人值守策略配置的 recovery 部分。

    Returns:
        恢复策略配置字典（5 个层级）
    """
    try:
        from settings.models import UnattendedStrategy

        strategy = UnattendedStrategy.objects.first()
        if strategy and strategy.is_active:
            return strategy.recovery_config or {}
    except Exception:
        logger.warning('load recovery config failed, fallback to default', exc_info=True)

    return {
        'stepLevel': {'maxRetries': 3, 'retryIntervalSeconds': 5, 'exponentialBackoff': False},
        'taskLevel': {'consecutiveFailureThreshold': 3, 'failureAction': 'skip'},
        'appLevel': {'freezeDetection': True, 'freezeTimeoutSeconds': 120, 'freezeAction': 'restart_app'},
        'deviceLevel': {'crashDetection': True, 'crashAction': 'restart_emulator', 'backupDeviceId': None, 'maxRestartCount': 2},
        'systemLevel': {'agentTimeoutSeconds': 300, 'timeoutActions': ['notify', 'mark_offline', 'reassign']},
    }


def _run_chain_and_log(
    level: str,
    trigger_event: str,
    target_id: Any,
    chain_result: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """ActionChain 跑完后写 RecoveryLog + 返回聚合结果 (内部 helper)

    向后兼容: action 字段保留旧接口的语义值 (e.g. 'system_recovery' 而非 'system_chain')
    """
    log_recovery(
        recovery_level=level,
        trigger_event=trigger_event,
        action_taken=f'ActionChain: {chain_result["completed"]}/{chain_result["total"]} 步完成',
        success=chain_result['success'],
        details={
            'target_id': target_id,
            'context': context,
            'chain_result': chain_result,
        },
    )
    # 旧接口兼容: action 字段保持原有语义值
    # - step → 'retry' (单 action retry)
    # - task → actions[0].type (skip / restart / switch_account)
    # - app  → actions[0].type (restart_app / relogin / notify_only)
    # - device → actions[0].type (restart_emulator / reconnect_adb / switch_backup)
    # - system → 'system_recovery' (system level 跑多个 actions, 旧接口固定值)
    if level == 'system':
        legacy_action = 'system_recovery'
    elif chain_result['results']:
        # 优先用第一个成功 action 的 type, 否则用第一个 action 的 type
        first_success = next(
            (r for r in chain_result['results'] if r['success']),
            None,
        )
        legacy_action = (first_success or chain_result['results'][0])['action_type']
    else:
        legacy_action = f'{level}_chain'

    return {
        'success': chain_result['success'],
        'action': legacy_action,
        'details': {
            'completed': chain_result['completed'],
            'total': chain_result['total'],
            'aborted_at': chain_result['aborted_at'],
        },
    }


def handle_step_failure(execution_step_id: int, error_message: str) -> dict:
    """
    处理步骤级失败，含重试+指数退避 (P-020-B: 委托给 ActionChain)。

    Args:
        execution_step_id: 执行步骤 ID
        error_message: 错误信息

    Returns:
        恢复结果字典 {success, action, details}
    """
    config = get_strategy_config()
    actions = _build_default_actions_for_level('step', execution_step_id, config)

    chain = RecoveryActionChain(actions, level='step')
    result = chain.execute(context={'error_message': error_message})
    return _run_chain_and_log(
        level='step',
        trigger_event=f'步骤 {execution_step_id} 执行失败: {error_message[:80]}',
        target_id=execution_step_id,
        chain_result=result,
        context={'error_message': error_message},
    )


def handle_task_failure(task_execution_id: int, consecutive_failures: int) -> dict:
    """
    处理任务级失败 (P-020-B: 委托给 ActionChain)。

    Args:
        task_execution_id: 任务执行 ID
        consecutive_failures: 当前连续失败次数

    Returns:
        恢复结果字典
    """
    config = get_strategy_config()
    task_config = config.get('taskLevel', {})
    threshold = task_config.get('consecutiveFailureThreshold', 3)

    if consecutive_failures < threshold:
        logger.info(
            '任务级恢复未触发: 连续失败 %s < 阈值 %s',
            consecutive_failures, threshold,
        )
        return {'success': True, 'action': 'continue', 'details': {}}

    actions = _build_default_actions_for_level('task', task_execution_id, config)
    chain = RecoveryActionChain(actions, level='task')
    result = chain.execute(context={'consecutive_failures': consecutive_failures})
    return _run_chain_and_log(
        level='task',
        trigger_event=f'任务 {task_execution_id} 连续失败 {consecutive_failures} 次（阈值 {threshold}）',
        target_id=task_execution_id,
        chain_result=result,
        context={'consecutive_failures': consecutive_failures, 'threshold': threshold},
    )


def handle_app_freeze(device_id: int, freeze_duration_seconds: int) -> dict:
    """
    处理应用级卡死 (P-020-B: 委托给 ActionChain)。

    Args:
        device_id: 设备 ID
        freeze_duration_seconds: 卡死持续时间（秒）

    Returns:
        恢复结果字典
    """
    config = get_strategy_config()
    app_config = config.get('appLevel', {})
    freeze_detection = app_config.get('freezeDetection', True)
    freeze_timeout = app_config.get('freezeTimeoutSeconds', 120)

    if not freeze_detection:
        logger.info('应用级卡死检测已禁用')
        return {'success': True, 'action': 'ignore', 'details': {}}

    if freeze_duration_seconds < freeze_timeout:
        logger.info(
            '应用级恢复未触发: 卡死 %ss < 超时 %ss',
            freeze_duration_seconds, freeze_timeout,
        )
        return {'success': True, 'action': 'waiting', 'details': {}}

    actions = _build_default_actions_for_level('app', device_id, config)
    chain = RecoveryActionChain(actions, level='app')
    result = chain.execute(context={'freeze_duration_seconds': freeze_duration_seconds})
    return _run_chain_and_log(
        level='app',
        trigger_event=f'设备 {device_id} 游戏卡死 {freeze_duration_seconds} 秒',
        target_id=device_id,
        chain_result=result,
        context={'freeze_duration_seconds': freeze_duration_seconds, 'freeze_timeout': freeze_timeout},
    )


def handle_device_crash(device_id: int) -> dict:
    """
    处理设备级崩溃 (P-020-B: 委托给 ActionChain)。

    Args:
        device_id: 设备 ID

    Returns:
        恢复结果字典
    """
    config = get_strategy_config()
    device_config = config.get('deviceLevel', {})
    crash_detection = device_config.get('crashDetection', True)

    if not crash_detection:
        logger.info('设备级崩溃检测已禁用')
        return {'success': True, 'action': 'ignore', 'details': {}}

    actions = _build_default_actions_for_level('device', device_id, config)
    chain = RecoveryActionChain(actions, level='device')
    result = chain.execute(context={})
    return _run_chain_and_log(
        level='device',
        trigger_event=f'设备 {device_id} 崩溃/断开',
        target_id=device_id,
        chain_result=result,
        context={},
    )


def handle_agent_timeout(agent_id: str, timeout_duration_seconds: int) -> dict:
    """
    处理系统级 Agent 无响应 (P-020-B: 委托给 ActionChain)。

    Args:
        agent_id: Agent ID
        timeout_duration_seconds: 超时时长（秒）

    Returns:
        恢复结果字典
    """
    config = get_strategy_config()
    system_config = config.get('systemLevel', {})
    agent_timeout = system_config.get('agentTimeoutSeconds', 300)

    if timeout_duration_seconds < agent_timeout:
        logger.info(
            '系统级恢复未触发: Agent 无响应 %ss < 超时 %ss',
            timeout_duration_seconds, agent_timeout,
        )
        return {'success': True, 'action': 'waiting', 'details': {}}

    actions = _build_default_actions_for_level('system', agent_id, config)
    chain = RecoveryActionChain(actions, level='system')
    result = chain.execute(context={'timeout_duration_seconds': timeout_duration_seconds})
    return _run_chain_and_log(
        level='system',
        trigger_event=f'Agent {agent_id} 无响应超过 {timeout_duration_seconds} 秒',
        target_id=agent_id,
        chain_result=result,
        context={
            'timeout_duration': timeout_duration_seconds,
            'agent_timeout': agent_timeout,
        },
    )


# ─────────────────────────────────────────────
# 动作执行器: execute_recovery_action 路由 + 具体动作实现
# ─────────────────────────────────────────────


def execute_recovery_action(action_type: str, target_id, config: dict) -> dict:
    """
    执行具体的恢复动作 (P-020-B: 升级支持 ActionSpec 调用, 返回结构化结果)。

    Args:
        action_type: 动作类型:
            - notify: 广播 dashboard 通知
            - mark_offline: Agent 置为 OFFLINE
            - reassign: 重分配 TaskExecution 到备用 agent
            - restart_app / relogin / notify_only / restart_emulator / reconnect_adb / switch_backup:
              WS device.command 帧派发
            - retry / skip / restart / switch_account: 语义性动作, 返回 success
            - 其他: 返回 error

        target_id: 目标 ID（步骤/任务/设备/Agent）
        config: 配置字典

    Returns:
        恢复结果字典
    """
    logger.info('执行恢复动作: type=%s, target=%s', action_type, target_id)

    if action_type == 'notify':
        return _action_notify(target_id, config)
    elif action_type == 'mark_offline':
        return _action_mark_offline(target_id, config)
    elif action_type == 'reassign':
        return _action_reassign(target_id, config)
    elif action_type in (
        'restart_app', 'relogin', 'notify_only',
        'restart_emulator', 'reconnect_adb', 'switch_backup',
    ):
        return _action_device_command(action_type, target_id, config)
    elif action_type in ('retry', 'skip', 'restart', 'switch_account'):
        return _action_semantic(action_type, target_id, config)
    else:
        return {
            'success': False,
            'action': action_type,
            'target_id': target_id,
            'error': f'unknown action_type: {action_type}',
        }


def _action_notify(target_id, config):
    """广播 dashboard 通知 via channel_layer.group_send."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return {
            'success': False,
            'action': 'notify',
            'target_id': target_id,
            'error': 'channel layer is None',
        }

    message = config.get('message', '')
    level = config.get('level', 'info')

    async_to_sync(channel_layer.group_send)(
        'dashboard',
        {
            'type': 'notification',
            'payload': {
                'message': message,
                'level': level,
                'target_id': target_id,
            },
        },
    )
    return {
        'success': True,
        'action': 'notify',
        'target_id': target_id,
        'details': {
            'message': message,
            'level': level,
            'target_id': target_id,
        },
    }


def _action_mark_offline(target_id, config):
    """将 Agent 状态置为 OFFLINE."""
    from workers.models import Worker

    try:
        agent = Worker.objects.get(agent_id=target_id)
        agent.status = Worker.Status.OFFLINE
        agent.save(update_fields=['status'])
        return {
            'success': True,
            'action': 'mark_offline',
            'target_id': target_id,
            'details': {'agent_id': target_id},
        }
    except Worker.DoesNotExist:
        return {
            'success': False,
            'action': 'mark_offline',
            'target_id': target_id,
            'error': f'agent not found: {target_id}',
        }


def _action_reassign(target_id, config):
    """将 TaskExecution 重分配到可用的备用 agent.

    1. 查找可用 (ONLINE) 且非当前执行 agent 的 Agent
    2. 切换 TaskExecution.agent 到备用 agent
    3. 设置 recovery_layer = 5 (system level)
    4. 重置所有 RUNNING execution_step 为 PENDING
    5. 重新派发 dispatch_task (S2: 否则任务永远卡 PENDING)

    S2 (2026-08-16): 评估发现 reassign 只改 agent + 重置 step, 没有
    重新派发 — 恢复动作"成功"但任务永远卡 PENDING, 死代码路径.
    现在换 agent 后调用 dispatch_task.delay 重新派发; 仅在执行
    非终态时派发 (防 FAILED/CANCELLED 执行被重新激活).
    """
    from workers.models import Worker

    from tasks.models import ExecutionStep, TaskExecution

    if not isinstance(target_id, int):
        return {
            'success': False,
            'action': 'reassign',
            'target_id': target_id,
            'error': 'target_id is not int',
        }

    try:
        execution = TaskExecution.objects.get(pk=target_id)
    except TaskExecution.DoesNotExist:
        return {
            'success': False,
            'action': 'reassign',
            'target_id': target_id,
            'error': 'TaskExecution not found',
        }

    # S2: 终态执行不重新激活
    if execution.status != TaskExecution.Status.RUNNING:
        return {
            'success': False,
            'action': 'reassign',
            'target_id': target_id,
            'error': f'execution not RUNNING (status={execution.status})',
        }

    # 查找可用 agent (ONLINE, 排除当前执行 agent)
    available = Worker.objects.filter(
        status=Worker.Status.ONLINE,
    ).exclude(pk=execution.agent_id).first()

    if available is None:
        return {
            'success': False,
            'action': 'reassign',
            'target_id': target_id,
            'error': 'no available agent',
        }

    # 重分配
    execution.agent = available
    execution.recovery_layer = 5
    execution.save(update_fields=['agent', 'recovery_layer'])

    # 重置 RUNNING step 为 PENDING
    ExecutionStep.objects.filter(
        task_result=execution,
        status=ExecutionStep.Status.RUNNING,
    ).update(status=ExecutionStep.Status.PENDING)

    # S2: 重新派发 — 否则任务永远卡 PENDING
    from tasks.tasks import dispatch_task
    dispatch_task.delay(execution.id)

    return {
        'success': True,
        'action': 'reassign',
        'target_id': target_id,
        'details': {'new_agent_id': available.id},
    }


def _resolve_agent_or_device_owner(target_id):
    """将 target_id (Device.pk) 解析为 (agent_id, device_id) 元组."""
    from workers.models import Device

    try:
        device = Device.objects.get(pk=target_id)
        if device.agent:
            return device.agent.agent_id, device.id
        return None, None
    except Device.DoesNotExist:
        return None, None


def _action_device_command(action_type, target_id, config):
    """通过 WS device.command 帧派发命令到 agent 拥有的设备.

    Device 命令: restart_app / relogin / notify_only / restart_emulator /
    reconnect_adb / switch_backup.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return {
            'success': False,
            'action': action_type,
            'target_id': target_id,
            'error': 'channel layer is None',
        }

    agent_id, device_id = _resolve_agent_or_device_owner(target_id)
    if not agent_id:
        return {
            'success': False,
            'action': action_type,
            'target_id': target_id,
            'error': 'cannot resolve agent for target_id',
        }

    async_to_sync(channel_layer.group_send)(
        f'agent_{agent_id}',
        {
            'type': 'device.command',
            'payload': {
                'command': action_type,
                'target_id': target_id,
                'config': config,
            },
        },
    )

    return {
        'success': True,
        'action': action_type,
        'target_id': target_id,
        'details': {
            'agent_id': agent_id,
        },
    }


def _action_semantic(action_type, target_id, config):
    """语义性动作 (retry / skip / restart / switch_account).

    S2 (2026-08-16): 评估发现旧实现返回假 success — "看起来执行了" 实际
    是死代码路径. 现在:
    - retry: 重置对应 ExecutionStep FAILED/RUNNING → PENDING (若其
      task_result 非终态), 使下游 retry_pending_executions / 重新调度
      可恢复. 保持防递归: 不改 signal 触发, 不保存触发 signal 的字段.
    - skip: 标记对应 ExecutionStep 为 SKIPPED (若其 task_result 非终态).
    - restart / switch_account (S2-2.7, 2026-08-17): 解析执行 agent 的
      ONLINE 设备 → 派发 device.command 帧 (restart → restart_app),
      不再诚实降级. Agent 端 handle_device_command 执行后通过
      device.action_result 上报真实结果 (P-048 写 RecoveryLog).
    """
    from tasks.models import ExecutionStep, TaskExecution

    if action_type == 'retry':
        try:
            step = ExecutionStep.objects.select_related('task_result').get(pk=target_id)
        except (ExecutionStep.DoesNotExist, ValueError, TypeError):
            return {
                'success': False,
                'action': action_type,
                'target_id': target_id,
                'error': 'ExecutionStep not found',
            }
        if step.task_result.status != TaskExecution.Status.RUNNING:
            return {
                'success': False,
                'action': action_type,
                'target_id': target_id,
                'error': f'execution not RUNNING (status={step.task_result.status})',
            }
        ExecutionStep.objects.filter(pk=step.pk).update(
            status=ExecutionStep.Status.PENDING,
            error_message='',
        )
        return {
            'success': True,
            'action': action_type,
            'target_id': target_id,
            'details': {'step_status': 'pending'},
        }

    if action_type == 'skip':
        # target 可能是 ExecutionStep id (step 级默认链) 或 TaskExecution id
        # (task 级默认链 failureAction='skip') — 分别落地:
        # - step 级: 标记 SKIPPED (execution 仍 RUNNING 时)
        # - task 级: 任务已 FAILED, skip 语义 = 确认失败不再恢复 (无动作,
        #   返回成功表示"已按策略跳过")
        from tasks.models import TaskExecution

        step = None
        try:
            step = ExecutionStep.objects.select_related('task_result').get(pk=target_id)
        except (ExecutionStep.DoesNotExist, ValueError, TypeError):
            step = None
        if step is not None:
            if step.task_result.status != TaskExecution.Status.RUNNING:
                return {
                    'success': False,
                    'action': action_type,
                    'target_id': target_id,
                    'error': f'execution not RUNNING (status={step.task_result.status})',
                }
            ExecutionStep.objects.filter(pk=step.pk).update(
                status=ExecutionStep.Status.SKIPPED,
            )
            return {
                'success': True,
                'action': action_type,
                'target_id': target_id,
                'details': {'step_status': 'skipped'},
            }

        # task 级: target 是 TaskExecution id
        try:
            execution = TaskExecution.objects.get(pk=target_id)
        except (TaskExecution.DoesNotExist, ValueError, TypeError):
            # skip 语义 = "接受失败, 不恢复" — 记录已不存在时跳过仍算成功
            return {
                'success': True,
                'action': action_type,
                'target_id': target_id,
                'details': {'note': 'execution not found; skip policy acknowledged'},
            }
        if execution.status == TaskExecution.Status.FAILED:
            return {
                'success': True,
                'action': action_type,
                'target_id': target_id,
                'details': {'note': 'task failed; skip policy acknowledged'},
            }
        return {
            'success': False,
            'action': action_type,
            'target_id': target_id,
            'error': f'execution not FAILED (status={execution.status})',
        }

    # restart / switch_account: 语义动作 — 解析执行 agent 的设备后派发
    # device.command (S2-2.7, 2026-08-17: agent 端 handle_device_command 已
    # 接线, backend 不再诚实降级, 派发即视为链路已接; agent 执行结果通过
    # device.action_result 帧上报写入 RecoveryLog).
    #
    # target 语义: step 级 target 是 ExecutionStep.id, task 级 target 是
    # TaskExecution.id. 从 task_result 反查 agent → 设备 → 派发.
    from tasks.models import ExecutionStep, TaskExecution

    step = None
    try:
        step = ExecutionStep.objects.select_related('task_result').get(pk=target_id)
    except (ExecutionStep.DoesNotExist, ValueError, TypeError):
        step = None
    execution = step.task_result if step is not None else None
    if execution is None:
        try:
            execution = TaskExecution.objects.get(pk=target_id)
        except (TaskExecution.DoesNotExist, ValueError, TypeError):
            execution = None
    if execution is None or not execution.agent_id:
        return {
            'success': False,
            'action': action_type,
            'target_id': target_id,
            'error': f'{action_type} requires an execution bound to an agent; cannot resolve target',
        }

    from workers.models import Device

    device = Device.objects.filter(
        agent=execution.agent_id,
        status=Device.Status.ONLINE,
    ).first()
    if device is None:
        return {
            'success': False,
            'action': action_type,
            'target_id': target_id,
            'error': f'{action_type} requires an ONLINE device bound to agent {execution.agent_id}',
        }

    # restart → restart_app 语义 (重启应用); switch_account 原样派发
    device_command = 'restart_app' if action_type == 'restart' else action_type
    return _action_device_command(device_command, device.id, config)


def log_recovery(
    recovery_level: str,
    trigger_event: str,
    action_taken: str,
    success: bool,
    details: dict | None = None,
):
    """
    记录恢复操作到 RecoveryLog。

    Args:
        recovery_level: 恢复层级 (step/task/app/device/system)
        trigger_event: 触发事件描述
        action_taken: 执行的动作描述
        success: 是否成功
        details: 详细信息字典
    """
    try:
        RecoveryLog.objects.create(
            recovery_level=recovery_level,
            trigger_event=trigger_event,
            action_taken=action_taken,
            success=success,
            details=details or {},
        )
        logger.info(
            'RecoveryLog 写入: level=%s, event=%s, success=%s',
            recovery_level, trigger_event[:50], success,
        )
    except Exception as e:
        logger.error('RecoveryLog 写入失败: %s', e)
