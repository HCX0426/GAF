"""ClickNode 默认轻量竞态防护集成测试 (spec 阶段 4.2.2 — 任务 1.6)

验证 ClickNode.execute 在点击后调用 wait_for_change_lightweight，
并把 expect_screen_change + screen_change_outcome 写入 result.data，
让 extract_result_fields 能提取进 JSONL 供 AI 诊断竞态。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import engine.nodes.click  # noqa: F401  (register ClickNode)
from core.wait_freezes import ScreenChangeOutcome
from engine.node import PIPELINE_NODE_REGISTRY

pytestmark = pytest.mark.unit


def _make_click_node(node_id="test_click", config=None):
    return PIPELINE_NODE_REGISTRY["click"].from_dict({
        "id": node_id,
        "node_type": "click",
        "config": config or {},
    })


def _make_mock_context_with_device(capture_screen_return=None):
    """Build a mock context whose device.capture_screen returns the given frame.

    If capture_screen_return is a list, returns elements in sequence (for
    simulating baseline + changed frame).

    Note: ctx.wait_freezes / ctx.capture_fn 显式设为 None, 让 ClickNode 走
    spec §4.2.3 回退路径 (per-call 新建 WaitFreezes + device.capture_screen).
    测试 InjectedWaitFreezes 场景见 TestClickNodeRaceProtectionInjected.
    """
    ctx = MagicMock()
    ctx.variables = {}
    ctx.debug_mode = False
    # spec §4.2.3: 默认 None 触发 ClickNode 回退路径 (向后兼容)
    ctx.wait_freezes = None
    ctx.capture_fn = None
    # N191: coord_transformer 必须显式 None, 否则 MagicMock 自动生成
    # 属性导致 click.py 中 transformer.convert_original_to_current_client
    # 返回 MagicMock 无法解包为 (x, y).
    ctx.coord_transformer = None
    device = MagicMock()
    device.device_id = "mock_device"
    device.activate_window = MagicMock()

    if isinstance(capture_screen_return, list):
        device.capture_screen.side_effect = capture_screen_return
    else:
        device.capture_screen.return_value = capture_screen_return

    ctx.device = device

    def set_var(key, value):
        ctx.variables[key] = value

    def get_var(key, default=None):
        return ctx.variables.get(key, default)

    ctx.set_variable.side_effect = set_var
    ctx.get_variable.side_effect = get_var
    return ctx, device


@pytest.fixture(autouse=True)
def fast_time(monkeypatch):
    """Make wait_for_change_lightweight's timeout fire instantly.

    Patches time.sleep (no-op) and time.monotonic (fast-forward) so
    UNCHANGED/TIMEOUT paths return immediately without waiting 2 real
    seconds. Each monotonic call advances 1.0s, so 2s timeout fires on
    the 2nd loop iteration.
    """
    import core.wait_freezes as wf_mod
    import engine.nodes.click as click_mod

    monkeypatch.setattr(click_mod.time, "sleep", lambda *_a, **_kw: None)
    monkeypatch.setattr(wf_mod.time, "sleep", lambda *_a, **_kw: None)

    _counter = {"t": 0.0}

    def fast_monotonic():
        _counter["t"] += 1.0
        return _counter["t"]

    # time module is shared globally; patching wf_mod.time.monotonic
    # affects all callers but only elapsed_time (unused by assertions)
    # is impacted in click.py.
    monkeypatch.setattr(wf_mod.time, "monotonic", fast_monotonic)


class TestClickNodeRaceProtectionDefault:
    """ClickNode 默认应启用轻量竞态防护。"""

    def test_click_with_screen_change_records_changed_outcome(self):
        """点击后画面变化，result.data 应包含 screen_change_outcome=CHANGED。"""
        # 第 1 帧 baseline（黑色），第 2 帧变化（白色）
        ctx, device = _make_mock_context_with_device([
            np.zeros((100, 100, 3), dtype=np.uint8),  # baseline
            np.full((100, 100, 3), 255, dtype=np.uint8),  # changed
        ])
        node = _make_click_node(config={"x": 50, "y": 60})
        result = node.execute(ctx)

        assert result.success
        assert result.data["x"] == 50
        assert result.data["y"] == 60
        # 默认 expect_screen_change=True
        assert result.data["expect_screen_change"] is True
        # 应记录 outcome 让 JSONL 能追踪
        assert result.data["screen_change_outcome"] == ScreenChangeOutcome.CHANGED.value

    def test_click_unchanged_does_not_fail(self):
        """点击后画面未变化，应记 UNCHANGED 但 success 仍为 True（兼容点击选中场景）。"""
        # 始终返回相同帧
        same_frame = np.full((100, 100, 3), 128, dtype=np.uint8)
        ctx, device = _make_mock_context_with_device(same_frame)
        node = _make_click_node(config={"x": 50, "y": 60})
        result = node.execute(ctx)

        # 关键：UNCHANGED 不 fail（spec 4.1 设计原则）
        assert result.success
        assert result.data["screen_change_outcome"] == ScreenChangeOutcome.UNCHANGED.value
        assert result.data["expect_screen_change"] is True

    def test_click_skipped_when_device_has_no_capture_screen(self):
        """device 无 capture_screen 方法应跳过防护，outcome=SKIPPED。"""
        ctx = MagicMock()
        ctx.variables = {}
        ctx.debug_mode = False
        # spec §4.2.3: 显式 None, 触发 ClickNode 回退路径检查 device.capture_screen
        ctx.wait_freezes = None
        ctx.capture_fn = None
        # N191: 同 _make_mock_context_with_device, coord_transformer 必须显式 None
        ctx.coord_transformer = None
        ctx.device = MagicMock(spec=["click", "activate_window", "device_id"])
        # 注意：spec=["click",...] 限制 MagicMock 只有这些属性，capture_screen 不存在

        def set_var(key, value):
            ctx.variables[key] = value

        ctx.set_variable.side_effect = set_var
        ctx.get_variable.side_effect = lambda key, default=None: ctx.variables.get(key, default)

        node = _make_click_node(config={"x": 50, "y": 60})
        result = node.execute(ctx)

        assert result.success
        # 无 capture_screen 应跳过防护
        assert result.data["screen_change_outcome"] == ScreenChangeOutcome.SKIPPED.value


class TestClickNodeRaceProtectionConfigurable:
    """expect_screen_change=False 应完全关闭默认防护。"""

    def test_expect_screen_change_false_skips_protection(self):
        """配置 expect_screen_change=False 应跳过防护，result.data 不含 outcome。"""
        ctx, device = _make_mock_context_with_device(
            np.zeros((100, 100, 3), dtype=np.uint8)
        )
        node = _make_click_node(config={
            "x": 50, "y": 60, "expect_screen_change": False,
        })
        result = node.execute(ctx)

        assert result.success
        # expect_screen_change=False 时不应记录 outcome（防护被关闭）
        assert result.data.get("expect_screen_change") is False
        # screen_change_outcome 不应出现（防护未运行）
        assert "screen_change_outcome" not in result.data

    def test_expect_screen_change_true_explicit_enables_protection(self):
        """显式 expect_screen_change=True 应启用防护（同默认行为）。"""
        ctx, device = _make_mock_context_with_device([
            np.zeros((100, 100, 3), dtype=np.uint8),
            np.full((100, 100, 3), 255, dtype=np.uint8),
        ])
        node = _make_click_node(config={
            "x": 50, "y": 60, "expect_screen_change": True,
        })
        result = node.execute(ctx)

        assert result.success
        assert result.data["expect_screen_change"] is True
        assert result.data["screen_change_outcome"] == ScreenChangeOutcome.CHANGED.value


class TestClickNodeRaceProtectionDeviceError:
    """设备异常时的降级行为。"""

    def test_capture_screen_exception_results_in_timeout_or_skipped(self):
        """capture_screen 抛异常应被吞掉，outcome 为 TIMEOUT 或 SKIPPED，不传播异常。"""
        ctx, device = _make_mock_context_with_device()
        device.capture_screen.side_effect = RuntimeError("device disconnected")
        node = _make_click_node(config={"x": 50, "y": 60})
        # 不应抛异常
        result = node.execute(ctx)

        assert result.success  # 点击本身成功
        # 异常应降级为 SKIPPED（baseline 捕获失败）
        assert result.data["screen_change_outcome"] in (
            ScreenChangeOutcome.SKIPPED.value,
            ScreenChangeOutcome.TIMEOUT.value,
        )

    def test_capture_screen_returns_none_results_in_skipped(self):
        """capture_screen 持续返回 None 应返回 SKIPPED（无 baseline）。"""
        ctx, device = _make_mock_context_with_device(None)
        node = _make_click_node(config={"x": 50, "y": 60})
        result = node.execute(ctx)

        assert result.success
        assert result.data["screen_change_outcome"] == ScreenChangeOutcome.SKIPPED.value


class TestClickNodeRaceProtectionDataFields:
    """result.data 字段约定（供 extract_result_fields 提取）。"""

    def test_result_data_includes_expect_screen_change_field(self):
        """成功点击的 result.data 必须包含 expect_screen_change 字段。"""
        ctx, device = _make_mock_context_with_device([
            np.zeros((100, 100, 3), dtype=np.uint8),
            np.full((100, 100, 3), 255, dtype=np.uint8),
        ])
        node = _make_click_node(config={"x": 50, "y": 60})
        result = node.execute(ctx)

        # extract_result_fields 的 click 分支依赖此字段
        assert "expect_screen_change" in result.data
        assert isinstance(result.data["expect_screen_change"], bool)

    def test_result_data_includes_screen_change_outcome_when_protection_runs(self):
        """防护运行时 result.data 必须包含 screen_change_outcome 字段。"""
        ctx, device = _make_mock_context_with_device([
            np.zeros((100, 100, 3), dtype=np.uint8),
            np.full((100, 100, 3), 255, dtype=np.uint8),
        ])
        node = _make_click_node(config={"x": 50, "y": 60})
        result = node.execute(ctx)

        # extract_result_fields 的 click 分支依赖此字段
        assert "screen_change_outcome" in result.data
        # 值必须是 ScreenChangeOutcome 枚举值的字符串形式
        outcome = result.data["screen_change_outcome"]
        assert outcome in (
            ScreenChangeOutcome.CHANGED.value,
            ScreenChangeOutcome.UNCHANGED.value,
            ScreenChangeOutcome.TIMEOUT.value,
            ScreenChangeOutcome.SKIPPED.value,
        )


class TestClickNodeRaceProtectionInjected:
    """spec §4.2.3 依赖注入: ClickNode 应优先用 context.wait_freezes + capture_fn."""

    def test_uses_injected_wait_freezes_when_provided(self):
        """context.wait_freezes 已注入时, ClickNode 应调用它而非新建 WaitFreezes.

        spec §4.2.3 要求: ClickNode 通过 PipelineContext 注入 WaitFreezes 实例,
        而非每次 click 都新建. 这避免了 per-click 分配, 且让未来 WaitFreezes
        自定义配置 (ROI 等) 能统一注入.
        """
        ctx, _device = _make_mock_context_with_device([
            np.zeros((100, 100, 3), dtype=np.uint8),
            np.full((100, 100, 3), 255, dtype=np.uint8),
        ])
        # 注入 mock wait_freezes + capture_fn
        mock_wf = MagicMock()
        mock_wf.wait_for_change_lightweight.return_value = ScreenChangeOutcome.CHANGED
        mock_capture = MagicMock(return_value=np.zeros((100, 100, 3), dtype=np.uint8))
        ctx.wait_freezes = mock_wf
        ctx.capture_fn = mock_capture

        node = _make_click_node(config={"x": 50, "y": 60})
        result = node.execute(ctx)

        assert result.success
        # 关键断言: 用了注入的 wait_freezes.wait_for_change_lightweight
        mock_wf.wait_for_change_lightweight.assert_called_once()
        # 关键断言: capture_fn 用的是注入的 mock_capture, 不是 device.capture_screen
        call_kwargs = mock_wf.wait_for_change_lightweight.call_args
        assert call_kwargs.kwargs["capture_fn"] is mock_capture
        # outcome 应来自注入的 mock (CHANGED), 而非真实 WaitFreezes 跑出来的结果
        assert result.data["screen_change_outcome"] == ScreenChangeOutcome.CHANGED.value

    def test_screen_change_timeout_config_passed_to_wait_for_change(self):
        """spec §4.2.2: screen_change_timeout 配置应传给 wait_for_change_lightweight.

        偏差 3 修复: timeout 不再写死 2.0, 通过 node.config 可配.
        """
        ctx, _device = _make_mock_context_with_device([
            np.zeros((100, 100, 3), dtype=np.uint8),
        ])
        mock_wf = MagicMock()
        mock_wf.wait_for_change_lightweight.return_value = ScreenChangeOutcome.UNCHANGED
        ctx.wait_freezes = mock_wf
        ctx.capture_fn = MagicMock(return_value=np.zeros((100, 100, 3), dtype=np.uint8))

        node = _make_click_node(config={
            "x": 50, "y": 60, "screen_change_timeout": 0.5,
        })
        result = node.execute(ctx)

        assert result.success
        call_kwargs = mock_wf.wait_for_change_lightweight.call_args
        assert call_kwargs.kwargs["timeout"] == 0.5
        # 默认值校验: 其他参数仍用 spec 默认
        assert call_kwargs.kwargs["change_threshold"] == 0.01
        assert call_kwargs.kwargs["poll_interval"] == 0.1

    def test_injected_wait_freezes_none_falls_back_to_device(self):
        """context.wait_freezes=None 时应回退到新建 WaitFreezes + device.capture_screen.

        向后兼容: 旧调用方/单测未注入 wait_freezes 时, ClickNode 不应崩溃.
        """
        ctx, device = _make_mock_context_with_device([
            np.zeros((100, 100, 3), dtype=np.uint8),
            np.full((100, 100, 3), 255, dtype=np.uint8),
        ])
        # wait_freezes / capture_fn 已在 fixture 中设为 None
        assert ctx.wait_freezes is None
        assert ctx.capture_fn is None

        node = _make_click_node(config={"x": 50, "y": 60})
        result = node.execute(ctx)

        # 回退路径应正常工作 (用 device.capture_screen)
        assert result.success
        assert result.data["screen_change_outcome"] == ScreenChangeOutcome.CHANGED.value
        # device.capture_screen 应被调用 (baseline + 至少 1 次轮询)
        assert device.capture_screen.call_count >= 2
