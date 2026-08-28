"""Tests for spec-45: monthly_health_check.py (4 checks C1/H1/I1/N1).

15 unit tests covering all 4 checks:
- C1 (active_td_count): 4 tests — missing file / below / warning / critical
- H1 (git_status_hygiene): 3 tests — clean / sensitive file / many uncommitted
- I1 (large_files): 3 tests — none / large .py / large .tsx (per-dir threshold)
- N1 (empty_dirs_files): 5 tests — none / empty dir / empty file / .gitkeep skip / __init__.py skip

Tests use tmp_path to avoid contaminating the real repo.
H1 tests use a small fixture repo with `git init` for real subprocess calls.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

from governance.monthly_health_check import (
    check_c1_active_td,
    check_h1_git_status,
    check_i1_large_files,
    check_n1_empty_dirs,
    run_all_checks,
)


# ---- C1: active_td_count ----

def test_c1_no_active_md(tmp_path: Path) -> None:
    """active-tech-debt.md missing -> P2 issue."""
    issues = check_c1_active_td(tmp_path, {})
    assert len(issues) == 1
    assert issues[0].severity == "P2"
    assert "not found" in issues[0].evidence


def test_c1_below_threshold(tmp_path: Path) -> None:
    """3 active TDs -> 0 issues."""
    active_md = tmp_path / "docs/archive/active-tech-debt.md"
    active_md.parent.mkdir(parents=True)
    rows = "\n".join(
        f"| TD-{i:03d} | 🔧 待修 |" for i in range(3)
    )
    active_md.write_text(f"# active\n\n{rows}\n", encoding="utf-8")
    issues = check_c1_active_td(tmp_path, {})
    assert issues == []


def test_c1_warning_threshold(tmp_path: Path) -> None:
    """7 active TDs -> P2 issue."""
    active_md = tmp_path / "docs/archive/active-tech-debt.md"
    active_md.parent.mkdir(parents=True)
    rows = "\n".join(
        f"| TD-{i:03d} | 🔧 待修 |" for i in range(7)
    )
    active_md.write_text(f"# active\n\n{rows}\n", encoding="utf-8")
    issues = check_c1_active_td(tmp_path, {})
    assert len(issues) == 1
    assert issues[0].severity == "P2"
    assert "7 active TDs" in issues[0].evidence


def test_c1_critical_threshold(tmp_path: Path) -> None:
    """12 active TDs -> P1 issue."""
    active_md = tmp_path / "docs/archive/active-tech-debt.md"
    active_md.parent.mkdir(parents=True)
    rows = "\n".join(
        f"| TD-{i:03d} | 🚧 进行中 |" for i in range(12)
    )
    active_md.write_text(f"# active\n\n{rows}\n", encoding="utf-8")
    issues = check_c1_active_td(tmp_path, {})
    assert len(issues) == 1
    assert issues[0].severity == "P1"
    assert "12 active TDs" in issues[0].evidence


# ---- H1: git_status_hygiene ----

def _make_git_repo(repo_root: Path) -> None:
    """Initialize a real git repo for H1 tests (uses real subprocess)."""
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                   cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo_root, check=True)


def test_h1_clean_repo(tmp_path: Path) -> None:
    """Clean git status -> 0 issues."""
    _make_git_repo(tmp_path)
    # Initial commit so working tree is clean
    (tmp_path / "README.md").write_text("init", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    issues = check_h1_git_status(tmp_path, {})
    assert issues == []


def test_h1_sensitive_file(tmp_path: Path) -> None:
    """Sensitive file (.env) in git -> P0 issue."""
    _make_git_repo(tmp_path)
    (tmp_path / ".env").write_text("SECRET=abc", encoding="utf-8")
    issues = check_h1_git_status(tmp_path, {})
    # Untracked .env is still flagged (appears in git status --porcelain)
    sensitive_issues = [i for i in issues if i.severity == "P0"]
    assert len(sensitive_issues) == 1
    assert ".env" in sensitive_issues[0].evidence


def test_h1_many_uncommitted(tmp_path: Path) -> None:
    """25 uncommitted files -> P2 issue."""
    _make_git_repo(tmp_path)
    # Create 25 untracked files (well above default warning=20)
    for i in range(25):
        (tmp_path / f"f{i:02d}.txt").write_text(f"file {i}", encoding="utf-8")
    issues = check_h1_git_status(tmp_path, {})
    p2_issues = [i for i in issues if i.severity == "P2"]
    assert len(p2_issues) == 1
    assert "25 uncommitted changes" in p2_issues[0].evidence


# ---- I1: large_files ----

def test_i1_no_large_files(tmp_path: Path) -> None:
    """All files < 1000 lines -> 0 issues."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "small.py").write_text(
        "x = 1\n" * 100, encoding="utf-8"
    )
    issues = check_i1_large_files(tmp_path, {})
    assert issues == []


def test_i1_large_python_file(tmp_path: Path) -> None:
    """1500-line .py in scripts/ (default threshold 1000) -> P2 issue."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "big.py").write_text(
        "x = 1\n" * 1500, encoding="utf-8"
    )
    issues = check_i1_large_files(
        tmp_path, {"default_lines": 1000, "per_dir": {"scripts": 1000}}
    )
    assert len(issues) == 1
    assert issues[0].severity == "P2"
    assert "big.py" in issues[0].evidence
    assert "1500 lines" in issues[0].evidence


def test_i1_large_frontend_file(tmp_path: Path) -> None:
    """1600-line .tsx in frontend/src (frontend threshold 1500) -> P2 issue."""
    front = tmp_path / "frontend/src"
    front.mkdir(parents=True)
    (front / "big.tsx").write_text(
        "export const X = 1;\n" * 1600, encoding="utf-8"
    )
    issues = check_i1_large_files(
        tmp_path,
        {"default_lines": 1000, "per_dir": {"frontend/src": 1500}},
    )
    assert len(issues) == 1
    assert issues[0].severity == "P2"
    assert "big.tsx" in issues[0].evidence


def test_i1_exclude_files_skips_deliberately_large(tmp_path: Path) -> None:
    """Files matched by exclude_files are skipped (TD-365 excluded pair)."""
    back = tmp_path / "backend"
    back.mkdir(parents=True)
    (back / "big.py").write_text("x = 1\n" * 2100, encoding="utf-8")
    (back / "big2.py").write_text("x = 1\n" * 2100, encoding="utf-8")
    issues = check_i1_large_files(
        tmp_path,
        {
            "default_lines": 1000,
            "per_dir": {"backend": 2000},
            "exclude_files": ["backend/big.py"],
        },
    )
    assert len(issues) == 1
    assert "big2.py" in issues[0].evidence


# ---- N1: empty_dirs_files ----

def test_n1_no_empty(tmp_path: Path) -> None:
    """No empty dirs/files -> 0 issues."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "main.py").write_text("x = 1\n", encoding="utf-8")
    issues = check_n1_empty_dirs(tmp_path, {})
    assert issues == []


def test_n1_empty_dir(tmp_path: Path) -> None:
    """Empty directory (no .gitkeep) -> P2 issue."""
    (tmp_path / "empty_dir").mkdir()
    issues = check_n1_empty_dirs(tmp_path, {})
    assert len(issues) == 1
    assert issues[0].severity == "P2"
    assert "empty directory" in issues[0].evidence
    assert "empty_dir" in issues[0].evidence


def test_n1_empty_file(tmp_path: Path) -> None:
    """Empty file (non-intentional) -> P2 issue."""
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    issues = check_n1_empty_dirs(tmp_path, {})
    assert len(issues) == 1
    assert issues[0].severity == "P2"
    assert "empty file" in issues[0].evidence
    assert "empty.txt" in issues[0].evidence


def test_n1_skips_lock_files(tmp_path: Path) -> None:
    """Empty .lock file -> 0 issues (intentional lock file)."""
    (tmp_path / ".sync.lock").write_text("", encoding="utf-8")
    (tmp_path / "another.lock").write_text("", encoding="utf-8")
    issues = check_n1_empty_dirs(tmp_path, {})
    assert issues == []


def test_n1_skips_gitkeep(tmp_path: Path) -> None:
    """Dir with only .gitkeep -> 0 issues (intentional placeholder)."""
    (tmp_path / "placeholder").mkdir()
    (tmp_path / "placeholder" / ".gitkeep").write_text("", encoding="utf-8")
    issues = check_n1_empty_dirs(tmp_path, {})
    assert issues == []


def test_n1_skips_init_py(tmp_path: Path) -> None:
    """Empty __init__.py -> 0 issues (intentional Python package marker)."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    issues = check_n1_empty_dirs(tmp_path, {})
    assert issues == []


# ---- Orchestration ----

def test_run_all_checks_passes_subconfig(tmp_path: Path) -> None:
    """run_all_checks passes per-check sub-config (not full YAML)."""
    # Build a tiny repo so C1/H1/I1/N1 don't crash
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "main.py").write_text("x = 1\n", encoding="utf-8")

    # Active.md missing → C1 returns P2 issue
    thresholds = {
        "c1_active_td": {"warning_threshold": 5, "critical_threshold": 10},
        "h1_git_status": {"uncommitted_warning": 20},
        "i1_large_files": {"default_lines": 1000},
        "n1_empty": {"skip_dirs": [".git"]},
    }
    issues = run_all_checks(tmp_path, thresholds)
    # Should have at least C1 (no active.md) issue; H1 may fail without git
    c1_issues = [i for i in issues if i.dimension == "c1_active_td"]
    assert len(c1_issues) == 1
    assert c1_issues[0].severity == "P2"


def test_run_all_checks_crash_isolation(tmp_path: Path) -> None:
    """If a check crashes, run_all_checks emits P0 issue instead of raising."""
    def crash_check(_root: Path, _cfg: dict) -> list:
        raise RuntimeError("simulated crash")

    # Monkey-patch _CHECKS to include a crashing check
    from governance import monthly_health_check as mhc
    orig_checks = mhc._CHECKS
    mhc._CHECKS = [("crash_check", crash_check)] + list(orig_checks)
    try:
        issues = mhc.run_all_checks(tmp_path, {})
        crash_issues = [i for i in issues if i.dimension == "crash_check"]
        assert len(crash_issues) == 1
        assert crash_issues[0].severity == "P0"
        assert "simulated crash" in crash_issues[0].evidence
    finally:
        mhc._CHECKS = orig_checks
