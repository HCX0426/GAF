"""Agent test conftest — prepend ``src/`` to ``sys.path``.

Historically this file also evicted ``core`` and ``ai`` submodules from
``sys.modules`` to work around a top-level package name collision between
``backend/core/`` + ``backend/ai/`` (Django apps) and ``worker/src/core/``
+ ``worker/src/ai/`` (agent packages). That workaround was removed in
TD-116 (2026-07-15) when the backend apps were renamed to ``gaf_core``
and ``gaf_ai``, eliminating the collision. Only the ``sys.path`` insert
remains.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
