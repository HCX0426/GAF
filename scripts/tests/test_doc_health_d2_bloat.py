"""d2_bloat Tests (split from test_doc_health_check.py, s40, TD-365 7/9)."""
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

# ---- d2_bloat tests (Task 2) ----
from governance.check_dimensions import d2_bloat


def _make_md(path: Path, lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"line {i}" for i in range(lines)) + "\n", encoding="utf-8")


def test_d2_bloat_triggers_p2_at_1_5x_threshold(tmp_path):
    """File with 1.5x threshold lines → P2."""
    _make_md(tmp_path / "docs" / "test.md", 1500)  # default threshold=1000, ratio=1.5
    issues = d2_bloat.check(tmp_path, {"per_file_thresholds": {"default": 1000},
                                         "severity_multipliers": {"p2": 1.5, "p1": 2.0, "p0": 3.0}})
    assert len(issues) == 1
    assert issues[0].severity == "P2"
    assert issues[0].dimension == "d2_bloat"


def test_d2_bloat_triggers_p1_at_2x_threshold(tmp_path):
    """File with 2.0x threshold lines → P1."""
    _make_md(tmp_path / "docs" / "big.md", 2000)
    issues = d2_bloat.check(tmp_path, {"per_file_thresholds": {"default": 1000},
                                         "severity_multipliers": {"p2": 1.5, "p1": 2.0, "p0": 3.0}})
    assert len(issues) == 1
    assert issues[0].severity == "P1"


def test_d2_bloat_uses_per_file_threshold(tmp_path):
    """Per-file threshold overrides default."""
    # architecture-mistakes.md threshold=1500, file has 2940 lines → ratio 1.96 → P2
    target = tmp_path / ".ai-memory/summaries/architecture-mistakes.md"
    _make_md(target, 2940)
    thresholds = {
        "per_file_thresholds": {
            ".ai-memory/summaries/architecture-mistakes.md": 1500,
            "default": 1000,
        },
        "severity_multipliers": {"p2": 1.5, "p1": 2.0, "p0": 3.0},
    }
    issues = d2_bloat.check(tmp_path, thresholds)
    assert len(issues) == 1
    assert issues[0].severity == "P2"
    assert "architecture-mistakes" in issues[0].file


def test_d2_bloat_skips_files_under_threshold(tmp_path):
    """File under threshold → no issue."""
    _make_md(tmp_path / "docs" / "small.md", 500)
    issues = d2_bloat.check(tmp_path, {"per_file_thresholds": {"default": 1000},
                                         "severity_multipliers": {"p2": 1.5, "p1": 2.0, "p0": 3.0}})
    assert len(issues) == 0
