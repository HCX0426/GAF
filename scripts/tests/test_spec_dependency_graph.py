"""test_spec_dependency_graph.py — TD-326 spec-89 tests.

Tests spec_dependency_graph.py:
1. parse_spec_frontmatter: frontmatter 解析 (spec_id/title/commit/created/depends_on/blocks)
2. extract_explicit_deps: 显式依赖提取 (depends_on 字段)
3. extract_implicit_deps: 隐式依赖提取 ("spec-XX 完成后" / "前置 spec-XX" 模式)
4. extract_implicit_deps 自引用排除 + 去重
5. build_dependency_map: 真实 repo 集成 (不抛异常 + 非空)
6. render_mermaid: mermaid 代码块生成 (graph TD + 节点 + 边)
7. render_markdown: 完整 markdown 文件内容 (frontmatter + 概述 + mermaid + 孤立清单)
8. main --check: CLI 端到端 (exit 0)
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

from spec_dependency_graph import (
    build_dependency_map,
    extract_explicit_deps,
    extract_implicit_deps,
    find_orphans,
    main,
    parse_spec_frontmatter,
    render_markdown,
    render_mermaid,
)

pytestmark = pytest.mark.unit

# =============================================================================
# Test 1: parse_spec_frontmatter — 基础解析
# =============================================================================

def test_parse_spec_frontmatter_basic():
    """parse_spec_frontmatter 提取 spec_id/title/commit/created/depends_on/blocks."""
    text = """---
spec_id: spec-89
title: TD-326 — spec 流程可视化依赖图
created: 2026-07-22
status: 🚧 in_progress
commit: TBD
related_td: [TD-326]
depends_on: [spec-84, spec-86]
blocks: []
priority: P2
---

# spec-89: TD-326 — spec 流程可视化依赖图

body text
"""
    fm = parse_spec_frontmatter(text)
    assert fm["spec_id"] == "spec-89"
    assert "TD-326" in fm["title"]
    assert fm["commit"] == "TBD"
    assert fm["created"] == "2026-07-22"
    assert fm["depends_on"] == ["spec-84", "spec-86"]
    assert fm["blocks"] == []


def test_parse_spec_frontmatter_empty_deps():
    """parse_spec_frontmatter depends_on 为空列表."""
    text = """---
spec_id: spec-89
title: test
depends_on: []
blocks: []
---
body
"""
    fm = parse_spec_frontmatter(text)
    assert fm["depends_on"] == []
    assert fm["blocks"] == []


def test_parse_spec_frontmatter_no_frontmatter():
    """parse_spec_frontmatter 无 frontmatter → 空字典."""
    text = "# no frontmatter\nbody"
    fm = parse_spec_frontmatter(text)
    assert fm == {}


# =============================================================================
# Test 2: extract_explicit_deps — 显式依赖提取
# =============================================================================

def test_extract_explicit_deps_from_depends_on():
    """extract_explicit_deps 从 frontmatter depends_on 字段提取."""
    fm = {"depends_on": ["spec-84", "spec-86", "spec-89"]}
    deps = extract_explicit_deps(fm)
    assert deps == ["spec-84", "spec-86", "spec-89"]


def test_extract_explicit_deps_empty():
    """extract_explicit_deps depends_on 为空 → 空列表."""
    assert extract_explicit_deps({"depends_on": []}) == []
    assert extract_explicit_deps({}) == []


# =============================================================================
# Test 3: extract_implicit_deps — 隐式依赖提取
# =============================================================================

def test_extract_implicit_deps_from_body():
    """extract_implicit_deps 从正文提取 "spec-XX 完成后" / "前置 spec-XX" 模式."""
    body = """
some text spec-38 完成后要做 X.
spec-41 完成后, 排序剩余 TD.
前置 spec-39 是必须的.
依赖 spec-42 的设计.
based on spec-49 红线.
spec-43 修复了 22 处静默吞.
"""
    deps = extract_implicit_deps(body, self_spec_id="spec-89")
    # 应提取 spec-38/41/39/42/49/43 (去重, 排除自引用 spec-89)
    assert "spec-38" in deps
    assert "spec-41" in deps
    assert "spec-39" in deps
    assert "spec-42" in deps
    assert "spec-49" in deps
    assert "spec-43" in deps
    # 自引用 spec-89 不应出现
    assert "spec-89" not in deps


def test_extract_implicit_deps_dedup():
    """extract_implicit_deps 去重 + 排除自引用."""
    body = """
spec-38 完成后做 X.
spec-38 完成后做 Y (重复).
spec-89 完成后做 Z (自引用, 应排除).
"""
    deps = extract_implicit_deps(body, self_spec_id="spec-89")
    # spec-38 去重 (只出现 1 次)
    assert deps.count("spec-38") == 1
    # spec-89 自引用排除
    assert "spec-89" not in deps


def test_extract_implicit_deps_no_match():
    """extract_implicit_deps 无匹配模式 → 空列表."""
    body = "no spec references here"
    deps = extract_implicit_deps(body, self_spec_id="spec-89")
    assert deps == []


# =============================================================================
# Test 4: build_dependency_map — 真实 repo 集成
# =============================================================================

def test_build_dependency_map_real_repo():
    """build_dependency_map 真实 repo: 不抛异常 + 非空 + spec-89 存在."""
    specs_dir = REPO_ROOT / "docs" / "specs" / "legacy-trae"
    if not specs_dir.is_dir():
        pytest.skip("docs/specs/legacy-trae/ not found (running outside GAF repo)")
    dep_map = build_dependency_map(specs_dir)
    assert dep_map, "expected non-empty dependency map"
    # spec-89 (本 spec) 应在 map 中
    assert "spec-89" in dep_map
    # spec-84 / spec-86 应在 map 中 (历史 spec)
    assert "spec-84" in dep_map
    assert "spec-86" in dep_map
    # 每个 entry 必须有 deps (set) + title (str) + filename (str)
    for sid, info in dep_map.items():
        assert "deps" in info
        assert "title" in info
        assert "filename" in info
        assert isinstance(info["deps"], set)


def test_build_dependency_map_empty_dir(tmp_path):
    """build_dependency_map 空目录 → 空字典."""
    fake = tmp_path / "empty_specs"
    fake.mkdir()
    assert build_dependency_map(fake) == {}


# =============================================================================
# Test 5: find_orphans — 孤立 spec 识别
# =============================================================================

def test_find_orphans_basic():
    """find_orphans 识别无依赖且不被依赖的 spec."""
    dep_map = {
        "spec-1": {"title": "a", "deps": set()},
        "spec-2": {"title": "b", "deps": {"spec-1"}},
        "spec-3": {"title": "c", "deps": set()},  # orphan
    }
    orphans = find_orphans(dep_map)
    # spec-1 被 spec-2 依赖, 非 orphan
    # spec-2 有依赖, 非 orphan
    # spec-3 无依赖且不被依赖, orphan
    assert "spec-3" in orphans
    assert "spec-1" not in orphans
    assert "spec-2" not in orphans


# =============================================================================
# Test 6: render_mermaid — mermaid 代码块生成
# =============================================================================

def test_render_mermaid_basic():
    """render_mermaid 生成 graph TD + 节点 + 边."""
    dep_map = {
        "spec-1": {"title": "first", "deps": set()},
        "spec-2": {"title": "second", "deps": {"spec-1"}},
        "spec-3": {"title": "third (orphan)", "deps": set()},  # 孤立, 不画
    }
    mermaid = render_mermaid(dep_map)
    assert mermaid.startswith("```mermaid")
    assert mermaid.endswith("```")
    assert "graph TD" in mermaid
    # spec-1 (被依赖) + spec-2 (有依赖) 应在图中, spec-3 (孤立) 不在
    assert "spec_1" in mermaid
    assert "spec_2" in mermaid
    assert "spec_3" not in mermaid
    # 边: spec-2 --> spec-1
    assert "spec_2 --> spec_1" in mermaid


# =============================================================================
# Test 7: render_markdown — 完整 markdown 文件内容
# =============================================================================

def test_render_markdown_full():
    """render_markdown 生成 frontmatter + 概述 + mermaid + 孤立清单."""
    dep_map = {
        "spec-1": {"title": "first", "deps": set(), "filename": "f1.md"},
        "spec-2": {"title": "second", "deps": {"spec-1"}, "filename": "f2.md"},
        "spec-3": {"title": "orphan", "deps": set(), "filename": "f3.md"},
    }
    orphans = ["spec-3"]
    mermaid = render_mermaid(dep_map)
    output_file = REPO_ROOT / "docs" / "specs" / "dependency-graph.md"
    content = render_markdown(dep_map, mermaid, orphans, output_file)
    # frontmatter
    assert content.startswith("---")
    assert "generated_by: scripts/governance/spec_dependency_graph.py" in content
    # 概述段
    assert "总计 **3** 个 spec" in content
    # mermaid 代码块
    assert "```mermaid" in content
    # 孤立 spec 清单
    assert "spec-3" in content
    assert "orphan" in content
    # 同号多版本段
    assert "同号多版本" in content


# =============================================================================
# Test 8: main --check — CLI 端到端
# =============================================================================

def test_main_check_mode_exit_0():
    """main --check 模式: exit 0, 不写文件."""
    specs_dir = REPO_ROOT / "docs" / "specs" / "legacy-trae"
    if not specs_dir.is_dir():
        pytest.skip("docs/specs/legacy-trae/ not found (running outside GAF repo)")
    exit_code = main(["--check"])
    assert exit_code == 0


def test_main_dry_run_exit_0(capsys):
    """main --dry-run 模式: exit 0, 打印 mermaid 到 stdout."""
    specs_dir = REPO_ROOT / "docs" / "specs" / "legacy-trae"
    if not specs_dir.is_dir():
        pytest.skip("docs/specs/legacy-trae/ not found (running outside GAF repo)")
    exit_code = main(["--dry-run"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "```mermaid" in captured.out
