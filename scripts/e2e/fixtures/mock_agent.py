"""Mock agent stub — returns a fixed response for e2e tests.

This module deliberately avoids any side effects: it is loaded by
``e2e/run_all.py`` and by the e2e pytest suite to simulate an Agent
worker without spinning up the real backend. The returned dict always
has the same shape so callers can rely on it.
"""
from __future__ import annotations

from typing import Any, Dict


def handle(task: Dict[str, Any]) -> Dict[str, Any]:
    """Return a deterministic stub response for ``task``.

    Parameters
    ----------
    task : dict
        Task payload. Recognised keys: ``name`` (str), ``type`` (str).

    Returns
    -------
    dict
        ``status`` is always ``"ok"``; ``output`` echoes the task name;
        ``evidence_path`` points to a synthetic file under the repo's
        ``.ai-memory/evidence`` tree.
    """
    name = task.get("name", "unknown")
    return {
        "status": "ok",
        "output": f"mock executed: {name}",
        "evidence_path": f".ai-memory/evidence/2026-06-17/test/{name}.md",
    }
