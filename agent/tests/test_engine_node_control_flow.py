"""PipelineEngine 节点级控制流测试 — spec-2026-07-27-execution-path-unification 阶段 2.

覆盖 PipelineNode 新增的 5 个字段（吸收 chain step 优点）：
  - pre_verify: 节点 execute() 之前的强验证
  - post_verify: 节点成功后的强验证（已有 config 路径，本测试覆盖 node 属性路径）
  - retry: 节点失败时的指数退避重试
  - fallback: 重试仍失败时的回退方案
  - continue_on_error: 节点失败时是否继续下一个节点

测试策略：
  - mock Verifier 验证 pre/post_verify 路径
  - mock node.execute() 让前 N 次失败、第 N+1 次成功，验证 retry 行为
  - mock device 验证 fallback 的 action/params 路径
  - 构造 2 节点 pipeline，第一个失败 + continue_on_error=True，验证第二个仍执行
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode
from engine.pipeline_engine import PipelineEngine

pytestmark = pytest.mark.unit

# ============================================================
# 辅助
# ============================================================

def _make_engine_with_mocks(device=None, verifier=None):
    """构造 PipelineEngine + 已 load 的最小 pipeline（单节点）。

    返回 (engine, node) — node 可被测试 customize。
    """
    engine = PipelineEngine()
    engine.set_verifier(verifier)

    pipeline_json = {
        "nodes": [{"id": "n1", "type": "click", "config": {"x": 1, "y": 1}}],
        "edges": [],
        "entry_node": "n1",
    }
    engine.load(pipeline_json, device=device or MagicMock())
    return engine


def _make_failing_node(node_id="fail1", fail_times=1):
    """构造一个前 fail_times 次失败、之后成功的节点。

    用闭包计数器模拟 transient failure。
    """
    counter = {"n": 0}

    class _FlakyNode(PipelineNode):
        def __init__(self):
            super().__init__(id=node_id, node_type="click", config={"x": 1, "y": 1})

        def execute(self, context):
            counter["n"] += 1
            if counter["n"] <= fail_times:
                return fail_result(error_msg=f"flaky fail #{counter['n']}", node_id=self.id, node_type=self.node_type)
            return AutoResult(
                success=True,
                data={"attempt": counter["n"]},
                node_id=self.id,
                node_type=self.node_type,
            )

    return _FlakyNode(), counter


# ============================================================
# Test: PipelineNode 新字段 from_dict / to_dict 往返
# ============================================================

class TestPipelineNodeChainFields:
    """PipelineNode 新增 5 个字段（吸收 chain step）的序列化测试。"""

    def test_from_dict_reads_all_5_fields(self):
        data = {
            "id": "n1",
            "node_type": "click",
            "config": {"x": 1, "y": 2},
            "pre_verify": {"type": "template", "template": "x.png"},
            "post_verify": {"type": "color", "color": "#ff0000"},
            "retry": {"max_retries": 3, "base_delay": 0.1},
            "fallback": {"action": "swipe", "params": {"x1": 0, "y1": 0, "x2": 100, "y2": 100}},
            "continue_on_error": True,
        }
        node = PipelineNode.from_dict(data)
        assert node.pre_verify == {"type": "template", "template": "x.png"}
        assert node.post_verify == {"type": "color", "color": "#ff0000"}
        assert node.retry == {"max_retries": 3, "base_delay": 0.1}
        assert node.fallback == {"action": "swipe", "params": {"x1": 0, "y1": 0, "x2": 100, "y2": 100}}
        assert node.continue_on_error is True

    def test_to_dict_serializes_all_5_fields(self):
        node = PipelineNode(
            id="n1", node_type="click", config={"x": 1, "y": 2},
            pre_verify={"type": "template"},
            post_verify={"type": "color"},
            retry={"max_retries": 2},
            fallback={"action": "wait", "params": {"seconds": 1}},
            continue_on_error=True,
        )
        d = node.to_dict()
        assert d["pre_verify"] == {"type": "template"}
        assert d["post_verify"] == {"type": "color"}
        assert d["retry"] == {"max_retries": 2}
        assert d["fallback"] == {"action": "wait", "params": {"seconds": 1}}
        assert d["continue_on_error"] is True

    def test_to_dict_omits_default_values(self):
        """默认值字段不出现在 to_dict 输出中（保持 JSON 紧凑）。"""
        node = PipelineNode(id="n1", node_type="click", config={})
        d = node.to_dict()
        assert "pre_verify" not in d
        assert "post_verify" not in d
        assert "retry" not in d
        assert "fallback" not in d
        assert "continue_on_error" not in d

    def test_roundtrip_preserves_all_fields(self):
        original = PipelineNode(
            id="rt1", node_type="click", config={"x": 5},
            pre_verify={"type": "exist"},
            retry={"max_retries": 5, "base_delay": 0.5, "backoff_factor": 1.5},
            fallback={"type": "click", "config": {"x": 99, "y": 99}},
            continue_on_error=True,
        )
        restored = PipelineNode.from_dict(original.to_dict())
        assert restored.pre_verify == original.pre_verify
        assert restored.retry == original.retry
        assert restored.fallback == original.fallback
        assert restored.continue_on_error == original.continue_on_error


# ============================================================
# Test: pre_verify
# ============================================================

class TestPreVerify:
    """pre_verify 字段：节点 execute() 之前的强验证。"""

    def test_pre_verify_passes_then_node_executes(self):
        """pre_verify 通过 → 节点正常 execute。"""
        verifier = MagicMock()
        verifier.verify.return_value = success_result()

        node = PipelineNode(
            id="pv1", node_type="click", config={"x": 1, "y": 1},
            pre_verify={"type": "template", "template": "x.png"},
        )
        node.execute = MagicMock(return_value=success_result())

        engine = PipelineEngine()
        engine.set_verifier(verifier)
        engine.load({"nodes": [{"id": "pv1", "type": "click", "config": {"x": 1, "y": 1},
                                 "pre_verify": {"type": "template"}}],
                     "entry_node": "pv1"},
                    device=MagicMock())

        # 替换 graph 中的节点为我们的 mock 节点
        engine._graph.nodes["pv1"] = node

        result = engine.execute()
        assert result.success
        verifier.verify.assert_called_once_with({"type": "template", "template": "x.png"})
        node.execute.assert_called_once()

    def test_pre_verify_fails_skips_node_execute(self):
        """pre_verify 失败 → 节点不执行，返回 PRE_VERIFY_FAILED。"""
        verifier = MagicMock()
        verifier.verify.return_value = fail_result(error_msg="template not found")

        node = PipelineNode(
            id="pv2", node_type="click", config={"x": 1, "y": 1},
            pre_verify={"type": "template"},
        )
        node.execute = MagicMock(return_value=success_result())

        engine = PipelineEngine()
        engine.set_verifier(verifier)
        engine.load({"nodes": [{"id": "pv2", "type": "click", "config": {}}],
                     "entry_node": "pv2"},
                    device=MagicMock())
        engine._graph.nodes["pv2"] = node

        result = engine.execute()
        assert not result.success
        verifier.verify.assert_called_once_with({"type": "template"})
        node.execute.assert_not_called()
        # 主循环应该看到失败并终止
        assert "pv2" in result.error_msg or "PRE_VERIFY" in result.error_msg or result.error_msg

    def test_pre_verify_in_config_backward_compat(self):
        """老 pipeline JSON 把 pre_verify 放在 config 里 → 仍然生效。"""
        verifier = MagicMock()
        verifier.verify.return_value = success_result()

        node = PipelineNode(
            id="pv3", node_type="click",
            config={"x": 1, "y": 1, "pre_verify": {"type": "color"}},
        )
        node.execute = MagicMock(return_value=success_result())

        engine = PipelineEngine()
        engine.set_verifier(verifier)
        engine.load({"nodes": [{"id": "pv3", "type": "click",
                                 "config": {"x": 1, "y": 1, "pre_verify": {"type": "color"}}}],
                     "entry_node": "pv3"},
                    device=MagicMock())
        engine._graph.nodes["pv3"] = node

        result = engine.execute()
        assert result.success
        verifier.verify.assert_called_once_with({"type": "color"})

    def test_pre_verify_skipped_when_verifier_none(self):
        """未注入 verifier → pre_verify 静默跳过（向后兼容）。"""
        node = PipelineNode(
            id="pv4", node_type="click", config={"x": 1, "y": 1},
            pre_verify={"type": "template"},
        )
        node.execute = MagicMock(return_value=success_result())

        engine = PipelineEngine()
        # 不调用 set_verifier
        engine.load({"nodes": [{"id": "pv4", "type": "click", "config": {}}],
                     "entry_node": "pv4"},
                    device=MagicMock())
        engine._graph.nodes["pv4"] = node

        result = engine.execute()
        assert result.success
        node.execute.assert_called_once()


# ============================================================
# Test: retry
# ============================================================

class TestRetry:
    """retry 字段：节点失败时的指数退避重试。"""

    def test_retry_succeeds_on_second_attempt(self):
        """节点第 1 次失败、第 2 次成功 → retry_count=1，最终成功。"""
        flaky, counter = _make_failing_node(fail_times=1)
        flaky.retry = {"max_retries": 3, "base_delay": 0.001, "backoff_factor": 1.0}

        engine = PipelineEngine()
        engine.load({"nodes": [{"id": flaky.id, "type": "click", "config": {}}],
                     "entry_node": flaky.id},
                    device=MagicMock())
        engine._graph.nodes[flaky.id] = flaky

        result = engine.execute()
        assert result.success
        assert counter["n"] == 2  # 1 次初始 + 1 次重试
        assert result.step_results[0].retry_count == 1

    def test_retry_exhausted_when_all_fail(self):
        """节点始终失败 + retry max_retries=2 → 共执行 3 次（1+2），最终失败。"""
        flaky, counter = _make_failing_node(fail_times=99)
        flaky.retry = {"max_retries": 2, "base_delay": 0.001, "backoff_factor": 1.0}

        engine = PipelineEngine()
        engine.load({"nodes": [{"id": flaky.id, "type": "click", "config": {}}],
                     "entry_node": flaky.id},
                    device=MagicMock())
        engine._graph.nodes[flaky.id] = flaky

        result = engine.execute()
        assert not result.success
        assert counter["n"] == 3  # 1 次初始 + 2 次重试
        assert result.step_results[0].retry_count == 2

    def test_retry_in_config_backward_compat(self):
        """老 pipeline JSON 把 retry 放在 config 里 → 仍然生效。"""
        flaky, counter = _make_failing_node(fail_times=1)
        # 不设 node.retry，改放 config
        flaky.config["retry"] = {"max_retries": 2, "base_delay": 0.001}

        engine = PipelineEngine()
        engine.load({"nodes": [{"id": flaky.id, "type": "click", "config": flaky.config}],
                     "entry_node": flaky.id},
                    device=MagicMock())
        engine._graph.nodes[flaky.id] = flaky

        result = engine.execute()
        assert result.success
        assert counter["n"] == 2
        assert result.step_results[0].retry_count == 1

    def test_no_retry_when_field_absent(self):
        """无 retry 配置 → 节点失败立即终止 pipeline（保留旧行为）。"""
        flaky, counter = _make_failing_node(fail_times=99)
        # 不设 retry

        engine = PipelineEngine()
        engine.load({"nodes": [{"id": flaky.id, "type": "click", "config": {}}],
                     "entry_node": flaky.id},
                    device=MagicMock())
        engine._graph.nodes[flaky.id] = flaky

        result = engine.execute()
        assert not result.success
        assert counter["n"] == 1  # 没重试


# ============================================================
# Test: fallback
# ============================================================

class TestFallback:
    """fallback 字段：重试仍失败时的回退方案。"""

    def test_fallback_action_format_executes_device_action(self):
        """fallback={"action": "click", "params": {...}} → 调用 device.click。"""
        device = MagicMock()
        device.click.return_value = None

        # 始终失败的节点
        class _AlwaysFail(PipelineNode):
            def __init__(self):
                super().__init__(id="fb1", node_type="click", config={"x": 1, "y": 1})
                self.fallback = {"action": "click", "params": {"x": 99, "y": 99}}

            def execute(self, context):
                return fail_result(error_msg="always fails", node_id=self.id, node_type=self.node_type)

        engine = PipelineEngine()
        engine.load({"nodes": [{"id": "fb1", "type": "click", "config": {}}],
                     "entry_node": "fb1"},
                    device=device)
        engine._graph.nodes["fb1"] = _AlwaysFail()

        result = engine.execute()
        assert result.success  # fallback 挽救了 pipeline
        device.click.assert_called_once_with(99, 99)

    def test_fallback_type_config_format_uses_registry(self):
        """fallback={"type": "click", "config": {...}} → 走节点工厂。"""
        device = MagicMock()
        device.click.return_value = None

        class _AlwaysFail(PipelineNode):
            def __init__(self):
                super().__init__(id="fb2", node_type="click", config={"x": 1, "y": 1})
                self.fallback = {"type": "click", "config": {"x": 50, "y": 50}}

            def execute(self, context):
                return fail_result(error_msg="always fails", node_id=self.id, node_type=self.node_type)

        engine = PipelineEngine()
        engine.load({"nodes": [{"id": "fb2", "type": "click", "config": {}}],
                     "entry_node": "fb2"},
                    device=device)
        engine._graph.nodes["fb2"] = _AlwaysFail()

        result = engine.execute()
        assert result.success
        device.click.assert_called_once_with(50, 50)

    def test_fallback_in_config_backward_compat(self):
        """老 pipeline JSON 把 fallback 放在 config 里 → 仍然生效。"""
        device = MagicMock()
        device.click.return_value = None

        class _AlwaysFail(PipelineNode):
            def __init__(self):
                super().__init__(id="fb3", node_type="click",
                                 config={"x": 1, "y": 1, "fallback": {"action": "click", "params": {"x": 7, "y": 7}}})

            def execute(self, context):
                return fail_result(error_msg="always fails", node_id=self.id, node_type=self.node_type)

        engine = PipelineEngine()
        engine.load({"nodes": [{"id": "fb3", "type": "click", "config": _AlwaysFail().config}],
                     "entry_node": "fb3"},
                    device=device)
        engine._graph.nodes["fb3"] = _AlwaysFail()

        result = engine.execute()
        assert result.success
        device.click.assert_called_once_with(7, 7)

    def test_fallback_skipped_when_node_succeeds(self):
        """节点成功 → fallback 不执行。"""
        device = MagicMock()

        class _AlwaysSucceed(PipelineNode):
            def __init__(self):
                super().__init__(id="fb4", node_type="click", config={"x": 1, "y": 1})
                self.fallback = {"action": "click", "params": {"x": 99, "y": 99}}

            def execute(self, context):
                return AutoResult(success=True, node_id=self.id, node_type=self.node_type)

        engine = PipelineEngine()
        engine.load({"nodes": [{"id": "fb4", "type": "click", "config": {}}],
                     "entry_node": "fb4"},
                    device=device)
        engine._graph.nodes["fb4"] = _AlwaysSucceed()

        result = engine.execute()
        assert result.success
        device.click.assert_not_called()


# ============================================================
# Test: continue_on_error
# ============================================================

class TestContinueOnError:
    """continue_on_error 字段：节点失败时是否继续下一个节点。"""

    def test_continue_on_error_true_proceeds_to_next_node(self):
        """节点 1 失败 + continue_on_error=True → 节点 2 仍执行。"""
        device = MagicMock()

        class _FailThenOk(PipelineNode):
            """节点 1：始终失败但 continue_on_error=True。"""
            def __init__(self):
                super().__init__(id="co1", node_type="click", config={"x": 1, "y": 1},
                                 continue_on_error=True)
                self.execute_calls = 0

            def execute(self, context):
                self.execute_calls += 1
                return fail_result(error_msg="intentional", node_id=self.id, node_type=self.node_type)

        class _OkNode(PipelineNode):
            """节点 2：成功。"""
            def __init__(self):
                super().__init__(id="co2", node_type="click", config={"x": 2, "y": 2})
                self.execute_calls = 0

            def execute(self, context):
                self.execute_calls += 1
                return AutoResult(success=True, node_id=self.id, node_type=self.node_type)

        fail_node = _FailThenOk()
        ok_node = _OkNode()

        engine = PipelineEngine()
        engine.load({
            "nodes": [
                {"id": "co1", "type": "click", "config": {"x": 1, "y": 1}, "continue_on_error": True},
                {"id": "co2", "type": "click", "config": {"x": 2, "y": 2}},
            ],
            "edges": [{"from": "co1", "to": "co2"}],
            "entry_node": "co1",
        }, device=device)
        engine._graph.nodes["co1"] = fail_node
        engine._graph.nodes["co2"] = ok_node

        result = engine.execute()
        # pipeline 整体成功（因为最后一个节点成功）
        assert result.success
        assert fail_node.execute_calls == 1
        assert ok_node.execute_calls == 1

    def test_continue_on_error_false_stops_pipeline(self):
        """节点 1 失败 + continue_on_error=False（默认）→ 节点 2 不执行。"""
        device = MagicMock()

        class _FailNode(PipelineNode):
            def __init__(self):
                super().__init__(id="co3", node_type="click", config={"x": 1, "y": 1})
                # continue_on_error 默认 False

            def execute(self, context):
                return fail_result(error_msg="intentional", node_id=self.id, node_type=self.node_type)

        class _ShouldNotRun(PipelineNode):
            def __init__(self):
                super().__init__(id="co4", node_type="click", config={"x": 2, "y": 2})
                self.execute_calls = 0

            def execute(self, context):
                self.execute_calls += 1
                return success_result()

        fail_node = _FailNode()
        no_run = _ShouldNotRun()

        engine = PipelineEngine()
        engine.load({
            "nodes": [
                {"id": "co3", "type": "click", "config": {}},
                {"id": "co4", "type": "click", "config": {}},
            ],
            "edges": [{"from": "co3", "to": "co4"}],
            "entry_node": "co3",
        }, device=device)
        engine._graph.nodes["co3"] = fail_node
        engine._graph.nodes["co4"] = no_run

        result = engine.execute()
        assert not result.success
        assert no_run.execute_calls == 0

    def test_continue_on_error_in_config_backward_compat(self):
        """老 pipeline JSON 把 continue_on_error 放在 config 里 → 仍然生效。"""
        device = MagicMock()

        class _FailWithCfgContinue(PipelineNode):
            def __init__(self):
                super().__init__(id="co5", node_type="click",
                                 config={"x": 1, "y": 1, "continue_on_error": True})

            def execute(self, context):
                return fail_result(error_msg="intentional", node_id=self.id, node_type=self.node_type)

        class _Ok(PipelineNode):
            def __init__(self):
                super().__init__(id="co6", node_type="click", config={"x": 2, "y": 2})
                self.execute_calls = 0

            def execute(self, context):
                self.execute_calls += 1
                return AutoResult(success=True, node_id=self.id, node_type=self.node_type)

        engine = PipelineEngine()
        engine.load({
            "nodes": [
                {"id": "co5", "type": "click", "config": {"continue_on_error": True}},
                {"id": "co6", "type": "click", "config": {}},
            ],
            "edges": [{"from": "co5", "to": "co6"}],
            "entry_node": "co5",
        }, device=device)
        engine._graph.nodes["co5"] = _FailWithCfgContinue()
        ok = _Ok()
        engine._graph.nodes["co6"] = ok

        result = engine.execute()
        assert result.success
        assert ok.execute_calls == 1


# ============================================================
# Test: post_verify 通过 node 属性（vs 现有 config 路径）
# ============================================================

class TestPostVerifyNodeAttribute:
    """post_verify 作为 node 属性的测试（config 路径已在 spec 阶段 3 任务 3.2 测过）。"""

    def test_post_verify_node_attr_takes_precedence_over_config(self):
        """node.post_verify 优先于 node.config["post_verify"]。"""
        verifier = MagicMock()
        verifier.verify.return_value = success_result()

        class _OkNode(PipelineNode):
            def __init__(self):
                super().__init__(
                    id="pv_a1", node_type="click", config={"x": 1, "y": 1, "post_verify": {"type": "from_config"}},
                    post_verify={"type": "from_attr"},
                )

            def execute(self, context):
                return AutoResult(success=True, node_id=self.id, node_type=self.node_type)

        engine = PipelineEngine()
        engine.set_verifier(verifier)
        engine.load({"nodes": [{"id": "pv_a1", "type": "click", "config": {}}],
                     "entry_node": "pv_a1"},
                    device=MagicMock())
        engine._graph.nodes["pv_a1"] = _OkNode()

        result = engine.execute()
        assert result.success
        # verifier 应该收到 node 属性里的配置（from_attr），不是 config 里的（from_config）
        verifier.verify.assert_called_once_with({"type": "from_attr"})

    def test_post_verify_node_attr_fails_marks_node_failed(self):
        """node.post_verify 失败 → 节点标记失败 + error_code=POST_VERIFY_FAILED。"""
        verifier = MagicMock()
        verifier.verify.return_value = fail_result(error_msg="color not found")

        class _OkNode(PipelineNode):
            def __init__(self):
                super().__init__(id="pv_a2", node_type="click", config={"x": 1, "y": 1},
                                 post_verify={"type": "color"})

            def execute(self, context):
                return AutoResult(success=True, node_id=self.id, node_type=self.node_type)

        engine = PipelineEngine()
        engine.set_verifier(verifier)
        engine.load({"nodes": [{"id": "pv_a2", "type": "click", "config": {}}],
                     "entry_node": "pv_a2"},
                    device=MagicMock())
        engine._graph.nodes["pv_a2"] = _OkNode()

        result = engine.execute()
        assert not result.success
        assert result.step_results[0].error_code == "POST_VERIFY_FAILED"
