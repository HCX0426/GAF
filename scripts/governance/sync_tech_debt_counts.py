"""sync_tech_debt_counts.py — TD-319 tech-debt 三文件计数自动同步.

扫描 ``docs/archive/{active-tech-debt,fixed-tech-debt,wontfix-tech-debt}.md``
的 ``^## TD-`` 行数, 同步到 ``docs/archive/tech-debt-README.md`` 总览表
(L23-26) + 更新 frontmatter ``last_updated`` 字段.

两种运行模式:
    python scripts/governance/sync_tech_debt_counts.py           # 同步 (默认)
    python scripts/governance/sync_tech_debt_counts.py --check   # 只检查, 不一致返回 1
    python scripts/governance/sync_tech_debt_counts.py --dry-run # 只报告不写文件
    python scripts/governance/sync_tech_debt_counts.py --root <path>

设计参考: ``scripts/bootstrap/sync_ai_memory.py`` (argparse + Path 对象 +
_encoding_safe Windows UTF-8 fix).

Exit codes
----------
    0 - 成功 (同步完成, 或 --check 模式下计数一致)
    1 - --check 模式下计数不一致
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
import datetime as _dt  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Dict, Tuple  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]

# ``^## TD-`` heading line — matches ``## TD-319: ...`` but not ``### TD-319``
# and not the ``## TD-XXX`` template placeholder in active-tech-debt.md.
TD_HEADING_RE = re.compile(r"^## TD-\d+", re.MULTILINE)

# Index-table row — fixed-tech-debt.md uses ``| [TD-NNN](L) | 摘要 |`` rows
# (one row per fixed TD), so its count is the number of index rows, not
# ``## TD-`` headings (only TD-330/335/336 retain full sections).
FIXED_INDEX_ROW_RE = re.compile(r"^\|\s*\[TD-\d+\]", re.MULTILINE)

# Front matter ``last_updated: YYYY-MM-DD`` line.
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def count_td_entries(path: Path) -> int:
    """Count ``^## TD-`` lines in a markdown file.

    Returns 0 if the file does not exist (defensive; real files always exist
    when invoked from ``main()`` after the directory check).
    """
    if not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8")
    return len(TD_HEADING_RE.findall(text))


def count_fixed_entries(path: Path) -> int:
    """Count index-table rows in fixed-tech-debt.md.

    The fixed file lists each closed TD as ``| [TD-NNN](L) | 摘要 |`` row;
    only a handful of recent entries (TD-330/335/336) also keep full
    ``## TD-`` sections. The README "TD 数量" column therefore counts the
    index rows.
    """
    if not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8")
    return len(FIXED_INDEX_ROW_RE.findall(text))


def compute_counts(root: Path) -> Dict[str, int]:
    """Compute TD counts for active/fixed/wontfix + total under ``root``.

    ``root`` is the GAF repo root. Returns a dict with keys
    ``active`` / ``fixed`` / ``wontfix`` / ``total``.
    """
    td_dir = root / "docs" / "archive"
    counts = {
        "active": count_td_entries(td_dir / "active-tech-debt.md"),
        "fixed": count_fixed_entries(td_dir / "fixed-tech-debt.md"),
        "wontfix": count_td_entries(td_dir / "wontfix-tech-debt.md"),
    }
    counts["total"] = counts["active"] + counts["fixed"] + counts["wontfix"]
    return counts


# Regexes for the tech-debt-README.md overview table rows.
# Row shape:
#   | [active-tech-debt.md](active-tech-debt.md) | 🔧 待修... | 22 |
#   | [fixed-tech-debt-details.md](fixed-tech-debt-details.md) | ✅ FIXED ... | 280 |
#   | [wontfix-tech-debt.md](wontfix-tech-debt.md) | ❌ ... | 7 |
#   | **合计** | | **309** |
# We match the trailing `` | <digits> |`` (or ``| **<digits>** |`` for total)
# and replace just the number, leaving the description column untouched.

_ACTIVE_ROW_RE = re.compile(
    r"(\|\s*\[active-tech-debt\.md\]\(active-tech-debt\.md\)\s*\|[^|]+\|\s*)\d+(\s*\|\s*$)",
    re.MULTILINE,
)
_FIXED_ROW_RE = re.compile(
    r"(\|\s*\[fixed-tech-debt\.md\]\(fixed-tech-debt\.md\)\s*\|[^|]+\|\s*)\d+(\s*\|\s*$)",
    re.MULTILINE,
)
_WONTFIX_ROW_RE = re.compile(
    r"(\|\s*\[wontfix-tech-debt\.md\]\(wontfix-tech-debt\.md\)\s*\|[^|]+\|\s*)\d+(\s*\|\s*$)",
    re.MULTILINE,
)
_TOTAL_ROW_RE = re.compile(
    r"(\|\s*\*\*合计\*\*\s*\|\s*\|\s*\*\*)\d+(\*\*\s*\|\s*$)",
    re.MULTILINE,
)


def update_readme_table(readme_path: Path, counts: Dict[str, int], *, dry_run: bool = False) -> bool:
    """Update README.md overview table with new counts.

    Returns True if the file content changed (and was written unless dry_run).
    Idempotent: returns False when counts already match.
    """
    text = readme_path.read_text(encoding="utf-8")
    new_text = text

    def _replace(pattern: re.Pattern, value: int) -> None:
        nonlocal new_text
        new_text = pattern.sub(rf"\g<1>{value}\g<2>", new_text, count=1)

    _replace(_ACTIVE_ROW_RE, counts["active"])
    _replace(_FIXED_ROW_RE, counts["fixed"])
    _replace(_WONTFIX_ROW_RE, counts["wontfix"])
    _replace(_TOTAL_ROW_RE, counts["total"])

    if new_text == text:
        return False
    if not dry_run:
        readme_path.write_text(new_text, encoding="utf-8")
    return True


def update_frontmatter_timestamp(path: Path, *, dry_run: bool = False) -> bool:
    """Update frontmatter ``last_updated`` field to today's date.

    Returns True if the file content changed. Idempotent.
    """
    today = _dt.date.today().isoformat()
    text = path.read_text(encoding="utf-8")
    fm_match = FRONTMATTER_RE.match(text)
    if not fm_match:
        return False
    fm = fm_match.group(1)
    new_fm = re.sub(
        r"^last_updated:.*$",
        f"last_updated: {today}",
        fm,
        count=1,
        flags=re.MULTILINE,
    )
    if new_fm == fm:
        return False
    new_text = text.replace(fm, new_fm, 1)
    if new_text == text:
        return False
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return True


def parse_readme_counts(readme_path: Path) -> Dict[str, int]:
    """Parse current counts from README.md overview table.

    Returns dict with keys ``active`` / ``fixed`` / ``wontfix`` / ``total``.
    Missing values are returned as -1 so callers can detect parse failures.
    """
    text = readme_path.read_text(encoding="utf-8")
    result: Dict[str, int] = {"active": -1, "fixed": -1, "wontfix": -1, "total": -1}

    m = _ACTIVE_ROW_RE.search(text)
    if m:
        # Re-extract the digit run from the matched region.
        digits = re.search(r"\d+", m.group(0))
        if digits:
            result["active"] = int(digits.group(0))
    m = _FIXED_ROW_RE.search(text)
    if m:
        digits = re.search(r"\d+", m.group(0))
        if digits:
            result["fixed"] = int(digits.group(0))
    m = _WONTFIX_ROW_RE.search(text)
    if m:
        digits = re.search(r"\d+", m.group(0))
        if digits:
            result["wontfix"] = int(digits.group(0))
    m = _TOTAL_ROW_RE.search(text)
    if m:
        digits = re.search(r"\d+", m.group(0))
        if digits:
            result["total"] = int(digits.group(0))
    return result


def check_consistency(root: Path) -> Tuple[bool, Dict[str, int], Dict[str, int]]:
    """Check whether README.md counts match actual ``^## TD-`` counts.

    Returns ``(is_consistent, actual_counts, readme_counts)``.
    """
    actual = compute_counts(root)
    readme_path = root / "docs" / "archive" / "tech-debt-README.md"
    readme = parse_readme_counts(readme_path)
    is_consistent = all(readme[k] == actual[k] for k in ("active", "fixed", "wontfix", "total"))
    return is_consistent, actual, readme


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="TD-319 tech-debt 三文件计数自动同步",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查不修改; 不一致时返回 1 (用于 pre-commit hook)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只报告会改动什么, 不写文件",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="GAF repo root (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    td_dir = root / "docs" / "archive"
    if not td_dir.is_dir():
        print(f"ERROR: {td_dir} does not exist or is not a directory", file=sys.stderr)
        return 2

    readme_path = td_dir / "tech-debt-README.md"
    if not readme_path.is_file():
        print(f"ERROR: {readme_path} not found", file=sys.stderr)
        return 2

    # --- --check mode: compare and exit ---
    if args.check:
        is_consistent, actual, readme = check_consistency(root)
        if is_consistent:
            print(
                f"✅ tech-debt counts consistent: "
                f"active={actual['active']} fixed={actual['fixed']} "
                f"wontfix={actual['wontfix']} total={actual['total']}"
            )
            return 0
        print("❌ tech-debt counts drifted:", file=sys.stderr)
        print(
            f"   README.md: active={readme['active']} fixed={readme['fixed']} "
            f"wontfix={readme['wontfix']} total={readme['total']}",
            file=sys.stderr,
        )
        print(
            f"   actual:    active={actual['active']} fixed={actual['fixed']} "
            f"wontfix={actual['wontfix']} total={actual['total']}",
            file=sys.stderr,
        )
        print(
            f"   Fix: python scripts/governance/sync_tech_debt_counts.py",
            file=sys.stderr,
        )
        return 1

    # --- sync mode: update README.md table + frontmatter ---
    counts = compute_counts(root)
    modified: list[str] = []
    if update_readme_table(readme_path, counts, dry_run=args.dry_run):
        modified.append("README.md:overview-table")
    if update_frontmatter_timestamp(readme_path, dry_run=args.dry_run):
        modified.append("README.md:last_updated")

    summary = (
        f"active={counts['active']} fixed={counts['fixed']} "
        f"wontfix={counts['wontfix']} total={counts['total']}"
    )
    if modified:
        verb = "would update" if args.dry_run else "updated"
        print(f"✅ sync_tech_debt_counts: {verb} {', '.join(modified)}")
        print(f"   {summary}")
    else:
        print(f"✅ sync_tech_debt_counts: already consistent ({summary})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
