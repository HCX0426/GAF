"""test_governance_dashboard.py — TD-325 spec-90 tests.

Tests governance_dashboard.py:
1. collect_spec_completion: 真实 repo 集成 + tmp_path fixture (frontmatter status 解析)
2. collect_td_counts: 真实 repo + tmp_path fixture (active/fixed/wontfix 三文件)
3. collect_lessons_counts: frontmatter 5 字段解析 (真实 repo + fixture)
4. collect_failure_modes_counts: Active/Retired/Dormant 段解析 (真实 repo + fixture)
5. collect_doc_health_latest: **bold** 标记匹配 (验证正则 bug 修复) + fixture
6. render_markdown: 完整 markdown 内容生成 (5 类指标 + 范围说明)
7. main --check: CLI 端到端 (exit 0)
8. main --dry-run: 打印 dashboard 到 stdout
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

from governance_dashboard import (
    collect_doc_health_latest,
    collect_failure_modes_counts,
    collect_lessons_counts,
    collect_spec_completion,
    collect_td_counts,
    main,
    render_markdown,
)

pytestmark = pytest.mark.unit

# =============================================================================
# Test 1: collect_spec_completion — spec 完成率统计
# =============================================================================

def test_collect_spec_completion_real_repo():
    """collect_spec_completion 真实 repo: 非空 + total == done + in_progress + no_frontmatter."""
    specs_dir = REPO_ROOT / "docs" / "specs" / "legacy-trae"
    if not specs_dir.is_dir():
        pytest.skip("docs/specs/legacy-trae/ not found (running outside GAF repo)")
    result = collect_spec_completion(specs_dir)
    assert result["total"] > 0, "expected non-zero spec count"
    # 守恒律: total = done + in_progress + no_frontmatter
    assert result["done"] + result["in_progress"] + result["no_frontmatter"] == result["total"]
    # spec-89 已完成, 至少有 1 个 done
    assert result["done"] >= 1


def test_collect_spec_completion_fixture(tmp_path):
    """collect_spec_completion tmp_path: 三种状态分类正确."""
    specs = tmp_path / "specs"
    specs.mkdir()
    # done (✅)
    (specs / "spec-done.md").write_text(
        "---\nspec_id: spec-1\nstatus: ✅ done\n---\nbody\n", encoding="utf-8"
    )
    # in_progress (🚧)
    (specs / "spec-wip.md").write_text(
        "---\nspec_id: spec-2\nstatus: 🚧 in_progress\n---\nbody\n", encoding="utf-8"
    )
    # no frontmatter
    (specs / "spec-nofm.md").write_text("# no frontmatter\nbody\n", encoding="utf-8")
    # frontmatter 但无 status
    (specs / "spec-nostatus.md").write_text(
        "---\nspec_id: spec-4\n---\nbody\n", encoding="utf-8"
    )
    result = collect_spec_completion(specs)
    assert result["total"] == 4
    assert result["done"] == 1
    assert result["in_progress"] == 1
    assert result["no_frontmatter"] == 2  # no-frontmatter + no-status


def test_collect_spec_completion_empty_dir(tmp_path):
    """collect_spec_completion 空目录 → 全 0."""
    result = collect_spec_completion(tmp_path / "nonexistent")
    assert result == {"done": 0, "in_progress": 0, "no_frontmatter": 0, "total": 0}


# =============================================================================
# Test 2: collect_td_counts — TD 计数
# =============================================================================

def test_collect_td_counts_real_repo():
    """collect_td_counts 真实 repo: 三文件存在, total > 0, total = active+fixed+wontfix."""
    td_dir = REPO_ROOT / "docs" / "archive"
    if not td_dir.is_dir():
        pytest.skip("docs/archive dir not found (running outside GAF repo)")
    result = collect_td_counts(td_dir)
    assert result["total"] > 0, "expected non-zero TD count"
    assert result["active"] + result["fixed"] + result["wontfix"] == result["total"]
    # fixed 应该是最大 (历史修复积累)
    assert result["fixed"] > 0


def test_collect_td_counts_fixture(tmp_path):
    """collect_td_counts tmp_path: active 2 heading / fixed 3 索引行 / wontfix 1 heading."""
    td = tmp_path / "td"
    td.mkdir()
    (td / "active-tech-debt.md").write_text("## TD-1: a\n\n## TD-2: b\n", encoding="utf-8")
    (td / "fixed-tech-debt.md").write_text(
        "| [TD-3](L) | c |\n| [TD-4](L) | d |\n| [TD-5](L) | e |\n", encoding="utf-8"
    )
    (td / "wontfix-tech-debt.md").write_text("## TD-6: f\n", encoding="utf-8")
    result = collect_td_counts(td)
    assert result["active"] == 2
    assert result["fixed"] == 3
    assert result["wontfix"] == 1
    assert result["total"] == 6


def test_collect_td_counts_missing_files(tmp_path):
    """collect_td_counts 文件不存在 → 全 0."""
    result = collect_td_counts(tmp_path / "nonexistent")
    assert result == {"active": 0, "fixed": 0, "wontfix": 0, "total": 0}


# =============================================================================
# Test 3: collect_lessons_counts — lessons frontmatter 字段
# =============================================================================

def test_collect_lessons_counts_real_repo():
    """collect_lessons_counts 真实 repo: 5 字段非零."""
    readme = REPO_ROOT / ".ai-memory" / "lessons" / "README.md"
    if not readme.is_file():
        pytest.skip("lessons/README.md not found (running outside GAF repo)")
    result = collect_lessons_counts(readme)
    assert result["lessons_count"] > 0
    assert result["active_n_count"] > 0
    # 5 个字段都应被解析 (非默认 0)
    assert all(v > 0 for v in result.values()), f"expected all fields > 0, got {result}"


def test_collect_lessons_counts_fixture(tmp_path):
    """collect_lessons_counts tmp_path: 5 字段 frontmatter 解析."""
    readme = tmp_path / "README.md"
    readme.write_text(
        "---\n"
        "lessons_count: 42\n"
        "active_n_count: 40\n"
        "retired_n_count: 5\n"
        "archived_n_count: 2\n"
        "dormant_n_count: 10\n"
        "---\n\n# Lessons\n",
        encoding="utf-8",
    )
    result = collect_lessons_counts(readme)
    assert result["lessons_count"] == 42
    assert result["active_n_count"] == 40
    assert result["retired_n_count"] == 5
    assert result["archived_n_count"] == 2
    assert result["dormant_n_count"] == 10


def test_collect_lessons_counts_missing_file(tmp_path):
    """collect_lessons_counts 文件不存在 → 全 0."""
    result = collect_lessons_counts(tmp_path / "nonexistent.md")
    assert all(v == 0 for v in result.values())


# =============================================================================
# Test 4: collect_failure_modes_counts — failure-modes.md 段解析
# =============================================================================

def test_collect_failure_modes_counts_real_repo():
    """collect_failure_modes_counts 真实 repo: Active 段 > 0."""
    fm_path = REPO_ROOT / ".ai-memory" / "meta" / "failure-modes.md"
    if not fm_path.is_file():
        pytest.skip("failure-modes.md not found (running outside GAF repo)")
    result = collect_failure_modes_counts(fm_path)
    assert result["active"] > 0, "expected non-zero Active N## count"
    # N91 应在 Active 段 (pre-commit hook 核心 N##)
    # 验证段解析正确: Active > 0, retired >= 0, dormant >= 0


def test_collect_failure_modes_counts_fixture(tmp_path):
    """collect_failure_modes_counts tmp_path: 三段表格行数."""
    fm = tmp_path / "failure-modes.md"
    fm.write_text(
        "---\nlast_updated: 2026-07-22\n---\n\n"
        "# failure-modes\n\n"
        "## Active N## 索引表\n\n"
        "| N## | 主题 |\n"
        "|:---:|------|\n"
        "| N91 | pre-commit |\n"
        "| N105 | spec |\n"
        "| N181 | retirement |\n"
        "\n"
        "## Retired N##\n\n"
        "| N## | 主题 |\n"
        "|:---:|------|\n"
        "| N96 | old |\n"
        "| N165 | reverted |\n"
        "\n"
        "## Dormant N##\n\n"
        "| N## | 主题 |\n"
        "|:---:|------|\n"
        "| N100 | family-merged |\n",
        encoding="utf-8",
    )
    result = collect_failure_modes_counts(fm)
    assert result["active"] == 3
    assert result["retired"] == 2
    assert result["dormant"] == 1


def test_collect_failure_modes_counts_missing_file(tmp_path):
    """collect_failure_modes_counts 文件不存在 → 全 0."""
    result = collect_failure_modes_counts(tmp_path / "nonexistent.md")
    assert result == {"active": 0, "retired": 0, "dormant": 0}


# =============================================================================
# Test 5: collect_doc_health_latest — doc_health 报告解析 (含 **bold** bug 修复)
# =============================================================================

def test_collect_doc_health_latest_real_repo():
    """collect_doc_health_latest 真实 repo: 2026-07.md 被找到, pass_rate=60.9%."""
    hc_dir = REPO_ROOT / "docs" / "general" / "health-checks"
    if not hc_dir.is_dir():
        pytest.skip("health-checks dir not found (running outside GAF repo)")
    result = collect_doc_health_latest(hc_dir)
    assert result["found"] is True, "expected doc_health report found"
    assert result["filename"] == "2026-07.md"
    # bug 修复验证: pass_rate 应为 60.9% (28/46), 而非 0.0%
    assert result["total"] == 46
    assert result["passed"] == 28
    assert result["failed"] == 6
    assert result["attention"] == 12
    assert result["pass_rate"] == 60.9, f"expected 60.9 (bug fix), got {result['pass_rate']}"


def test_collect_doc_health_latest_bold_marker(tmp_path):
    """collect_doc_health_latest 匹配 ``**总项数**：46`` (bold 标记) 格式.

    这是 spec-90 Phase 2 修复的核心 bug: 原正则 ``总项数[：:]`` 不匹配
    ``**总项数**：46`` (有 ``**`` bold 标记), 导致 pass_rate=0.0%.
    """
    hc_dir = tmp_path / "hc"
    hc_dir.mkdir()
    (hc_dir / "2026-08.md").write_text(
        "---\n"
        "last_updated: 2026-08-15\n"
        "---\n\n"
        "# 报告\n\n"
        "> **总项数**：50 | **通过**：40 | **失败**：5 | **需关注**：5\n"
        "> **通过率**：80.0%\n",
        encoding="utf-8",
    )
    result = collect_doc_health_latest(hc_dir)
    assert result["found"] is True
    assert result["filename"] == "2026-08.md"
    assert result["date"] == "2026-08-15"
    assert result["total"] == 50
    assert result["passed"] == 40
    assert result["failed"] == 5
    assert result["attention"] == 5
    assert result["pass_rate"] == 80.0


def test_collect_doc_health_latest_no_bold_marker(tmp_path):
    """collect_doc_health_latest 兼容无 bold 标记的格式."""
    hc_dir = tmp_path / "hc"
    hc_dir.mkdir()
    (hc_dir / "2026-09.md").write_text(
        "---\nlast_updated: 2026-09-01\n---\n\n"
        "# 报告\n\n"
        "> 总项数：20 | 通过：18 | 失败：1 | 需关注：1\n",
        encoding="utf-8",
    )
    result = collect_doc_health_latest(hc_dir)
    assert result["found"] is True
    assert result["total"] == 20
    assert result["passed"] == 18
    assert result["pass_rate"] == 90.0


def test_collect_doc_health_latest_empty_dir(tmp_path):
    """collect_doc_health_latest 空目录 → found=False."""
    hc_dir = tmp_path / "hc"
    hc_dir.mkdir()
    result = collect_doc_health_latest(hc_dir)
    assert result["found"] is False
    assert result["filename"] == ""
    assert result["pass_rate"] == 0.0


def test_collect_doc_health_latest_excludes_readme(tmp_path):
    """collect_doc_health_latest 排除 README.md, 取最新 YYYY-MM.md."""
    hc_dir = tmp_path / "hc"
    hc_dir.mkdir()
    (hc_dir / "README.md").write_text("# README\n", encoding="utf-8")
    (hc_dir / "2026-07.md").write_text(
        "---\nlast_updated: 2026-07-01\n---\n\n"
        "> **总项数**：10 | **通过**：8 | **失败**：1 | **需关注**：1\n",
        encoding="utf-8",
    )
    result = collect_doc_health_latest(hc_dir)
    # 不应选 README.md, 应选 2026-07.md
    assert result["filename"] == "2026-07.md"
    assert result["total"] == 10


# =============================================================================
# Test 6: render_markdown — 完整 markdown 生成
# =============================================================================

def test_render_markdown_full():
    """render_markdown 生成 frontmatter + 5 类指标 + 范围说明."""
    metrics = {
        "spec": {"done": 50, "in_progress": 2, "no_frontmatter": 10, "total": 62},
        "td": {"active": 5, "fixed": 290, "wontfix": 30, "total": 325},
        "lessons": {
            "lessons_count": 60,
            "active_n_count": 58,
            "retired_n_count": 7,
            "archived_n_count": 1,
            "dormant_n_count": 15,
        },
        "failure_modes": {"active": 58, "retired": 7, "dormant": 7},
        "doc_health": {
            "date": "2026-07-11",
            "total": 46,
            "passed": 28,
            "failed": 6,
            "attention": 12,
            "pass_rate": 60.9,
            "filename": "2026-07.md",
            "found": True,
        },
    }
    content = render_markdown(metrics)
    # frontmatter
    assert content.startswith("---")
    assert "generated_by: scripts/governance/governance_dashboard.py" in content
    assert "td: TD-325" in content
    assert "spec: spec-90" in content
    # 5 类指标 section
    assert "## 1. spec 完成率" in content
    assert "## 2. 技术债务计数" in content
    assert "## 3. AI Lessons 计数" in content
    assert "## 4. failure-modes.md N## 计数" in content
    assert "## 5. doc_health 最新报告" in content
    # 数据点
    assert "**62**" in content  # spec total
    assert "**325**" in content  # TD total
    assert "**60**" in content  # lessons_count
    assert "**58**" in content  # fm active
    assert "60.9%" in content  # doc_health pass_rate
    # 范围说明
    assert "## 范围说明" in content
    assert "不做历史趋势" in content


def test_render_markdown_no_doc_health():
    """render_markdown doc_health not found 时显示 ⚠️ 提示."""
    metrics = {
        "spec": {"done": 0, "in_progress": 0, "no_frontmatter": 0, "total": 0},
        "td": {"active": 0, "fixed": 0, "wontfix": 0, "total": 0},
        "lessons": {
            "lessons_count": 0,
            "active_n_count": 0,
            "retired_n_count": 0,
            "archived_n_count": 0,
            "dormant_n_count": 0,
        },
        "failure_modes": {"active": 0, "retired": 0, "dormant": 0},
        "doc_health": {
            "date": "",
            "total": 0,
            "passed": 0,
            "failed": 0,
            "attention": 0,
            "pass_rate": 0.0,
            "filename": "",
            "found": False,
        },
    }
    content = render_markdown(metrics)
    assert "⚠️ 未找到 doc_health 报告" in content


# =============================================================================
# Test 7: main --check — CLI 端到端
# =============================================================================

def test_main_check_exit_0():
    """main --check: exit 0, 不写文件."""
    specs_dir = REPO_ROOT / "docs" / "specs" / "legacy-trae"
    if not specs_dir.is_dir():
        pytest.skip("docs/specs/legacy-trae/ not found (running outside GAF repo)")
    exit_code = main(["--check"])
    assert exit_code == 0


def test_main_dry_run_exit_0(capsys):
    """main --dry-run: exit 0, 打印 dashboard 到 stdout."""
    specs_dir = REPO_ROOT / "docs" / "specs" / "legacy-trae"
    if not specs_dir.is_dir():
        pytest.skip("docs/specs/legacy-trae/ not found (running outside GAF repo)")
    exit_code = main(["--dry-run"])
    assert exit_code == 0
    captured = capsys.readouterr()
    # dry-run 输出应包含 dashboard 内容
    assert "## 1. spec 完成率" in captured.out
    assert "## 5. doc_health 最新报告" in captured.out


def test_main_missing_specs_dir(tmp_path):
    """main 当 specs dir 不存在 → exit 2."""
    exit_code = main(["--root", str(tmp_path / "nonexistent"), "--check"])
    assert exit_code == 2
