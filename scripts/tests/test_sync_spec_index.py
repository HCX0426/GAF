"""test_sync_spec_index.py — TD-322 spec-84 方案 B tests.

Tests sync_spec_index.py + check_spec_id_collision.py:
1. parse_frontmatter: 提取 spec_id/title/commit/created
2. extract_spec_id_from_filename: fallback 从文件名提取
3. scan_specs: 扫描 specs_dir 返回 list
4. detect_collisions: 检测同号多版本
5. check_spec_id_collision hook: 新增冲突 → exit 1
"""
from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap scripts/ import
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
GOVERNANCE_DIR = SCRIPTS_DIR / "governance"
for _p in (SCRIPTS_DIR, GOVERNANCE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest

from sync_spec_index import (
    detect_collisions,
    extract_spec_id_from_filename,
    parse_frontmatter,
    render_collisions_section,
    render_index,
    scan_specs,
)

pytestmark = pytest.mark.unit


# Tests

def test_parse_frontmatter_extracts_all_fields():
    """parse_frontmatter 提取 spec_id / title / commit / created."""
    text = """---
spec_id: spec-83
title: TD-321 — B2 大修改 pre-commit hook 强制
created: 2026-07-21
status: ✅ done
commit: 2bf99135
related_td: [TD-321]
---

# spec-83: ...
"""
    fm = parse_frontmatter(text)
    assert fm["spec_id"] == "spec-83"
    assert "B2" in fm["title"]
    assert fm["commit"] == "2bf99135"
    assert fm["created"] == "2026-07-21"


def test_parse_frontmatter_no_frontmatter_returns_empty():
    """No frontmatter → empty dict."""
    text = "# spec-36: 标题\n\n正文..."
    fm = parse_frontmatter(text)
    assert fm == {}


def test_extract_spec_id_from_filename():
    """Fallback: 从文件名提取 spec-NN."""
    assert extract_spec_id_from_filename("2026-07-21-spec83-td321-b2.md") == "spec-83"
    assert extract_spec_id_from_filename("2026-07-20-spec59f-td277.md") == "spec-59f"
    assert extract_spec_id_from_filename("2026-07-20-spec36-a11y.md") == "spec-36"
    # No spec-NN pattern
    assert extract_spec_id_from_filename("README.md") is None


def test_scan_specs_and_detect_collisions(tmp_path):
    """scan_specs 扫描目录, detect_collisions 检测同号多版本."""
    # Create fake specs dir with 3 files: spec-99 (1 file), spec-100 (2 files = collision)
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    (specs_dir / "2026-07-21-spec99-unique.md").write_text(
        "---\nspec_id: spec-99\ntitle: unique\n---\n# spec-99\n", encoding="utf-8")
    (specs_dir / "2026-07-21-spec100a-first.md").write_text(
        "---\nspec_id: spec-100a\ntitle: first\n---\n# spec-100a\n", encoding="utf-8")
    (specs_dir / "2026-07-21-spec100b-second.md").write_text(
        "---\nspec_id: spec-100b\ntitle: second\n---\n# spec-100b\n", encoding="utf-8")
    # No frontmatter, fallback to filename
    (specs_dir / "2026-07-21-spec50-legacy.md").write_text("# spec-50 legacy\n", encoding="utf-8")

    specs = scan_specs(specs_dir)
    assert len(specs) == 4

    # No collisions in this set (all unique spec_ids)
    collisions = detect_collisions(specs)
    assert collisions == {}

    # Add a collision: another spec-99 file
    (specs_dir / "2026-07-22-spec99-duplicate.md").write_text(
        "---\nspec_id: spec-99\ntitle: duplicate\n---\n# spec-99 dup\n", encoding="utf-8")
    specs = scan_specs(specs_dir)
    collisions = detect_collisions(specs)
    assert "spec-99" in collisions
    assert len(collisions["spec-99"]) == 2


def test_render_index_contains_all_specs():
    """render_index 生成 markdown 表格含所有 spec."""
    specs = [
        {"spec_id": "spec-83", "filename": "spec83.md", "title": "TD-321", "commit": "abc123", "created": "2026-07-21", "source": "frontmatter"},
        {"spec_id": "spec-84", "filename": "spec84.md", "title": "TD-322", "commit": "", "created": "", "source": "filename"},
    ]
    content = render_index(specs)
    assert "spec-83" in content
    assert "spec-84" in content
    assert "spec83.md" in content
    assert "spec84.md" in content
    assert "TD-321" in content
    assert "TD-322" in content


def test_render_collisions_section_lists_collisions():
    """render_collisions_section 列出冲突组."""
    collisions = {
        "spec-36": [
            {"filename": "spec36a.md", "commit": "111", "created": "2026-07-19"},
            {"filename": "spec36b.md", "commit": "222", "created": "2026-07-20"},
        ],
    }
    content = render_collisions_section(collisions)
    assert "spec-36" in content
    assert "spec36a.md" in content
    assert "spec36b.md" in content
    assert "111" in content
    assert "222" in content


def test_hook_no_spec_staged_passes():
    """check_spec_id_collision hook: 无 spec staged → exit 0."""
    from hooks import check_spec_id_collision
    # No staged files (assuming clean test env) → exit 0
    exit_code = check_spec_id_collision.main([])
    assert exit_code == 0


def test_hook_force_mode_no_staged_passes():
    """check_spec_id_collision hook: --force 模式但无 staged → exit 0 (no collisions to report)."""
    from hooks import check_spec_id_collision
    exit_code = check_spec_id_collision.main(["--force", "--no-fail"])
    # No staged specs means no NEW collisions to report, even with --force
    assert exit_code == 0


def test_real_repo_has_known_collisions():
    """Integration: 真实 repo 扫描应检测到 8 组 16 文件冲突 (spec-36/38/39/41/42/43/44/45)."""
    specs_dir = REPO_ROOT / ".trae" / "specs"
    if not specs_dir.is_dir():
        pytest.skip("not in GAF repo")
    specs = scan_specs(specs_dir)
    collisions = detect_collisions(specs)
    # Historical: 8 collision groups (spec-36/38/39/41/42/43/44/45)
    expected = {"spec-36", "spec-38", "spec-39", "spec-41", "spec-42", "spec-43", "spec-44", "spec-45"}
    assert expected.issubset(set(collisions.keys()))
    # Each group has exactly 2 files
    for sid in expected:
        assert len(collisions[sid]) == 2, f"{sid} should have 2 files, got {len(collisions[sid])}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
