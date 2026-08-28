"""check_spec_context.py — TD-342 pre-commit hook: 强制 B2 大修改 spec-context 承载体.

When staged changes constitute a "big change" (per check_big_change.py 4-dimension
check) AND B2 evidence is valid, this hook requires a corresponding spec-context
file (docs/archive/spec-context/<spec-name>-context.md) to exist.

The hook is a no-op (exit 0) when:
- Staged changes are NOT a big change (is_big=false), OR
- B2 evidence is invalid (check_big_change_hook.py already blocks this), OR
- A spec-context file exists matching the active spec AND N173 用时字段全部填写

Otherwise the commit is blocked with a remediation hint.

spec-context 承载体内容要求 (project_rules.md §6.x):
- 用户决策原文 (对话片段)
- N151 5 步法评估过程
- N167 七维度评分细节
- 关键实施决策
- N173 用时字段 (start_ts / end_ts / duration_min / within_baseline / root_cause_if_over)

Usage
-----
    python scripts/hooks/check_spec_context.py            # auto-detect staged
    python scripts/hooks/check_spec_context.py --no-fail  # warn only
    python scripts/hooks/check_spec_context.py --force    # always check

Exit codes
----------
    0 - not a big change, OR B2 invalid, OR spec-context exists + N173 fields filled
    1 - big change + B2 valid but no spec-context OR N173 fields missing (blocks commit unless --no-fail)
    2 - configuration / argument error

TD-342 (spec-2026-07-26-meta-governance-fix T3, 2026-07-26): spec-context 机制设计但
未硬约束化, AI 自决 P2 任务跳过. 此 hook 把 spec-context 从"AI 自决"升级为"pre-commit 强制".

N173 强化 (spec-2026-07-26-ai-governance-execution-rate-fix Wave 1, 2026-07-26):
spec-context 必含 5 个用时字段 (start_ts / end_ts / duration_min / within_baseline /
root_cause_if_over). 缺失或占位符 → commit 失败. 把 N173 从"AI 自填"升级为"hook 强制".
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
import json  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from check_big_change import (  # noqa: E402
    check_big_change_staged,
    is_b2_evidence_valid,
    read_b2_evidence,
)

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
SPEC_CONTEXT_DIR = REPO_ROOT_DEFAULT / "docs" / "archive" / "spec-context"
ACTIVE_SPECS_DIR = REPO_ROOT_DEFAULT / "docs" / "specs" / "active"


def find_active_spec_name() -> str | None:
    """Find the active spec name from B2 evidence or active specs dir.

    Returns spec-name (without .md) if found, else None.
    """
    # Try B2 evidence first (may contain spec_id)
    evidence = read_b2_evidence()
    if evidence:
        spec_id = evidence.get("spec_id")
        if spec_id:
            # spec_id format: spec-2026-07-26-td341-ref-docs-merge
            # spec-context file: 2026-07-26-td341-ref-docs-merge-context.md
            match = re.match(r"^spec-(.+)$", spec_id)
            if match:
                return match.group(1)

    # Fallback: find the most recent active spec (by mtime)
    if not ACTIVE_SPECS_DIR.exists():
        return None
    spec_files = sorted(
        ACTIVE_SPECS_DIR.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not spec_files:
        return None
    # spec file: 2026-07-26-meta-governance-fix.md → spec name: 2026-07-26-meta-governance-fix
    return spec_files[0].stem


def spec_context_exists(spec_name: str | None) -> bool:
    """Check if spec-context file exists for the given spec name."""
    if not spec_name:
        return False
    if not SPEC_CONTEXT_DIR.exists():
        return False
    # Try exact match: <spec-name>-context.md
    context_file = SPEC_CONTEXT_DIR / f"{spec_name}-context.md"
    if context_file.exists():
        return True
    # Try without "-context" suffix (some specs may use different naming)
    context_file2 = SPEC_CONTEXT_DIR / f"{spec_name}.md"
    if context_file2.exists():
        return True
    return False


def find_spec_context_file(spec_name: str | None) -> Path | None:
    """Return the actual spec-context file Path for the given spec name, or None."""
    if not spec_name:
        return None
    if not SPEC_CONTEXT_DIR.exists():
        return None
    context_file = SPEC_CONTEXT_DIR / f"{spec_name}-context.md"
    if context_file.exists():
        return context_file
    context_file2 = SPEC_CONTEXT_DIR / f"{spec_name}.md"
    if context_file2.exists():
        return context_file2
    return None


# N173 用时字段占位符检测 — 字段值若匹配以下模式视为未填写
N173_PLACEHOLDER_PATTERNS = [
    r"^\(.*\)$",            # (Wave 3 完成后填写) / (计算后填写) / (对照...基线)
    r"^TBD$",               # 显式 TBD
    r"^<.*>$",              # <fill-in>
    r"^待填写$",
    r"^未填$",
    r"^-$",                 # 短横线 (failure-modes 表格风格)
    r"^$",
]


def _is_placeholder(value: str) -> bool:
    """Return True if the field value looks like an unfilled placeholder."""
    if value is None:
        return True
    v = value.strip()
    if not v:
        return True
    import re as _re
    for pat in N173_PLACEHOLDER_PATTERNS:
        if _re.match(pat, v, _re.IGNORECASE):
            return True
    return False


def check_n173_timing_fields(context_file: Path) -> tuple[bool, list[str]]:
    """Validate N173 用时字段 in spec-context file.

    Required fields (in "## N173 用时字段" section or frontmatter):
    - start_ts: ISO8601 datetime
    - end_ts: ISO8601 datetime
    - duration_min: number (minutes)
    - within_baseline: bool (true/false)
    - root_cause_if_over: string (required only if within_baseline=false)

    Returns (is_valid, missing_or_placeholder_fields).
    """
    if not context_file.exists():
        return False, ["spec-context 文件不存在"]

    text = context_file.read_text(encoding="utf-8")

    # Try frontmatter first (preferred — structured)
    fields = {}
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            frontmatter = text[4:end]
            for line in frontmatter.splitlines():
                m = re.match(r"^(\w+):\s*(.+?)\s*$", line)
                if m and m.group(1) in {
                    "start_ts",
                    "end_ts",
                    "duration_min",
                    "within_baseline",
                    "root_cause_if_over",
                }:
                    fields[m.group(1)] = m.group(2).strip()

    # Fallback: parse "## N173 用时字段" section (supports "- `field`: value" or "- field: value")
    # Header may be "## N173 用时字段" or "## 7. N173 用时字段" (with section number)
    if not fields:
        section_match = re.search(
            r"^##\s*(?:\d+\.\s*)?N173\s*用时字段.*?$([\s\S]*?)(?=^##\s|\Z)",
            text,
            re.MULTILINE,
        )
        if section_match:
            section_body = section_match.group(1)
            # Match patterns like: - `start_ts`: 2026-07-26T16:30:00+08:00
            for fm in re.finditer(
                r"^[-*]\s*`?(\w+)`?\s*[:：]\s*(.+?)\s*$",
                section_body,
                re.MULTILINE,
            ):
                key = fm.group(1)
                val = fm.group(2)
                if key in {
                    "start_ts",
                    "end_ts",
                    "duration_min",
                    "within_baseline",
                    "root_cause_if_over",
                }:
                    fields[key] = val

    missing = []
    for required in ["start_ts", "end_ts", "duration_min", "within_baseline"]:
        val = fields.get(required)
        if val is None or _is_placeholder(val):
            missing.append(required)

    # root_cause_if_over: required only if within_baseline is false
    wb_raw = fields.get("within_baseline", "")
    wb_str = wb_raw.lower().strip()
    if wb_str in {"false", "no", "n", "f"}:
        rc = fields.get("root_cause_if_over")
        if rc is None or _is_placeholder(rc):
            missing.append("root_cause_if_over (因 within_baseline=false 必填)")

    return (len(missing) == 0), missing


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="TD-342 pre-commit hook: 强制 B2 大修改 spec-context 承载体",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run the check even when not in a pre-commit context",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Warn-only mode: print warning but do not exit 1",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="GAF repo root (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()
    _ = repo_root  # future-proof

    # Step 1: evaluate staged changes
    result = check_big_change_staged()

    if not result["is_big"]:
        # Small change — no spec-context required
        return 0

    # Step 2: big change detected — check B2 evidence validity
    evidence = read_b2_evidence()
    is_valid, fail_reason = is_b2_evidence_valid(evidence)

    if not is_valid:
        # B2 evidence invalid — check_big_change_hook.py already blocks this
        # We don't double-block; just warn
        print(
            f"⚠️ spec-context 检查跳过: B2 evidence 无效 ({fail_reason}) — check_big_change_hook.py 会阻塞",
            file=sys.stderr,
        )
        return 0

    # Step 3: B2 valid — require spec-context file
    spec_name = find_active_spec_name()
    if not spec_name:
        # No active spec (e.g. pure archive/cleanup commit after spec completion) —
        # spec-context carrier is only required for active spec changes.
        print(
            "⚠️ spec-context 检查跳过: 无活跃 spec (active/ 目录为空, 归档/清理 commit)",
            file=sys.stderr,
        )
        return 0
    if spec_context_exists(spec_name):
        # spec-context exists — now validate N173 用时字段 (Wave 1 强化)
        context_file = find_spec_context_file(spec_name)
        if context_file is None:
            # shouldn't happen (spec_context_exists returned True), defensive
            print(
                f"⚠️ spec-context 承载体存在但路径解析失败: {spec_name}",
                file=sys.stderr,
            )
            return 0
        n173_ok, missing = check_n173_timing_fields(context_file)
        if n173_ok:
            print(
                f"✅ spec-context 承载体存在 + N173 用时字段完整: docs/archive/spec-context/{context_file.name}",
                file=sys.stderr,
            )
            return 0
        # N173 fields missing or placeholder — block commit (unless --no-fail)
        print(
            f"❌ spec-context 承载体存在但 N173 用时字段未填写: {context_file.name}",
            file=sys.stderr,
        )
        print(f"   缺失/占位符字段: {', '.join(missing)}", file=sys.stderr)
        print("", file=sys.stderr)
        print("💡 N173 用时字段必填 (spec-2026-07-26-ai-governance-execution-rate-fix Wave 1):", file=sys.stderr)
        print("   在 spec-context 文件中填写以下 5 个字段 (## N173 用时字段 段或 frontmatter):", file=sys.stderr)
        print("     - start_ts: ISO8601 任务开始时间 (第一个工具调用前)", file=sys.stderr)
        print("     - end_ts: ISO8601 任务结束时间 (commit 时刻)", file=sys.stderr)
        print("     - duration_min: 数字, 用时 (分钟)", file=sys.stderr)
        print("     - within_baseline: true/false (小<5/中<15/大<60/沉淀<5)", file=sys.stderr)
        print("     - root_cause_if_over: 超基线时必填根因 (within_baseline=false 时)", file=sys.stderr)
        print("", file=sys.stderr)
        print("   绕过 (仅紧急情况):", file=sys.stderr)
        print("   git commit --no-verify  # 跳过 hook (不推荐)", file=sys.stderr)
        if args.no_fail:
            print("⚠️ --no-fail 模式: 仅警告, 不阻塞 commit", file=sys.stderr)
            return 0
        return 1

    # Step 4: spec-context missing — block commit (unless --no-fail)
    reasons_str = "; ".join(result["reasons"]) if result["reasons"] else "(no reasons)"
    print(
        f"🔍 B2 大修改检测到: {reasons_str}",
        file=sys.stderr,
    )
    print(f"❌ spec-context 承载体缺失 (spec: {spec_name})", file=sys.stderr)
    print("", file=sys.stderr)
    print("💡 B2 大修改 commit 需先写 spec-context 承载体 (project_rules.md §6.x):", file=sys.stderr)
    print(f"   1. 创建 docs/archive/spec-context/{spec_name}-context.md", file=sys.stderr)
    print("   2. 内容必含:", file=sys.stderr)
    print("      - 用户决策原文 (对话片段)", file=sys.stderr)
    print("      - N151 5 步法评估过程", file=sys.stderr)
    print("      - N167 七维度评分细节", file=sys.stderr)
    print("      - 关键实施决策", file=sys.stderr)
    print("      - N173 用时字段 (start_ts / end_ts / duration_min / within_baseline / root_cause_if_over)", file=sys.stderr)
    print("   3. 豁免: 小修改 (无 B2 evidence) / 纯文档修改", file=sys.stderr)
    print("", file=sys.stderr)
    print("   绕过 (仅紧急情况):", file=sys.stderr)
    print("   git commit --no-verify  # 跳过 hook (不推荐)", file=sys.stderr)

    if args.no_fail:
        print("⚠️ --no-fail 模式: 仅警告, 不阻塞 commit", file=sys.stderr)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
