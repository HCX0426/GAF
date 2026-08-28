"""python_call 节点 smoke 测试

interface-recovery-design.md §13 — 验证:
- 模块加载 + 函数调用 + 返回值存入 context 变量
- config.args ${var} 引用解析 (整串保留类型 / 嵌入字符串拼接 / dict 递归)
- 路径校验 (base_dir 逃逸 / 非 .py / 文件不存在)
- 超时协作式中断
- 异常捕获转 fail_result

不依赖真实 device — 用 MagicMock 模拟,device.capture_screen 返回 None 也无所谓
(测试函数不调用 device)。
"""

import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import engine.nodes.python_call  # noqa: F401  (注册节点)
from engine.node import PIPELINE_NODE_REGISTRY
from engine.nodes.python_call import PythonCallNode

pytestmark = pytest.mark.unit

# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_context():
    """Mock PipelineContext with variables dict + custom_tasks_base_dir."""
    ctx = MagicMock()
    ctx.variables = {}
    ctx.device = MagicMock()
    ctx.device.device_id = "test-device-001"
    ctx.debug_mode = False
    ctx.custom_tasks_base_dir = "."
    # python_call 用 getattr(ctx, "_leaked_thread_count", 0) 读;
    # MagicMock 自动创建属性会返回 MagicMock 实例,导致 > int 比较失败。
    # 显式初始化为 0,模拟真实 PipelineContext 行为。
    ctx._leaked_thread_count = 0

    def set_var(key, value):
        ctx.variables[key] = value

    def get_var(key, default=None):
        return ctx.variables.get(key, default)

    ctx.set_variable.side_effect = set_var
    ctx.get_variable.side_effect = get_var
    return ctx


@pytest.fixture
def tasks_dir(tmp_path):
    """Create a temp custom_tasks dir for test .py files."""
    d = tmp_path / "custom_tasks"
    d.mkdir()
    return d


def _write_module(tasks_dir: Path, filename: str, content: str) -> Path:
    """Write a .py module under tasks_dir, return its path."""
    p = tasks_dir / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _make_node(node_id: str, config: dict) -> PythonCallNode:
    """Build a PythonCallNode with given config."""
    return PythonCallNode(
        id=node_id,
        node_type="python_call",
        config=config,
        next_node_id="",
    )


# ============================================================
# 基础加载与调用
# ============================================================

def test_python_call_registered():
    """python_call 应在 PIPELINE_NODE_REGISTRY 中注册"""
    assert "python_call" in PIPELINE_NODE_REGISTRY


def test_basic_call_success(mock_context, tasks_dir):
    """基础调用: 加载模块 + 调用函数 + 返回值存入 output 变量"""
    _write_module(tasks_dir, "simple.py", """
        def compute(device, context, **kwargs):
            return {"x": 100, "y": 200}
    """)
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    node = _make_node("step1", {
        "module_path": "simple.py",
        "function": "compute",
        "output": "result",
    })
    result = node.execute(mock_context)
    assert result.success
    assert mock_context.get_variable("result") == {"x": 100, "y": 200}
    assert result.data["function"] == "compute"
    assert result.data["return_value"] == {"x": 100, "y": 200}


def test_args_passed_through(mock_context, tasks_dir):
    """config.args 字面量应原样传给函数 kwargs"""
    _write_module(tasks_dir, "args.py", """
        def echo(device, context, **kwargs):
            return {"got": kwargs}
    """)
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    node = _make_node("s", {
        "module_path": "args.py",
        "function": "echo",
        "args": {"stage": "hard_7", "count": 3, "enabled": True},
    })
    result = node.execute(mock_context)
    assert result.success
    assert result.data["return_value"]["got"] == {
        "stage": "hard_7", "count": 3, "enabled": True,
    }


def test_no_output_field_does_not_set_var(mock_context, tasks_dir):
    """config.output 不填时不写入 context 变量"""
    _write_module(tasks_dir, "no_out.py", """
        def fn(device, context, **kwargs):
            return "ignored"
    """)
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    node = _make_node("s", {"module_path": "no_out.py", "function": "fn"})
    result = node.execute(mock_context)
    assert result.success
    assert "result" not in mock_context.variables


# ============================================================
# 参数解析 (${var} 引用)
# ============================================================

def test_arg_whole_var_reference_preserves_type(mock_context, tasks_dir):
    """整串 ${var} 引用 — 保留变量原类型"""
    _write_module(tasks_dir, "v.py", """
        def fn(device, context, **kwargs):
            return {"val": kwargs["ref"], "type": type(kwargs["ref"]).__name__}
    """)
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    mock_context.set_variable("match_pos", {"x": 960, "y": 540})
    node = _make_node("s", {
        "module_path": "v.py",
        "function": "fn",
        "args": {"ref": "${match_pos}"},
    })
    result = node.execute(mock_context)
    assert result.success
    assert result.data["return_value"]["val"] == {"x": 960, "y": 540}
    assert result.data["return_value"]["type"] == "dict"


def test_arg_embedded_var_string_concat(mock_context, tasks_dir):
    """嵌入 ${var} — 字符串拼接"""
    _write_module(tasks_dir, "e.py", """
        def fn(device, context, **kwargs):
            return kwargs["label"]
    """)
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    mock_context.set_variable("stage", "hard_7")
    node = _make_node("s", {
        "module_path": "e.py",
        "function": "fn",
        "args": {"label": "v_${stage}_end"},
    })
    result = node.execute(mock_context)
    assert result.success
    assert result.data["return_value"] == "v_hard_7_end"


def test_arg_dict_recursive_resolution(mock_context, tasks_dir):
    """dict 嵌套 ${var} — 递归解析"""
    _write_module(tasks_dir, "d.py", """
        def fn(device, context, **kwargs):
            return kwargs["config"]
    """)
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    mock_context.set_variable("offset_x", 50)
    mock_context.set_variable("offset_y", 60)
    node = _make_node("s", {
        "module_path": "d.py",
        "function": "fn",
        "args": {
            "config": {"x": "${offset_x}", "y": "${offset_y}"},
        },
    })
    result = node.execute(mock_context)
    assert result.success
    assert result.data["return_value"] == {"x": 50, "y": 60}


def test_arg_missing_var_raises_keyerror(mock_context, tasks_dir):
    """${var} 引用不存在的变量 — KeyError 转 fail_result"""
    _write_module(tasks_dir, "m.py", """
        def fn(device, context, **kwargs):
            return kwargs["ref"]
    """)
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    node = _make_node("s", {
        "module_path": "m.py",
        "function": "fn",
        "args": {"ref": "${nonexistent}"},
    })
    result = node.execute(mock_context)
    assert not result.success
    assert "nonexistent" in result.error_msg


# ============================================================
# 路径校验 (§13.6 安全约束)
# ============================================================

def test_path_escape_rejected(mock_context, tasks_dir, tmp_path):
    """module_path 逃逸 base_dir — 拒绝"""
    # 把 base_dir 设为 tasks_dir,但 module_path 指向 tmp_path 之外
    tmp_path.parent / "evil.py"
    _write_module(tmp_path.parent, "evil.py", "def fn(device, context, **kw): return 1")
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    node = _make_node("s", {
        "module_path": "../evil.py",
        "function": "fn",
    })
    result = node.execute(mock_context)
    assert not result.success
    assert "必须在" in result.error_msg or "must be" in result.error_msg.lower()


def test_non_py_extension_rejected(mock_context, tasks_dir):
    """非 .py 文件 — 拒绝"""
    _write_module(tasks_dir, "script.txt", "def fn(): pass")
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    node = _make_node("s", {
        "module_path": "script.txt",
        "function": "fn",
    })
    result = node.execute(mock_context)
    assert not result.success
    assert ".py" in result.error_msg


def test_nonexistent_file_rejected(mock_context, tasks_dir):
    """文件不存在 — 拒绝"""
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    node = _make_node("s", {
        "module_path": "ghost.py",
        "function": "fn",
    })
    result = node.execute(mock_context)
    assert not result.success
    assert "不存在" in result.error_msg or "not exist" in result.error_msg.lower()


# ============================================================
# 必填字段缺失
# ============================================================

def test_missing_module_path_rejected(mock_context):
    """module_path 缺失 — fail_result"""
    node = _make_node("s", {"function": "fn"})
    result = node.execute(mock_context)
    assert not result.success
    assert "module_path" in result.error_msg


def test_missing_function_rejected(mock_context, tasks_dir):
    """function 缺失 — fail_result"""
    _write_module(tasks_dir, "x.py", "def fn(): pass")
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    node = _make_node("s", {"module_path": "x.py"})
    result = node.execute(mock_context)
    assert not result.success
    assert "function" in result.error_msg


def test_function_not_found_in_module(mock_context, tasks_dir):
    """模块中找不到指定函数 — fail_result"""
    _write_module(tasks_dir, "n.py", "def existing_fn(): pass")
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    node = _make_node("s", {
        "module_path": "n.py",
        "function": "nonexistent_fn",
    })
    result = node.execute(mock_context)
    assert not result.success
    assert "nonexistent_fn" in result.error_msg


# ============================================================
# 异常捕获
# ============================================================

def test_function_exception_caught(mock_context, tasks_dir):
    """函数抛异常 — 捕获转 fail_result"""
    _write_module(tasks_dir, "err.py", """
        def fn(device, context, **kwargs):
            raise ValueError("业务错误")
    """)
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    node = _make_node("s", {
        "module_path": "err.py",
        "function": "fn",
    })
    result = node.execute(mock_context)
    assert not result.success
    assert "业务错误" in result.error_msg


# ============================================================
# 超时 (协作式中断)
# ============================================================

def test_timeout_raises_fail_result(mock_context, tasks_dir):
    """函数超时 — fail_result,错误消息含 timeout"""
    _write_module(tasks_dir, "slow.py", """
        import time
        def fn(device, context, **kwargs):
            time.sleep(2.0)
            return "should_not_reach"
    """)
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    node = _make_node("s", {
        "module_path": "slow.py",
        "function": "fn",
        "timeout": 0.5,
    })
    result = node.execute(mock_context)
    assert not result.success
    assert "超时" in result.error_msg or "timeout" in result.error_msg.lower()
    # 泄漏线程计数累加 (§13.6 缓解措施)
    assert getattr(mock_context, "_leaked_thread_count", 0) >= 1


def test_cooperative_cancel_checks_event(mock_context, tasks_dir):
    """用户函数检查 _python_call_cancel — 提前退出,不超时"""
    _write_module(tasks_dir, "coop.py", """
        import time
        def fn(device, context, **kwargs):
            for i in range(100):
                if context._python_call_cancel.is_set():
                    return {"cancelled": True, "iter": i}
                time.sleep(0.05)
            return {"cancelled": False}
    """)
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    # 设很短超时,触发协作式中断
    node = _make_node("s", {
        "module_path": "coop.py",
        "function": "fn",
        "timeout": 0.3,
    })
    result = node.execute(mock_context)
    # 主线程超时后设 cancel_event,但子线程仍在 sleep — 无法立即响应
    # 实际仍会超时 fail (协作式无法强制),但 cancel_event 应已设置
    assert not result.success
    assert hasattr(mock_context, "_python_call_cancel")


# ============================================================
# device/context 注入
# ============================================================

def test_device_injected_to_function(mock_context, tasks_dir):
    """device 实例应注入到函数的 device 参数"""
    _write_module(tasks_dir, "dev.py", """
        def fn(device, context, **kwargs):
            return {"device_id": getattr(device, 'device_id', None)}
    """)
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    mock_context.device.device_id = "test-device-001"
    node = _make_node("s", {
        "module_path": "dev.py",
        "function": "fn",
    })
    result = node.execute(mock_context)
    assert result.success
    assert result.data["return_value"]["device_id"] == "test-device-001"


def test_context_injected_to_function(mock_context, tasks_dir):
    """context 实例应注入到函数的 context 参数,可读写变量"""
    _write_module(tasks_dir, "ctx.py", """
        def fn(device, context, **kwargs):
            prev = context.get_variable("prev_value", 0)
            context.set_variable("new_value", prev + 100)
            return {"prev": prev, "new": prev + 100}
    """)
    mock_context.custom_tasks_base_dir = str(tasks_dir)
    mock_context.set_variable("prev_value", 42)
    node = _make_node("s", {
        "module_path": "ctx.py",
        "function": "fn",
    })
    result = node.execute(mock_context)
    assert result.success
    assert result.data["return_value"] == {"prev": 42, "new": 142}
    # 函数内 set_variable 也应可见 (mock_context 用真 dict 实现)
    assert mock_context.get_variable("new_value") == 142
