"""test_sync_skills_timestamps.py — TD-323 spec-85 tests.

Tests sync_skills.py frontmatter timestamp helpers:
1. parse_frontmatter_updated: 解析 `updated:` 字段 (含/缺/无 frontmatter)
2. update_frontmatter_updated: 替换 + 插入 (含/缺/无 frontmatter)
3. get_skill_last_commit_date: 真实 repo 集成 (gaf-orchestrator/SKILL.md)
4. cmd_update_timestamps (s32): 写 today 而非 git log 日期 (自引用循环修复)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap scripts/ import
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
BOOTSTRAP_DIR = SCRIPTS_DIR / "bootstrap"
for _p in (SCRIPTS_DIR, BOOTSTRAP_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest

from sync_skills import (
    cmd_update_timestamps,
    get_skill_last_commit_date,
    parse_frontmatter_updated,
    update_frontmatter_updated,
)

pytestmark = pytest.mark.unit


# =============================================================================
# Test 1: parse_frontmatter_updated
# =============================================================================

def test_parse_frontmatter_updated_extracts_date():
    """parse_frontmatter_updated extracts YYYY-MM-DD from frontmatter."""
    text = (
        "---\n"
        "name: gaf-test\n"
        "version: 9.0\n"
        "updated: 2026-07-21\n"
        "---\n\n"
        "# gaf-test\n"
    )
    assert parse_frontmatter_updated(text) == "2026-07-21"


def test_parse_frontmatter_updated_returns_empty_when_field_missing():
    """parse_frontmatter_updated returns '' when `updated:` is absent."""
    text = (
        "---\n"
        "name: gaf-test\n"
        "version: 9.0\n"
        "---\n\n"
        "# gaf-test\n"
    )
    assert parse_frontmatter_updated(text) == ""


def test_parse_frontmatter_updated_returns_empty_when_no_frontmatter():
    """parse_frontmatter_updated returns '' when no frontmatter block exists."""
    text = "# gaf-test\n\nNo frontmatter here.\n"
    assert parse_frontmatter_updated(text) == ""


# =============================================================================
# Test 2: update_frontmatter_updated
# =============================================================================

def test_update_frontmatter_updated_replaces_existing():
    """update_frontmatter_updated replaces existing `updated:` value."""
    text = (
        "---\n"
        "name: gaf-test\n"
        "version: 9.0\n"
        "updated: 2026-07-17\n"
        "---\n\n"
        "# gaf-test\n"
    )
    new_text = update_frontmatter_updated(text, "2026-07-21")
    assert "updated: 2026-07-21" in new_text
    assert "updated: 2026-07-17" not in new_text
    # Other fields preserved
    assert "name: gaf-test" in new_text
    assert "version: 9.0" in new_text


def test_update_frontmatter_updated_inserts_when_missing():
    """update_frontmatter_updated inserts `updated:` line when field is absent."""
    text = (
        "---\n"
        "name: gaf-test\n"
        "version: 9.0\n"
        "---\n\n"
        "# gaf-test\n"
    )
    new_text = update_frontmatter_updated(text, "2026-07-21")
    assert "updated: 2026-07-21" in new_text
    # Frontmatter structure preserved (still has --- delimiters)
    assert new_text.startswith("---\n")
    assert "name: gaf-test" in new_text
    assert "version: 9.0" in new_text


def test_update_frontmatter_updated_noop_when_no_frontmatter():
    """update_frontmatter_updated returns text unchanged when no frontmatter block."""
    text = "# gaf-test\n\nNo frontmatter.\n"
    new_text = update_frontmatter_updated(text, "2026-07-21")
    assert new_text == text


# =============================================================================
# Test 3: get_skill_last_commit_date (real repo integration)
# =============================================================================

def test_get_skill_last_commit_date_returns_valid_date_for_real_skill():
    """get_skill_last_commit_date returns YYYY-MM-DD for tracked SKILL.md.

    Integration test: uses the real gaf-orchestrator/SKILL.md which is
    tracked in git. Returns a date matching \\d{4}-\\d{2}-\\d{2} format.
    """
    skill_md = REPO_ROOT / ".skills" / "skills" / "gaf-orchestrator" / "SKILL.md"
    if not skill_md.exists():
        pytest.skip("gaf-orchestrator/SKILL.md not found (running outside GAF repo)")
    date_str = get_skill_last_commit_date(skill_md)
    # Should match YYYY-MM-DD format
    assert date_str, "expected non-empty date string for tracked file"
    parts = date_str.split("-")
    assert len(parts) == 3, f"expected YYYY-MM-DD, got {date_str!r}"
    for p in parts:
        assert p.isdigit() and len(p) >= 2, f"invalid date component in {date_str!r}"


def test_get_skill_last_commit_date_returns_empty_for_untracked_path(tmp_path):
    """get_skill_last_commit_date returns '' for a non-tracked file."""
    fake = tmp_path / "FAKE_SKILL.md"
    fake.write_text("---\nname: fake\n---\n", encoding="utf-8")
    # tmp_path is outside the GAF repo, so git log will fail
    date_str = get_skill_last_commit_date(fake)
    assert date_str == ""


# =============================================================================
# Test 4: cmd_update_timestamps (s32 — writes today, not git log date)
# =============================================================================

class _Args:
    def __init__(self, root: str):
        self.root = root


def test_cmd_update_timestamps_writes_today(tmp_path, monkeypatch):
    """cmd_update_timestamps writes today's date (s32), not the git log date.

    Regression for the self-referential loop: writing the git log date means
    the follow-up commit advances git log past the written value → stale
    forever. Writing today converges after commit.
    """
    import datetime
    import sync_skills
    import skill_sync.constants

    # Build a fake .skills/skills/<skill>/SKILL.md tree
    skill_dir = tmp_path / ".skills" / "skills" / "gaf-test"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\nname: gaf-test\nversion: 9.0\nupdated: 2026-07-17\n---\n\n# test\n",
        encoding="utf-8",
    )
    # s39: cmd_update_timestamps reads TIMESTAMP_SKILLS from skill_sync.constants,
    # not the main-file re-export binding — patch the real owner.
    monkeypatch.setattr(skill_sync.constants, "TIMESTAMP_SKILLS", ["gaf-test"])
    today = datetime.date.today().isoformat()

    rc = cmd_update_timestamps(_Args(str(tmp_path)))
    assert rc == 0
    text = skill_md.read_text(encoding="utf-8")
    assert f"updated: {today}" in text
    assert "updated: 2026-07-17" not in text


def test_cmd_update_timestamps_idempotent_when_already_today(tmp_path, monkeypatch):
    """Running again on the same day is a no-op (idempotent)."""
    import datetime
    import sync_skills
    import skill_sync.constants

    skill_dir = tmp_path / ".skills" / "skills" / "gaf-test"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    today = datetime.date.today().isoformat()
    skill_md.write_text(
        f"---\nname: gaf-test\nversion: 9.0\nupdated: {today}\n---\n\n# test\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(skill_sync.constants, "TIMESTAMP_SKILLS", ["gaf-test"])

    before = skill_md.read_text(encoding="utf-8")
    rc = cmd_update_timestamps(_Args(str(tmp_path)))
    assert rc == 0
    assert skill_md.read_text(encoding="utf-8") == before
