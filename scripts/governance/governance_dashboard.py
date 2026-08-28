"""governance_dashboard.py — TD-325 spec-90: 治理指标 dashboard (当前快照版).

汇聚 5 类治理指标生成 markdown dashboard 到 ``docs/business/ops/governance-dashboard.md``:

1. **spec 完成率**: ``docs/specs/legacy-trae/*.md`` frontmatter ``status`` 字段统计 (spec-2026-07-26-trae-specs-plans-merge 迁移自旧 trae-specs 目录)
2. **TD 计数**: ``docs/archive/`` active-tech-debt/fixed-tech-debt/wontfix-tech-debt 三文件 ``^## TD-`` 行数
3. **lessons 计数**: ``.ai-memory/lessons/README.md`` frontmatter 5 字段
4. **failure-modes 计数**: ``.ai-memory/meta/failure-modes.md`` Active/Retired/Dormant 段
5. **doc_health 最新报告**: ``docs/health/*.md`` 最新文件 frontmatter

三种运行模式:
    python scripts/governance/governance_dashboard.py           # 生成 / 更新
    python scripts/governance/governance_dashboard.py --check   # 仅报告, 不写文件
    python scripts/governance/governance_dashboard.py --dry-run # 打印 dashboard 到 stdout
    python scripts/governance/governance_dashboard.py --root <path>

设计参考: ``sync_tech_debt_counts.py`` + ``spec_dependency_graph.py`` (argparse + Path +
_encoding_safe Windows UTF-8 fix).

Exit codes
----------
    0 - 成功
    2 - 配置/参数错误 (目录不存在等)
"""
# ruff: noqa: I001  # _encoding_safe must stay first; do not reorder imports
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout to UTF-8)

import argparse  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Dict, List, Optional  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
SPECS_DIR_DEFAULT = REPO_ROOT_DEFAULT / "docs" / "specs" / "legacy-trae"
TECH_DEBT_DIR_DEFAULT = REPO_ROOT_DEFAULT / "docs" / "archive"
LESSONS_README_DEFAULT = REPO_ROOT_DEFAULT / ".ai-memory" / "lessons" / "README.md"
FAILURE_MODES_PATH_DEFAULT = REPO_ROOT_DEFAULT / ".ai-memory" / "meta" / "failure-modes.md"
HEALTH_CHECKS_DIR_DEFAULT = REPO_ROOT_DEFAULT / "docs" / "health"
OUTPUT_FILE_DEFAULT = REPO_ROOT_DEFAULT / "docs" / "business" / "ops" / "governance-dashboard.md"

# Frontmatter ``---`` block.
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
STATUS_RE = re.compile(r"^status:\s*(.+?)\s*$", re.MULTILINE)

# TD heading: ``^## TD-NNN`` (excludes the ``## TD-XXX`` template placeholder)
TD_HEADING_RE = re.compile(r"^## TD-\d+", re.MULTILINE)
# fixed-tech-debt.md counts its index-table rows (``| [TD-NNN](L) | ... |``)
FIXED_INDEX_ROW_RE = re.compile(r"^\|\s*\[TD-\d+\]", re.MULTILINE)

# failure-modes.md section markers
ACTIVE_SECTION_START = "## Active N##"
RETIRED_SECTION_START = "## Retired N##"
DORMANT_SECTION_START = "## Dormant N##"
# Active N## row: ``| N91 | ... |``
ACTIVE_N_ROW_RE = re.compile(r"^\|\s*(N\d+)\s*\|", re.MULTILINE)

# lessons/README.md frontmatter numeric fields
LESSONS_FIELDS = [
    "lessons_count",
    "active_n_count",
    "retired_n_count",
    "archived_n_count",
    "dormant_n_count",
]


def collect_spec_completion(specs_dir: Path) -> Dict[str, int]:
    """扫描 docs/specs/legacy-trae/*.md frontmatter status, 返回 {done, in_progress, no_frontmatter, total}.

    - ``done``: status 含 "✅" 或 "done"
    - ``in_progress``: status 含 "🚧" 或 "in_progress"
    - ``no_frontmatter``: 无 frontmatter 或无 status 字段
    """
    result = {"done": 0, "in_progress": 0, "no_frontmatter": 0, "total": 0}
    if not specs_dir.is_dir():
        return result
    for md_file in specs_dir.glob("*.md"):
        result["total"] += 1
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            result["no_frontmatter"] += 1
            continue
        fm_match = FRONTMATTER_RE.match(text)
        if not fm_match:
            result["no_frontmatter"] += 1
            continue
        fm_text = fm_match.group(1)
        m = STATUS_RE.search(fm_text)
        if not m:
            result["no_frontmatter"] += 1
            continue
        status = m.group(1).lower()
        if "✅" in status or "done" in status:
            result["done"] += 1
        elif "🚧" in status or "in_progress" in status:
            result["in_progress"] += 1
        else:
            result["no_frontmatter"] += 1
    return result


def collect_td_counts(tech_debt_dir: Path) -> Dict[str, int]:
    """扫描 active/fixed/wontfix 三文件 TD 条目数, 返回 {active, fixed, wontfix, total}.

    active/wontfix 按 ``^## TD-NNN`` heading 计数; fixed 按索引表
    ``| [TD-NNN](L) |`` 行计数 (fixed-tech-debt.md 以索引表为主, 仅少数
    条目保留完整段落).
    """
    def _count(p: Path, row_re: re.Pattern) -> int:
        if not p.is_file():
            return 0
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return 0
        return len(row_re.findall(text))

    active = _count(tech_debt_dir / "active-tech-debt.md", TD_HEADING_RE)
    fixed = _count(tech_debt_dir / "fixed-tech-debt.md", FIXED_INDEX_ROW_RE)
    wontfix = _count(tech_debt_dir / "wontfix-tech-debt.md", TD_HEADING_RE)
    return {
        "active": active,
        "fixed": fixed,
        "wontfix": wontfix,
        "total": active + fixed + wontfix,
    }


def collect_lessons_counts(
    lessons_readme: Path,
    failure_modes_path: Optional[Path] = None,
) -> Dict[str, int]:
    """读 .ai-memory/lessons/README.md frontmatter 5 字段, 返回 {lessons_count, active_n_count, ...}.

    如果提供了 ``failure_modes_path``, 用 ``collect_failure_modes_counts()`` 的实时结果
    覆盖 ``active_n_count`` / ``retired_n_count`` / ``dormant_n_count``,
    消除 lessons/README.md frontmatter 手工维护滞后导致的计数漂移.
    """
    result = {f: 0 for f in LESSONS_FIELDS}
    if not lessons_readme.is_file():
        return result
    try:
        text = lessons_readme.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return result
    fm_match = FRONTMATTER_RE.match(text)
    if not fm_match:
        return result
    fm_text = fm_match.group(1)
    for field in LESSONS_FIELDS:
        m = re.search(rf"^{field}:\s*(\d+)\s*$", fm_text, re.MULTILINE)
        if m:
            result[field] = int(m.group(1))

    # 如果提供了 failure_modes_path, 用实时计数覆盖 active/retired/dormant
    if failure_modes_path:
        fm_counts = collect_failure_modes_counts(failure_modes_path)
        result["active_n_count"] = fm_counts["active"]
        result["retired_n_count"] = fm_counts["retired"]
        result["dormant_n_count"] = fm_counts["dormant"]

    return result


def collect_failure_modes_counts(failure_modes_path: Path) -> Dict[str, int]:
    """解析 .ai-memory/meta/failure-modes.md Active/Retired/Dormant 段, 返回 {active, retired, dormant}.

    段定义: ``## Active N##`` / ``## Retired N##`` / ``## Dormant N##`` 起始.
    计数: ``| N91 | ... |`` 表格行数.
    """
    result = {"active": 0, "retired": 0, "dormant": 0}
    if not failure_modes_path.is_file():
        return result
    try:
        text = failure_modes_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return result

    def _count_section(start_marker: str, end_markers: List[str]) -> int:
        start = text.find(start_marker)
        if start < 0:
            return 0
        end = len(text)
        for em in end_markers:
            pos = text.find(em, start + len(start_marker))
            if pos >= 0 and pos < end:
                end = pos
        section = text[start:end]
        return len(ACTIVE_N_ROW_RE.findall(section))

    # Active: ## Active N## → ## Retired N## 或 ## Dormant N##
    result["active"] = _count_section(
        ACTIVE_SECTION_START, [RETIRED_SECTION_START, DORMANT_SECTION_START]
    )
    # Retired: ## Retired N## → ## Dormant N## 或文件末尾
    result["retired"] = _count_section(
        RETIRED_SECTION_START, [DORMANT_SECTION_START]
    )
    # Dormant: ## Dormant N## → 文件末尾
    result["dormant"] = _count_section(DORMANT_SECTION_START, [])
    return result


def collect_doc_health_latest(health_checks_dir: Path) -> Dict[str, object]:
    """读 docs/health/*.md 最新文件 frontmatter, 返回最新报告摘要.

    Returns ``{date, total, passed, failed, attention, pass_rate, filename, found}``.
    ``found=False`` 表示无报告.
    """
    result: Dict[str, object] = {
        "date": "",
        "total": 0,
        "passed": 0,
        "failed": 0,
        "attention": 0,
        "pass_rate": 0.0,
        "filename": "",
        "found": False,
    }
    if not health_checks_dir.is_dir():
        return result
    # 找最新的 .md 文件 (按文件名排序, 取最后一个)
    md_files = sorted(health_checks_dir.glob("*.md"))
    # 排除 README.md
    md_files = [f for f in md_files if f.name.lower() != "readme.md"]
    if not md_files:
        return result
    latest = md_files[-1]
    result["filename"] = latest.name
    result["found"] = True
    try:
        text = latest.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return result

    # 从 frontmatter 提取 last_updated
    fm_match = FRONTMATTER_RE.match(text)
    if fm_match:
        fm_text = fm_match.group(1)
        m = re.search(r"^last_updated:\s*(\S+)\s*$", fm_text, re.MULTILINE)
        if m:
            result["date"] = m.group(1)

    # 从正文提取 "总项数|通过|失败|需关注" (2026-07.md 格式)
    # "> **总项数**：46 | **通过**：28 | **失败**：6 | **需关注**：12"
    # 字段名前后可能有 `**` bold 标记, 用 \*{0,2} 兼容
    m = re.search(
        r"\*{0,2}总项数\*{0,2}[：:]\s*(\d+)\s*\|\s*\*{0,2}通过\*{0,2}[：:]\s*(\d+)\s*\|\s*\*{0,2}失败\*{0,2}[：:]\s*(\d+)\s*\|\s*\*{0,2}需关注\*{0,2}[：:]\s*(\d+)",
        text,
    )
    if m:
        total = int(m.group(1))
        passed = int(m.group(2))
        failed = int(m.group(3))
        attention = int(m.group(4))
        result["total"] = total
        result["passed"] = passed
        result["failed"] = failed
        result["attention"] = attention
        if total > 0:
            result["pass_rate"] = round(passed / total * 100, 1)
    return result


def render_markdown(metrics: Dict[str, object]) -> str:
    """Render full markdown content for ``docs/business/ops/governance-dashboard.md``."""
    spec = metrics["spec"]
    td = metrics["td"]
    lessons = metrics["lessons"]
    fm_counts = metrics["failure_modes"]
    health = metrics["doc_health"]

    lines: List[str] = []
    lines.append("---")
    lines.append("date: 2026-07-22")
    lines.append("source: multi-source (specs + tech-debt + lessons + failure-modes + health-checks)")
    lines.append("generated_by: scripts/governance/governance_dashboard.py")
    lines.append("td: TD-325")
    lines.append("spec: spec-90")
    lines.append("---")
    lines.append("")
    lines.append("# 治理指标 Dashboard (auto-generated by governance_dashboard.py)")
    lines.append("")
    lines.append("> 当前快照版 (无历史趋势, 留到后续 spec). 手动跑 ``python scripts/governance/governance_dashboard.py`` 更新.")
    lines.append("")

    # 1. spec 完成率
    spec_total = spec["total"]
    spec_done = spec["done"]
    spec_in_progress = spec["in_progress"]
    spec_no_fm = spec["no_frontmatter"]
    spec_done_pct = (spec_done / spec_total * 100) if spec_total else 0
    lines.append("## 1. spec 完成率")
    lines.append("")
    lines.append(f"> 总计 **{spec_total}** 个 spec | ✅ done **{spec_done}** ({spec_done_pct:.1f}%) | "
                 f"🚧 in_progress **{spec_in_progress}** | 无 frontmatter **{spec_no_fm}**")
    lines.append("")
    lines.append("| 状态 | 计数 | 百分比 |")
    lines.append("|:---:|:---:|:---:|")
    lines.append(f"| ✅ done | {spec_done} | {spec_done_pct:.1f}% |")
    lines.append(f"| 🚧 in_progress | {spec_in_progress} | {(spec_in_progress/spec_total*100 if spec_total else 0):.1f}% |")
    lines.append(f"| 无 frontmatter | {spec_no_fm} | {(spec_no_fm/spec_total*100 if spec_total else 0):.1f}% |")
    lines.append(f"| **总计** | **{spec_total}** | 100.0% |")
    lines.append("")

    # 2. TD 计数
    lines.append("## 2. 技术债务计数")
    lines.append("")
    lines.append(f"> 总计 **{td['total']}** 个 TD | 🔧 active **{td['active']}** | ✅ fixed **{td['fixed']}** | ❌ wontfix **{td['wontfix']}**")
    lines.append("")
    lines.append("| 类别 | 计数 |")
    lines.append("|:---:|:---:|")
    lines.append(f"| 🔧 active (待修) | {td['active']} |")
    lines.append(f"| ✅ fixed (已修) | {td['fixed']} |")
    lines.append(f"| ❌ wontfix (不修) | {td['wontfix']} |")
    lines.append(f"| **总计** | **{td['total']}** |")
    lines.append("")

    # 3. lessons 计数
    lines.append("## 3. AI Lessons 计数")
    lines.append("")
    lines.append(f"> 总计 **{lessons['lessons_count']}** 个 lesson 文件 | Active N## **{lessons['active_n_count']}** | Retired **{lessons['retired_n_count']}** | Archived **{lessons['archived_n_count']}** | Dormant **{lessons['dormant_n_count']}**")
    lines.append("")
    lines.append("| 字段 | 计数 | 说明 |")
    lines.append("|:---:|:---:|---|")
    lines.append(f"| lessons_count | {lessons['lessons_count']} | lessons/ root .md 文件总数 (排除 README.md + archived-early/) |")
    lines.append(f"| active_n_count | {lessons['active_n_count']} | failure-modes.md §Active N## 编号数 (家族主条目) |")
    lines.append(f"| retired_n_count | {lessons['retired_n_count']} | M0.M 闭环 N## (硬约束沉淀到 rules/skills) |")
    lines.append(f"| archived_n_count | {lessons['archived_n_count']} | 仅 N30 (true archived) |")
    lines.append(f"| dormant_n_count | {lessons['dormant_n_count']} | 家族合并子条目 (§Dormant) |")
    lines.append("")

    # 4. failure-modes 计数
    lines.append("## 4. failure-modes.md N## 计数")
    lines.append("")
    lines.append(f"> Active **{fm_counts['active']}** | Retired **{fm_counts['retired']}** | Dormant **{fm_counts['dormant']}**")
    lines.append("")
    lines.append("| 段 | 计数 |")
    lines.append("|:---:|:---:|")
    lines.append(f"| §Active N## | {fm_counts['active']} |")
    lines.append(f"| §Retired N## | {fm_counts['retired']} |")
    lines.append(f"| §Dormant N## | {fm_counts['dormant']} |")
    lines.append("")

    # 5. doc_health 最新报告
    lines.append("## 5. doc_health 最新报告")
    lines.append("")
    if health["found"]:
        lines.append(f"> 最新报告: ``{health['filename']}`` (last_updated: {health['date']})")
        lines.append(f"> 总项数 **{health['total']}** | 通过 **{health['passed']}** ({health['pass_rate']}%) | 失败 **{health['failed']}** | 需关注 **{health['attention']}**")
        lines.append("")
        lines.append("| 字段 | 值 |")
        lines.append("|:---:|:---:|")
        lines.append(f"| 文件名 | {health['filename']} |")
        lines.append(f"| last_updated | {health['date']} |")
        lines.append(f"| 总项数 | {health['total']} |")
        lines.append(f"| 通过 | {health['passed']} |")
        lines.append(f"| 失败 | {health['failed']} |")
        lines.append(f"| 需关注 | {health['attention']} |")
        lines.append(f"| 通过率 | {health['pass_rate']}% |")
    else:
        lines.append("> ⚠️ 未找到 doc_health 报告 (docs/health/*.md)")
    lines.append("")

    lines.append("## 范围说明 (本 dashboard 不做)")
    lines.append("")
    lines.append("- **不做历史趋势**: 数据持久化机制未建立, 仅当前快照 (留到后续 spec)")
    lines.append("- **不做 CI 定时生成**: 留到 TD-327 e2e CI 接入时一并加入")
    lines.append("- **不做 HTML dashboard**: markdown 已足够, HTML 留到后续需求")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="TD-325 spec-90: 治理指标 dashboard (当前快照版)",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="GAF repo root (default: %(default)s)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check (report stats, do not write output file)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print dashboard to stdout, do not write files",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()
    specs_dir = repo_root / "docs" / "specs" / "legacy-trae"
    tech_debt_dir = repo_root / "docs" / "archive"
    lessons_readme = repo_root / ".ai-memory" / "lessons" / "README.md"
    failure_modes_path = repo_root / ".ai-memory" / "meta" / "failure-modes.md"
    health_checks_dir = repo_root / "docs" / "health"
    output_file = repo_root / "docs" / "business" / "ops" / "governance-dashboard.md"

    if not specs_dir.is_dir():
        print(f"ERROR: specs dir not found: {specs_dir}", file=sys.stderr)
        return 2

    # Collect metrics
    metrics: Dict[str, object] = {
        "spec": collect_spec_completion(specs_dir),
        "td": collect_td_counts(tech_debt_dir),
        "lessons": collect_lessons_counts(lessons_readme, failure_modes_path),
        "failure_modes": collect_failure_modes_counts(failure_modes_path),
        "doc_health": collect_doc_health_latest(health_checks_dir),
    }

    spec = metrics["spec"]
    td = metrics["td"]
    lessons = metrics["lessons"]
    fm = metrics["failure_modes"]
    health = metrics["doc_health"]

    print(f"[governance_dashboard] spec: {spec['total']} total ({spec['done']} done / {spec['in_progress']} in_progress / {spec['no_frontmatter']} no_fm)")
    print(f"[governance_dashboard] TD: {td['total']} total ({td['active']} active / {td['fixed']} fixed / {td['wontfix']} wontfix)")
    print(f"[governance_dashboard] lessons: {lessons['lessons_count']} files ({lessons['active_n_count']} Active N##)")
    print(f"[governance_dashboard] failure-modes: {fm['active']} Active / {fm['retired']} Retired / {fm['dormant']} Dormant")
    if health["found"]:
        print(f"[governance_dashboard] doc_health: {health['filename']} (pass_rate={health['pass_rate']}%)")
    else:
        print(f"[governance_dashboard] doc_health: not found")

    if args.dry_run:
        print("[governance_dashboard] --dry-run: dashboard output:")
        print(render_markdown(metrics))
        return 0

    if args.check:
        print("[governance_dashboard] --check mode: report only (exit 0)")
        return 0

    content = render_markdown(metrics)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(content, encoding="utf-8")
    print(f"[governance_dashboard] ✅ wrote {output_file} ({len(content)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
