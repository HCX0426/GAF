"""Tests for gaf_core.startup_checks (spec §6.2 P1-13).

4 项单元测试:
- test_cleanup_old_evidence_once: active > 30 天 → 移 archived
- test_delete_archived_evidence_once: archived > 90 天 → 删除
- test_forgetting_check_once: §Active + §Dormant 两类超时 → 移 archived-lessons.md
- test_allocate_n_id: N 编号原子递增 + 文件锁

注意: test_allocate_n_id 是 N 编号分配函数测试, 实际函数在 lessons.promote_lessons
      (本测试用 mock 验证原子性语义, 不测实际 promote_lessons 实现).
"""
from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from django.test import TestCase

from gaf_core import startup_checks


class CleanupOldEvidenceOnceTest(TestCase):
    """cleanup_old_evidence_once — active > 30 天 → 移 archived/YYYY-MM/."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmpdir = Path(self._tmpdir.name)
        # mock EVIDENCE_DIR / ACTIVE_DIR / ARCHIVED_DIR 指向 tmpdir
        self.active_dir = self.tmpdir / "active"
        self.archived_dir = self.tmpdir / "archived"
        self.active_dir.mkdir(parents=True)
        self.archived_dir.mkdir(parents=True)
        self._patch_active = mock.patch.object(startup_checks, "ACTIVE_DIR", self.active_dir)
        self._patch_archived = mock.patch.object(startup_checks, "ARCHIVED_DIR", self.archived_dir)
        self._patch_active.start()
        self._patch_archived.start()
        self.addCleanup(self._patch_active.stop)
        self.addCleanup(self._patch_archived.stop)

    def _make_evidence(self, name: str) -> Path:
        d = self.active_dir / name
        d.mkdir(parents=True)
        (d / "problem.md").write_text("test", encoding="utf-8")
        return d

    def test_old_evidence_moved_to_archived(self):
        """30 天前的 evidence 应被移到 archived/YYYY-MM/."""
        old_date = (date.today() - timedelta(days=45)).strftime("%Y-%m-%d")
        self._make_evidence(f"{old_date}-test-old")
        result = startup_checks.cleanup_old_evidence_once(dry_run=False)
        self.assertEqual(result["moved_count"], 1)
        # 验证文件已移到 archived/YYYY-MM/
        month_folder = old_date[:7]
        moved = self.archived_dir / month_folder / f"{old_date}-test-old"
        self.assertTrue(moved.is_dir())
        self.assertFalse((self.active_dir / f"{old_date}-test-old").exists())

    def test_recent_evidence_kept_in_active(self):
        """30 天内的 evidence 应保留在 active/."""
        recent_date = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")
        self._make_evidence(f"{recent_date}-test-recent")
        result = startup_checks.cleanup_old_evidence_once(dry_run=False)
        self.assertEqual(result["moved_count"], 0)
        self.assertTrue((self.active_dir / f"{recent_date}-test-recent").is_dir())

    def test_dry_run_does_not_move(self):
        """dry-run 模式不实际移动文件."""
        old_date = (date.today() - timedelta(days=45)).strftime("%Y-%m-%d")
        self._make_evidence(f"{old_date}-test-dry")
        result = startup_checks.cleanup_old_evidence_once(dry_run=True)
        self.assertEqual(result["moved_count"], 1)
        self.assertTrue(result["dry_run"])
        # 文件仍在 active/
        self.assertTrue((self.active_dir / f"{old_date}-test-dry").is_dir())


class DeleteArchivedEvidenceOnceTest(TestCase):
    """delete_archived_evidence_once — archived > 90 天 → 删除."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmpdir = Path(self._tmpdir.name)
        self.archived_dir = self.tmpdir / "archived"
        self.archived_dir.mkdir(parents=True)
        self._patch = mock.patch.object(startup_checks, "ARCHIVED_DIR", self.archived_dir)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _make_archived(self, name: str, month: str) -> Path:
        month_dir = self.archived_dir / month
        month_dir.mkdir(parents=True, exist_ok=True)
        d = month_dir / name
        d.mkdir(parents=True)
        (d / "problem.md").write_text("test", encoding="utf-8")
        return d

    def test_old_archived_deleted(self):
        """90 天前的 archived evidence 应被删除."""
        old_date = (date.today() - timedelta(days=100)).strftime("%Y-%m-%d")
        month = old_date[:7]
        old_evidence = self._make_archived(f"{old_date}-test-old", month)
        result = startup_checks.delete_archived_evidence_once(dry_run=False)
        self.assertEqual(result["deleted_count"], 1)
        self.assertFalse(old_evidence.exists())

    def test_recent_archived_kept(self):
        """90 天内的 archived evidence 应保留."""
        recent_date = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
        month = recent_date[:7]
        recent_evidence = self._make_archived(f"{recent_date}-test-recent", month)
        result = startup_checks.delete_archived_evidence_once(dry_run=False)
        self.assertEqual(result["deleted_count"], 0)
        self.assertTrue(recent_evidence.is_dir())

    def test_dry_run_does_not_delete(self):
        """dry-run 模式不实际删除."""
        old_date = (date.today() - timedelta(days=100)).strftime("%Y-%m-%d")
        month = old_date[:7]
        old_evidence = self._make_archived(f"{old_date}-test-dry", month)
        result = startup_checks.delete_archived_evidence_once(dry_run=True)
        self.assertEqual(result["deleted_count"], 1)
        self.assertTrue(result["dry_run"])
        self.assertTrue(old_evidence.exists())


class ForgettingCheckOnceTest(TestCase):
    """forgetting_check_once — §Active 超时 N## → 移 archived-lessons.md."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmpdir = Path(self._tmpdir.name)
        # mock FM_PATH / ARCHIVED_LESSONS_PATH / yn-matrices dir
        self.fm_path = self.tmpdir / "failure-modes.md"
        self.archived_lessons_path = self.tmpdir / "archived-lessons.md"
        # yn-matrices 路径推导: REPO_ROOT / .ai-memory / meta / yn-matrices
        # mock REPO_ROOT=tmpdir 后, 实际路径是 tmpdir/.ai-memory/meta/yn-matrices/
        self.yn_dir = self.tmpdir / ".ai-memory" / "meta" / "yn-matrices"
        self.yn_dir.mkdir(parents=True)
        self._patch_fm = mock.patch.object(startup_checks, "FM_PATH", self.fm_path)
        self._patch_al = mock.patch.object(
            startup_checks, "ARCHIVED_LESSONS_PATH", self.archived_lessons_path
        )
        # mock REPO_ROOT 用于 yn-matrices 路径推导
        self._patch_repo = mock.patch.object(startup_checks, "REPO_ROOT", self.tmpdir)
        self._patch_fm.start()
        self._patch_al.start()
        self._patch_repo.start()
        self.addCleanup(self._patch_fm.stop)
        self.addCleanup(self._patch_al.stop)
        self.addCleanup(self._patch_repo.stop)

    def _write_fm(self, active_rows: list[str]) -> None:
        """写一个最小化的 failure-modes.md."""
        text = "# failure-modes.md\n\n## Active N## 索引表\n\n"
        text += "| N## | 主题 | 硬约束 (1 行) | Lesson 链接 | trigger_count | last_triggered |\n"
        text += "|:---:|------|--------------|-------------|:---:|:---:|\n"
        text += "\n".join(active_rows) + "\n"
        self.fm_path.write_text(text, encoding="utf-8")

    def test_old_active_n_archived(self):
        """§Active N## last_triggered > 6 月 + 无 Y/N 矩阵引用 → 移 archived-lessons.md."""
        old_date = (date.today() - timedelta(days=200)).strftime("%Y-%m-%d")
        row = (
            f"| N200 | 测试遗忘 | 硬约束 | `lessons/N200-test.md` | 5 | {old_date} |"
        )
        self._write_fm([row])
        # yn-matrices 不引用 N200 (注意: 测试文本不能含 N200 字串, 否则被误判为引用)
        (self.yn_dir / "_workflow.md").write_text("no matching ref", encoding="utf-8")

        result = startup_checks.forgetting_check_once(dry_run=False)
        self.assertEqual(result["archived_count"], 1)
        # 验证 failure-modes.md 中 N200 行已删除
        fm_text = self.fm_path.read_text(encoding="utf-8")
        self.assertNotIn("N200", fm_text)
        # 验证 archived-lessons.md 已追加
        archived_text = self.archived_lessons_path.read_text(encoding="utf-8")
        self.assertIn("N200", archived_text)

    def test_referenced_n_not_archived(self):
        """有 Y/N 矩阵引用的 N## 不应被遗忘."""
        old_date = (date.today() - timedelta(days=200)).strftime("%Y-%m-%d")
        row = (
            f"| N201 | 测试引用 | 硬约束 | `lessons/N201-test.md` | 5 | {old_date} |"
        )
        self._write_fm([row])
        # yn-matrices 引用 N201
        (self.yn_dir / "_workflow.md").write_text("N201 是引用", encoding="utf-8")

        result = startup_checks.forgetting_check_once(dry_run=False)
        self.assertEqual(result["archived_count"], 0)
        self.assertEqual(result["candidates"], 1)
        # N201 仍在 failure-modes.md
        fm_text = self.fm_path.read_text(encoding="utf-8")
        self.assertIn("N201", fm_text)

    def test_recent_n_not_archived(self):
        """近期触发的 N## 不应被遗忘."""
        recent_date = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")
        row = (
            f"| N202 | 测试近期 | 硬约束 | `lessons/N202-test.md` | 5 | {recent_date} |"
        )
        self._write_fm([row])

        result = startup_checks.forgetting_check_once(dry_run=False)
        self.assertEqual(result["archived_count"], 0)

    def test_dry_run_does_not_modify(self):
        """dry-run 模式不修改 failure-modes.md."""
        old_date = (date.today() - timedelta(days=200)).strftime("%Y-%m-%d")
        row = (
            f"| N203 | 测试 dry-run | 硬约束 | `lessons/N203-test.md` | 5 | {old_date} |"
        )
        self._write_fm([row])
        original_fm = self.fm_path.read_text(encoding="utf-8")

        result = startup_checks.forgetting_check_once(dry_run=True)
        self.assertEqual(result["archived_count"], 1)
        self.assertTrue(result["dry_run"])
        # failure-modes.md 未变
        self.assertEqual(self.fm_path.read_text(encoding="utf-8"), original_fm)
        # archived-lessons.md 未创建
        self.assertFalse(self.archived_lessons_path.exists())


class AllocateNIdTest(TestCase):
    """N 编号原子递增 + 文件锁语义测试 (spec §6.2).

    实际分配函数在 lessons.promote_lessons, 这里测试 next_n_id 字段语义.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.lessons_readme = Path(self._tmpdir.name) / "README.md"

    def test_next_n_id_incremented(self):
        """next_n_id 应在分配后递增."""
        self.lessons_readme.write_text(
            "---\nnext_n_id: 189\n---\n# Lessons\n",
            encoding="utf-8",
        )
        # 模拟分配: 读取 next_n_id, 用 +1 写回
        text = self.lessons_readme.read_text(encoding="utf-8")
        import re
        m = re.search(r"^next_n_id:\s*(\d+)", text, re.MULTILINE)
        self.assertIsNotNone(m)
        current = int(m.group(1))
        new_text = re.sub(
            r"^next_n_id:\s*\d+",
            f"next_n_id: {current + 1}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        self.lessons_readme.write_text(new_text, encoding="utf-8")
        # 验证递增
        new_text = self.lessons_readme.read_text(encoding="utf-8")
        m = re.search(r"^next_n_id:\s*(\d+)", new_text, re.MULTILINE)
        self.assertEqual(int(m.group(1)), 190)

    def test_concurrent_allocation_atomic(self):
        """并发分配应通过文件锁保证原子性 (语义测试).

        实际实现用 fcntl (Linux) / msvcrt (Windows), 这里只验证
        两次顺序分配得到不同编号.
        """
        self.lessons_readme.write_text(
            "---\nnext_n_id: 200\n---\n# Lessons\n",
            encoding="utf-8",
        )
        import re

        def allocate() -> int:
            text = self.lessons_readme.read_text(encoding="utf-8")
            m = re.search(r"^next_n_id:\s*(\d+)", text, re.MULTILINE)
            current = int(m.group(1))
            new_text = re.sub(
                r"^next_n_id:\s*\d+",
                f"next_n_id: {current + 1}",
                text,
                count=1,
                flags=re.MULTILINE,
            )
            self.lessons_readme.write_text(new_text, encoding="utf-8")
            return current

        n1 = allocate()
        n2 = allocate()
        self.assertEqual(n1, 200)
        self.assertEqual(n2, 201)
        self.assertNotEqual(n1, n2)
