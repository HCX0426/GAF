"""Tests for LLM auto-heal integration (spec S2 / P0-2).

Verifies the ``WorkerLlmClient`` activation per spec S2 / P0-2
(archived: ai-architecture-defects spec):

1. ``WorkerLlmClient.diagnose_failure()`` — prompt construction, response
   parsing, error fallbacks (network / config-missing / malformed reply).
2. ``TemplateMatchNode._llm_diagnose_match_failure()`` — non-blocking
   when ``context.llm_client`` is None; delegates when set; attaches
   diagnosis to fail_result.data.
3. ``TaskOrchestrator._llm_diagnose_pipeline_failure()`` — builds error
   context from PipelineResult, delegates to llm_client, returns None
   on any failure.
4. ``PipelineContext.llm_client`` field — default None, accepted by
   dataclass constructor, not serialized.
5. ``PipelineEngine.load()`` — llm_client kwarg threaded into context
   and re-injected after restore.

All tests mock the HTTP layer — no real backend or LLM calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from engine.context import PipelineContext

# Agent tests run with worker/src on sys.path (see agent/conftest.py).
from ai.llm_client import WorkerLlmClient

pytestmark = pytest.mark.e2e

# ============================================================
# Test fixtures
# ============================================================

class FakeResponse:
    """Minimal urllib response stub for WorkerLlmClient.chat()."""

    def __init__(self, payload: bytes, status: int = 200):
        self._payload = payload
        self.status = status
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._closed = True

    def read(self) -> bytes:
        return self._payload


def make_client() -> WorkerLlmClient:
    """Construct an WorkerLlmClient with a fake server URL + token."""
    return WorkerLlmClient(
        server_url="ws://127.0.0.1:8000/ws/protocol/agents/",
        token="test-token-abc",
    )


# ============================================================
# 1. WorkerLlmClient.diagnose_failure() — response parsing
# ============================================================

class TestDiagnoseFailureParsing:
    """diagnose_failure() parses DIAGNOSIS:/FIX: format correctly."""

    def test_parses_well_formed_response(self):
        """LLM returns DIAGNOSIS: ... FIX: ... — both fields extracted."""
        client = make_client()
        reply_body = {
            "reply": "DIAGNOSIS: Template image too small after scaling.\n"
                     "FIX: Use a larger template image (>= 64x64 pixels).",
            "model": "deepseek-chat",
            "tokens_used": 100,
            "input_tokens": 60,
            "output_tokens": 40,
            "cost": 0.001,
            "timestamp": "2026-07-14T10:00:00Z",
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = FakeResponse(
                json.dumps(reply_body).encode("utf-8"),
            )
            result = client.diagnose_failure({
                "node_type": "template_match",
                "error_msg": "confidence 0.4 < threshold 0.8",
            })

        assert "error" not in result
        assert "template image too small" in result["diagnosis"].lower()
        assert "larger template" in result["suggested_fix"].lower()
        assert result["model"] == "deepseek-chat"
        assert result["raw_reply"] == reply_body["reply"]

    def test_falls_back_to_raw_reply_when_format_missing(self):
        """LLM doesn't follow DIAGNOSIS:/FIX: format — use full reply."""
        client = make_client()
        reply_body = {
            "reply": "The template appears corrupted. Replace it.",
            "model": "deepseek-chat",
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = FakeResponse(
                json.dumps(reply_body).encode("utf-8"),
            )
            result = client.diagnose_failure({"error_msg": "match failed"})

        assert result["diagnosis"] == reply_body["reply"]
        assert result["suggested_fix"] == ""
        assert result["raw_reply"] == reply_body["reply"]

    def test_parses_only_diagnosis_line(self):
        """LLM returns only DIAGNOSIS: (no FIX: line)."""
        client = make_client()
        reply_body = {
            "reply": "DIAGNOSIS: ROI coordinates out of screen bounds.",
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = FakeResponse(
                json.dumps(reply_body).encode("utf-8"),
            )
            result = client.diagnose_failure({"error_msg": "x"})

        assert "out of screen bounds" in result["diagnosis"]
        assert result["suggested_fix"] == ""

    def test_prompt_includes_all_error_context_fields(self):
        """diagnose_failure() should pass all error_context fields to chat()."""
        client = make_client()
        captured_payload = {}

        def fake_urlopen(req, timeout=None):
            captured_payload["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse(json.dumps({"reply": "DIAGNOSIS: x"}).encode())

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.diagnose_failure({
                "node_type": "template_match",
                "error_msg": "conf=0.3",
                "template_name": "guild_btn.png",
                "confidence": 0.3,
                "threshold": 0.8,
                "roi": {"x": 0, "y": 0, "w": 100, "h": 100},
                "diagnostic_report": "METHOD WGC conf=0.3",
                "pipeline_name": "login_flow",
                "structured_log_path": "/tmp/log.jsonl",
                "extra": {"attempt": 3},
            })

        msg = captured_payload["body"]["message"]
        assert "template_match" in msg
        assert "conf=0.3" in msg
        assert "guild_btn.png" in msg
        assert "0.3000" in msg  # confidence formatted to 4 decimals
        assert "0.80" in msg  # threshold formatted to 2 decimals
        assert "WGC conf=0.3" in msg  # diagnostic_report
        assert "login_flow" in msg  # pipeline_name
        assert "/tmp/log.jsonl" in msg  # structured_log_path
        assert "attempt" in msg  # extra


# ============================================================
# 2. WorkerLlmClient.diagnose_failure() — error fallbacks
# ============================================================

class TestDiagnoseFailureErrorFallbacks:
    """diagnose_failure() must NEVER raise — all errors return error dict."""

    def test_network_error_returns_error_dict(self):
        """Backend unreachable — return {'error': ...} without raising."""
        from urllib import error as urllib_error

        client = make_client()
        with patch("urllib.request.urlopen",
                   side_effect=urllib_error.URLError("connection refused")):
            result = client.diagnose_failure({"error_msg": "x"})

        assert "error" in result
        assert result["diagnosis"] == ""
        assert result["suggested_fix"] == ""

    def test_http_error_returns_error_dict(self):
        """Backend returns 500 — return error dict without raising."""
        from urllib import error as urllib_error

        client = make_client()
        http_err = urllib_error.HTTPError(
            url="http://x", code=500, msg="Server Error",
            hdrs=None, fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            result = client.diagnose_failure({"error_msg": "x"})

        assert "error" in result
        assert result["diagnosis"] == ""

    def test_config_missing_response_returns_error_dict(self):
        """Backend reachable but LLM not configured — config_missing flag."""
        client = make_client()
        reply_body = {
            "reply": "",
            "config_missing": True,
            "message": "LLMConfig not set",
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = FakeResponse(
                json.dumps(reply_body).encode("utf-8"),
            )
            result = client.diagnose_failure({"error_msg": "x"})

        assert "error" in result
        assert "not configured" in result["error"].lower()
        assert result["diagnosis"] == ""

    def test_empty_reply_returns_error_dict(self):
        """LLM returns empty reply — return error dict."""
        client = make_client()
        reply_body = {"reply": "", "model": "deepseek-chat"}
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = FakeResponse(
                json.dumps(reply_body).encode("utf-8"),
            )
            result = client.diagnose_failure({"error_msg": "x"})

        assert "error" in result
        assert "empty" in result["error"].lower()


# ============================================================
# 3. TemplateMatchNode._llm_diagnose_match_failure()
# ============================================================

class TestTemplateMatchLLMDiagnosis:
    """template_match LLM diagnosis — non-blocking, attaches to fail_result."""

    def test_returns_none_when_llm_client_not_set(self):
        """No llm_client in context — return None (non-blocking)."""
        from engine.nodes.template_match import TemplateMatchNode

        ctx = PipelineContext()  # llm_client defaults to None
        node = TemplateMatchNode(
            id="tm1", node_type="template_match",
            config={"template": "x.png", "threshold": 0.8},
        )

        result = node._llm_diagnose_match_failure(
            context=ctx,
            original_error="conf 0.3 < 0.8",
            diagnostic_report="report...",
            template_name="x.png",
            confidence=0.3,
            threshold=0.8,
            roi={"x": 0, "y": 0, "w": 100, "h": 100},
        )
        assert result is None

    def test_delegates_to_llm_client_when_set(self):
        """llm_client set — delegate and return diagnosis dict."""
        from engine.nodes.template_match import TemplateMatchNode

        ctx = PipelineContext()
        mock_llm = MagicMock()
        mock_llm.diagnose_failure.return_value = {
            "diagnosis": "Template too small",
            "suggested_fix": "Use larger template",
            "raw_reply": "...",
            "model": "deepseek-chat",
        }
        ctx.llm_client = mock_llm

        node = TemplateMatchNode(
            id="tm1", node_type="template_match",
            config={"template": "x.png", "threshold": 0.8},
        )

        result = node._llm_diagnose_match_failure(
            context=ctx,
            original_error="conf 0.3 < 0.8",
            diagnostic_report="report...",
            template_name="x.png",
            confidence=0.3,
            threshold=0.8,
            roi={"x": 0, "y": 0, "w": 100, "h": 100},
        )

        assert result is not None
        assert result["diagnosis"] == "Template too small"
        assert result["suggested_fix"] == "Use larger template"
        # Verify error_context passed to diagnose_failure
        mock_llm.diagnose_failure.assert_called_once()
        call_args = mock_llm.diagnose_failure.call_args[0][0]
        assert call_args["node_type"] == "template_match"
        assert call_args["template_name"] == "x.png"
        assert call_args["confidence"] == 0.3
        assert call_args["threshold"] == 0.8

    def test_returns_none_when_llm_returns_error(self):
        """LLM unavailable — diagnose_failure returns error dict, we return None."""
        from engine.nodes.template_match import TemplateMatchNode

        ctx = PipelineContext()
        mock_llm = MagicMock()
        mock_llm.diagnose_failure.return_value = {
            "error": "network error",
            "diagnosis": "",
            "suggested_fix": "",
        }
        ctx.llm_client = mock_llm

        node = TemplateMatchNode(
            id="tm1", node_type="template_match",
            config={"template": "x.png"},
        )

        result = node._llm_diagnose_match_failure(
            context=ctx,
            original_error="x",
            diagnostic_report="r",
            template_name="x.png",
            confidence=0.0,
            threshold=0.8,
            roi=None,
        )
        assert result is None

    def test_returns_none_when_llm_raises(self):
        """diagnose_failure raises unexpectedly — return None (non-blocking)."""
        from engine.nodes.template_match import TemplateMatchNode

        ctx = PipelineContext()
        mock_llm = MagicMock()
        mock_llm.diagnose_failure.side_effect = RuntimeError("boom")
        ctx.llm_client = mock_llm

        node = TemplateMatchNode(
            id="tm1", node_type="template_match",
            config={"template": "x.png"},
        )

        result = node._llm_diagnose_match_failure(
            context=ctx,
            original_error="x",
            diagnostic_report="r",
            template_name="x.png",
            confidence=0.0,
            threshold=0.8,
            roi=None,
        )
        assert result is None


# ============================================================
# 4. TaskOrchestrator._llm_diagnose_pipeline_failure()
# ============================================================

class TestOrchestratorLLMDiagnosis:
    """Orchestrator pipeline-failure LLM diagnosis — non-blocking."""

    def test_returns_none_when_llm_returns_error(self):
        """LLM unavailable — return None (don't attach empty diagnosis)."""
        from core.config import WorkerConfig
        from core.orchestrator import TaskOrchestrator
        from devices.manager import DeviceManager
        from image.processor import ImageProcessor

        orch = TaskOrchestrator(
            device_manager=DeviceManager(),
            image_processor=ImageProcessor(),
            config=WorkerConfig(),
        )

        mock_llm = MagicMock()
        mock_llm.diagnose_failure.return_value = {
            "error": "network error",
            "diagnosis": "",
        }

        from engine.pipeline_engine import PipelineResult, PipelineState
        failed_result = PipelineResult(
            success=False,
            state=PipelineState.FAILED,
            error_msg="template_match confidence too low",
        )

        result = orch._llm_diagnose_pipeline_failure(
            llm_client=mock_llm,
            result=failed_result,
            pipeline_json={"metadata": {"pipeline_name": "test"}},
            structured_log_path="/tmp/log.jsonl",
        )
        assert result is None

    def test_returns_diagnosis_on_success(self):
        """LLM returns valid diagnosis — return it for caller to attach."""
        from core.config import WorkerConfig
        from core.orchestrator import TaskOrchestrator
        from devices.manager import DeviceManager
        from engine.pipeline_engine import PipelineResult, PipelineState
        from image.processor import ImageProcessor

        orch = TaskOrchestrator(
            device_manager=DeviceManager(),
            image_processor=ImageProcessor(),
            config=WorkerConfig(),
        )

        mock_llm = MagicMock()
        mock_llm.diagnose_failure.return_value = {
            "diagnosis": "Template missing",
            "suggested_fix": "Re-add template",
            "raw_reply": "...",
            "model": "deepseek-chat",
        }

        failed_result = PipelineResult(
            success=False,
            state=PipelineState.FAILED,
            error_msg="template not found",
        )

        result = orch._llm_diagnose_pipeline_failure(
            llm_client=mock_llm,
            result=failed_result,
            pipeline_json={"metadata": {"pipeline_name": "test"}},
            structured_log_path="/tmp/log.jsonl",
        )
        assert result is not None
        assert result["diagnosis"] == "Template missing"

    def test_returns_none_when_llm_raises(self):
        """diagnose_failure raises — return None (non-blocking)."""
        from core.config import WorkerConfig
        from core.orchestrator import TaskOrchestrator
        from devices.manager import DeviceManager
        from engine.pipeline_engine import PipelineResult, PipelineState
        from image.processor import ImageProcessor

        orch = TaskOrchestrator(
            device_manager=DeviceManager(),
            image_processor=ImageProcessor(),
            config=WorkerConfig(),
        )

        mock_llm = MagicMock()
        mock_llm.diagnose_failure.side_effect = RuntimeError("backend down")

        failed_result = PipelineResult(
            success=False,
            state=PipelineState.FAILED,
            error_msg="x",
        )

        result = orch._llm_diagnose_pipeline_failure(
            llm_client=mock_llm,
            result=failed_result,
            pipeline_json={},
            structured_log_path="",
        )
        assert result is None

    def test_error_context_includes_first_failed_step(self):
        """When a step failed, its error_msg is included in error_context.extra."""
        from core.config import WorkerConfig
        from core.orchestrator import TaskOrchestrator
        from devices.manager import DeviceManager
        from engine.pipeline_engine import PipelineResult, PipelineState
        from image.processor import ImageProcessor

        orch = TaskOrchestrator(
            device_manager=DeviceManager(),
            image_processor=ImageProcessor(),
            config=WorkerConfig(),
        )

        mock_llm = MagicMock()
        mock_llm.diagnose_failure.return_value = {
            "diagnosis": "x", "suggested_fix": "y", "raw_reply": "z",
            "model": "m",
        }

        failed_result = PipelineResult(
            success=False,
            state=PipelineState.FAILED,
            error_msg="pipeline failed",
            step_results=[
                # First step succeeded, second failed
                type("R", (), {"success": True, "error_msg": ""})(),
                type("R", (), {"success": False, "error_msg": "step 2 boom"})(),
            ],
        )

        orch._llm_diagnose_pipeline_failure(
            llm_client=mock_llm,
            result=failed_result,
            pipeline_json={},
            structured_log_path="",
        )

        call_args = mock_llm.diagnose_failure.call_args[0][0]
        assert call_args["extra"]["first_failed_step_error"] == "step 2 boom"
        assert call_args["extra"]["total_steps"] == 2


# ============================================================
# 5. PipelineContext.llm_client field
# ============================================================

class TestPipelineContextLLMClient:
    """PipelineContext.llm_client — default, set, not serialized."""

    def test_default_is_none(self):
        ctx = PipelineContext()
        assert ctx.llm_client is None

    def test_can_be_set_via_constructor(self):
        mock_llm = MagicMock()
        ctx = PipelineContext(llm_client=mock_llm)
        assert ctx.llm_client is mock_llm

    def test_not_in_serialized_dict(self):
        """llm_client is runtime-only — must not appear in serialize()."""
        mock_llm = MagicMock()
        ctx = PipelineContext(llm_client=mock_llm, pipeline_name="test")
        serialized = ctx.serialize()
        assert "llm_client" not in serialized
        assert "device" not in serialized  # sanity check same pattern

    def test_restore_does_not_carry_llm_client(self):
        """Restored context has llm_client=None (caller must re-inject)."""
        ctx = PipelineContext(pipeline_name="test")
        serialized = ctx.serialize()
        restored = PipelineContext.restore(serialized)
        assert restored.llm_client is None


# ============================================================
# 6. PipelineEngine.load() — llm_client kwarg
# ============================================================

class TestPipelineEngineLoadLLMClient:
    """PipelineEngine.load() accepts llm_client and threads it into context."""

    def test_load_passes_llm_client_to_context(self):
        """llm_client kwarg appears on engine._context.llm_client."""
        from engine.pipeline_engine import PipelineEngine

        mock_llm = MagicMock()
        engine = PipelineEngine()
        pipeline_json = {
            "nodes": [
                {"id": "n1", "type": "click", "config": {"x": 1, "y": 2}}
            ],
            "edges": [],
            "entry_node": "n1",
        }
        engine.load(pipeline_json, llm_client=mock_llm)
        assert engine._context.llm_client is mock_llm
        # Cached for restore re-injection
        assert engine._llm_client is mock_llm

    def test_load_without_llm_client_defaults_to_none(self):
        from engine.pipeline_engine import PipelineEngine

        engine = PipelineEngine()
        pipeline_json = {
            "nodes": [
                {"id": "n1", "type": "click", "config": {"x": 1, "y": 2}}
            ],
            "edges": [],
            "entry_node": "n1",
        }
        engine.load(pipeline_json)
        assert engine._context.llm_client is None


# ============================================================
# 7. Dead code activation — Grep verification
# ============================================================

class TestWorkerLlmClientActivated:
    """Verify WorkerLlmClient is no longer dead code (P0-2 closure).

    These tests assert that WorkerLlmClient has at least one real caller
    in the agent source tree. They use subprocess grep because pytest
    can't directly assert "file X imports from module Y" — but we can
    check the source text.
    """

    def test_orchestrator_imports_agent_llm_client(self):
        """orchestrator.py imports WorkerLlmClient (lazy import in execute_pipeline)."""
        from pathlib import Path

        orch_path = Path(__file__).resolve().parent.parent / "src" / "core" / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "from ai.llm_client import WorkerLlmClient" in content
        assert "WorkerLlmClient(" in content

    def test_template_match_uses_llm_client_via_context(self):
        """template_match.py reads context.llm_client and calls diagnose_failure."""
        from pathlib import Path

        tm_path = (
            Path(__file__).resolve().parent.parent / "src" / "engine" /
            "nodes" / "template_match.py"
        )
        content = tm_path.read_text(encoding="utf-8")
        assert "context.llm_client" in content or "getattr(context, \"llm_client\"" in content
        assert "diagnose_failure" in content

    def test_llm_client_has_diagnose_failure_method(self):
        """WorkerLlmClient class defines diagnose_failure method."""
        from pathlib import Path

        client_path = Path(__file__).resolve().parent.parent / "src" / "ai" / "llm_client.py"
        content = client_path.read_text(encoding="utf-8")
        assert "def diagnose_failure" in content
