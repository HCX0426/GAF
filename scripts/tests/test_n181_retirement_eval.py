"""test_n181_retirement_eval.py — TD-324 spec-86 tests.

Tests n181_retirement_eval.py:
1. parse_active_n_ids: 解析 Active N## 段 (真实 repo + tmp_path fixture)
2. scan_recent_specs: 扫描最近 N 个 spec (tmp_path fixture)
3. find_retirement_candidates: 条件 A 候选逻辑 (mention_count=0)
4. render_report: 报告渲染 (含/无候选)
5. main: CLI 端到端 (exit code 0)
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

from n181_retirement_eval import (
    find_retirement_candidates,
    parse_active_n_ids,
    render_report,
    scan_recent_specs,
)

pytestmark = pytest.mark.unit


# =============================================================================
# Test 1: parse_active_n_ids — 真实 repo 集成
# =============================================================================

def test_parse_active_n_ids_returns_non_empty_for_real_repo():
    """parse_active_n_ids 真实 repo: failure-modes.md Active N## 段非空.

    当前 repo 有 ~60 Active N## (spec-59-D 后 N165/N170 退役).
    """
    fm_path = REPO_ROOT / ".ai-memory" / "meta" / "failure-modes.md"
    if not fm_path.exists():
        pytest.skip("failure-modes.md not found (running outside GAF repo)")
    n_ids = parse_active_n_ids(fm_path)
    assert n_ids, "expected non-empty Active N## list"
    # v9.2 Spec A (2026-08-22): cap-clear 机械出清使 Active 成员动态变化,
    # 不再断言具体 N## (N91 等早期条目已被出清到 archived-lessons.md).
    # 仅验证 Retired 段不混入 (编号永不复用, N96/N165 永久 Retired).
    assert "N96" not in n_ids, "N96 (Retired) should NOT be in Active"
    assert "N165" not in n_ids, "N165 (Retired) should NOT be in Active"


def test_parse_active_n_ids_returns_empty_for_missing_file(tmp_path):
    """parse_active_n_ids 文件不存在 → 空列表."""
    fake = tmp_path / "nonexistent.md"
    assert parse_active_n_ids(fake) == []


def test_parse_active_n_ids_parses_only_active_section(tmp_path):
    """parse_active_n_ids 只解析 Active 段, 不含 Retired/Dormant.

    构造含 Active + Retired + Dormant 三段的 fixture, 验证只返回 Active 段 N##.
    """
    fm = tmp_path / "failure-modes.md"
    fm.write_text(
        "---\nlast_updated: 2026-07-22\n---\n\n"
        "# failure-modes\n\n"
        "## Active N## 索引表\n\n"
        "| N## | 主题 | 硬约束 | Lesson 链接 |\n"
        "|:---:|------|--------|-------------|\n"
        "| N91 | active-1 | rule-1 | lessons/a.md |\n"
        "| N105 | active-2 | rule-2 | lessons/b.md |\n"
        "\n"
        "## Retired N## 索引\n\n"
        "| N## | 主题 | 硬约束沉淀位置 | 闭环原因 |\n"
        "|:---:|------|---------------|---------|\n"
        "| N96 | retired-1 | rules | M0.M 闭环 |\n"
        "\n"
        "## Dormant N## 索引\n\n"
        "| N## | 主题 | 家族主条目 | Y/N 矩阵位置 |\n"
        "|:---:|------|-----------|-------------|\n"
        "| N107 | dormant-1 | N105 | _workflow.md |\n",
        encoding="utf-8",
    )
    n_ids = parse_active_n_ids(fm)
    assert n_ids == ["N91", "N105"], f"expected [N91, N105], got {n_ids}"


# =============================================================================
# Test 2: scan_recent_specs — tmp_path fixture
# =============================================================================

def test_scan_recent_specs_counts_mentions_correctly(tmp_path):
    """scan_recent_specs 统计每个 N## 在最近 spec 中的提及次数.

    构造 3 个 spec 文件, 验证 mention_count 正确.
    """
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    # 3 spec files (按日期命名, 最新在前)
    (specs_dir / "2026-07-22-spec1-test.md").write_text(
        "N91 mentioned here, N105 too.", encoding="utf-8"
    )
    (specs_dir / "2026-07-21-spec2-test.md").write_text(
        "Only N91 in this spec.", encoding="utf-8"
    )
    (specs_dir / "2026-07-20-spec3-test.md").write_text(
        "N105 and N181 in this spec.", encoding="utf-8"
    )
    # Non-spec file (should be ignored)
    (specs_dir / "README.md").write_text("N91 N105 N181", encoding="utf-8")
    n_ids = ["N91", "N105", "N181"]
    mention_map = scan_recent_specs(specs_dir, n_ids, recent_count=3)
    assert mention_map == {"N91": 2, "N105": 2, "N181": 1}, \
        f"expected N91=2, N105=2, N181=1, got {mention_map}"


def test_scan_recent_specs_respects_recent_count(tmp_path):
    """scan_recent_specs 只扫描最近 N 个 spec (recent_count 参数)."""
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    (specs_dir / "2026-07-22-spec1-test.md").write_text("N91", encoding="utf-8")
    (specs_dir / "2026-07-21-spec2-test.md").write_text("N91", encoding="utf-8")
    (specs_dir / "2026-07-20-spec3-test.md").write_text("N91", encoding="utf-8")
    n_ids = ["N91"]
    # Only scan 1 most recent spec
    mention_map = scan_recent_specs(specs_dir, n_ids, recent_count=1)
    assert mention_map == {"N91": 1}, f"expected N91=1, got {mention_map}"


def test_scan_recent_specs_returns_empty_for_missing_dir(tmp_path):
    """scan_recent_specs 目录不存在 → 所有 N## mention_count=0."""
    missing_dir = tmp_path / "nonexistent"
    n_ids = ["N91", "N105"]
    mention_map = scan_recent_specs(missing_dir, n_ids, recent_count=3)
    assert mention_map == {"N91": 0, "N105": 0}


# =============================================================================
# Test 3: find_retirement_candidates — 条件 A 逻辑
# =============================================================================

def test_find_retirement_candidates_returns_zero_mention_n_ids():
    """find_retirement_candidates 返回 mention_count=0 的 N##."""
    active_n_ids = ["N91", "N105", "N181", "N140"]
    mention_map = {"N91": 2, "N105": 0, "N181": 1, "N140": 0}
    candidates = find_retirement_candidates(active_n_ids, mention_map)
    assert candidates == ["N105", "N140"], f"expected [N105, N140], got {candidates}"


def test_find_retirement_candidates_returns_empty_when_all_mentioned():
    """find_retirement_candidates 所有 N## 都被提及 → 空列表."""
    active_n_ids = ["N91", "N105"]
    mention_map = {"N91": 1, "N105": 2}
    candidates = find_retirement_candidates(active_n_ids, mention_map)
    assert candidates == []


def test_find_retirement_candidates_handles_missing_keys():
    """find_retirement_candidates mention_map 缺 key → 视为 0 (候选)."""
    active_n_ids = ["N91", "N105", "N181"]
    mention_map = {"N91": 1}  # N105/N181 缺 key
    candidates = find_retirement_candidates(active_n_ids, mention_map)
    assert candidates == ["N105", "N181"], f"expected [N105, N181], got {candidates}"


# =============================================================================
# Test 4: render_report — 报告渲染
# =============================================================================

def test_render_report_contains_candidates_and_stats():
    """render_report 含候选清单 + 提及统计表."""
    active_n_ids = ["N91", "N105", "N181"]
    mention_map = {"N91": 2, "N105": 0, "N181": 1}
    candidates = ["N105"]
    report = render_report(
        active_n_ids=active_n_ids,
        mention_map=mention_map,
        candidates=candidates,
        threshold=70,
        recent_count=3,
        threshold_exceeded=False,
    )
    assert "N181 月度退役评估报告" in report
    assert "Active N## 总数: 3" in report
    assert "条件 A 候选" in report
    assert "N105" in report  # candidate
    assert "| N91 | 2 |" in report  # mention stat table
    assert "| N105 | 0 🔸候选 |" in report  # candidate marker


def test_render_report_handles_no_candidates():
    """render_report 无候选时打印 '无候选' 消息."""
    active_n_ids = ["N91"]
    mention_map = {"N91": 1}
    candidates = []
    report = render_report(
        active_n_ids=active_n_ids,
        mention_map=mention_map,
        candidates=candidates,
        threshold=70,
        recent_count=3,
        threshold_exceeded=False,
    )
    assert "无候选" in report
    assert "均被提及" in report


def test_render_report_shows_threshold_exceeded_warning():
    """render_report threshold_exceeded=True 时显示超阈值警告."""
    report = render_report(
        active_n_ids=["N91"],
        mention_map={"N91": 0},
        candidates=["N91"],
        threshold=70,
        recent_count=3,
        threshold_exceeded=True,
    )
    assert "超阈值" in report
