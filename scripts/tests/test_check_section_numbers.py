"""Tests for hooks/check_section_numbers.py (章节序号一致性, 2026-08-29).

覆盖:
1. 重复章节号 → exit 1 (阻断)
2. 无重复/连续 → exit 0
3. 跳号 → warning 但 exit 0
4. 目标文档缺失 → 仅 warning
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

from hooks import check_section_numbers  # noqa: E402


def _write_doc(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_duplicate_section_numbers_block(tmp_path):
    """重复章节号 → main() 返回 1 (阻断)."""
    doc = "docs/standards/api-contract.md"
    _write_doc(tmp_path, doc, "## 1. 甲\n\n## 2. 乙\n\n## 2. 丙\n")
    # 只登记这一个文档, 避免依赖真实仓库其他登记文件
    import unittest.mock as mock

    with mock.patch.object(check_section_numbers, "DOCUMENTED_DOCS", [doc]):
        assert check_section_numbers.main(["--root", str(tmp_path)]) == 1


def test_sequential_sections_pass(tmp_path):
    """连续且无重复 → 返回 0."""
    doc = "docs/standards/api-contract.md"
    _write_doc(tmp_path, doc, "## 1. 甲\n\n## 2. 乙\n\n## 3. 丙\n")
    import unittest.mock as mock

    with mock.patch.object(check_section_numbers, "DOCUMENTED_DOCS", [doc]):
        assert check_section_numbers.main(["--root", str(tmp_path)]) == 0


def test_gap_warns_but_passes(tmp_path):
    """跳号 (缺 2) → warning 但不阻断 (返回 0)."""
    doc = "docs/standards/api-contract.md"
    _write_doc(tmp_path, doc, "## 1. 甲\n\n## 3. 丙\n")
    import unittest.mock as mock

    with mock.patch.object(check_section_numbers, "DOCUMENTED_DOCS", [doc]):
        assert check_section_numbers.main(["--root", str(tmp_path)]) == 0


def test_missing_registered_doc_warns(tmp_path):
    """登记文档缺失 → 仅 warning, 返回 0."""
    import unittest.mock as mock

    with mock.patch.object(
        check_section_numbers,
        "DOCUMENTED_DOCS",
        ["docs/standards/not-there.md"],
    ):
        assert check_section_numbers.main(["--root", str(tmp_path)]) == 0


def test_no_fail_mode_ignores_duplicates(tmp_path):
    """--no-fail 模式下重复章节号 → 返回 0."""
    doc = "docs/standards/api-contract.md"
    _write_doc(tmp_path, doc, "## 1. 甲\n\n## 1. 乙\n")
    import unittest.mock as mock

    with mock.patch.object(check_section_numbers, "DOCUMENTED_DOCS", [doc]):
        assert check_section_numbers.main(["--root", str(tmp_path), "--no-fail"]) == 0
