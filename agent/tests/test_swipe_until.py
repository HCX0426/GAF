"""swipe_until node tests — swipe loop until any template matches.

Uses test-only mocks that temporarily replace the template_match_any and
swipe registrations via fixtures, so the swipe-loop logic can be verified
without OpenCV / device dependencies and without leaking mocks into other
test modules. ``time.sleep`` is monkeypatched to a no-op so tests run fast.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import engine.nodes to trigger @register_node side effects for all nodes
# (including swipe_until).
import engine.nodes  # noqa: F401
from core.result import fail_result, success_result
from engine.context import PipelineContext
from engine.node import PIPELINE_NODE_REGISTRY, PipelineNode

pytestmark = pytest.mark.e2e

# ============================================================
# Mock template_match_any node (call-count aware)
# ============================================================

class _CallCountMatchNode(PipelineNode):
    """Mock template_match_any that succeeds on a configurable call.

    Tests set the class attribute ``succeed_at_call`` (1-based) to control
    which match attempt succeeds. Call 1 is the first match attempt (before
    any swipe), call 2 is after one swipe, etc. ``succeed_at_call=0`` means
    "never succeed" (exhaust all swipes). Default is 1 (immediate success).
    """

    node_type: str = "template_match_any"
    succeed_at_call: int = 1
    call_count: int = 0

    def execute(self, context):
        type(self).call_count += 1
        if type(self).succeed_at_call > 0 and type(self).call_count >= type(self).succeed_at_call:
            data = {"confidence": 0.9, "center": [100, 200],
                    "template": self.config.get("templates", ["?"])[0]}
            context.set_variable(f"{self.id}_match_result", data)
            return success_result(data={"winner": {"data": data}, "matched": True})
        return fail_result(error_msg=f"mock match fail (call {type(self).call_count})")


class _CapturingSwipeNode(PipelineNode):
    """Mock swipe node that records each call and always succeeds."""

    node_type: str = "swipe"
    calls: list = []

    def execute(self, context):
        type(self).calls.append(dict(self.config))
        return success_result(data={"swiped": True})


class _FailingSwipeNode(PipelineNode):
    """Mock swipe node that always fails (to test swipe-error tolerance)."""

    node_type: str = "swipe"

    def execute(self, context):
        return fail_result(error_msg="mock swipe fail")


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_match_and_swipe():
    """Replace template_match_any + swipe with mocks; reset counters.

    The test sets ``_CallCountMatchNode.succeed_at_call`` to control when
    the match succeeds. Default is 1 (immediate success, no swipe).
    """
    real_match = PIPELINE_NODE_REGISTRY["template_match_any"]
    real_swipe = PIPELINE_NODE_REGISTRY["swipe"]
    PIPELINE_NODE_REGISTRY["template_match_any"] = _CallCountMatchNode
    PIPELINE_NODE_REGISTRY["swipe"] = _CapturingSwipeNode
    _CallCountMatchNode.succeed_at_call = 1
    _CallCountMatchNode.call_count = 0
    _CapturingSwipeNode.calls = []
    yield
    PIPELINE_NODE_REGISTRY["template_match_any"] = real_match
    PIPELINE_NODE_REGISTRY["swipe"] = real_swipe
    _CallCountMatchNode.succeed_at_call = 1
    _CallCountMatchNode.call_count = 0
    _CapturingSwipeNode.calls = []


@pytest.fixture
def mock_match_and_failing_swipe():
    """Like mock_match_and_swipe but swipe always fails."""
    real_match = PIPELINE_NODE_REGISTRY["template_match_any"]
    real_swipe = PIPELINE_NODE_REGISTRY["swipe"]
    PIPELINE_NODE_REGISTRY["template_match_any"] = _CallCountMatchNode
    PIPELINE_NODE_REGISTRY["swipe"] = _FailingSwipeNode
    _CallCountMatchNode.succeed_at_call = 1
    _CallCountMatchNode.call_count = 0
    yield
    PIPELINE_NODE_REGISTRY["template_match_any"] = real_match
    PIPELINE_NODE_REGISTRY["swipe"] = real_swipe
    _CallCountMatchNode.succeed_at_call = 1
    _CallCountMatchNode.call_count = 0


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Replace time.sleep with a no-op so tests don't wait delay_between."""
    import engine.nodes.swipe_until as su
    monkeypatch.setattr(su.time, "sleep", lambda *_args, **_kw: None)


def _swipe_until_node(templates=None, **config):
    """Build a swipe_until node spec with sensible test defaults."""
    if templates is None:
        templates = ["t1.png"]
    defaults = {
        "x1": 100, "y1": 500, "x2": 100, "y2": 200,
        "duration": 200,
        "max_swipes": 2,
        "delay_between": 0.5,
    }
    defaults.update(config)
    return {
        "id": "su1",
        "node_type": "swipe_until",
        "config": {"templates": templates, **defaults},
    }


# ============================================================
# Test: registration
# ============================================================

class TestRegistration:
    def test_swipe_until_registered(self):
        assert "swipe_until" in PIPELINE_NODE_REGISTRY

    def test_swipe_until_class(self):
        cls = PIPELINE_NODE_REGISTRY["swipe_until"]
        assert cls.__name__ == "SwipeUntilNode"


# ============================================================
# Test: empty templates
# ============================================================

class TestEmptyTemplates:
    def test_empty_templates_returns_fail(self):
        node = PipelineNode.create(_swipe_until_node(templates=[]))
        result = node.execute(PipelineContext())
        assert not result.success
        assert "non-empty" in result.error_msg


# ============================================================
# Test: match/swipe loop scenarios
# ============================================================

class TestSwipeLoop:
    def test_match_before_first_swipe(self, mock_match_and_swipe):
        # succeed_at_call=1 (default) -> match succeeds immediately, no swipe.
        node = PipelineNode.create(_swipe_until_node(["t1.png"], max_swipes=3))
        result = node.execute(PipelineContext())
        assert result.success
        assert result.data["matched"] is True
        assert result.data["swipes_performed"] == 0
        assert len(_CapturingSwipeNode.calls) == 0

    def test_match_after_one_swipe(self, mock_match_and_swipe):
        # succeed_at_call=2 -> first match fails, swipe, then match wins.
        _CallCountMatchNode.succeed_at_call = 2
        node = PipelineNode.create(_swipe_until_node(["t1.png"], max_swipes=3))
        result = node.execute(PipelineContext())
        assert result.success
        assert result.data["matched"] is True
        assert result.data["swipes_performed"] == 1
        assert len(_CapturingSwipeNode.calls) == 1

    def test_match_after_two_swipes(self, mock_match_and_swipe):
        _CallCountMatchNode.succeed_at_call = 3
        node = PipelineNode.create(_swipe_until_node(["t1.png"], max_swipes=3))
        result = node.execute(PipelineContext())
        assert result.success
        assert result.data["swipes_performed"] == 2
        assert len(_CapturingSwipeNode.calls) == 2

    def test_max_swipes_exhausted(self, mock_match_and_swipe):
        # succeed_at_call=0 -> never succeeds; max_swipes=2 -> 2 swipes.
        _CallCountMatchNode.succeed_at_call = 0
        node = PipelineNode.create(_swipe_until_node(["t1.png"], max_swipes=2))
        result = node.execute(PipelineContext())
        assert not result.success
        assert result.data["matched"] is False
        assert result.data["swipes_performed"] == 2
        # 3 match attempts (before swipe 1, before swipe 2, after swipe 2)
        # + 2 swipe calls.
        assert len(_CapturingSwipeNode.calls) == 2
        assert _CallCountMatchNode.call_count == 3


# ============================================================
# Test: context variable + swipe failure tolerance
# ============================================================

class TestContextAndTolerance:
    def test_sets_context_variable_on_success(self, mock_match_and_swipe):
        ctx = PipelineContext()
        node = PipelineNode.create(_swipe_until_node(["t1.png"], max_swipes=1))
        node.execute(ctx)
        assert "su1_match_result" in ctx.variables
        assert ctx.variables["su1_match_result"]["template"] == "t1.png"

    def test_no_context_variable_on_failure(self, mock_match_and_swipe):
        _CallCountMatchNode.succeed_at_call = 0
        ctx = PipelineContext()
        node = PipelineNode.create(_swipe_until_node(["t1.png"], max_swipes=1))
        node.execute(ctx)
        assert "su1_match_result" not in ctx.variables

    def test_swipe_failure_does_not_abort_loop(self, mock_match_and_failing_swipe):
        # Swipe child fails but loop continues; match still attempted after.
        # succeed_at_call=2 -> match fails first, swipe (fails), match wins.
        _CallCountMatchNode.succeed_at_call = 2
        node = PipelineNode.create(_swipe_until_node(["t1.png"], max_swipes=1))
        result = node.execute(PipelineContext())
        assert result.success
        assert result.data["swipes_performed"] == 1


# ============================================================
# Test: swipe config forwarding
# ============================================================

class TestSwipeConfigForwarding:
    def test_swipe_coordinates_forwarded(self, mock_match_and_swipe):
        _CallCountMatchNode.succeed_at_call = 0  # force a swipe
        node = PipelineNode.create(_swipe_until_node(
            ["t1.png"], max_swipes=1,
            x1=10, y1=20, x2=30, y2=40, duration=500))
        node.execute(PipelineContext())
        swipe_cfg = _CapturingSwipeNode.calls[0]
        assert swipe_cfg["x1"] == 10
        assert swipe_cfg["y1"] == 20
        assert swipe_cfg["x2"] == 30
        assert swipe_cfg["y2"] == 40
        assert swipe_cfg["duration"] == 500
