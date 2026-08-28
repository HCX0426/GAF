"""conftest.py for e2e tests — shared fixtures and path setup.

Lets pytest collect e2e tests from ``scripts/e2e/tests/`` while
importing fixtures and helpers from ``scripts/e2e/`` and
``scripts/``. We also force UTF-8 stdout (N92 CJK garble fix) and
expose the 7 canonical scenario names.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure UTF-8 stdout for child Python processes (N92 Windows CJK fix).
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("LC_ALL", "C.UTF-8")

# GAF/ root → ``from scripts.xxx import yyy`` works from e2e tests.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# 10 canonical scenarios (mirrors spec/tasks.md §3.2.2 + browser_login +
# devices_control_mode + full_routes persisted case library).
SCENARIO_NAMES = [
    "cold_start",
    "new_feature",
    "bug_fix",
    "documentation",
    "refactor",
    "cross_repo",
    "collaboration",
    "browser_login",
    "devices_control_mode",
    "full_routes",
]
