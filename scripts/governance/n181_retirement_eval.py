"""n181_retirement_eval.py — TD-324 spec-86 N181 月度退役机制自动化.

评估 ``failure-modes.md`` §Active N## 索引, 识别可退役候选:

- **条件 A**: 连续 3 spec 未提及该 N## (扫描最近 3 个 spec 文件 grep ``N<编号>``)
- **条件 B/C**: 不自动判定 (需 AI 判断), 仅打印提示
- **硬阈值紧急评估**: Active N## > 70 → WARN (非阻塞, 类似 P5 机制)

三种运行模式:
    python scripts/governance/n181_retirement_eval.py             # 默认: 评估 + 打印报告
    python scripts/governance/n181_retirement_eval.py --check     # CI 模式: 仅检查, 不修改文件
    python scripts/governance/n181_retirement_eval.py --threshold 70  # 覆盖默认阈值
    python scripts/governance/n181_retirement_eval.py --root <path>
    python scripts/governance/n181_retirement_eval.py --recent-specs 5  # 覆盖默认 3 spec

设计参考: ``sync_tech_debt_counts.py`` + ``sync_spec_index.py`` (argparse + Path +
_encoding_safe Windows UTF-8 fix).

Exit codes
----------
    0 - 成功 (评估完成; 即使 Active > 70 阈值也返回 0, 仅 WARN 不阻塞)
    1 - 配置/参数错误 (目录不存在等)
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
from typing import Dict, List, Tuple  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
FAILURE_MODES_PATH_DEFAULT = REPO_ROOT_DEFAULT / ".ai-memory" / "meta" / "failure-modes.md"
SPECS_DIR_DEFAULT = REPO_ROOT_DEFAULT / "docs" / "specs"

# Active N## 段标题 (failure-modes.md)
ACTIVE_SECTION_START = "## Active N##"
ACTIVE_SECTION_END = "## Retired N##"  # Active 段结束 = Retired 段开始

# 匹配 Active N## 索引表行: ``| N91 | ... |`` (4 列表格)
ACTIVE_N_ROW_RE = re.compile(r"^\|\s*(N\d+)\s*\|", re.MULTILINE)

# spec 文件名模式: YYYY-MM-DD-<id>-<topic>.md (兼容 s1 / s27 / 无 s 号, 如 2026-08-20-governance-...)
SPEC_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-", re.IGNORECASE)


def parse_active_n_ids(failure_modes_path: Path) -> List[str]:
    """解析 failure-modes.md Active N## 段, 返回 N## 编号 list (按出现顺序).

    Active 段定义: ``## Active N##`` 起始, ``## Retired N##`` 结束.
    仅匹配 ``| N91 | ... |`` 4 列表格行, 不匹配标题或注释.

    Returns 空列表 if 文件不存在或段未找到.
    """
    if not failure_modes_path.exists():
        return []
    try:
        text = failure_modes_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    start = text.find(ACTIVE_SECTION_START)
    if start < 0:
        return []
    end = text.find(ACTIVE_SECTION_END, start)
    if end < 0:
        end = len(text)
    section = text[start:end]
    return ACTIVE_N_ROW_RE.findall(section)


def scan_recent_specs(
    specs_dir: Path, n_ids: List[str], recent_count: int = 3
) -> Dict[str, int]:
    """扫描最近 N 个 spec 文件, 统计每个 N## 被提及次数.

    spec 文件按文件名 (日期前缀) 降序排序, 取最近 ``recent_count`` 个.
    对每个 spec, grep ``N<编号>`` (whole word match) 统计提及次数.

    Returns ``{n_id: total_mention_count_across_recent_specs}``.
    """
    if not specs_dir.exists() or not n_ids:
        return {n_id: 0 for n_id in n_ids}
    # 收集所有 spec 文件 (按文件名排序, 最新在前) — 递归扫 active/ + archived/ (排除 legacy-trae)
    spec_files = sorted(
        [
            f
            for f in specs_dir.rglob("*.md")
            if "legacy-trae" not in f.parts and SPEC_FILENAME_RE.match(f.name)
        ],
        key=lambda f: f.name,
        reverse=True,
    )
    recent_specs = spec_files[:recent_count]
    mention_map: Dict[str, int] = {n_id: 0 for n_id in n_ids}
    for spec_file in recent_specs:
        try:
            text = spec_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n_id in n_ids:
            # whole word match: \bN91\b 不匹配 N910 / N91X
            pattern = rf"\b{re.escape(n_id)}\b"
            if re.search(pattern, text):
                mention_map[n_id] += 1
    return mention_map


def find_retirement_candidates(
    active_n_ids: List[str], mention_map: Dict[str, int]
) -> List[str]:
    """条件 A 候选: mention_count == 0 (最近 3 spec 未提及).

    Returns list of N## 满足条件 A (未提及).
    """
    return [n_id for n_id in active_n_ids if mention_map.get(n_id, 0) == 0]


def render_report(
    active_n_ids: List[str],
    mention_map: Dict[str, int],
    candidates: List[str],
    threshold: int,
    recent_count: int,
    threshold_exceeded: bool,
) -> str:
    """渲染评估报告 (markdown 格式)."""
    lines: List[str] = []
    lines.append("# N181 月度退役评估报告")
    lines.append("")
    lines.append(f"- Active N## 总数: {len(active_n_ids)}")
    lines.append(f"- 扫描最近 spec 数: {recent_count}")
    lines.append(f"- 硬阈值: Active > {threshold} 触发紧急评估")
    lines.append(
        f"- 阈值状态: {'⚠️ 超阈值 (触发紧急评估)' if threshold_exceeded else '✅ 未超阈值'}"
    )
    lines.append("")
    lines.append("## 条件 A 候选 (最近 {} spec 未提及)".format(recent_count))
    if candidates:
        lines.append("")
        for n_id in candidates:
            lines.append(f"- {n_id} (mention_count=0)")
        lines.append("")
        lines.append(
            "> 条件 A 满足可退役, 但需 AI/人工复核条件 B/C (是否已被新 N## 覆盖 / "
            "AI 默认行为已符合). 退役流程见 project_rules.md §4.12."
        )
    else:
        lines.append("")
        lines.append("无候选 — 所有 Active N## 在最近 {} spec 中均被提及.".format(recent_count))
    lines.append("")
    lines.append("## 条件 B/C (需 AI 判断)")
    lines.append("")
    lines.append(
        "- **条件 B**: 已被新 N## 覆盖 (如 N165 合并到 N170 模式) — 需 AI 检查 N## 主题重叠"
    )
    lines.append(
        "- **条件 C**: AI 默认行为已符合 — 需 AI 评估当前是否默认不犯此反模式"
    )
    lines.append("")
    lines.append("## 提及统计 (最近 {} spec)".format(recent_count))
    lines.append("")
    lines.append("| N## | 提及次数 |")
    lines.append("|:---:|:--------:|")
    for n_id in active_n_ids:
        count = mention_map.get(n_id, 0)
        marker = " 🔸候选" if count == 0 else ""
        lines.append(f"| {n_id} | {count}{marker} |")
    return "\n".join(lines)


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(
        description="N181 月度退役机制自动化评估 (TD-324 spec-86)."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="CI 模式: 仅检查, 不修改文件 (默认即不修改, 此 flag 保留供 CI 调用).",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=70,
        help="Active N## 硬阈值 (默认 %(default)s, 超过触发紧急评估 WARN).",
    )
    parser.add_argument(
        "--recent-specs",
        type=int,
        default=3,
        help="条件 A 扫描最近 N 个 spec (默认 %(default)s, N181 spec-62 修订).",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="GAF repo 根路径 (默认 %(default)s).",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    failure_modes_path = root / ".ai-memory" / "meta" / "failure-modes.md"
    specs_dir = root / "docs" / "specs"

    if not failure_modes_path.exists():
        print(f"❌ failure-modes.md 不存在: {failure_modes_path}")
        return 1
    if not specs_dir.exists():
        print(f"⚠️ specs/ 目录不存在: {specs_dir} (条件 A 检查将返回全部 Active 为候选)")

    # Step 1: parse Active N##
    active_n_ids = parse_active_n_ids(failure_modes_path)
    if not active_n_ids:
        print("⚠️ 未解析到 Active N## (failure-modes.md §Active N## 段为空或格式不符)")
        return 0

    print(f"📊 Active N## 总数: {len(active_n_ids)}")

    # Step 2: 硬阈值紧急评估
    threshold_exceeded = len(active_n_ids) > args.threshold
    if threshold_exceeded:
        print(
            f"⚠️ N181 紧急评估: Active N## {len(active_n_ids)} > {args.threshold} 硬阈值 "
            "(project_rules.md §4.12) — 需立即评估退役候选"
        )
    else:
        print(f"✅ 阈值检查: Active N## {len(active_n_ids)} ≤ {args.threshold} (未超阈值)")

    # Step 3: 条件 A — 扫描最近 spec
    mention_map = scan_recent_specs(specs_dir, active_n_ids, args.recent_specs)
    candidates = find_retirement_candidates(active_n_ids, mention_map)

    print()
    print(f"🔍 条件 A 候选 (最近 {args.recent_specs} spec 未提及): {len(candidates)}")
    if candidates:
        for n_id in candidates:
            print(f"   - {n_id}")

    # Step 4: 完整报告
    print()
    print("=" * 60)
    report = render_report(
        active_n_ids=active_n_ids,
        mention_map=mention_map,
        candidates=candidates,
        threshold=args.threshold,
        recent_count=args.recent_specs,
        threshold_exceeded=threshold_exceeded,
    )
    print(report)
    print("=" * 60)
    print()
    print(
        "📝 下一步: AI/人工复核条件 B/C, 确认退役的 N## 按项目规则 §4.12 流程迁移到 §Retired."
    )
    print("   退役流程: failure-modes.md §Active → §Retired + lesson 文件迁 archived-lessons.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
