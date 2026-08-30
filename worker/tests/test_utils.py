"""工具类单元测试合并 (delay + timeout + safe_point + result + task_queue)

合并说明: 这些文件测试独立的工具类，共享简单 fixture，合并后减少文件碎片。
原文件: test_delay.py, test_timeout.py, test_safe_point.py, test_result.py, test_task_queue.py
"""

import logging
import threading
import time

import pytest
from core.delay import DelayManager
from core.result import AutoResult, fail_result, success_result
from core.safe_point import SafePointChecker, TaskCancelledError
from core.task_queue import TaskQueue
from core.timeout import TimeoutError, call_with_timeout, with_timeout

pytestmark = pytest.mark.unit

# ===========================================================================
# DelayManager tests (原 test_delay.py)
# ===========================================================================


class TestDelayInterrupt:
    """中断延迟测试"""

    def test_delay_interrupt(self):
        """验证中断延迟后 wait 返回 False"""
        dm = DelayManager()

        result_normal = dm.wait(0.01)
        assert result_normal is True

        def interrupt_after_delay():
            """延迟后中断"""
            time.sleep(0.01)
            dm.interrupt()

        t = threading.Thread(target=interrupt_after_delay)
        t.start()

        result_interrupted = dm.wait(10)
        t.join()
        assert result_interrupted is False

    def test_delay_zero(self):
        """验证零延迟直接返回 True"""
        dm = DelayManager()
        result = dm.wait(0)
        assert result is True

    def test_delay_negative(self):
        """验证负延迟直接返回 True"""
        dm = DelayManager()
        result = dm.wait(-1)
        assert result is True

    def test_delay_reset(self):
        """验证重置中断状态后可正常等待"""
        dm = DelayManager()
        dm.interrupt()
        dm.reset()
        result = dm.wait(0.01)
        assert result is True


# ===========================================================================
# Timeout tests (原 test_timeout.py)
# ===========================================================================


class TestCallWithTimeoutBaseException:
    """Verify non-Exception BaseException subclasses are re-raised."""

    def test_propagates_keyboard_interrupt(self):
        def raises_kbi():
            raise KeyboardInterrupt("ctrl-c")

        with pytest.raises(KeyboardInterrupt, match="ctrl-c"):
            call_with_timeout(raises_kbi, 1.0)

    def test_propagates_system_exit(self):
        def raises_system_exit():
            raise SystemExit(2)

        with pytest.raises(SystemExit):
            call_with_timeout(raises_system_exit, 1.0)


class TestCallWithTimeoutLogging:
    """Verify the timeout path logs a warning."""

    def test_logs_warning_on_timeout(self, caplog):
        def slow():
            time.sleep(2.0)
            return "done"

        with (
            caplog.at_level(logging.WARNING, logger="core.timeout"),
            pytest.raises(TimeoutError),
        ):
            call_with_timeout(slow, 0.1)

        assert any("timed out" in r.getMessage() for r in caplog.records)

    def test_thread_name_derived_from_func_name(self):
        """Thread name should follow ``timeout-<func_name>`` convention."""
        captured_names: list[str] = []

        def capture(self):
            import threading

            captured_names.append(threading.current_thread().name)
            return "ok"

        capture.__name__ = "capture_thread_name"
        call_with_timeout(capture, 1.0, capture)

        assert captured_names, "worker thread did not run"
        assert captured_names[0] == "timeout-capture_thread_name"


class TestCallWithTimeoutBoundary:
    """Verify boundary behaviour for tiny positive timeouts."""

    def test_tiny_positive_timeout_still_runs_fast_func(self):
        def quick():
            return 42

        result = call_with_timeout(quick, 0.001)
        assert result == 42

    def test_lambda_without_dunder_name_uses_call_fallback(self):
        result = call_with_timeout(lambda x: x + 1, 1.0, 10)
        assert result == 11


class TestWithTimeoutMetadata:
    """Verify ``functools.wraps`` preserves function metadata."""

    def test_preserves_function_name_and_doc(self):
        @with_timeout(timeout_sec=1.0)
        def compute(x):
            """Compute twice the input."""
            return x * 2

        assert compute.__name__ == "compute"
        assert compute.__doc__ == "Compute twice the input."

    def test_decorator_passes_through_args_and_kwargs(self):
        @with_timeout(timeout_sec=1.0)
        def greet(name, greeting="hi"):
            return f"{greeting}, {name}"

        assert greet("world") == "hi, world"
        assert greet("world", greeting="hey") == "hey, world"

    def test_decorator_propagates_exception(self):
        @with_timeout(timeout_sec=1.0)
        def raises():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            raises()


class TestTimeoutErrorType:
    """Verify ``TimeoutError`` is catchable as a normal exception."""

    def test_timeout_error_is_exception_subclass(self):
        assert issubclass(TimeoutError, Exception)

    def test_timeout_error_carries_message(self):
        try:
            raise TimeoutError("custom timeout msg")
        except TimeoutError as exc:
            assert "custom timeout msg" in str(exc)


# ===========================================================================
# SafePointChecker tests (原 test_safe_point.py)
# ===========================================================================


@pytest.fixture
def cancel_event():
    """Fresh threading.Event per test."""
    return threading.Event()


@pytest.fixture
def checker(cancel_event):
    """Fresh SafePointChecker wrapping the cancel_event fixture."""
    return SafePointChecker(cancel_event)


class TestSafePointCheckerInit:
    """Verify constructor stores the event and exposes it read-only."""

    def test_cancel_event_property_returns_original_event(self, cancel_event):
        sp = SafePointChecker(cancel_event)
        assert sp.cancel_event is cancel_event

    def test_check_returns_false_when_unset(self, checker):
        assert checker.check() is False


class TestSafePointCheckerCheck:
    """Verify check() reflects event state."""

    def test_check_returns_true_when_event_set(self, checker, cancel_event):
        cancel_event.set()
        assert checker.check() is True

    def test_check_returns_false_when_event_cleared(self, checker, cancel_event):
        cancel_event.set()
        cancel_event.clear()
        assert checker.check() is False


class TestSafePointCheckerWait:
    """Verify wait_for_safe_point semantics."""

    def test_wait_returns_true_immediately_when_already_set(self, checker, cancel_event):
        cancel_event.set()
        assert checker.wait_for_safe_point(timeout=1.0) is True

    def test_wait_returns_false_on_timeout(self, checker):
        result = checker.wait_for_safe_point(timeout=0.05)
        assert result is False

    def test_wait_returns_true_when_set_during_wait(self, checker, cancel_event):
        def setter():
            cancel_event.wait(timeout=0.01)
            cancel_event.set()

        threading.Thread(target=setter, daemon=True).start()

        result = checker.wait_for_safe_point(timeout=1.0)
        assert result is True


class TestSafePointCheckerRaise:
    """Verify raise_if_cancelled behaviour."""

    def test_raises_when_event_set_default_message(self, checker, cancel_event):
        cancel_event.set()
        with pytest.raises(TaskCancelledError, match="Task cancelled at safe point"):
            checker.raise_if_cancelled()

    def test_raises_when_event_set_custom_message(self, checker, cancel_event):
        cancel_event.set()
        with pytest.raises(TaskCancelledError, match="custom reason"):
            checker.raise_if_cancelled(message="custom reason")

    def test_does_not_raise_when_event_unset(self, checker):
        assert checker.raise_if_cancelled() is None

    def test_raises_after_set_then_no_raise_after_reset(self, checker, cancel_event):
        cancel_event.set()
        with pytest.raises(TaskCancelledError):
            checker.raise_if_cancelled()
        checker.reset()
        assert checker.raise_if_cancelled() is None


class TestSafePointCheckerReset:
    """Verify reset clears the underlying event."""

    def test_reset_clears_set_event(self, checker, cancel_event):
        cancel_event.set()
        assert checker.check() is True
        checker.reset()
        assert checker.check() is False
        assert cancel_event.is_set() is False

    def test_reset_on_unset_event_is_noop(self, checker, cancel_event):
        checker.reset()
        assert cancel_event.is_set() is False
        assert checker.check() is False


class TestTaskCancelledErrorType:
    """Verify TaskCancelledError is a catchable exception."""

    def test_is_exception_subclass(self):
        assert issubclass(TaskCancelledError, Exception)

    def test_can_be_caught_as_exception(self):
        try:
            raise TaskCancelledError("boom")
        except Exception as exc:
            assert isinstance(exc, TaskCancelledError)
            assert "boom" in str(exc)


# ===========================================================================
# AutoResult tests (原 test_result.py)
# ===========================================================================


class TestSuccessResult:
    """成功结果工厂方法测试"""

    def test_success_result(self):
        """验证 success_result 创建成功结果"""
        result = success_result(data={"key": "value"}, elapsed_time=1.5, retry_count=2)
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.elapsed_time == 1.5
        assert result.retry_count == 2
        assert result.error_msg == ""
        assert result.is_interrupted is False

    def test_success_result_bool(self):
        """验证成功结果的布尔转换为 True"""
        result = success_result()
        assert bool(result) is True

    def test_success_result_failed_property(self):
        """验证成功结果的 failed 属性为 False"""
        result = success_result()
        assert result.failed is False


class TestFailResult:
    """失败结果工厂方法测试"""

    def test_fail_result(self):
        """验证 fail_result 创建失败结果"""
        result = fail_result(
            error_msg="操作失败",
            data={"partial": True},
            elapsed_time=0.5,
            is_interrupted=True,
            retry_count=3,
        )
        assert result.success is False
        assert result.error_msg == "操作失败"
        assert result.data == {"partial": True}
        assert result.elapsed_time == 0.5
        assert result.is_interrupted is True
        assert result.retry_count == 3

    def test_fail_result_bool(self):
        """验证失败结果的布尔转换为 False"""
        result = fail_result(error_msg="error")
        assert bool(result) is False

    def test_fail_result_failed_property(self):
        """验证失败结果的 failed 属性为 True"""
        result = fail_result(error_msg="error")
        assert result.failed is True

    def test_fail_result_with_error_code(self):
        """fail_result 应支持 error_code 参数用于诊断分类"""
        result = fail_result(error_msg="模板匹配失败", error_code="NO_MATCH")
        assert result.error_code == "NO_MATCH"
        assert result.failed is True


class TestAutoResultNodeMetadata:
    """AutoResult 节点元数据字段测试"""

    def test_auto_result_has_node_metadata_fields(self):
        """AutoResult 应该携带 node_id/node_type/error_code 用于诊断。"""
        result = AutoResult(
            success=False,
            error_msg="模板匹配失败",
            error_code="NO_MATCH",
            node_id="step_3",
            node_type="template_match",
        )
        assert result.node_id == "step_3"
        assert result.node_type == "template_match"
        assert result.error_code == "NO_MATCH"
        assert result.failed is True

    def test_auto_result_defaults_for_new_fields(self):
        """新字段应该有默认空字符串，向后兼容。"""
        result = AutoResult(success=True)
        assert result.node_id == ""
        assert result.node_type == ""
        assert result.error_code == ""

    def test_auto_result_backward_compatible_with_positional_args(self):
        """已有调用代码使用位置参数应继续工作。"""
        result = AutoResult(True, {"k": 1}, "ok")
        assert result.success is True
        assert result.data == {"k": 1}
        assert result.error_msg == "ok"
        assert result.node_id == ""
        assert result.error_code == ""


# ===========================================================================
# TaskQueue tests (原 test_task_queue.py)
# ===========================================================================


class TestEnqueueDequeue:
    """入队出队测试"""

    def test_enqueue_dequeue(self):
        """验证任务入队后按 FIFO 顺序出队"""
        queue = TaskQueue()
        queue.enqueue({"name": "task1"})
        queue.enqueue({"name": "task2"})
        queue.enqueue({"name": "task3"})

        assert queue.dequeue() == {"name": "task1"}
        assert queue.dequeue() == {"name": "task2"}
        assert queue.dequeue() == {"name": "task3"}


class TestPriority:
    """优先级排序测试"""

    def test_priority(self):
        """验证优先级数字越小越先出队"""
        queue = TaskQueue()
        queue.enqueue({"name": "low"}, priority=10)
        queue.enqueue({"name": "high"}, priority=0)
        queue.enqueue({"name": "medium"}, priority=5)

        assert queue.dequeue() == {"name": "high"}
        assert queue.dequeue() == {"name": "medium"}
        assert queue.dequeue() == {"name": "low"}

    def test_same_priority_fifo(self):
        """验证相同优先级按入队顺序出队"""
        queue = TaskQueue()
        queue.enqueue({"name": "first"}, priority=0)
        queue.enqueue({"name": "second"}, priority=0)
        queue.enqueue({"name": "third"}, priority=0)

        assert queue.dequeue() == {"name": "first"}
        assert queue.dequeue() == {"name": "second"}
        assert queue.dequeue() == {"name": "third"}


class TestEmptyQueue:
    """空队列行为测试"""

    def test_empty_queue(self):
        """验证空队列出队返回 None"""
        queue = TaskQueue()
        assert queue.is_empty() is True
        assert queue.size() == 0
        assert queue.dequeue() is None
        assert queue.peek() is None

    def test_clear_queue(self):
        """验证清空队列后为空"""
        queue = TaskQueue()
        queue.enqueue({"name": "task1"})
        queue.enqueue({"name": "task2"})
        queue.clear()
        assert queue.is_empty() is True
        assert queue.size() == 0
