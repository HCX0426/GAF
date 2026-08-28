"""d1_overlap Tests (split from test_doc_health_check.py, s40, TD-365 7/9)."""
from __future__ import annotations

import sys
import sys
from pathlib import Path

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

# ---- d1_overlap tests (Task 7) ----
from governance.check_dimensions import d1_overlap


def test_d1_overlap_detects_high_jaccard(tmp_path):
    """Two files with very similar summary → P1."""
    f1 = tmp_path / "docs/a.md"
    f1.parent.mkdir(parents=True, exist_ok=True)
    f1.write_text("---\nsummary: 异步 Celery Channels 消息队列\n---\n# A\n", encoding="utf-8")
    f2 = tmp_path / ".ai-memory/b.md"
    f2.parent.mkdir(parents=True, exist_ok=True)
    f2.write_text("---\nsummary: 异步 Celery Channels 消息队列详解\n---\n# B\n", encoding="utf-8")
    thresholds = {"summary_jaccard_p2": 0.6, "summary_jaccard_p1": 0.8, "whitelist": []}
    issues = d1_overlap.check(tmp_path, thresholds)
    assert len(issues) >= 1
    assert issues[0].severity in ("P1", "P2")


def test_d1_overlap_no_issue_for_unrelated_files(tmp_path):
    """Files with different summaries → no issue."""
    f1 = tmp_path / "docs/a.md"
    f1.parent.mkdir(parents=True, exist_ok=True)
    f1.write_text("---\nsummary: Django setup\n---\n# A\n", encoding="utf-8")
    f2 = tmp_path / ".ai-memory/b.md"
    f2.parent.mkdir(parents=True, exist_ok=True)
    f2.write_text("---\nsummary: React component patterns\n---\n# B\n", encoding="utf-8")
    thresholds = {"summary_jaccard_p2": 0.6, "summary_jaccard_p1": 0.8, "whitelist": []}
    issues = d1_overlap.check(tmp_path, thresholds)
    assert len(issues) == 0


def test_d1_overlap_whitelist_skips_lessons(tmp_path):
    """Files in .ai-memory/lessons/ are whitelisted."""
    f1 = tmp_path / ".ai-memory/lessons/a.md"
    f1.parent.mkdir(parents=True, exist_ok=True)
    f1.write_text("---\nsummary: Django setup\n---\n# A\n", encoding="utf-8")
    f2 = tmp_path / ".ai-memory/lessons/b.md"
    f2.write_text("---\nsummary: Django setup details\n---\n# B\n", encoding="utf-8")
    thresholds = {"summary_jaccard_p2": 0.6, "summary_jaccard_p1": 0.8,
                  "whitelist": [".ai-memory/lessons/*.md"]}
    issues = d1_overlap.check(tmp_path, thresholds)
    assert len(issues) == 0
