"""test_sync_tech_debt_counts.py — tests for TD-319 sync_tech_debt_counts.py.

Covers:
1. test_count_td_entries        — ``^## TD-`` line counting
2. test_update_readme_table      — README.md overview table update
3. test_check_mode_detects_drift — ``--check`` returns 1 on drift, 0 after sync
4. test_idempotent_sync          — running sync twice is a no-op
5. test_update_frontmatter       — ``last_updated`` frontmatter field updated

Run with: ``pytest scripts/tests/test_sync_tech_debt_counts.py -v``
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ and scripts/governance/ importable. conftest.py already adds
# scripts/ + bootstrap/hooks/lessons to sys.path, but NOT governance, so we
# add it explicitly here.
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_GOVERNANCE_DIR = _SCRIPTS_DIR / "governance"

pytestmark = pytest.mark.unit
for _p in (_SCRIPTS_DIR, _GOVERNANCE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import sync_tech_debt_counts as sync  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers: build a synthetic tech-debt directory under tmp_path
# ---------------------------------------------------------------------------

README_TEMPLATE = """\
---
summary: GAF 技术债务登记表
last_updated: 2026-01-01
---

# GAF 技术债务登记表

## 目录结构

| 文件 | 内容 | TD 数量 |
|:---|:---|:---:|
| [active-tech-debt.md](active-tech-debt.md) | 🔧 待修 条目 | {active} |
| [fixed-tech-debt.md](fixed-tech-debt.md) | ✅ FIXED 条目 | {fixed} |
| [wontfix-tech-debt.md](wontfix-tech-debt.md) | ❌ WONTFIX 条目 | {wontfix} |
| **合计** | | **{total}** |
"""


def _make_td_file(num_entries: int) -> str:
    """Build a markdown body with ``num_entries`` ``## TD-NNN`` headings."""
    lines = ["# Tech Debts", ""]
    for i in range(1, num_entries + 1):
        lines.append(f"## TD-{i:03d}: sample debt {i}")
        lines.append("")
        lines.append(f"- body for TD-{i:03d}")
        lines.append("")
    # Add a non-matching heading to ensure ``### TD-`` is not counted.
    lines.append("### TD-999: sub-heading should not count")
    lines.append("")
    return "\n".join(lines)


def _make_fixed_index_file(num_entries: int) -> str:
    """Build fixed-tech-debt.md body: ``| [TD-NNN](L) | 摘要 |`` index rows."""
    lines = ["# Fixed Tech Debts", "", "| TD | 摘要 |", "|----|------|"]
    for i in range(1, num_entries + 1):
        lines.append(f"| [TD-{i:03d}](L) | fixed debt {i} |")
    return "\n".join(lines)


def _build_tech_debt_dir(
    root: Path,
    *,
    active: int,
    fixed: int,
    wontfix: int,
    readme_active: int | None = None,
    readme_fixed: int | None = None,
    readme_wontfix: int | None = None,
    readme_total: int | None = None,
) -> Path:
    """Create a synthetic docs/archive/ directory under ``root``.

    By default the tech-debt-README.md counts match the file contents; pass
    ``readme_*`` overrides to introduce drift for --check tests.
    """
    td_dir = root / "docs" / "archive"
    td_dir.mkdir(parents=True, exist_ok=True)
    (td_dir / "active-tech-debt.md").write_text(_make_td_file(active), encoding="utf-8")
    (td_dir / "fixed-tech-debt.md").write_text(_make_fixed_index_file(fixed), encoding="utf-8")
    (td_dir / "wontfix-tech-debt.md").write_text(_make_td_file(wontfix), encoding="utf-8")

    ra = readme_active if readme_active is not None else active
    rf = readme_fixed if readme_fixed is not None else fixed
    rw = readme_wontfix if readme_wontfix is not None else wontfix
    rt = readme_total if readme_total is not None else ra + rf + rw
    (td_dir / "tech-debt-README.md").write_text(
        README_TEMPLATE.format(active=ra, fixed=rf, wontfix=rw, total=rt),
        encoding="utf-8",
    )
    return td_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_count_td_entries(tmp_path: Path) -> None:
    """count_td_entries counts ``^## TD-`` lines and ignores ``### TD-``."""
    _build_tech_debt_dir(tmp_path, active=3, fixed=5, wontfix=2)

    counts = sync.compute_counts(tmp_path)
    assert counts["active"] == 3
    assert counts["fixed"] == 5
    assert counts["wontfix"] == 2
    assert counts["total"] == 10

    # Direct count_td_entries on a single file.
    active_path = tmp_path / "docs" / "archive" / "active-tech-debt.md"
    assert sync.count_td_entries(active_path) == 3

    # Defensive: missing file returns 0, not an exception.
    assert sync.count_td_entries(tmp_path / "nonexistent.md") == 0


def test_update_readme_table(tmp_path: Path) -> None:
    """update_readme_table rewrites the four count cells in README.md."""
    # Start with deliberately wrong README counts.
    td_dir = _build_tech_debt_dir(
        tmp_path,
        active=4,
        fixed=6,
        wontfix=1,
        readme_active=99,
        readme_fixed=99,
        readme_wontfix=99,
        readme_total=999,
    )
    readme_path = td_dir / "tech-debt-README.md"
    counts = sync.compute_counts(tmp_path)

    changed = sync.update_readme_table(readme_path, counts)
    assert changed is True

    parsed = sync.parse_readme_counts(readme_path)
    assert parsed["active"] == 4
    assert parsed["fixed"] == 6
    assert parsed["wontfix"] == 1
    assert parsed["total"] == 11

    # Running again with the same counts is a no-op.
    changed_again = sync.update_readme_table(readme_path, counts)
    assert changed_again is False


def test_check_mode_detects_drift(tmp_path: Path) -> None:
    """--check returns 1 on drift, then 0 after sync."""
    _build_tech_debt_dir(
        tmp_path,
        active=2,
        fixed=3,
        wontfix=1,
        readme_active=10,
        readme_fixed=20,
        readme_wontfix=5,
        readme_total=35,
    )

    # Drift: --check must fail.
    rc = sync.main(["--check", "--root", str(tmp_path)])
    assert rc == 1

    # Sync: default mode fixes the drift.
    rc = sync.main(["--root", str(tmp_path)])
    assert rc == 0

    # After sync: --check must pass.
    rc = sync.main(["--check", "--root", str(tmp_path)])
    assert rc == 0

    # Verify the README.md now reflects actual counts.
    readme_path = tmp_path / "docs" / "archive" / "tech-debt-README.md"
    parsed = sync.parse_readme_counts(readme_path)
    assert parsed["active"] == 2
    assert parsed["fixed"] == 3
    assert parsed["wontfix"] == 1
    assert parsed["total"] == 6


def test_idempotent_sync(tmp_path: Path) -> None:
    """Running sync twice does not change the file on the second run."""
    _build_tech_debt_dir(
        tmp_path,
        active=1,
        fixed=2,
        wontfix=0,
        readme_active=0,
        readme_fixed=0,
        readme_wontfix=0,
        readme_total=0,
    )
    # First sync writes the correct counts.
    assert sync.main(["--root", str(tmp_path)]) == 0
    readme_path = tmp_path / "docs" / "archive" / "tech-debt-README.md"
    snapshot = readme_path.read_text(encoding="utf-8")

    # Second sync is a no-op (idempotent).
    assert sync.main(["--root", str(tmp_path)]) == 0
    assert readme_path.read_text(encoding="utf-8") == snapshot


def test_update_frontmatter_timestamp(tmp_path: Path) -> None:
    """update_frontmatter_timestamp rewrites ``last_updated`` to today."""
    import datetime as _dt

    _build_tech_debt_dir(tmp_path, active=1, fixed=1, wontfix=0)
    readme_path = tmp_path / "docs" / "archive" / "tech-debt-README.md"

    today = _dt.date.today().isoformat()
    changed = sync.update_frontmatter_timestamp(readme_path)
    assert changed is True
    text = readme_path.read_text(encoding="utf-8")
    assert f"last_updated: {today}" in text

    # Idempotent: second call is a no-op.
    changed_again = sync.update_frontmatter_timestamp(readme_path)
    assert changed_again is False


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    """--dry-run reports drift but leaves README.md untouched."""
    _build_tech_debt_dir(
        tmp_path,
        active=1,
        fixed=1,
        wontfix=1,
        readme_active=9,
        readme_fixed=9,
        readme_wontfix=9,
        readme_total=27,
    )
    readme_path = tmp_path / "docs" / "archive" / "tech-debt-README.md"
    before = readme_path.read_text(encoding="utf-8")

    rc = sync.main(["--dry-run", "--root", str(tmp_path)])
    assert rc == 0  # dry-run does not fail on drift
    assert readme_path.read_text(encoding="utf-8") == before
