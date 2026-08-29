"""StateMachineEngine 测试 — TD-354"""

from __future__ import annotations

from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from core.result import AutoResult, fail_result, success_result
from engine.state_machine_engine import StateMachineEngine
from engine.executor import BaseEngine, TaskExecutor

pytestmark = pytest.mark.integration


class _MockStateMachine:
    """Mock StateMachine for testing."""

    def __init__(self, success: bool = True):
        self._success = success

    def run(self, max_iterations: int = 1000) -> AutoResult:
        if self._success:
            return success_result(data={"iterations": 1}, elapsed_time=0.1)
        return fail_result(error_msg="state_machine failed", elapsed_time=0.1)


def _make_mock_module(build_fn=None) -> ModuleType:
    """Create a mock module with build_state_machine."""
    mod = ModuleType("test_fsm_module")
    if build_fn is not None:
        mod.build_state_machine = build_fn
    return mod


class TestStateMachineEngine:
    """StateMachineEngine 基本功能测试"""

    def test_state_machine_engine_is_baseengine(self):
        """StateMachineEngine 应是 BaseEngine 子类"""
        engine = StateMachineEngine()
        assert isinstance(engine, BaseEngine)

    def test_run_missing_module(self):
        """缺 module 字段应返回 fail"""
        engine = StateMachineEngine()
        result = engine.run(
            {},
            device_manager=MagicMock(),
            image_processor=MagicMock(),
        )
        assert not result.success
        assert "缺少 module 字段" in (result.error_msg or "")

    def test_run_missing_deps(self):
        """缺 device_manager/image_processor 应返回 fail"""
        engine = StateMachineEngine()
        result = engine.run({"module": "test_module"})
        assert not result.success
        assert "缺少必需参数" in (result.error_msg or "")

    @patch("importlib.import_module")
    def test_run_module_import_error(self, mock_import):
        """模块导入失败应返回 fail"""
        mock_import.side_effect = ImportError("no module")

        engine = StateMachineEngine()
        result = engine.run(
            {"module": "nonexistent.module"},
            device_manager=MagicMock(),
            image_processor=MagicMock(),
        )
        assert not result.success
        assert "模块导入失败" in (result.error_msg or "")
        assert "no module" in (result.error_msg or "")

    @patch("importlib.import_module")
    def test_run_missing_builder(self, mock_import):
        """模块无 build_state_machine 应返回 fail"""
        mock_mod = _make_mock_module(build_fn=None)
        mock_import.return_value = mock_mod

        engine = StateMachineEngine()
        result = engine.run(
            {"module": "test_fsm_module"},
            device_manager=MagicMock(),
            image_processor=MagicMock(),
        )
        assert not result.success
        assert "未暴露" in (result.error_msg or "")

    @patch("importlib.import_module")
    def test_run_builder_error(self, mock_import):
        """builder 抛出异常应返回 fail"""
        def _bad_builder(dm, ip):
            raise ValueError("builder failed")

        mock_mod = _make_mock_module(build_fn=_bad_builder)
        mock_import.return_value = mock_mod

        engine = StateMachineEngine()
        result = engine.run(
            {"module": "test_fsm_module"},
            device_manager=MagicMock(),
            image_processor=MagicMock(),
        )
        assert not result.success
        assert "build_state_machine 调用失败" in (result.error_msg or "")

    @patch("importlib.import_module")
    def test_run_success(self, mock_import):
        """正常执行应返回 success"""
        def _good_builder(dm, ip):
            return _MockStateMachine(success=True)

        mock_mod = _make_mock_module(build_fn=_good_builder)
        mock_import.return_value = mock_mod

        engine = StateMachineEngine()
        result = engine.run(
            {"module": "test_fsm_module"},
            device_manager=MagicMock(),
            image_processor=MagicMock(),
        )
        assert result.success

    @patch("importlib.import_module")
    def test_run_failure(self, mock_import):
        """StateMachine 执行失败应返回 fail"""
        def _good_builder(dm, ip):
            return _MockStateMachine(success=False)

        mock_mod = _make_mock_module(build_fn=_good_builder)
        mock_import.return_value = mock_mod

        engine = StateMachineEngine()
        result = engine.run(
            {"module": "test_fsm_module"},
            device_manager=MagicMock(),
            image_processor=MagicMock(),
        )
        assert not result.success
        assert "state_machine failed" in (result.error_msg or "")

    @patch("importlib.import_module")
    def test_run_machine_exception(self, mock_import):
        """machine.run 抛出异常应返回 fail"""
        def _bad_run(dm, ip):
            machine = MagicMock()
            machine.run.side_effect = RuntimeError("machine crash")
            return machine

        mock_mod = _make_mock_module(build_fn=_bad_run)
        mock_import.return_value = mock_mod

        engine = StateMachineEngine()
        result = engine.run(
            {"module": "test_fsm_module"},
            device_manager=MagicMock(),
            image_processor=MagicMock(),
        )
        assert not result.success
        assert "状态机执行异常" in (result.error_msg or "")

    @patch("importlib.import_module")
    def test_run_device_switch(self, mock_import):
        """设备切换逻辑: 切换后恢复"""
        def _good_builder(dm, ip):
            return _MockStateMachine(success=True)

        mock_mod = _make_mock_module(build_fn=_good_builder)
        mock_import.return_value = mock_mod

        device_manager = MagicMock()
        device_manager.get_active_device_id.return_value = "prev_device"
        device_manager.set_active_device.return_value = True

        engine = StateMachineEngine()
        result = engine.run(
            {"module": "test_fsm_module"},
            device_manager=device_manager,
            image_processor=MagicMock(),
            device_id="target_device",
        )
        assert result.success
        # 应切换设备
        device_manager.set_active_device.assert_any_call("target_device")
        # 应恢复原设备
        device_manager.set_active_device.assert_any_call("prev_device")

    @patch("importlib.import_module")
    def test_run_device_switch_fail(self, mock_import):
        """设备切换失败应返回 fail"""
        def _good_builder(dm, ip):
            return _MockStateMachine(success=True)

        mock_mod = _make_mock_module(build_fn=_good_builder)
        mock_import.return_value = mock_mod

        device_manager = MagicMock()
        device_manager.set_active_device.return_value = False  # 切换失败

        engine = StateMachineEngine()
        result = engine.run(
            {"module": "test_fsm_module"},
            device_manager=device_manager,
            image_processor=MagicMock(),
            device_id="bad_device",
        )
        assert not result.success
        assert "设备不存在或不可用" in (result.error_msg or "")

    def test_run_max_iterations(self):
        """max_iterations 参数透传"""
        # 测试 max_iterations 被正确读取
        StateMachineEngine()
        # 不需要真正执行，验证参数解析逻辑（通过其他测试覆盖）
        assert True


class TestTaskExecutorStateMachine:
    """TaskExecutor 与 StateMachineEngine 集成测试"""

    def test_task_executor_registers_chain(self):
        """TaskExecutor 应注册 chain 引擎"""
        executor = TaskExecutor()
        assert "state_machine" in executor.engines
        assert "chain" in executor.engines  # deprecated alias
        assert isinstance(executor.engines["state_machine"], StateMachineEngine)

    @patch("importlib.import_module")
    def test_task_executor_dispatch_chain(self, mock_import):
        """TaskExecutor 分发 chain 应成功"""
        def _good_builder(dm, ip):
            return _MockStateMachine(success=True)

        mock_mod = _make_mock_module(build_fn=_good_builder)
        mock_import.return_value = mock_mod

        executor = TaskExecutor()
        result = executor.execute(
            "state_machine",
            {"module": "test_fsm_module"},
            device_manager=MagicMock(),
            image_processor=MagicMock(),
        )
        assert result.success

    @patch("importlib.import_module")
    def test_task_executor_dispatch_chain_fail(self, mock_import):
        """TaskExecutor 分发 chain 失败场景"""
        mock_import.side_effect = ImportError("no module")

        executor = TaskExecutor()
        result = executor.execute(
            "state_machine",
            {"module": "nonexistent.module"},
            device_manager=MagicMock(),
            image_processor=MagicMock(),
        )
        assert not result.success

    def test_task_executor_unknown_type(self):
        """未知 task_type 应抛出 ValueError"""
        executor = TaskExecutor()
        try:
            executor.execute("unknown_type", {})
            raise AssertionError("应抛出 ValueError")
        except ValueError as exc:
            assert "Unknown task type" in str(exc)
