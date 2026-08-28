"""TD-336 #7: 杂项节点 smoke 测试

覆盖 6 个节点 (含子节点):
- NotifyNode (notify): 空 message/模板替换/webhook/存储结果
- RandomDelayNode (random_delay): 基本延时/无效范围/无效 min-max
- AppControl: start_app / stop_app (无设备/缺包名/缺命令)
- PythonCallNode (python_call): 缺字段/路径逃逸/文件不存在/正常执行
- NeuralNetworkNode (neural_network): 废弃别名委托给 nn_classifier/nn_regressor
- NNRecognition: nn_classifier / nn_regressor (缺 model_path/无图像)

使用 MagicMock 模拟 PipelineContext 与 device, 不依赖真实 ONNX/网络.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import to register nodes.
import engine.nodes.app_control  # noqa: F401
import engine.nodes.neural_network  # noqa: F401
import engine.nodes.nn_recognition  # noqa: F401
import engine.nodes.notify  # noqa: F401
import engine.nodes.python_call  # noqa: F401
import engine.nodes.random_delay  # noqa: F401
from engine.node import PIPELINE_NODE_REGISTRY

pytestmark = pytest.mark.unit


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_context():
    """Build a mock PipelineContext with variables dict."""
    ctx = MagicMock()
    ctx.variables = {}
    ctx.device = None
    ctx.debug_mode = False
    ctx.coord_transformer = None
    ctx.custom_tasks_base_dir = "."
    ctx.execution_history = []
    # python_call reads these via getattr() — MagicMock returns a Mock by
    # default, which breaks numeric comparisons. Pre-set them to ints.
    ctx._leaked_thread_count = 0

    def set_var(key, value):
        ctx.variables[key] = value

    def get_var(key, default=None):
        return ctx.variables.get(key, default)

    ctx.set_variable.side_effect = set_var
    ctx.get_variable.side_effect = get_var
    return ctx


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Patch time.sleep in random_delay so tests run fast."""
    import engine.nodes.random_delay as rd_mod
    monkeypatch.setattr(rd_mod.time, "sleep", lambda *_a, **_kw: None)
    # random_delay uses random.uniform; we can leave it (no I/O).


def _make_node(node_type, node_id="test_node", config=None):
    return PIPELINE_NODE_REGISTRY[node_type].from_dict({
        "id": node_id,
        "node_type": node_type,
        "config": config or {},
    })


# ============================================================
# Registration
# ============================================================

class TestRegistration:
    def test_notify_registered(self):
        assert "notify" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["notify"].__name__ == "NotifyNode"

    def test_random_delay_registered(self):
        assert "random_delay" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["random_delay"].__name__ == "RandomDelayNode"

    def test_start_app_registered(self):
        assert "start_app" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["start_app"].__name__ == "StartAppNode"

    def test_stop_app_registered(self):
        assert "stop_app" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["stop_app"].__name__ == "StopAppNode"

    def test_python_call_registered(self):
        assert "python_call" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["python_call"].__name__ == "PythonCallNode"

    def test_neural_network_registered(self):
        assert "neural_network" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["neural_network"].__name__ == "NeuralNetworkNode"

    def test_nn_classifier_registered(self):
        assert "nn_classifier" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["nn_classifier"].__name__ == "NNClassifierNode"

    def test_nn_regressor_registered(self):
        assert "nn_regressor" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["nn_regressor"].__name__ == "NNRegressorNode"


# ============================================================
# NotifyNode
# ============================================================

class TestNotifyNode:
    """NotifyNode: 日志 + 可选 webhook 通知."""

    def test_empty_message_returns_fail(self, mock_context):
        node = _make_node("notify", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "message" in result.error_msg.lower()

    def test_basic_notify_succeeds(self, mock_context):
        node = _make_node("notify", config={"message": "hello"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["message"] == "hello"
        assert result.data["channel"] == "log"
        assert result.data["level"] == "info"

    def test_template_substitution(self, mock_context):
        node = _make_node("notify", config={
            "message": "User {name} logged in at {time}",
            "variables": {"name": "alice", "time": "10:00"},
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["message"] == "User alice logged in at 10:00"

    def test_template_missing_variable_returns_fail(self, mock_context):
        # variables must be non-empty to trigger format() path; otherwise the
        # node bypasses substitution and returns the raw template.
        node = _make_node("notify", config={
            "message": "Hello {missing_var}",
            "variables": {"other_var": "present"},
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert "template" in result.error_msg.lower()

    def test_custom_channel_and_level(self, mock_context):
        node = _make_node("notify", config={
            "message": "warn msg",
            "channel": "alert",
            "level": "warning",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["channel"] == "alert"
        assert result.data["level"] == "warning"

    def test_default_channel_is_log(self, mock_context):
        node = _make_node("notify", config={"message": "x"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["channel"] == "log"

    def test_default_level_is_info(self, mock_context):
        node = _make_node("notify", config={"message": "x"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["level"] == "info"

    def test_stores_result_in_context(self, mock_context):
        node = _make_node("notify", node_id="n1", config={"message": "stored"})
        node.execute(mock_context)
        assert "n1_notify_result" in mock_context.variables
        assert mock_context.variables["n1_notify_result"]["message"] == "stored"

    def test_webhook_not_attempted_when_no_url(self, mock_context):
        node = _make_node("notify", config={"message": "x"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["webhook"]["attempted"] is False


# ============================================================
# RandomDelayNode
# ============================================================

class TestRandomDelayNode:
    """RandomDelayNode: [min, max] 区间内随机延时."""

    def test_basic_delay_succeeds(self, mock_context):
        node = _make_node("random_delay", config={"min": 0.1, "max": 0.2})
        result = node.execute(mock_context)
        assert result.success is True
        assert 0.1 <= result.data["delay"] <= 0.2
        assert result.data["min"] == 0.1
        assert result.data["max"] == 0.2

    def test_default_range_is_0_5_to_2_0(self, mock_context):
        node = _make_node("random_delay", config={})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["min"] == 0.5
        assert result.data["max"] == 2.0

    def test_invalid_range_max_less_than_min_returns_fail(self, mock_context):
        node = _make_node("random_delay", config={"min": 1.0, "max": 0.5})
        result = node.execute(mock_context)
        assert result.success is False
        assert "invalid range" in result.error_msg.lower()

    def test_negative_min_returns_fail(self, mock_context):
        node = _make_node("random_delay", config={"min": -1.0, "max": 1.0})
        result = node.execute(mock_context)
        assert result.success is False
        assert "invalid range" in result.error_msg.lower()

    def test_invalid_min_max_type_returns_fail(self, mock_context):
        node = _make_node("random_delay", config={"min": "abc", "max": 1.0})
        result = node.execute(mock_context)
        assert result.success is False
        assert "invalid min/max" in result.error_msg.lower()

    def test_equal_min_max_succeeds(self, mock_context):
        node = _make_node("random_delay", config={"min": 0.5, "max": 0.5})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["delay"] == 0.5


# ============================================================
# StartAppNode
# ============================================================

class TestStartAppNode:
    """StartAppNode: 启动应用."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node("start_app", config={"package": "com.x"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "no device" in result.error_msg.lower()

    def test_android_device_missing_package_returns_fail(self, mock_context):
        dev = MagicMock()
        dev.device_type = "emulator"
        mock_context.device = dev
        node = _make_node("start_app", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "package" in result.error_msg.lower()

    def test_windows_device_missing_command_returns_fail(self, mock_context):
        dev = MagicMock()
        dev.device_type = "windows"
        mock_context.device = dev
        node = _make_node("start_app", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "command" in result.error_msg.lower()

    def test_android_with_package_succeeds(self, mock_context):
        # Patch _run_adb to avoid calling real adb binary.
        dev = MagicMock()
        dev.device_type = "emulator"
        dev.adb_serial = ""
        mock_context.device = dev
        node = _make_node("start_app", config={"package": "com.test.app"})
        with patch("engine.nodes.app_control._run_adb",
                   return_value=(0, "ok", "")):
            result = node.execute(mock_context)
        assert result.success is True
        assert result.data["returncode"] == 0

    def test_android_with_activity_succeeds(self, mock_context):
        dev = MagicMock()
        dev.device_type = "android"
        dev.adb_serial = "device123"
        mock_context.device = dev
        node = _make_node("start_app", config={
            "package": "com.test.app", "activity": "MainActivity",
        })
        with patch("engine.nodes.app_control._run_adb",
                   return_value=(0, "", "")) as mock_adb:
            result = node.execute(mock_context)
        assert result.success is True
        # Verify adb args include the activity.
        adb_args = mock_adb.call_args.args[1]
        assert "com.test.app/MainActivity" in adb_args

    def test_adb_command_failure_returns_fail(self, mock_context):
        dev = MagicMock()
        dev.device_type = "emulator"
        mock_context.device = dev
        node = _make_node("start_app", config={"package": "com.x"})
        with patch("engine.nodes.app_control._run_adb",
                   return_value=(1, "", "device not found")):
            result = node.execute(mock_context)
        assert result.success is False
        assert "command failed" in result.error_msg.lower()


# ============================================================
# StopAppNode
# ============================================================

class TestStopAppNode:
    """StopAppNode: 停止应用."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node("stop_app", config={"package": "com.x"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "no device" in result.error_msg.lower()

    def test_android_device_missing_package_returns_fail(self, mock_context):
        dev = MagicMock()
        dev.device_type = "emulator"
        mock_context.device = dev
        node = _make_node("stop_app", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "package" in result.error_msg.lower()

    def test_windows_device_missing_command_and_process_returns_fail(self, mock_context):
        dev = MagicMock()
        dev.device_type = "windows"
        mock_context.device = dev
        node = _make_node("stop_app", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "command" in result.error_msg.lower() or "process" in result.error_msg.lower()

    def test_android_force_stop_succeeds(self, mock_context):
        dev = MagicMock()
        dev.device_type = "emulator"
        mock_context.device = dev
        node = _make_node("stop_app", config={
            "package": "com.test.app", "force": True,
        })
        with patch("engine.nodes.app_control._run_adb",
                   return_value=(0, "", "")) as mock_adb:
            result = node.execute(mock_context)
        assert result.success is True
        adb_args = mock_adb.call_args.args[1]
        assert "force-stop" in adb_args

    def test_android_kill_no_force_uses_am_kill(self, mock_context):
        dev = MagicMock()
        dev.device_type = "emulator"
        mock_context.device = dev
        node = _make_node("stop_app", config={
            "package": "com.test.app", "force": False,
        })
        with patch("engine.nodes.app_control._run_adb",
                   return_value=(0, "", "")) as mock_adb:
            result = node.execute(mock_context)
        assert result.success is True
        adb_args = mock_adb.call_args.args[1]
        assert "kill" in adb_args
        assert "force-stop" not in adb_args


# ============================================================
# PythonCallNode
# ============================================================

class TestPythonCallNode:
    """PythonCallNode: 加载并执行自定义 Python 函数."""

    def test_missing_module_path_returns_fail(self, mock_context):
        node = _make_node("python_call", config={"function": "my_func"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "module_path" in result.error_msg and "function" in result.error_msg

    def test_missing_function_returns_fail(self, mock_context):
        node = _make_node("python_call", config={"module_path": "x.py"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "module_path" in result.error_msg and "function" in result.error_msg

    def test_path_escape_returns_fail(self, mock_context):
        node = _make_node("python_call", config={
            "module_path": "../../etc/passwd.py",
            "function": "x",
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert "路径校验失败" in result.error_msg

    def test_non_py_extension_returns_fail(self, mock_context):
        node = _make_node("python_call", config={
            "module_path": "tasks.txt", "function": "x",
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert "路径校验失败" in result.error_msg
        assert ".py" in result.error_msg

    def test_nonexistent_file_returns_fail(self, mock_context):
        node = _make_node("python_call", config={
            "module_path": "nonexistent_file.py", "function": "x",
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert "路径校验失败" in result.error_msg or "模块加载失败" in result.error_msg

    def test_valid_module_and_function_succeeds(self, mock_context, tmp_path):
        # Create a real Python module file with a function.
        module_file = tmp_path / "my_task.py"
        module_file.write_text(
            "def my_func(device, context, **kwargs):\n"
            "    return {'result': 'success', 'kwargs': kwargs}\n"
        )
        mock_context.custom_tasks_base_dir = str(tmp_path)
        node = _make_node("python_call", config={
            "module_path": "my_task.py",
            "function": "my_func",
            "args": {"key1": "value1"},
            "timeout": 2.0,
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["function"] == "my_func"
        assert result.data["return_value"]["result"] == "success"
        assert result.data["return_value"]["kwargs"] == {"key1": "value1"}

    def test_function_exception_returns_fail(self, mock_context, tmp_path):
        module_file = tmp_path / "failing_task.py"
        module_file.write_text(
            "def boom(device, context, **kwargs):\n"
            "    raise ValueError('intentional failure')\n"
        )
        mock_context.custom_tasks_base_dir = str(tmp_path)
        node = _make_node("python_call", config={
            "module_path": "failing_task.py",
            "function": "boom",
            "timeout": 2.0,
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert "intentional failure" in result.error_msg or "执行异常" in result.error_msg

    def test_function_not_callable_returns_fail(self, mock_context, tmp_path):
        module_file = tmp_path / "no_func.py"
        module_file.write_text("not_a_function = 42\n")
        mock_context.custom_tasks_base_dir = str(tmp_path)
        node = _make_node("python_call", config={
            "module_path": "no_func.py",
            "function": "missing_func",
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert "未找到可调用函数" in result.error_msg or "未找到" in result.error_msg

    def test_stores_return_value_in_output_variable(self, mock_context, tmp_path):
        module_file = tmp_path / "task_with_output.py"
        module_file.write_text(
            "def compute(device, context, **kwargs):\n"
            "    return 42\n"
        )
        mock_context.custom_tasks_base_dir = str(tmp_path)
        node = _make_node("python_call", config={
            "module_path": "task_with_output.py",
            "function": "compute",
            "output": "computed_value",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert mock_context.variables["computed_value"] == 42

    def test_args_var_reference_resolved(self, mock_context, tmp_path):
        module_file = tmp_path / "var_task.py"
        module_file.write_text(
            "def echo(device, context, **kwargs):\n"
            "    return kwargs\n"
        )
        mock_context.custom_tasks_base_dir = str(tmp_path)
        mock_context.variables["user_input"] = "hello"
        node = _make_node("python_call", config={
            "module_path": "var_task.py",
            "function": "echo",
            "args": {"msg": "${user_input}"},
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["return_value"]["msg"] == "hello"


# ============================================================
# NeuralNetworkNode (deprecated alias)
# ============================================================

class TestNeuralNetworkNode:
    """NeuralNetworkNode: 废弃别名, 委托给 nn_classifier/nn_regressor."""

    def test_default_mode_classifier_delegates(self, mock_context):
        # No model_path → delegated nn_classifier fails with "model_path is required".
        node = _make_node("neural_network", config={"model_path": ""})
        result = node.execute(mock_context)
        assert result.success is False
        assert "model_path" in result.error_msg.lower()

    def test_explicit_classifier_mode_delegates(self, mock_context):
        node = _make_node("neural_network", config={
            "mode": "classifier", "model_path": "",
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert "model_path" in result.error_msg.lower()

    def test_regressor_mode_delegates(self, mock_context):
        node = _make_node("neural_network", config={
            "mode": "regressor", "model_path": "",
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert "model_path" in result.error_msg.lower()

    def test_deprecated_warning_logged(self, mock_context, caplog):
        # Use caplog to capture the deprecation warning.
        import logging
        node = _make_node("neural_network", config={"model_path": ""})
        with caplog.at_level(logging.WARNING, logger="engine.nodes.neural_network"):
            node.execute(mock_context)
        assert any("deprecated" in r.message.lower() for r in caplog.records)

    def test_no_image_with_model_path_still_fails_on_image(self, mock_context):
        # Even with model_path, no image → fail at image acquisition step.
        node = _make_node("neural_network", config={
            "model_path": "/nonexistent/model.onnx",
        })
        result = node.execute(mock_context)
        # Should fail either at model load OR at "no image available" — both
        # indicate the delegate was invoked.
        assert result.success is False


# ============================================================
# NNClassifierNode
# ============================================================

class TestNNClassifierNode:
    """NNClassifierNode: ONNX 分类推理 (smoke 走早期失败路径)."""

    def test_missing_model_path_returns_fail(self, mock_context):
        node = _make_node("nn_classifier", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "model_path" in result.error_msg.lower()

    def test_no_image_returns_fail(self, mock_context):
        node = _make_node("nn_classifier", config={
            "model_path": "/dummy/model.onnx",
        })
        result = node.execute(mock_context)
        assert result.success is False
        # Failure can be "no image available" or ONNX session error.
        assert "image" in result.error_msg.lower() or "onnxruntime" in result.error_msg.lower() \
            or "model" in result.error_msg.lower()

    def test_with_image_still_fails_on_model_load(self, mock_context):
        # Provide image but invalid model_path → fails at session init.
        import numpy as np
        mock_context.variables["image"] = np.zeros((10, 10, 3), dtype=np.uint8)
        node = _make_node("nn_classifier", config={
            "model_path": "/nonexistent/model.onnx",
        })
        result = node.execute(mock_context)
        assert result.success is False
        # ONNX Runtime raises various errors; just verify it failed.


# ============================================================
# NNRegressorNode
# ============================================================

class TestNNRegressorNode:
    """NNRegressorNode: ONNX 回归推理 (smoke 走早期失败路径)."""

    def test_missing_model_path_returns_fail(self, mock_context):
        node = _make_node("nn_regressor", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "model_path" in result.error_msg.lower()

    def test_no_image_returns_fail(self, mock_context):
        node = _make_node("nn_regressor", config={
            "model_path": "/dummy/model.onnx",
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert "image" in result.error_msg.lower() or "onnxruntime" in result.error_msg.lower() \
            or "model" in result.error_msg.lower()

    def test_with_image_still_fails_on_model_load(self, mock_context):
        import numpy as np
        mock_context.variables["image"] = np.zeros((10, 10, 3), dtype=np.uint8)
        node = _make_node("nn_regressor", config={
            "model_path": "/nonexistent/model.onnx",
        })
        result = node.execute(mock_context)
        assert result.success is False
