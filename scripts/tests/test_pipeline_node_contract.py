"""s42: cross-layer pipeline node type contract.

Guards the invariant:
    agent registry (@register_node names) ⊆ backend ALL_NODE_TYPES
    frontend PipelineNodeType            ⊆ backend ALL_NODE_TYPES
    backend − agent                      == deprecated legacy set

Text-scan based (no imports): agent registry from agent/src/engine/nodes/*.py,
frontend from frontend/src/types/models/pipeline.ts, backend from
backend/pipeline/schema.py. Rooted at repo root (tests run from repo root).
"""

from __future__ import annotations

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Deprecated BD2-AUTO legacy types — deliberately kept in backend enum
# (backward-compat of persisted pipelines), no frontend/agent support.
LEGACY_NODE_TYPES = {
    "login_account",
    "switch_account",
    "switch_resource",
    "captcha_detect",
}


def _agent_registered_types() -> set[str]:
    nodes_dir = REPO_ROOT / "agent" / "src" / "engine" / "nodes"
    names: set[str] = set()
    for f in nodes_dir.glob("*.py"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'@register_node\(\s*"([a-z_]+)"', text):
            names.add(m.group(1))
    return names


def _frontend_node_types() -> set[str]:
    text = (REPO_ROOT / "frontend" / "src" / "types" / "models" / "pipeline.ts").read_text(
        encoding="utf-8", errors="ignore"
    )
    block = text.split("export type PipelineNodeType =", 1)[1]
    block = block.split(";", 1)[0]
    return set(re.findall(r"'([a-z_]+)'", block))


def _backend_allowed_types() -> set[str]:
    text = (REPO_ROOT / "backend" / "pipeline" / "schema.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    block = text.split("ALL_NODE_TYPES = [", 1)[1]
    block = block.split("]", 1)[0]
    return set(re.findall(r"'([a-z_]+)'", block))


def test_agent_registry_subset_of_backend() -> None:
    assert _agent_registered_types() <= _backend_allowed_types(), (
        "agent @register_node types missing from backend ALL_NODE_TYPES: "
        f"{sorted(_agent_registered_types() - _backend_allowed_types())}"
    )


def test_frontend_subset_of_backend() -> None:
    assert _frontend_node_types() <= _backend_allowed_types(), (
        "frontend PipelineNodeType missing from backend ALL_NODE_TYPES: "
        f"{sorted(_frontend_node_types() - _backend_allowed_types())}"
    )


def test_backend_minus_agent_is_exactly_legacy() -> None:
    extra = _backend_allowed_types() - _agent_registered_types()
    assert extra == LEGACY_NODE_TYPES, (
        "backend ALL_NODE_TYPES has types neither registered in agent nor "
        f"marked legacy (expected {sorted(LEGACY_NODE_TYPES)}, got {sorted(extra)})"
    )


def test_backend_covers_agent_union_frontend() -> None:
    """Sanity: backend enum is a strict superset of agent ∪ frontend."""
    union = _agent_registered_types() | _frontend_node_types()
    missing = union - _backend_allowed_types()
    assert not missing, f"missing from backend: {sorted(missing)}"
