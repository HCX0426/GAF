"""
P-020-B: RecoveryActionChain 重构测试

覆盖:
- ActionSpec 序列化往返
- RecoveryActionChain 顺序执行
- on_failure=abort 中止后续
- on_failure=continue 单步失败继续
- on_failure=skip 跳过后续但 chain 成功
- 单 action max_retries 重试
- 默认 handler 委托给 ActionChain
"""

import pytest

from scheduler.recovery_engine import (
    ActionSpec,
    OnFailurePolicy,
    RecoveryActionChain,
    _build_default_actions_for_level,
    get_strategy_config,
    handle_step_failure,
    handle_task_failure,
)

pytestmark = pytest.mark.integration


class TestActionSpec:
    """ActionSpec 序列化"""

    def test_action_spec_to_dict_from_dict_roundtrip(self):
        """ActionSpec.to_dict + from_dict 应能往返还原"""
        original = ActionSpec(
            type='retry',
            target=42,
            params={'max_retries': 3},
            on_failure='continue',
            max_retries=3,
            timeout_seconds=60,
            description='test step',
        )
        data = original.to_dict()
        restored = ActionSpec.from_dict(data)
        assert restored.type == original.type
        assert restored.target == original.target
        assert restored.params == original.params
        assert restored.on_failure == original.on_failure
        assert restored.max_retries == original.max_retries
        assert restored.timeout_seconds == original.timeout_seconds
        assert restored.description == original.description

    def test_action_spec_from_dict_defaults(self):
        """from_dict 应使用默认值填补缺失字段"""
        spec = ActionSpec.from_dict({'type': 'restart'})
        assert spec.type == 'restart'
        assert spec.target is None
        assert spec.params == {}
        assert spec.on_failure == OnFailurePolicy.ABORT.value
        assert spec.max_retries == 1
        assert spec.timeout_seconds == 30


class TestRecoveryActionChain:
    """RecoveryActionChain 核心行为"""

    def test_chain_executes_in_order(self):
        """Chain 应按顺序执行 action, results 顺序与 actions 一致"""
        actions = [
            ActionSpec(type='action_a', target=1),
            ActionSpec(type='action_b', target=2),
            ActionSpec(type='action_c', target=3),
        ]
        chain = RecoveryActionChain(actions, level='test')
        result = chain.execute()

        assert result['success'] is True
        assert result['completed'] == 3
        assert result['total'] == 3
        assert result['aborted_at'] == -1
        assert len(result['results']) == 3
        assert [r['action_type'] for r in result['results']] == ['action_a', 'action_b', 'action_c']

    def test_chain_abort_on_failure_stops_subsequent(self):
        """on_failure=abort 单步失败时中止后续, chain.success=False"""
        # 用 raise 模拟 action body 失败: 包装 execute_recovery_action
        actions = [
            ActionSpec(type='action_a', target=1, on_failure=OnFailurePolicy.ABORT.value),
            ActionSpec(type='action_b', target=2, on_failure=OnFailurePolicy.ABORT.value),
            ActionSpec(type='action_c', target=3, on_failure=OnFailurePolicy.ABORT.value),
        ]
        chain = RecoveryActionChain(actions, level='test')

        # 替换 _run_action_body 让 action_b 抛异常
        original_body = chain._run_action_body

        def fake_body(action, context):
            if action.type == 'action_b':
                raise RuntimeError('simulated failure')
            return original_body(action, context)

        chain._run_action_body = fake_body
        result = chain.execute()

        assert result['success'] is False
        assert result['completed'] == 2  # a 成功, b 失败, c 没跑
        assert result['aborted_at'] == 1
        assert [r['action_type'] for r in result['results']] == ['action_a', 'action_b']
        assert result['results'][1]['success'] is False
        assert 'simulated failure' in result['results'][1]['error']

    def test_chain_continue_on_failure_keeps_going(self):
        """on_failure=continue 单步失败时继续, chain.success=False 但跑完所有"""
        actions = [
            ActionSpec(type='action_a', target=1, on_failure=OnFailurePolicy.CONTINUE.value),
            ActionSpec(type='action_b', target=2, on_failure=OnFailurePolicy.CONTINUE.value),
            ActionSpec(type='action_c', target=3, on_failure=OnFailurePolicy.CONTINUE.value),
        ]
        chain = RecoveryActionChain(actions, level='test')

        original_body = chain._run_action_body

        def fake_body(action, context):
            if action.type == 'action_b':
                raise RuntimeError('simulated failure')
            return original_body(action, context)

        chain._run_action_body = fake_body
        result = chain.execute()

        assert result['success'] is False  # 整体失败 (有单步失败)
        assert result['completed'] == 3  # 全部跑完
        assert result['aborted_at'] == -1  # 没有中止
        assert [r['action_type'] for r in result['results']] == ['action_a', 'action_b', 'action_c']

    def test_chain_skip_on_failure_marks_success(self):
        """on_failure=skip 单步失败时跳过后续, chain.success=True"""
        actions = [
            ActionSpec(type='action_a', target=1, on_failure=OnFailurePolicy.SKIP.value),
            ActionSpec(type='action_b', target=2, on_failure=OnFailurePolicy.SKIP.value),
            ActionSpec(type='action_c', target=3, on_failure=OnFailurePolicy.SKIP.value),
        ]
        chain = RecoveryActionChain(actions, level='test')

        original_body = chain._run_action_body

        def fake_body(action, context):
            if action.type == 'action_b':
                raise RuntimeError('simulated failure')
            return original_body(action, context)

        chain._run_action_body = fake_body
        result = chain.execute()

        assert result['success'] is True  # skip 视为成功
        assert result['completed'] == 2  # 跑到 b 失败后跳过 c
        assert result['aborted_at'] == 1
        assert [r['action_type'] for r in result['results']] == ['action_a', 'action_b']

    def test_single_action_retries_on_failure(self):
        """单 action max_retries=3 时, 失败重试 3 次后仍失败则返回 success=False"""
        actions = [
            ActionSpec(type='flaky', target=1, max_retries=3),
        ]
        chain = RecoveryActionChain(actions, level='test')

        def always_fail(action, context):
            raise RuntimeError('always fails')

        chain._run_action_body = always_fail
        result = chain.execute()

        assert result['success'] is False
        assert result['results'][0]['attempts'] == 3
        assert result['results'][0]['success'] is False
        assert 'always fails' in result['results'][0]['error']

    def test_single_action_succeeds_on_retry(self):
        """单 action 第 2 次重试成功"""
        actions = [
            ActionSpec(type='flaky', target=1, max_retries=3),
        ]
        chain = RecoveryActionChain(actions, level='test')
        call_count = {'n': 0}

        def fail_then_success(action, context):
            call_count['n'] += 1
            if call_count['n'] < 2:
                raise RuntimeError('first call fails')
            return {'ok': True}

        chain._run_action_body = fail_then_success
        result = chain.execute()

        assert result['success'] is True
        assert result['results'][0]['attempts'] == 2
        assert result['results'][0]['success'] is True
        assert result['results'][0]['output'] == {'ok': True}


class TestBuildDefaultActions:
    """_build_default_actions_for_level 配置化映射"""

    def test_step_level_uses_retry_action(self):
        config = get_strategy_config()
        actions = _build_default_actions_for_level('step', 42, config)
        assert len(actions) == 1
        assert actions[0].type == 'retry'
        assert actions[0].target == 42
        assert actions[0].on_failure == OnFailurePolicy.ABORT.value

    def test_app_level_has_two_actions_continue_policy(self):
        """app level 默认 [freeze_action, notify], 全部 continue"""
        config = get_strategy_config()
        actions = _build_default_actions_for_level('app', 1, config)
        assert len(actions) == 2
        assert actions[0].type == 'restart_app'
        assert actions[0].on_failure == OnFailurePolicy.CONTINUE.value
        assert actions[1].type == 'notify'
        assert actions[1].on_failure == OnFailurePolicy.CONTINUE.value

    def test_system_level_uses_timeout_actions_list(self):
        """system level 应展开 timeoutActions 列表"""
        config = get_strategy_config()
        actions = _build_default_actions_for_level('system', 'agent-x', config)
        timeout_actions = config['systemLevel']['timeoutActions']
        assert len(actions) == len(timeout_actions)
        assert [a.type for a in actions] == timeout_actions
        for a in actions:
            assert a.on_failure == OnFailurePolicy.CONTINUE.value

    def test_unknown_level_returns_empty(self):
        """未知 level 应返回空 list"""
        actions = _build_default_actions_for_level('unknown_level', 1, {})
        assert actions == []


@pytest.mark.django_db
class TestHandlerUsesActionChain:
    """现有 handle_* 函数应已委托给 ActionChain (验证 details.chain_result 存在)"""

    def test_handle_step_failure_returns_chain_result(self):
        """handle_step_failure 返回 details 应含 chain_result 字段 (RecoveryLog 内)"""
        result = handle_step_failure(execution_step_id=1, error_message='timeout')
        # 向后兼容: action 字段保持原 'retry' 语义 (而非 'step_chain')
        assert result['action'] == 'retry'
        assert 'details' in result
        # 验证 RecoveryLog 被写入, 且 details.chain_result 存在
        from scheduler.models import RecoveryLog
        log = RecoveryLog.objects.filter(recovery_level='step').first()
        assert log is not None
        assert 'chain_result' in log.details

    def test_handle_task_failure_below_threshold_no_log(self):
        """连续失败未达阈值时不应写 RecoveryLog (return continue)"""
        from scheduler.models import RecoveryLog
        before = RecoveryLog.objects.filter(recovery_level='task').count()
        result = handle_task_failure(task_execution_id=1, consecutive_failures=1)
        after = RecoveryLog.objects.filter(recovery_level='task').count()
        assert result['action'] == 'continue'
        assert before == after  # 无新 log

    def test_handle_task_failure_above_threshold_writes_log(self):
        """连续失败达阈值时应写 RecoveryLog (含 chain_result)"""
        from scheduler.models import RecoveryLog
        handle_task_failure(task_execution_id=1, consecutive_failures=5)
        log = RecoveryLog.objects.filter(
            recovery_level='task', trigger_event__contains='任务 1 连续失败 5 次'
        ).first()
        assert log is not None
        assert 'chain_result' in log.details
        chain = log.details['chain_result']
        assert chain['total'] >= 1
        assert chain['completed'] >= 1
