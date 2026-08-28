"""test_probe_unknown_task.py — Unit tests for scripts/probe_unknown_task.py (B4 治本机制).

Covers the 5 paths required by TD-317:
1. test_parse_roadmap_active_entries      — 正确解析 pending-roadmap.md 活跃 P-NNN (⏳/🔧/🚧)
2. test_parse_roadmap_skips_non_active    — ✅/❌/⏸️ 状态被过滤
3. test_recent_specs_top_n_by_mtime       — 正确按 mtime 取 top 3 spec
4. test_suggested_task_type_with_roadmap  — 有 roadmap 活跃条目 → suggested_task_type=new_feature
5. test_suggested_task_type_empty         — 空信号 → suggested_task_type=unknown
6. test_empty_roadmap_file                — 空 roadmap 文件的处理 (返回空列表)
7. test_missing_roadmap_returns_empty     — roadmap 文件不存在时返回空列表
8. test_main_json_output_format           — main --json 输出格式正确 (JSON 含 3 个顶层 key)

Run with: pytest scripts/tests/test_probe_unknown_task.py -v
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

# Make scripts/ importable without installing as a package.
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

import probe_unknown_task  # noqa: E402


SAMPLE_ROADMAP = """\
# Roadmap

| ID | 优先级 | 模块 | 项 | 状态 | 何时 | 关联 |
|:---|:------:|:----:|---|:----:|:----:|:-----|
| P-001 | P1 | agents | Agent 重连 | ⏳ 待实现 | 下 spec | spec-42 |
| P-002 | P2 | search | 索引重建 | 🔧 部分实现 | 后续 | — |
| P-003 | P3 | frontend | 暗色模式 | 🚧 进行中 | 下月 | — |
| P-004 | P3 | docs | 旧文档清理 | ✅ 已完成 | — | — |
| P-005 | P3 | i18n | 翻译补全 | ⏸️ 暂缓 | TBD | — |
"""


@pytest.fixture()
def temp_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect probe_unknown_task module paths to a temp repo root.

    We patch REPO_ROOT, ROADMAP_PATH, SPECS_DIR consistently so that
    `path.relative_to(REPO_ROOT)` and `REPO_ROOT / spec['path']` keep working.
    """
    monkeypatch.setattr(probe_unknown_task, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        probe_unknown_task,
        "ROADMAP_PATH",
        tmp_path / "docs" / "general" / "pending-roadmap.md",
    )
    monkeypatch.setattr(
        probe_unknown_task,
        "SPECS_DIR",
        tmp_path / "docs" / "specs" / "active",
    )
    return tmp_path


def _write_roadmap(repo_root: Path, content: str = SAMPLE_ROADMAP) -> Path:
    """Write a roadmap file at the expected path under repo_root."""
    path = repo_root / "docs" / "general" / "pending-roadmap.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _write_spec(repo_root: Path, name: str, title: str, body: str = "",
                mtime_offset: float = 0.0) -> Path:
    """Write a spec file with the given title and set its mtime."""
    specs_dir = repo_root / "docs" / "specs" / "active"
    specs_dir.mkdir(parents=True, exist_ok=True)
    path = specs_dir / name
    path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    if mtime_offset:
        # Set mtime to now + offset (negative = older).
        ts = time.time() + mtime_offset
        os.utime(path, (ts, ts))
    return path


# ---------------------------------------------------------------------------
# 1. parse roadmap active entries
# ---------------------------------------------------------------------------


def test_parse_roadmap_active_entries(temp_repo: Path) -> None:
    """collect_roadmap_hints returns only ⏳/🔧/🚧 rows with all 7 fields."""
    _write_roadmap(temp_repo)
    hints = probe_unknown_task.collect_roadmap_hints()
    ids = [h["id"] for h in hints]
    # Active entries P-001/002/003 must be present; ✅ and ⏸️ filtered out.
    assert ids == ["P-001", "P-002", "P-003"]
    # Spot-check fields on the first entry.
    first = hints[0]
    assert first["id"] == "P-001"
    assert first["priority"] == "P1"
    assert first["module"] == "agents"
    assert "Agent 重连" in first["item"]
    assert "⏳" in first["status"]


def test_parse_roadmap_skips_non_active(temp_repo: Path) -> None:
    """✅ / ⏸️ / ❌ status rows must be filtered out (only ⏳/🔧/🚧 pass)."""
    _write_roadmap(temp_repo)
    hints = probe_unknown_task.collect_roadmap_hints()
    for h in hints:
        assert any(marker in h["status"]
                   for marker in probe_unknown_task.ACTIVE_STATUS_MARKERS)


# ---------------------------------------------------------------------------
# 2. empty / missing roadmap handling
# ---------------------------------------------------------------------------


def test_empty_roadmap_file(temp_repo: Path) -> None:
    """An empty roadmap file yields an empty list (no crash)."""
    _write_roadmap(temp_repo, content="")
    assert probe_unknown_task.collect_roadmap_hints() == []


def test_missing_roadmap_returns_empty(temp_repo: Path) -> None:
    """When the roadmap file does not exist, return an empty list."""
    # Do NOT write the roadmap file.
    assert probe_unknown_task.collect_roadmap_hints() == []


# ---------------------------------------------------------------------------
# 3. recent specs by mtime
# ---------------------------------------------------------------------------


def test_recent_specs_top_n_by_mtime(temp_repo: Path) -> None:
    """collect_recent_specs returns top N specs sorted by mtime descending."""
    # Write 4 specs with staggered mtimes (oldest first by mtime offset).
    _write_spec(temp_repo, "old.md",       "Old Spec",       mtime_offset=-3600)
    _write_spec(temp_repo, "mid.md",       "Mid Spec",       mtime_offset=-1800)
    _write_spec(temp_repo, "fresh.md",     "Fresh Spec",     mtime_offset=-60)
    _write_spec(temp_repo, "newest.md",    "Newest Spec",    mtime_offset=0)

    specs = probe_unknown_task.collect_recent_specs(top_n=3)
    assert len(specs) == 3
    # Sorted newest first → "newest.md", "fresh.md", "mid.md".
    assert specs[0]["path"].endswith("newest.md")
    assert specs[1]["path"].endswith("fresh.md")
    assert specs[2]["path"].endswith("mid.md")
    # Title is extracted from the `# ` heading.
    assert specs[0]["title"] == "Newest Spec"
    # Path is relative to REPO_ROOT (no drive letter, no leading slash).
    assert "docs/specs/active/newest.md" in specs[0]["path"].replace("\\", "/")


def test_recent_specs_missing_dir_returns_empty(temp_repo: Path) -> None:
    """When SPECS_DIR does not exist, return an empty list."""
    # Do NOT create the specs dir.
    assert probe_unknown_task.collect_recent_specs() == []


# ---------------------------------------------------------------------------
# 4. suggested_task_type
# ---------------------------------------------------------------------------


def test_suggested_task_type_with_roadmap(temp_repo: Path) -> None:
    """Active roadmap hints (and no recent spec with ⏳/🔄) → 'new_feature'."""
    _write_roadmap(temp_repo)
    hints = probe_unknown_task.collect_roadmap_hints()
    # Pass empty recent_specs so the spec-continuation branch is skipped.
    suggested = probe_unknown_task.suggest_task_type(hints, recent_specs=[])
    assert suggested == "new_feature"


def test_suggested_task_type_empty(temp_repo: Path) -> None:
    """No roadmap hints and no recent specs → 'unknown'."""
    suggested = probe_unknown_task.suggest_task_type([], [])
    assert suggested == "unknown"


def test_suggested_task_type_spec_continuation(temp_repo: Path) -> None:
    """A recent spec containing ⏳ marker → suggested 'new_feature' (continuation)."""
    _write_spec(temp_repo, "spec-99.md", "Spec 99", body="some content with ⏳ marker")
    specs = probe_unknown_task.collect_recent_specs(top_n=1)
    # No roadmap hints — should still suggest new_feature due to spec continuation.
    suggested = probe_unknown_task.suggest_task_type([], specs)
    assert suggested == "new_feature"


# ---------------------------------------------------------------------------
# 5. main() JSON output format
# ---------------------------------------------------------------------------


def test_main_json_output_format(temp_repo: Path, capsys: pytest.CaptureFixture) -> None:
    """main(['--json']) should print valid JSON with the 3 top-level keys."""
    _write_roadmap(temp_repo)
    _write_spec(temp_repo, "spec-1.md", "Spec 1", body="content")

    rc = probe_unknown_task.main(["--json"])
    assert rc == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    # Required top-level keys per docstring.
    assert "roadmap_hints" in data
    assert "recent_specs" in data
    assert "suggested_task_type" in data
    # Roadmap hints should contain the 3 active entries.
    assert len(data["roadmap_hints"]) == 3
    # suggested_task_type is one of the documented values.
    assert data["suggested_task_type"] in {
        "new_feature", "bug_fix", "refactor", "documentation", "unknown",
    }
