"""TaskOrchestrator unit tests — covers execute_task / state machine /
cancel-pause-resume / retry-fallback / execute_pipeline paths.

Mocks DeviceManager, ImageProcessor, and PipelineEngine so no real device
or Win32 API is touched. Validates state transitions, callback dispatch,
error propagation, and device switching semantics.
"""

from unittest.mock import MagicMock, patch

import pytest
from core.config import AgentConfig, RetryConfig
from core.orchestrator import TaskOrchestrator, TaskState
from core.result import fail_result, success_result
from engine.context import PipelineState

pytestmark = pytest.mark.unit

# ============================================================
# Fixtures and helpers
# ============================================================


def _make_device_manager(active_device=None, active_device_id="dev1"):
    """Build a MagicMock DeviceManager with sane defaults.

    By default returns ``active_device`` from get_active_device() and
    ``active_device_id`` from get_active_device_id(); set_active_device
    returns True. Tests override return values as needed.
    """
    dm = MagicMock()
    dm.get_active_device.return_value = active_device
    dm.get_active_device_id.return_value = active_device_id
    dm.set_active_device.return_value = True
    return dm


def _make_image_processor():
    """Build a MagicMock ImageProcessor with no-op find_* methods."""
    ip = MagicMock()
    ip.find_template.return_value = None
    ip.find_color.return_value = None
    return ip


def _make_config():
    """Build an AgentConfig with fast retry settings for test speed."""
    cfg = AgentConfig()
    cfg.retry_config = RetryConfig(
        max_retries=2, base_delay=0.001, max_delay=0.005, backoff_factor=1.0
    )
    return cfg


@pytest.fixture
def orchestrator():
    """Build a TaskOrchestrator with mocked dependencies."""
    device = MagicMock()
    device.device_id = "dev1"
    device.click.return_value = None
    device.swipe.return_value = None
    device.key_press.return_value = None
    device.text_input.return_value = None
    device.capture_screen.return_value = MagicMock(name="frame")
    # N191 §10.7 P0-2 (架构层归一化, 2026-07-27): MagicMock 默认任意属性存在,
    # 导致 orchestrator 的 `hasattr(device, "get_resolution")` 返回 True 走 ADB
    # 回退路径。让 get_resolution 返回合理 tuple (1920x1080), 使 ADB 路径成功
    # 构造 ADBCoordinateTransformer, 避免 CoordTransformerError fail fast。
    # test_metadata_base_res_triggers_transformer_build 仍能验证 Windows
    # build_transformer 被尝试调用 (在 try 块内)。
    #
    # N191 §10.11 D5 修正 (2026-07-27): orchestrator 现在用
    # `getattr(device, "hwnd", None) is not None` 判断 Windows 设备。
    # MagicMock 默认 hwnd 是 MagicMock 实例 (truthy) 会误判 Windows → fail fast。
    # 显式设 device.hwnd = None, 让 is_windows_device=False, 走 ADB 路径。
    device.get_resolution.return_value = (1920, 1080)
    device.hwnd = None  # 非 Windows 设备

    dm = _make_device_manager(active_device=device, active_device_id="dev1")
    ip = _make_image_processor()
    cfg = _make_config()
    orch = TaskOrchestrator(
        device_manager=dm, image_processor=ip, config=cfg
    )
    return orch


# ============================================================
# execute_task — pipeline 委托（spec-2026-07-27 阶段 4）
# ============================================================


class TestExecuteTaskPipelineDelegation:
    """spec-2026-07-27-execution-path-unification 阶段 4:
    execute_task(chain) 已废弃，委托 execute_pipeline。用 pipeline schema 验证。
    """

    def test_single_node_pipeline_delegates_to_execute_pipeline(self, orchestrator):
        """单节点 pipeline JSON 通过 execute_task 委托给 execute_pipeline 执行。"""
        task = {"nodes": [{"id": "n1", "type": "click", "config": {"x": 10, "y": 20}}]}
        result = orchestrator.execute_task(task)

        assert result.success is True
        assert orchestrator.state == TaskState.COMPLETED

    def test_multi_node_linear_pipeline_delegates(self, orchestrator):
        """3 节点线性 pipeline（无 edges）按顺序执行。"""
        task = {
            "nodes": [
                {"id": "n1", "type": "click", "config": {"x": 1, "y": 1}},
                {"id": "n2", "type": "wait", "config": {"seconds": 0.001}},
                {"id": "n3", "type": "click", "config": {"x": 2, "y": 2}},
            ]
        }
        result = orchestrator.execute_task(task)

        assert result.success is True
        assert len(result.step_results) == 3

    def test_empty_nodes_returns_fail(self, orchestrator):
        """空 nodes 列表 → pipeline 校验失败。"""
        result = orchestrator.execute_task({"nodes": []})

        assert result.success is False
        # pipeline 校验失败的错误信息（不再是 chain 的"为空"）
        assert result.error_msg

    def test_continue_on_error_node_keeps_pipeline_running(self, orchestrator):
        """节点 continue_on_error=True → pipeline 继续执行下一个节点。"""
        # 用一个始终失败的节点 + continue_on_error，后面跟一个成功节点
        task = {
            "nodes": [
                # 第一个节点：未知 type 会失败，但 continue_on_error=True
                {"id": "fail1", "type": "click", "config": {},
                 "continue_on_error": True},
                {"id": "ok1", "type": "click", "config": {"x": 1, "y": 1}},
            ]
        }
        # 让第一个节点的 click 失败：device.click 抛异常
        # 但 orchestrator fixture 的 device.click 默认返回 None（成功）
        # 所以这里我们用一个未知 action 让节点工厂抛 ValueError
        # 实际上 click 节点会成功，所以这个测试验证的是：
        # 即使节点失败，continue_on_error 让 pipeline 不终止
        # 改用更直接的方式：让 device.click 第一次抛异常
        original_click = orchestrator._device_manager.get_active_device().click

        def flaky_click(x, y):
            if not hasattr(flaky_click, "calls"):
                flaky_click.calls = 0
            flaky_click.calls += 1
            if flaky_click.calls == 1:
                raise RuntimeError("intentional fail")
            return None

        orchestrator._device_manager.get_active_device().click = flaky_click
        try:
            result = orchestrator.execute_task(task)
            # 第一个节点失败但 continue_on_error=True，第二个节点成功 → pipeline 整体成功
            assert result.success is True
        finally:
            orchestrator._device_manager.get_active_device().click = original_click

    def test_device_id_passed_to_execute_pipeline(self, orchestrator):
        """execute_task(device_id=...) 透传给 execute_pipeline。"""
        task = {"nodes": [{"id": "n1", "type": "click", "config": {"x": 1, "y": 1}}]}
        # dev2 在 device_manager 中存在（MagicMock 默认 get_device 返回 MagicMock）
        result = orchestrator.execute_task(task, device_id="dev2")

        assert result.success is True
        # execute_pipeline 内部调用 get_device(device_id) 解析设备
        orchestrator._device_manager.get_device.assert_called_with("dev2")


# ============================================================
# execute_task — state_machine mode
# ============================================================


class TestExecuteTaskStateMachine:
    """execute_task with execution_mode='state_machine'."""

    def test_state_machine_without_module_delegates_to_pipeline(self, orchestrator):
        """state_machine mode without 'module' key → 委托 execute_pipeline (spec-2026-07-27 阶段 4).

        旧行为是回退到 chain 执行；归一化后 state_machine 缺 module 时
        按 pipeline 处理（task_definition 应是 pipeline JSON）。
        """
        task = {"nodes": [{"id": "n1", "type": "click", "config": {"x": 1, "y": 1}}]}
        result = orchestrator.execute_task(task, execution_mode="state_machine")

        assert result.success is True
        assert orchestrator.state == TaskState.COMPLETED

    def test_state_machine_module_import_fails(self, orchestrator):
        """ImportError on module path returns a descriptive fail result."""
        task = {"module": "nonexistent.module.path"}
        result = orchestrator.execute_task(task, execution_mode="state_machine")

        assert result.success is False
        assert "模块导入失败" in result.error_msg
        assert orchestrator.state == TaskState.FAILED

    def test_state_machine_missing_builder_returns_fail(self, orchestrator):
        """Module loads but lacks build_state_machine → fail."""
        fake_module = MagicMock()
        # No build_state_machine attribute → getattr returns MagicMock that
        # is not callable. Force it to None to hit the missing-builder path.
        fake_module.build_state_machine = None
        with patch("importlib.import_module", return_value=fake_module):
            task = {"module": "fake.module"}
            result = orchestrator.execute_task(task, execution_mode="state_machine")

        assert result.success is False
        assert "build_state_machine" in result.error_msg

    def test_state_machine_builder_raises_returns_fail(self, orchestrator):
        """Builder callable raising returns fail with descriptive message."""
        fake_module = MagicMock()
        fake_module.build_state_machine.side_effect = RuntimeError("boom")
        with patch("importlib.import_module", return_value=fake_module):
            task = {"module": "fake.module"}
            result = orchestrator.execute_task(task, execution_mode="state_machine")

        assert result.success is False
        assert "build_state_machine 调用失败" in result.error_msg

    def test_state_machine_run_raises_returns_fail(self, orchestrator):
        """machine.run() raising returns fail with descriptive message."""
        machine = MagicMock()
        machine.run.side_effect = RuntimeError("fsm error")
        fake_module = MagicMock()
        fake_module.build_state_machine.return_value = machine
        with patch("importlib.import_module", return_value=fake_module):
            task = {"module": "fake.module"}
            result = orchestrator.execute_task(task, execution_mode="state_machine")

        assert result.success is False
        assert "状态机执行异常" in result.error_msg

    def test_state_machine_success(self, orchestrator):
        """machine.run() returning success → COMPLETED + on_complete fired."""
        completed = []
        orchestrator.set_callbacks(on_complete=lambda r: completed.append(r))

        machine = MagicMock()
        machine.run.return_value = success_result(data={"final": "state"})
        fake_module = MagicMock()
        fake_module.build_state_machine.return_value = machine
        with patch("importlib.import_module", return_value=fake_module):
            task = {"module": "fake.module", "max_iterations": 50}
            result = orchestrator.execute_task(task, execution_mode="state_machine")

        assert result.success is True
        assert orchestrator.state == TaskState.COMPLETED
        machine.run.assert_called_once_with(max_iterations=50)
        assert len(completed) == 1


# ============================================================
# cancel / pause / resume
# ============================================================


class TestCancelPauseResume:
    """cancel_task / pause_task / resume_task state transitions."""

    def test_cancel_task_sets_cancelled_state(self, orchestrator):
        orchestrator._state = TaskState.RUNNING
        orchestrator.cancel_task()
        assert orchestrator.state == TaskState.CANCELLED

    def test_pause_task_from_running(self, orchestrator):
        orchestrator._state = TaskState.RUNNING
        orchestrator.pause_task()
        assert orchestrator.state == TaskState.PAUSED

    def test_pause_task_from_pending_is_noop(self, orchestrator):
        """pause_task only fires from RUNNING; PENDING stays PENDING."""
        orchestrator._state = TaskState.PENDING
        orchestrator.pause_task()
        assert orchestrator.state == TaskState.PENDING

    def test_resume_task_from_paused(self, orchestrator):
        orchestrator._state = TaskState.PAUSED
        orchestrator.resume_task()
        assert orchestrator.state == TaskState.RUNNING

    def test_resume_task_from_running_is_noop(self, orchestrator):
        """resume_task only fires from PAUSED; RUNNING stays RUNNING."""
        orchestrator._state = TaskState.RUNNING
        orchestrator.resume_task()
        assert orchestrator.state == TaskState.RUNNING


# ============================================================
# _execute_step / _run_action / retry / fallback
# ============================================================
# spec-2026-07-27-execution-path-unification 阶段 6:
# TestRunAction / TestExecuteStep 已删除 — _run_action / _execute_step /
# _handle_retry / _handle_fallback 等 chain 死代码方法已从 orchestrator.py
# 移除。等价测试覆盖在 agent/tests/test_engine_node_control_flow.py
# (PipelineEngine 节点控制流: pre_verify/retry/fallback/continue_on_error)。


# ============================================================
# _run_verify — type dispatch
# ============================================================


class TestRunVerify:
    """_run_verify dispatches by 'type' and returns AutoResult."""

    def test_unknown_verify_type_returns_fail(self, orchestrator):
        result = orchestrator._run_verify({"type": "magic"})
        assert result.success is False
        assert "未知验证类型" in result.error_msg

    def test_template_match_success(self, orchestrator):
        orchestrator._image_processor.find_template.return_value = {"x": 10, "y": 20}
        result = orchestrator._run_verify({"type": "template", "template": "t.png"})
        assert result.success is True
        assert result.data == {"x": 10, "y": 20}

    def test_template_match_failure(self, orchestrator):
        orchestrator._image_processor.find_template.return_value = None
        result = orchestrator._run_verify({"type": "template", "template": "t.png"})
        assert result.success is False
        assert "模板未匹配" in result.error_msg

    def test_color_match_success(self, orchestrator):
        orchestrator._image_processor.find_color.return_value = {"x": 5, "y": 5}
        result = orchestrator._run_verify({"type": "color", "color": [255, 0, 0]})
        assert result.success is True

    def test_color_match_failure(self, orchestrator):
        orchestrator._image_processor.find_color.return_value = None
        result = orchestrator._run_verify({"type": "color", "color": [255, 0, 0]})
        assert result.success is False
        assert "颜色未匹配" in result.error_msg

    def test_verify_exist_template_present(self, orchestrator):
        """'exist' type with template element found → success."""
        orchestrator._image_processor.find_template.return_value = {"x": 1, "y": 1}
        result = orchestrator._run_verify(
            {"type": "exist", "element": "template", "template": "t.png"}
        )
        assert result.success is True

    def test_verify_disappear_template_absent(self, orchestrator):
        """'disappear' type with template not found → success."""
        orchestrator._image_processor.find_template.return_value = None
        result = orchestrator._run_verify(
            {"type": "disappear", "element": "template", "template": "t.png"}
        )
        assert result.success is True

    def test_verify_disappear_but_present_returns_fail(self, orchestrator):
        """'disappear' type but element still present → fail."""
        orchestrator._image_processor.find_template.return_value = {"x": 1, "y": 1}
        result = orchestrator._run_verify(
            {"type": "disappear", "element": "template", "template": "t.png"}
        )
        assert result.success is False
        assert "消失" in result.error_msg

    def test_verify_exist_unknown_element(self, orchestrator):
        """'exist' type with unknown element value → fail."""
        result = orchestrator._run_verify(
            {"type": "exist", "element": "audio", "template": "t.png"}
        )
        assert result.success is False
        assert "未知 element 类型" in result.error_msg

    def test_verify_text_missing_text_param(self, orchestrator):
        """'text' verify without 'text' key → fail early (no OCR call)."""
        result = orchestrator._run_verify({"type": "text"})
        assert result.success is False
        assert "'text' 参数" in result.error_msg

    def test_verify_custom_missing_module(self, orchestrator):
        """'custom_verify' without module/function → fail."""
        result = orchestrator._run_verify({"type": "custom_verify"})
        assert result.success is False
        assert "module" in result.error_msg

    def test_verify_custom_load_failure(self, orchestrator):
        """custom_verify with unimportable module → fail with load error."""
        with patch("importlib.import_module", side_effect=ImportError("nope")):
            result = orchestrator._run_verify(
                {"type": "custom_verify", "module": "x", "function": "y"}
            )
        assert result.success is False
        assert "custom_verify 加载失败" in result.error_msg


# ============================================================
# execute_pipeline — device resolution, callbacks, state mapping
# ============================================================


def _build_pipeline_result(success=True, state_str="completed"):
    """Build a fake PipelineResult-like object for mocked engine.execute()."""
    fake = MagicMock()
    fake.success = success
    fake.state = PipelineState(state_str)
    fake.data = {"steps": []}
    fake.error_msg = "" if success else "pipeline failed"
    fake.elapsed_time = 0.01
    fake.step_results = []
    fake.structured_log_path = ""
    return fake


class TestExecutePipeline:
    """execute_pipeline device resolution + engine wiring + state mapping."""

    def test_device_id_not_found_returns_fail(self, orchestrator):
        orchestrator._device_manager.get_device.return_value = None
        result = orchestrator.execute_pipeline({"nodes": []}, device_id="missing")

        assert result.success is False
        assert "device_id=missing" in result.error_msg
        assert orchestrator.state == TaskState.FAILED

    def test_no_active_device_returns_fail(self, orchestrator):
        orchestrator._device_manager.get_active_device.return_value = None
        result = orchestrator.execute_pipeline({"nodes": []})

        assert result.success is False
        assert "无可用设备" in result.error_msg
        assert orchestrator.state == TaskState.FAILED

    def test_pipeline_load_failure_returns_fail(self, orchestrator):
        """engine.load() raising → fail with 'Pipeline 加载失败'."""
        with patch("engine.pipeline_engine.PipelineEngine") as engine_cls:
            engine_inst = engine_cls.return_value
            engine_inst.load.side_effect = RuntimeError("bad json")
            result = orchestrator.execute_pipeline({"nodes": []})

        assert result.success is False
        assert "Pipeline 加载失败" in result.error_msg
        assert orchestrator.state == TaskState.FAILED

    def test_pipeline_success_maps_to_completed(self, orchestrator):
        completed = []
        orchestrator.set_callbacks(on_complete=lambda r: completed.append(r))

        with patch("engine.pipeline_engine.PipelineEngine") as engine_cls:
            engine_inst = engine_cls.return_value
            engine_inst.execute.return_value = _build_pipeline_result(
                success=True, state_str="completed"
            )
            result = orchestrator.execute_pipeline({"nodes": []})

        assert result.success is True
        assert orchestrator.state == TaskState.COMPLETED
        assert len(completed) == 1
        # set_callbacks wired with on_step_complete and on_error
        engine_inst.set_callbacks.assert_called_once()

    def test_pipeline_failure_maps_to_failed_and_fires_on_failed(self, orchestrator):
        failed = []
        orchestrator.set_callbacks(on_failed=lambda r: failed.append(r))

        with patch("engine.pipeline_engine.PipelineEngine") as engine_cls:
            engine_inst = engine_cls.return_value
            engine_inst.execute.return_value = _build_pipeline_result(
                success=False, state_str="failed"
            )
            result = orchestrator.execute_pipeline({"nodes": []})

        assert result.success is False
        assert orchestrator.state == TaskState.FAILED
        assert len(failed) == 1

    def test_pipeline_cancelled_maps_to_cancelled(self, orchestrator):
        with patch("engine.pipeline_engine.PipelineEngine") as engine_cls:
            engine_inst = engine_cls.return_value
            engine_inst.execute.return_value = _build_pipeline_result(
                success=False, state_str="cancelled"
            )
            result = orchestrator.execute_pipeline({"nodes": []})

        assert result.success is False
        assert orchestrator.state == TaskState.CANCELLED

    def test_on_step_progress_callback_wired(self, orchestrator):
        """on_step_progress callback is invoked via engine's on_step_complete."""
        progress_calls = []

        def on_progress(node_id, res, step_index):
            progress_calls.append((node_id, step_index))

        with patch("engine.pipeline_engine.PipelineEngine") as engine_cls:
            engine_inst = engine_cls.return_value
            engine_inst.execute.return_value = _build_pipeline_result(
                success=True, state_str="completed"
            )
            orchestrator.execute_pipeline({"nodes": []}, on_step_progress=on_progress)

            # Retrieve the on_step_complete callback wired into the engine
            # and invoke it to simulate the engine reporting a step.
            wired = engine_inst.set_callbacks.call_args.kwargs
            wired["on_step_complete"]("node_1", success_result(data={"ok": True}))

        assert progress_calls == [("node_1", 0)]

    def test_on_step_progress_exception_does_not_crash(self, orchestrator):
        """A raising on_step_progress callback must not crash the pipeline."""
        def bad_callback(node_id, res, step_index):
            raise RuntimeError("callback bug")

        with patch("engine.pipeline_engine.PipelineEngine") as engine_cls:
            engine_inst = engine_cls.return_value
            engine_inst.execute.return_value = _build_pipeline_result(
                success=True, state_str="completed"
            )
            orchestrator.execute_pipeline({"nodes": []}, on_step_progress=bad_callback)

            wired = engine_inst.set_callbacks.call_args.kwargs
            # Should not raise — exception is swallowed inside _on_step_complete.
            wired["on_step_complete"]("n1", success_result())

    def test_metadata_base_res_triggers_transformer_build(self, orchestrator):
        """Pipeline metadata with original_base_res attempts to build a transformer."""
        with patch("engine.pipeline_engine.PipelineEngine"), \
             patch("platforms.windows.display_builder.build_transformer") as bt:
            bt.return_value = None  # transformer build returns None → no display_context
            orchestrator.execute_pipeline(
                {"nodes": [], "metadata": {"original_base_res": [1920, 1080]}}
            )
            bt.assert_called_once()


# ============================================================
# _llm_diagnose_pipeline_failure
# ============================================================


class TestLlmDiagnose:
    """_llm_diagnose_pipeline_failure non-blocking error handling."""

    def test_diagnose_failure_exception_returns_none(self, orchestrator):
        """If llm_client.diagnose_failure raises, method returns None."""
        llm_client = MagicMock()
        llm_client.diagnose_failure.side_effect = RuntimeError("network down")
        result_obj = fail_result(error_msg="pipeline failed")
        result_obj.step_results = []

        diagnosis = orchestrator._llm_diagnose_pipeline_failure(
            llm_client=llm_client,
            result=result_obj,
            pipeline_json={"metadata": {}},
            structured_log_path="",
        )
        assert diagnosis is None

    def test_diagnose_returns_error_only_dict_returns_none(self, orchestrator):
        """If diagnose_failure returns {'error': ...} without 'diagnosis', return None."""
        llm_client = MagicMock()
        llm_client.diagnose_failure.return_value = {"error": "llm unavailable"}
        result_obj = fail_result(error_msg="pipeline failed")
        result_obj.step_results = []

        diagnosis = orchestrator._llm_diagnose_pipeline_failure(
            llm_client=llm_client,
            result=result_obj,
            pipeline_json={"metadata": {}},
            structured_log_path="",
        )
        assert diagnosis is None

    def test_diagnose_returns_valid_dict_passes_through(self, orchestrator):
        """A valid diagnosis dict is returned to the caller unchanged."""
        llm_client = MagicMock()
        llm_client.diagnose_failure.return_value = {
            "diagnosis": "template not found",
            "suggested_fix": "re-capture template",
            "raw_reply": "...",
            "model": "gpt-4",
        }
        result_obj = fail_result(error_msg="pipeline failed")
        result_obj.step_results = []

        diagnosis = orchestrator._llm_diagnose_pipeline_failure(
            llm_client=llm_client,
            result=result_obj,
            pipeline_json={"metadata": {}},
            structured_log_path="",
        )
        assert diagnosis is not None
        assert diagnosis["diagnosis"] == "template not found"


class TestLlmDiagnoseJsonlContent:
    """_llm_diagnose_pipeline_failure 应读取 JSONL 内容传给 LLM (spec §7.5)."""

    def test_reads_jsonl_content_into_error_context(self, orchestrator, tmp_path):
        """JSONL 文件存在时, error_context 应包含 structured_log_content."""
        from core.result import fail_result

        jsonl_path = tmp_path / "structured.jsonl"
        jsonl_path.write_text(
            '{"node_id":"step_1","success":false,"error_code":"NO_MATCH"}\n',
            encoding="utf-8",
        )

        llm_client = MagicMock()
        llm_client.diagnose_failure.return_value = {"diagnosis": "ok"}

        result_obj = fail_result(error_msg="pipeline failed")
        result_obj.step_results = []

        orchestrator._llm_diagnose_pipeline_failure(
            llm_client=llm_client,
            result=result_obj,
            pipeline_json={"metadata": {}},
            structured_log_path=str(jsonl_path),
        )

        call_args = llm_client.diagnose_failure.call_args
        error_context = call_args[0][0]
        assert "structured_log_content" in error_context
        assert "NO_MATCH" in error_context["structured_log_content"]

    def test_jsonl_content_empty_when_file_missing(self, orchestrator):
        """JSONL 文件不存在时, structured_log_content 应为空字符串."""
        llm_client = MagicMock()
        llm_client.diagnose_failure.return_value = {"diagnosis": "ok"}

        result_obj = fail_result(error_msg="pipeline failed")
        result_obj.step_results = []

        orchestrator._llm_diagnose_pipeline_failure(
            llm_client=llm_client,
            result=result_obj,
            pipeline_json={"metadata": {}},
            structured_log_path="/nonexistent/path/structured.jsonl",
        )

        error_context = llm_client.diagnose_failure.call_args[0][0]
        assert error_context["structured_log_content"] == ""

    def test_jsonl_content_truncated_to_8000_chars(self, orchestrator, tmp_path):
        """JSONL 内容超过 8000 字符时应截断到最后 8000 字符."""
        jsonl_path = tmp_path / "big.jsonl"
        # 写入 10000 字符的 JSONL
        long_line = '{"msg":"' + "x" * 9900 + '"}\n'
        jsonl_path.write_text(long_line, encoding="utf-8")

        llm_client = MagicMock()
        llm_client.diagnose_failure.return_value = {"diagnosis": "ok"}

        result_obj = fail_result(error_msg="pipeline failed")
        result_obj.step_results = []

        orchestrator._llm_diagnose_pipeline_failure(
            llm_client=llm_client,
            result=result_obj,
            pipeline_json={"metadata": {}},
            structured_log_path=str(jsonl_path),
        )

        error_context = llm_client.diagnose_failure.call_args[0][0]
        assert len(error_context["structured_log_content"]) <= 8000

    def test_extracts_first_failed_step_metadata(self, orchestrator):
        """应从第一个失败步骤提取 node_id/node_type/error_code."""
        from core.result import AutoResult, fail_result

        llm_client = MagicMock()
        llm_client.diagnose_failure.return_value = {"diagnosis": "ok"}

        failed_step = AutoResult(
            success=False,
            error_msg="模板未匹配",
            error_code="NO_MATCH",
            node_id="step_3",
            node_type="template_match",
        )
        result_obj = fail_result(error_msg="pipeline failed")
        result_obj.step_results = [AutoResult(success=True), failed_step]

        orchestrator._llm_diagnose_pipeline_failure(
            llm_client=llm_client,
            result=result_obj,
            pipeline_json={"metadata": {}},
            structured_log_path="",
        )

        error_context = llm_client.diagnose_failure.call_args[0][0]
        assert error_context["node_id"] == "step_3"
        assert error_context["node_type"] == "template_match"
        assert error_context["error_code"] == "NO_MATCH"
