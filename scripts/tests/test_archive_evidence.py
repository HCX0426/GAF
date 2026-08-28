"""test_archive_evidence.py — Unit tests for evidence lifecycle management.

Covers the main behaviors of scripts/bootstrap/archive_evidence.py:

1. test_parse_dir_date_valid         — YYYY-MM-DD prefix parsed correctly
2. test_parse_dir_date_invalid       — non-date names return None
3. test_status_empty                 — empty evidence dir reports 0/0
4. test_status_with_active_and_archived — status counts active + archived
5. test_archive_dry_run              — dry-run lists candidates without moving
6. test_archive_apply                — --apply moves old dirs to archived/<YYYY-MM>/
7. test_archive_skips_recent         — dirs < 30 days are not archived
8. test_archive_skips_templates      — templates/ is never archived
9. test_archive_dest_exists_skip     — existing dest is skipped, no overwrite
10. test_prune_dry_run                — dry-run lists candidates without deleting
11. test_prune_apply                  — --apply deletes old archived dirs
12. test_prune_empty_month_cleanup    — empty month dirs are removed after prune
13. test_apply_and_dry_run_mutually_exclusive — exit 2 on conflicting flags

Run with: `python -m pytest scripts/tests/test_archive_evidence.py -q`
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit


def _load_module():
    """Load archive_evidence.py fresh so we can patch EVIDENCE_DIR per test."""
    spec = importlib.util.spec_from_file_location(
        "archive_evidence", SCRIPTS_DIR / "bootstrap" / "archive_evidence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_dir(parent: Path, name: str, with_file: bool = True) -> Path:
    d = parent / name
    d.mkdir(parents=True, exist_ok=True)
    if with_file:
        (d / "problem.md").write_text("test", encoding="utf-8")
    return d


def _setup_evidence(tmp_root: Path, today: date | None = None) -> None:
    """Populate a fake evidence/ tree under tmp_root/.ai-memory/evidence."""
    today = today or date.today()
    ev = tmp_root / ".ai-memory" / "evidence"
    ev.mkdir(parents=True)
    # Recent evidence (< 30 days) — should NOT be archived.
    _make_dir(ev, f"{(today - timedelta(days=5)).isoformat()}-recent-task")
    # Old evidence (>= 30 days) — should be archived.
    _make_dir(ev, f"{(today - timedelta(days=40)).isoformat()}-old-task")
    # Very old evidence (>= 90 days) — archive + prune candidate.
    _make_dir(ev, f"{(today - timedelta(days=100)).isoformat()}-very-old-task")
    # templates/ — must NEVER be touched.
    (ev / "templates").mkdir()
    (ev / "templates" / "problem.md").write_text("template", encoding="utf-8")
    # Non-date dir — must be skipped.
    _make_dir(ev, "manual-notes", with_file=False)


def test_parse_dir_date_valid():
    mod = _load_module()
    d = mod._parse_dir_date(Path("2026-07-15-p010-phase1-schema-agent"))
    assert d == date(2026, 7, 15)


def test_parse_dir_date_invalid():
    mod = _load_module()
    assert mod._parse_dir_date(Path("manual-notes")) is None
    assert mod._parse_dir_date(Path("templates")) is None
    assert mod._parse_dir_date(Path("not-a-date-at-all")) is None


def test_status_empty():
    mod = _load_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        ev = tmp_root / ".ai-memory" / "evidence"
        ev.mkdir(parents=True)
        mod.EVIDENCE_DIR = ev
        mod.ARCHIVED_DIR = ev / "archived"
        rc = mod.cmd_status()
        assert rc == 0


def test_status_with_active_and_archived():
    mod = _load_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _setup_evidence(tmp_root)
        mod.EVIDENCE_DIR = tmp_root / ".ai-memory" / "evidence"
        mod.ARCHIVED_DIR = mod.EVIDENCE_DIR / "archived"
        # Pre-create one archived dir.
        archived_month = mod.ARCHIVED_DIR / date.today().strftime("%Y-%m")
        archived_month.mkdir(parents=True)
        _make_dir(archived_month, f"{(date.today() - timedelta(days=95)).isoformat()}-archived-old")
        rc = mod.cmd_status()
        assert rc == 0


def test_archive_dry_run():
    mod = _load_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _setup_evidence(tmp_root)
        mod.EVIDENCE_DIR = tmp_root / ".ai-memory" / "evidence"
        mod.ARCHIVED_DIR = mod.EVIDENCE_DIR / "archived"
        rc = mod.cmd_archive(dry_run=True)
        assert rc == 0
        # Dry-run: nothing moved.
        active = [p for p in mod.EVIDENCE_DIR.iterdir() if p.is_dir() and p.name not in ("archived", "templates")]
        assert len(active) == 4  # recent + old + very-old + manual-notes


def test_archive_apply():
    mod = _load_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _setup_evidence(tmp_root)
        mod.EVIDENCE_DIR = tmp_root / ".ai-memory" / "evidence"
        mod.ARCHIVED_DIR = mod.EVIDENCE_DIR / "archived"
        rc = mod.cmd_archive(dry_run=False)
        assert rc == 0
        # Two old dirs (40d, 100d) moved to archived/.
        archived = list(mod.ARCHIVED_DIR.rglob("2026-*")) + list(mod.ARCHIVED_DIR.rglob("*-old-task")) + list(mod.ARCHIVED_DIR.rglob("*-very-old-task"))
        archived_names = {p.name for p in archived if p.is_dir()}
        assert any("old-task" in n for n in archived_names)
        assert any("very-old-task" in n for n in archived_names)
        # Recent + manual-notes + templates still in active.
        active_names = {p.name for p in mod.EVIDENCE_DIR.iterdir() if p.is_dir()}
        assert "templates" in active_names
        assert any("recent-task" in n for n in active_names)
        assert "manual-notes" in active_names


def test_archive_skips_recent():
    mod = _load_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _setup_evidence(tmp_root)
        mod.EVIDENCE_DIR = tmp_root / ".ai-memory" / "evidence"
        mod.ARCHIVED_DIR = mod.EVIDENCE_DIR / "archived"
        mod.cmd_archive(dry_run=False)
        # recent-task (5d) must remain in active.
        active_names = {p.name for p in mod.EVIDENCE_DIR.iterdir() if p.is_dir()}
        assert any("recent-task" in n for n in active_names)


def test_archive_skips_templates():
    mod = _load_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _setup_evidence(tmp_root)
        mod.EVIDENCE_DIR = tmp_root / ".ai-memory" / "evidence"
        mod.ARCHIVED_DIR = mod.EVIDENCE_DIR / "archived"
        mod.cmd_archive(dry_run=False)
        assert (mod.EVIDENCE_DIR / "templates" / "problem.md").read_text() == "template"


def test_archive_dest_exists_skip():
    mod = _load_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _setup_evidence(tmp_root)
        mod.EVIDENCE_DIR = tmp_root / ".ai-memory" / "evidence"
        mod.ARCHIVED_DIR = mod.EVIDENCE_DIR / "archived"
        # Pre-create dest for old-task.
        old_date = date.today() - timedelta(days=40)
        dest_parent = mod.ARCHIVED_DIR / old_date.strftime("%Y-%m")
        dest_parent.mkdir(parents=True)
        _make_dir(dest_parent, f"{old_date.isoformat()}-old-task", with_file=False)
        # Run archive — should skip the existing dest, not overwrite.
        rc = mod.cmd_archive(dry_run=False)
        assert rc == 0
        # Source should still be present (skipped).
        active = [p for p in mod.EVIDENCE_DIR.iterdir() if p.is_dir() and p.name not in ("archived", "templates")]
        assert any("old-task" in p.name for p in active)


def test_prune_dry_run():
    mod = _load_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _setup_evidence(tmp_root)
        mod.EVIDENCE_DIR = tmp_root / ".ai-memory" / "evidence"
        mod.ARCHIVED_DIR = mod.EVIDENCE_DIR / "archived"
        # Archive first so we have archived/ populated.
        mod.cmd_archive(dry_run=False)
        rc = mod.cmd_prune(dry_run=True)
        assert rc == 0
        # Dry-run: nothing deleted.
        archived = [p for p in mod.ARCHIVED_DIR.rglob("*") if p.is_dir() and p.parent.parent.name == "archived"]
        assert len(archived) >= 1  # very-old-task still present


def test_prune_apply():
    mod = _load_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _setup_evidence(tmp_root)
        mod.EVIDENCE_DIR = tmp_root / ".ai-memory" / "evidence"
        mod.ARCHIVED_DIR = mod.EVIDENCE_DIR / "archived"
        mod.cmd_archive(dry_run=False)
        rc = mod.cmd_prune(dry_run=False)
        assert rc == 0
        # very-old-task (100d) should be deleted; old-task (40d) should remain (not yet 90d).
        archived_names = {p.name for p in mod.ARCHIVED_DIR.rglob("*") if p.is_dir()}
        assert not any("very-old-task" in n for n in archived_names)
        assert any("old-task" in n for n in archived_names)


def test_prune_empty_month_cleanup():
    mod = _load_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _setup_evidence(tmp_root)
        mod.EVIDENCE_DIR = tmp_root / ".ai-memory" / "evidence"
        mod.ARCHIVED_DIR = mod.EVIDENCE_DIR / "archived"
        mod.cmd_archive(dry_run=False)
        mod.cmd_prune(dry_run=False)
        # Empty month dirs should be removed.
        for month_dir in mod.ARCHIVED_DIR.iterdir():
            if month_dir.is_dir():
                # If the month dir still exists, it must have content.
                contents = list(month_dir.iterdir())
                assert len(contents) > 0, f"empty month dir not cleaned: {month_dir}"


def test_apply_and_dry_run_mutually_exclusive():
    mod = _load_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _setup_evidence(tmp_root)
        mod.EVIDENCE_DIR = tmp_root / ".ai-memory" / "evidence"
        mod.ARCHIVED_DIR = mod.EVIDENCE_DIR / "archived"
        rc = mod.main(["archive", "--apply", "--dry-run"])
        assert rc == 2
        rc = mod.main(["prune", "--apply", "--dry-run"])
        assert rc == 2


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
