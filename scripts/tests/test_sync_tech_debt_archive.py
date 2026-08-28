"""test_sync_tech_debt_archive.py — Tests for sync_tech_debt_archive.py (spec-2026-07-26-meta-governance-fix T2).

Covers:
1. test_parse_fixed_md       — parse fixed.md into header + paragraphs
2. test_extract_year         — extract year from TD paragraph
3. test_archive_keep_n       --archive --keep N mode (dry-run + real)
4. test_check_mode           --check returns correct stats
5. test_build_index_table    index table generation

Run with:
    conda run -n gaf python -m pytest scripts/tests/test_sync_tech_debt_archive.py -v
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

# Import module under test
from bootstrap import sync_tech_debt_archive  # type: ignore


SAMPLE_FIXED_MD = """---
summary: 已修复技术债务清单
last_updated: 2026-07-26
---

# Fixed Tech Debts

> 本文件包含所有 ✅ FIXED 状态的技术债务条目。

---

## TD-341: 测试段落 1 (✅ FIXED — commit `abc`)

- **状态**: ✅ FIXED
- **修复时间**: 2026-07-26
- **优先级**: P2

一些内容。

## TD-340: 测试段落 2 (✅ FIXED — commit `def`)

- **状态**: ✅ FIXED
- **修复时间**: 2026-07-25
- **优先级**: P1

另一些内容。

## TD-100: 测试段落 3 (✅ FIXED — commit `ghi`)

- **状态**: ✅ FIXED
- **修复时间**: 2026-06-15
- **优先级**: P3

更早的内容。

## TD-002: 最旧段落 (✅ FIXED — commit `jkl`)

- **状态**: ✅ FIXED
- **修复时间**: 2026-06-01
- **优先级**: P0

最旧的内容。
"""


class TestSyncTechDebtArchive(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.fixed_md = self.tmp_path / "fixed.md"
        self.fixed_md.write_text(SAMPLE_FIXED_MD, encoding="utf-8")
        # Patch FIXED_MD + ARCHIVE_DIR to point to tmp
        self._orig_fixed_md = sync_tech_debt_archive.FIXED_MD
        self._orig_archive_dir = sync_tech_debt_archive.ARCHIVE_DIR
        sync_tech_debt_archive.FIXED_MD = self.fixed_md
        sync_tech_debt_archive.ARCHIVE_DIR = self.tmp_path

    def tearDown(self) -> None:
        sync_tech_debt_archive.FIXED_MD = self._orig_fixed_md
        sync_tech_debt_archive.ARCHIVE_DIR = self._orig_archive_dir
        self.tmp.cleanup()

    def test_parse_fixed_md(self) -> None:
        """parse_fixed_md 正确切分 header + paragraphs."""
        content = self.fixed_md.read_text(encoding="utf-8")
        header, paragraphs = sync_tech_debt_archive.parse_fixed_md(content)
        self.assertIn("# Fixed Tech Debts", header)
        self.assertEqual(len(paragraphs), 4)
        self.assertEqual(paragraphs[0][2], "TD-341")  # 第一个段落
        self.assertEqual(paragraphs[-1][2], "TD-002")  # 最后一个段落

    def test_extract_year(self) -> None:
        """extract_year 从段落提取年份."""
        para_2026 = "## TD-341: test\n- **修复时间**: 2026-07-26\n"
        para_2025 = "## TD-100: test\n- **修复时间**: 2025-12-31\n"
        para_no_year = "## TD-200: test\n- no time field\n"
        para_fallback = "## TD-300: test\n- **登记时间**: 2024-01-01\n"

        self.assertEqual(sync_tech_debt_archive.extract_year(para_2026), 2026)
        self.assertEqual(sync_tech_debt_archive.extract_year(para_2025), 2025)
        self.assertIsNone(sync_tech_debt_archive.extract_year(para_no_year))
        self.assertEqual(sync_tech_debt_archive.extract_year(para_fallback), 2024)

    def test_check_mode(self) -> None:
        """--check 返回正确统计."""
        result = sync_tech_debt_archive.check(self.fixed_md)
        self.assertEqual(result["paragraphs"], 4)
        self.assertEqual(result["by_year"], {2026: 4})
        # 样本小 (4 段落, < 1KB), 不需归档
        self.assertFalse(result["needs_archive"])

    def test_archive_keep_n_dry_run(self) -> None:
        """--archive --keep 2 --dry-run 预演: 保留前 2, 归档后 2."""
        result = sync_tech_debt_archive.archive_keep_n(self.fixed_md, keep_n=2, dry_run=True)
        self.assertEqual(result["action"], "archive")
        self.assertEqual(result["total_paragraphs"], 4)
        self.assertEqual(result["archived"], 2)
        self.assertEqual(result["kept"], 2)
        # 不应修改原文件
        self.assertEqual(self.fixed_md.read_text(encoding="utf-8"), SAMPLE_FIXED_MD)

    def test_archive_keep_n_real(self) -> None:
        """--archive --keep 2 实际执行: 保留前 2 (TD-341, TD-340), 归档后 2 (TD-100, TD-002)."""
        result = sync_tech_debt_archive.archive_keep_n(self.fixed_md, keep_n=2, dry_run=False)
        self.assertEqual(result["action"], "archive")
        self.assertEqual(result["archived"], 2)
        self.assertEqual(result["kept"], 2)

        # fixed.md 应只保留前 2 段落 + 索引表
        new_content = self.fixed_md.read_text(encoding="utf-8")
        self.assertIn("TD-341", new_content)
        self.assertIn("TD-340", new_content)
        self.assertNotIn("TD-100", new_content)
        self.assertNotIn("TD-002", new_content)
        self.assertIn("<!-- fixed.md 索引表", new_content)

        # archive 文件应含归档的 2 段落
        archive_file = self.tmp_path / "fixed-archive-2026.md"
        self.assertTrue(archive_file.exists())
        archive_content = archive_file.read_text(encoding="utf-8")
        self.assertIn("TD-100", archive_content)
        self.assertIn("TD-002", archive_content)
        self.assertIn("2026", archive_content)  # 标题含年份

    def test_build_index_table(self) -> None:
        """build_index_table 生成索引表."""
        paragraphs = [
            (0, 100, "TD-341", "## TD-341: 测试摘要 (✅ FIXED)\n内容"),
            (100, 200, "TD-340", "## TD-340: 另一个测试\n内容"),
        ]
        table = sync_tech_debt_archive.build_index_table(paragraphs)
        self.assertIn("TD-341", table)
        self.assertIn("TD-340", table)
        self.assertIn("测试摘要", table)
        self.assertIn("<!-- fixed.md 索引表", table)

    def test_archive_noop_when_below_keep_n(self) -> None:
        """--archive --keep 10 (大于段落数) 应 noop."""
        result = sync_tech_debt_archive.archive_keep_n(self.fixed_md, keep_n=10, dry_run=True)
        self.assertEqual(result["action"], "noop")
        self.assertEqual(result["total_paragraphs"], 4)


if __name__ == "__main__":
    unittest.main()
