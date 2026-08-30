"""Shared test fixtures for worker/tests/.

One specific responsibility of this conftest: keep the repo clean of
test-generated JSONL files.

Background
----------
``PipelineEngine.execute()`` (engine/engine.py) always creates a
``StructuredLogger`` via ``get_structured_logger(execution_id, debug_dir=...)``
and writes JSONL files to the debug directory.

``debug_dir`` is read from ``context.debug_dir`` (default ``./debug``).
Several test modules (e.g. ``test_engine_lifecycle.py``) call
``engine.load(pipeline_json, device=device)`` *without* passing
``debug_dir``, so the context falls back to ``./debug`` relative to CWD.
When pytest runs from the repo root, this accumulates test
JSONL files that are never cleaned up.

Fix
---
This autouse fixture monkeypatches
``engine.pipeline_engine.get_structured_logger`` so that every call is redirected
to the per-test ``tmp_path``. Tests that already pass ``debug_dir=str(tmp_path)``
explicitly (e.g. ``test_engine_structured_log_integration.py``,
``test_structured_logger.py``) are unaffected — same ``tmp_path`` is used.

``test_structured_logger.py`` imports ``get_logger`` directly from
``utils.structured_logger`` (not via ``engine.pipeline_engine``), so it is also
unaffected by this patch.
"""

import sys
from pathlib import Path

# Make ``src/`` importable for all tests under worker/tests/. Individual
# test modules also do this themselves; duplicating here is harmless and
# ensures conftest-level imports (engine.pipeline_engine) resolve even if a future
# test module drops its own sys.path manipulation.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest


@pytest.fixture(autouse=True)
def _structured_logger_to_tmp(tmp_path, monkeypatch):
    """Redirect all StructuredLogger output to a per-test tmp directory.

    Patches ``engine.pipeline_engine.get_structured_logger`` (the binding used by
    ``PipelineEngine.execute``) to ignore the ``debug_dir`` argument
    coming from ``context.debug_dir`` and always write under ``tmp_path``.
    This prevents test runs from polluting the repo-root ``debug/``
    directory.
    """
    from engine import pipeline_engine as engine_mod

    original = engine_mod.get_structured_logger

    def _patched(execution_id, debug_dir="./debug", **kwargs):
        # Always write to the per-test tmp_path, regardless of what
        # debug_dir the caller (engine.execute) read from context.
        # **kwargs absorbs new parameters (e.g. pipeline_name) added by
        # engine.load() so the mock doesn't break when engine evolves.
        return original(execution_id, debug_dir=str(tmp_path), **kwargs)

    monkeypatch.setattr(engine_mod, "get_structured_logger", _patched)
