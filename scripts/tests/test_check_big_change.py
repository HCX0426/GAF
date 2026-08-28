"""test_check_big_change.py — Unit tests for scripts/check_big_change.py (B2 治本机制).

Covers the 4 dimensions required by TD-317:
1. test_small_change_not_big               — diff < 500 行 → is_big=False
2. test_big_diff_triggers_big              — diff > 500 行 → is_big=True (diff 维度)
3. test_cross_app_triggers_big             — 跨 ≥ 2 app → is_big=True (cross-app 维度)
4. test_db_migration_triggers_big          — 有 migration 文件 → is_big=True (migration 维度)
5. test_api_contract_triggers_big          — 有 API 契约变更 → is_big=True (API 维度)
6. test_count_cross_apps_single            — 单 app 不触发 cross-app 维度
7. test_has_migration_files_excludes_non_migration — 非 migration 文件不计
8. test_has_api_contract_excludes_migration — migration 文件不计入 API contract

Run with: pytest scripts/tests/test_check_big_change.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest

# Make scripts/ importable without installing as a package.
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

import check_big_change  # noqa: E402


def _patch_diff(monkeypatch: pytest.MonkeyPatch,
                files: List[str],
                diff_lines: int) -> None:
    """Patch run_git_diff_names / run_git_diff_stat to return controlled values."""
    monkeypatch.setattr(
        check_big_change, "run_git_diff_names",
        lambda base, head: list(files),
    )
    monkeypatch.setattr(
        check_big_change, "run_git_diff_stat",
        lambda base, head: diff_lines,
    )


# ---------------------------------------------------------------------------
# 1. small change → is_big=False
# ---------------------------------------------------------------------------


def test_small_change_not_big(monkeypatch: pytest.MonkeyPatch) -> None:
    """A small diff with no migrations / API / cross-app → is_big=False."""
    _patch_diff(
        monkeypatch,
        files=["backend/foo/views.py", "frontend/src/components/Foo.tsx"],
        diff_lines=42,
    )
    result = check_big_change.check_big_change("HEAD~1", "HEAD")
    assert result["is_big"] is False
    assert result["reasons"] == []
    assert result["suggested_flow"] == "normal"


# ---------------------------------------------------------------------------
# 2. diff > 500 → is_big=True (diff dimension)
# ---------------------------------------------------------------------------


def test_big_diff_triggers_big(monkeypatch: pytest.MonkeyPatch) -> None:
    """diff line count above DIFF_LINE_THRESHOLD triggers is_big via dim 1."""
    _patch_diff(
        monkeypatch,
        files=["backend/foo/views.py"],
        diff_lines=check_big_change.DIFF_LINE_THRESHOLD + 1,
    )
    result = check_big_change.check_big_change("HEAD~1", "HEAD")
    assert result["is_big"] is True
    assert any("diff" in r for r in result["reasons"])
    assert result["dimensions"]["diff_lines"] > check_big_change.DIFF_LINE_THRESHOLD
    assert "N151 5-step" in result["suggested_flow"]


# ---------------------------------------------------------------------------
# 3. cross-app ≥ 2 → is_big=True (cross-app dimension)
# ---------------------------------------------------------------------------


def test_cross_app_triggers_big(monkeypatch: pytest.MonkeyPatch) -> None:
    """2+ backend apps in the diff triggers is_big via dim 2."""
    _patch_diff(
        monkeypatch,
        files=[
            "backend/accounts/views.py",
            "backend/agents/models.py",
        ],
        diff_lines=10,
    )
    result = check_big_change.check_big_change("HEAD~1", "HEAD")
    assert result["is_big"] is True
    assert result["dimensions"]["cross_app_count"] == 2
    assert sorted(result["dimensions"]["cross_apps"]) == ["accounts", "agents"]
    assert any("backend app" in r for r in result["reasons"])


def test_count_cross_apps_single() -> None:
    """Single backend app should not trigger cross-app dimension."""
    count, apps = check_big_change.count_cross_apps(
        ["backend/accounts/views.py", "backend/accounts/models.py"]
    )
    assert count == 1
    assert apps == ["accounts"]


# ---------------------------------------------------------------------------
# 4. DB migration files → is_big=True (migration dimension)
# ---------------------------------------------------------------------------


def test_db_migration_triggers_big(monkeypatch: pytest.MonkeyPatch) -> None:
    """A new migration file triggers is_big via dim 3."""
    _patch_diff(
        monkeypatch,
        files=["backend/accounts/migrations/0042_add_index.py"],
        diff_lines=5,
    )
    result = check_big_change.check_big_change("HEAD~1", "HEAD")
    assert result["is_big"] is True
    assert "migration_files" in result["dimensions"]
    assert len(result["dimensions"]["migration_files"]) == 1
    assert any("DB 迁移" in r for r in result["reasons"])


def test_has_migration_files_excludes_non_migration() -> None:
    """Non-migration .py files in backend/ do not count as migrations."""
    has, files = check_big_change.has_migration_files(
        ["backend/accounts/views.py", "backend/accounts/urls.py"]
    )
    assert has is False
    assert files == []


# ---------------------------------------------------------------------------
# 5. API contract files → is_big=True (API dimension)
# ---------------------------------------------------------------------------


def test_api_contract_triggers_big(monkeypatch: pytest.MonkeyPatch) -> None:
    """A change to urls.py triggers is_big via dim 4 (API contract)."""
    _patch_diff(
        monkeypatch,
        files=["backend/accounts/urls.py"],
        diff_lines=3,
    )
    result = check_big_change.check_big_change("HEAD~1", "HEAD")
    assert result["is_big"] is True
    assert len(result["dimensions"]["api_contract_files"]) == 1
    assert any("API 契约" in r for r in result["reasons"])


def test_has_api_contract_excludes_migration() -> None:
    """Migration files are NOT counted as API contract changes (handled by dim 3)."""
    has, files = check_big_change.has_api_contract_changes(
        ["backend/accounts/migrations/0042_add_index.py"]
    )
    assert has is False
    assert files == []


def test_api_contract_matches_frontend_types() -> None:
    """frontend/src/types/models.ts is an API contract file."""
    has, files = check_big_change.has_api_contract_changes(
        ["frontend/src/types/models.ts"]
    )
    assert has is True
    assert "frontend/src/types/models.ts" in files
