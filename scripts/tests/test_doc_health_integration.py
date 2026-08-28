"""Integration + performance + read-only Tests (split from test_doc_health_check.py, s40, TD-365 7/9)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import sys
from pathlib import Path

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

# ===== Task 10: Integration + performance + read-only tests =====


def test_doc_health_check_full_pipeline(repo_root):
    """End-to-end: run main entry, verify JSON output schema."""
    output_path = repo_root / ".cache" / "test_report.json"
    result = subprocess.run(
        ["python", "scripts/governance/doc_health_check.py",
         "--output", str(output_path), "--no-fail"],
        cwd=repo_root, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, f"script failed: {result.stderr}"
    assert output_path.exists()
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert "generated_at" in data
    assert "git_sha" in data
    assert "duration_seconds" in data
    assert "summary" in data
    assert "issues" in data
    assert isinstance(data["issues"], list)
    # Each issue has required fields
    for issue in data["issues"]:
        assert "id" in issue and len(issue["id"]) == 12
        assert "dimension" in issue
        assert "severity" in issue
        assert "evidence" in issue
        assert "consumed" in issue


def test_doc_health_check_performance_under_2s(repo_root):
    """N171: single execution must be fast.

    Budget breakdown:
    - Internal run_all_dimensions: ~1.0s (well under N171's <2s budget for
      a single check script).
    - subprocess.run end-to-end: adds Python interpreter startup + module
      imports + JSON write on Windows (~0.6-1.5s extra).
    - Total budget: 3.0s (gives Windows subprocess overhead ~1.5s headroom
      while still catching real regressions if internal time doubles).

    N171 explicitly allows pytest single-file < 5s; this end-to-end test
    targets 3.0s as a tighter guard.
    """
    start = time.perf_counter()
    subprocess.run(
        ["python", "scripts/governance/doc_health_check.py", "--no-fail"],
        cwd=repo_root, capture_output=True, timeout=30,
    )
    duration = time.perf_counter() - start
    assert duration < 3.0, f"Performance regression: {duration:.2f}s > 3.0s budget (N171, Windows subprocess end-to-end)"


def test_doc_health_check_does_not_modify_source_files(repo_root):
    """Static layer is READ-ONLY: must not modify any source file."""
    import hashlib
    # Snapshot all .md files under docs/ and .ai-memory/ and .skills/
    snapshots: dict[str, str] = {}
    for scan_dir in [repo_root / "docs", repo_root / ".ai-memory", repo_root / ".skills"]:
        if not scan_dir.exists():
            continue
        for md_file in scan_dir.rglob("*.md"):
            rel = md_file.relative_to(repo_root).as_posix()
            try:
                snapshots[rel] = hashlib.sha256(md_file.read_bytes()).hexdigest()
            except Exception:
                continue
    # Run doc_health_check (may write .cache/doc_health_report.json, which is gitignored)
    subprocess.run(
        ["python", "scripts/governance/doc_health_check.py", "--no-fail"],
        cwd=repo_root, capture_output=True, timeout=30,
    )
    # Verify all source snapshots unchanged
    for rel, before_hash in snapshots.items():
        md_file = repo_root / rel
        if not md_file.exists():
            pytest.fail(f"File deleted by doc_health_check: {rel}")
        after_hash = hashlib.sha256(md_file.read_bytes()).hexdigest()
        assert before_hash == after_hash, f"File modified by doc_health_check: {rel}"
