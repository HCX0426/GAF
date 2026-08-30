"""template_match_any node tests — multi-template first-match-wins logic.

Uses a test-only mock that temporarily replaces the template_match
registration via monkeypatch, so composite logic can be verified without
OpenCV / device dependencies and without leaking the mock into other test
modules.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import engine.nodes to trigger @register_node side effects for all nodes
# (including template_match_any).
import engine.nodes  # noqa: F401
from core.result import fail_result, success_result
from engine.context import PipelineContext
from engine.node import PIPELINE_NODE_REGISTRY, PipelineNode

pytestmark = pytest.mark.unit

# ============================================================
# Mock template_match node (path-aware)
# ============================================================

class _MockTemplateMatchNode(PipelineNode):
    """Mock whose success depends on the template path.

    Path containing "fail"  -> failure.
    Path containing "win"   -> success (confidence 0.9).
    Other paths             -> success (confidence 0.85).

    Mimics the real TemplateMatchNode contract enough for
    template_match_any to consume: writes a {id}_match_result variable and
    returns data with a confidence field on success.
    """

    node_type: str = "template_match"

    def execute(self, context):
        path = self.config.get("template", "")
        if "fail" in path:
            return fail_result(error_msg=f"mock fail for {path}")
        confidence = 0.9 if "win" in path else 0.85
        data = {"confidence": confidence, "center": [100, 200], "template": path}
        context.set_variable(f"{self.id}_match_result", data)
        return success_result(data=data)


class _CapturingTemplateMatchNode(PipelineNode):
    """Mock that captures its config into a list for forwarding assertions."""

    node_type: str = "template_match"

    # Class-level capture list; tests reset it before use.
    captured: list = []

    def execute(self, context):
        type(self).captured.append(dict(self.config))
        return success_result(data={"confidence": 0.9})


@pytest.fixture
def mock_template_match():
    """Replace template_match with _MockTemplateMatchNode for one test."""
    real = PIPELINE_NODE_REGISTRY["template_match"]
    PIPELINE_NODE_REGISTRY["template_match"] = _MockTemplateMatchNode
    yield
    PIPELINE_NODE_REGISTRY["template_match"] = real


@pytest.fixture
def capturing_template_match():
    """Replace template_match with a config-capturing mock for one test."""
    real = PIPELINE_NODE_REGISTRY["template_match"]
    PIPELINE_NODE_REGISTRY["template_match"] = _CapturingTemplateMatchNode
    _CapturingTemplateMatchNode.captured = []
    yield _CapturingTemplateMatchNode
    PIPELINE_NODE_REGISTRY["template_match"] = real
    _CapturingTemplateMatchNode.captured = []


def _any_node(templates, **config):
    """Build a template_match_any node spec."""
    return {
        "id": "tma1",
        "node_type": "template_match_any",
        "config": {"templates": templates, **config},
    }


# ============================================================
# Test: registration
# ============================================================

class TestRegistration:
    def test_template_match_any_registered(self):
        assert "template_match_any" in PIPELINE_NODE_REGISTRY

    def test_template_match_any_class(self):
        cls = PIPELINE_NODE_REGISTRY["template_match_any"]
        assert cls.__name__ == "TemplateMatchAnyNode"


# ============================================================
# Test: empty templates
# ============================================================

class TestEmptyTemplates:
    def test_empty_templates_returns_fail(self):
        node = PipelineNode.create(_any_node([]))
        result = node.execute(PipelineContext())
        assert not result.success
        assert "non-empty" in result.error_msg


# ============================================================
# Test: first-match-wins scenarios
# ============================================================

class TestFirstMatchWins:
    def test_first_template_succeeds(self, mock_template_match):
        node = PipelineNode.create(_any_node(["a.png", "b.png"]))
        result = node.execute(PipelineContext())
        assert result.success
        assert result.data["matched"] is True
        assert result.data["winner"]["template"] == "a.png"
        # Short-circuit: only 1 child attempted.
        assert result.data["count"] == 1

    def test_second_template_succeeds_after_first_fail(self, mock_template_match):
        node = PipelineNode.create(_any_node(["fail1.png", "win1.png"]))
        result = node.execute(PipelineContext())
        assert result.success
        assert result.data["winner"]["template"] == "win1.png"
        assert result.data["count"] == 2

    def test_all_fail(self, mock_template_match):
        node = PipelineNode.create(_any_node(["fail1.png", "fail2.png", "fail3.png"]))
        result = node.execute(PipelineContext())
        assert not result.success
        assert result.data["matched"] is False
        assert result.data["count"] == 3

    def test_sets_context_variable_on_success(self, mock_template_match):
        ctx = PipelineContext()
        node = PipelineNode.create(_any_node(["win1.png"]))
        node.execute(ctx)
        # Variable name follows the {id}_match_result convention.
        assert "tma1_match_result" in ctx.variables
        assert ctx.variables["tma1_match_result"]["template"] == "win1.png"

    def test_no_context_variable_on_failure(self, mock_template_match):
        ctx = PipelineContext()
        node = PipelineNode.create(_any_node(["fail1.png"]))
        node.execute(ctx)
        assert "tma1_match_result" not in ctx.variables


# ============================================================
# Test: config forwarding
# ============================================================

class TestConfigForwarding:
    def test_threshold_forwarded(self, capturing_template_match):
        node = PipelineNode.create(_any_node(["x.png"], threshold=0.92))
        node.execute(PipelineContext())
        assert capturing_template_match.captured[0]["threshold"] == 0.92

    def test_click_on_match_forwarded(self, capturing_template_match):
        node = PipelineNode.create(_any_node(["x.png"], click_on_match=True))
        node.execute(PipelineContext())
        assert capturing_template_match.captured[0]["click_on_match"] is True

    def test_roi_forwarded(self, capturing_template_match):
        roi = [10, 20, 100, 50]
        node = PipelineNode.create(_any_node(["x.png"], roi=roi))
        node.execute(PipelineContext())
        assert capturing_template_match.captured[0]["roi"] == roi

    def test_roi_absent_not_forwarded(self, capturing_template_match):
        node = PipelineNode.create(_any_node(["x.png"]))
        node.execute(PipelineContext())
        assert "roi" not in capturing_template_match.captured[0]

    def test_roi_coord_type_forwarded(self, capturing_template_match):
        node = PipelineNode.create(_any_node(["x.png"], roi_coord_type="base"))
        node.execute(PipelineContext())
        assert capturing_template_match.captured[0]["roi_coord_type"] == "base"
