"""test_sync_ai_memory_cache.py — Unit tests for sync_ai_memory mtime cache (TD-332/TD-344).

spec-2026-07-26-governance-batch-perf-cache §3 Wave 3: 7 test cases.

1. test_cache_miss_first_run          — 首次运行无 cache → 全量扫描 → 写 cache
2. test_cache_hit_second_run          — 第二次运行 cache 命中 → 跳过全量扫描
3. test_cache_invalidate_on_modify    — 修改一个 .md → cache 失效 → 全量扫描 → 更新 cache
4. test_cache_invalidate_on_delete    — 删除一个 .md → cache 失效
5. test_cache_corrupt_fallback        — cache JSON 损坏 → 视为 cache miss
6. test_dry_run_no_cache_write        — --dry-run 不写 cache
7. test_no_counters_sync_skip_cache   — --no-counters-sync 跳过缓存检查

Run with: `conda run -n gaf python -m pytest scripts/tests/test_sync_ai_memory_cache.py -v`
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

# Make the parent scripts/ directory importable so we can load the modules
# under test without installing them as a package.
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

import sync_ai_memory  # noqa: E402


SAMPLE_LESSON = """\
---
date: '2026-07-26'
maintainer: manual
symptom: [test_cache]
solution: unit test fixture
related_files: []
created_by: AI
priority: low
---

# Test lesson for cache validation
"""

SAMPLE_LESSON_2 = """\
---
date: '2026-07-26'
maintainer: manual
symptom: [test_cache_2]
solution: second fixture
related_files: []
created_by: AI
priority: low
---

# Second test lesson
"""


def _make_temp_repo(files: dict | None = None) -> Path:
    """Create a temporary GAF-like repo with .ai-memory/ structure.

    `files` is a mapping of relative paths -> file content. All paths
    are placed under .ai-memory/ by default unless they already start
    with .ai-memory/ or .skills/.
    """
    tmp = Path(tempfile.mkdtemp(prefix="gaf_test_cache_"))
    ai_memory = tmp / ".ai-memory"
    ai_memory.mkdir(parents=True, exist_ok=True)
    # Always create lessons/README.md (counter-sync dep)
    (ai_memory / "lessons").mkdir(exist_ok=True)
    (ai_memory / "lessons" / "README.md").write_text(
        "---\nlessons_count: 0\n---\n# Lessons\n", encoding="utf-8"
    )
    # Always create meta/ (for yn-matrices.md / archived-lessons.md deps)
    (ai_memory / "meta").mkdir(exist_ok=True)
    (ai_memory / "meta" / "yn-matrices.md").write_text("# Y/N matrices\n", encoding="utf-8")
    (ai_memory / "meta" / "archived-lessons.md").write_text(
        "# Archived\n", encoding="utf-8"
    )
    # project_rules.md dep — create .skills/rules/
    (tmp / ".skills" / "rules").mkdir(parents=True, exist_ok=True)
    (tmp / ".skills" / "rules" / "project_rules.md").write_text(
        "# Project rules\n", encoding="utf-8"
    )
    # Add caller-specified files
    for rel, content in (files or {}).items():
        if rel.startswith(".ai-memory/") or rel.startswith(".skills/"):
            p = tmp / rel
        else:
            p = tmp / ".ai-memory" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp


class CacheMissFirstRunTests(unittest.TestCase):
    def test_cache_miss_first_run(self):
        """首次运行无 cache → _check_cache_valid 返回 False."""
        tmp = _make_temp_repo({"lessons/test.md": SAMPLE_LESSON})
        try:
            # No cache file exists → should be cache miss
            self.assertFalse(sync_ai_memory._check_cache_valid(tmp))
            # No cache file written yet
            self.assertFalse(sync_ai_memory._cache_path(tmp).exists())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class CacheHitSecondRunTests(unittest.TestCase):
    def test_cache_hit_second_run(self):
        """第二次运行 cache 命中 → _check_cache_valid 返回 True."""
        tmp = _make_temp_repo({"lessons/test.md": SAMPLE_LESSON})
        try:
            # First run: build manifest and write cache
            manifest = sync_ai_memory._build_mtime_manifest(tmp)
            sync_ai_memory._write_cache(tmp, manifest)
            self.assertTrue(sync_ai_memory._cache_path(tmp).exists())
            # Second run: no files changed → cache hit
            self.assertTrue(sync_ai_memory._check_cache_valid(tmp))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class CacheInvalidateOnModifyTests(unittest.TestCase):
    def test_cache_invalidate_on_modify(self):
        """修改一个 .md → cache 失效."""
        tmp = _make_temp_repo({"lessons/test.md": SAMPLE_LESSON})
        try:
            manifest = sync_ai_memory._build_mtime_manifest(tmp)
            sync_ai_memory._write_cache(tmp, manifest)
            self.assertTrue(sync_ai_memory._check_cache_valid(tmp))
            # Modify a file (write new content, mtime will change)
            test_file = tmp / ".ai-memory" / "lessons" / "test.md"
            test_file.write_text(SAMPLE_LESSON + "\n# modified\n", encoding="utf-8")
            # Cache should now be invalid
            self.assertFalse(sync_ai_memory._check_cache_valid(tmp))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class CacheInvalidateOnDeleteTests(unittest.TestCase):
    def test_cache_invalidate_on_delete(self):
        """删除一个 .md → cache 失效 (manifest 集合不同)."""
        tmp = _make_temp_repo({
            "lessons/test1.md": SAMPLE_LESSON,
            "lessons/test2.md": SAMPLE_LESSON_2,
        })
        try:
            manifest = sync_ai_memory._build_mtime_manifest(tmp)
            sync_ai_memory._write_cache(tmp, manifest)
            self.assertTrue(sync_ai_memory._check_cache_valid(tmp))
            # Delete a file
            (tmp / ".ai-memory" / "lessons" / "test2.md").unlink()
            # Cache should now be invalid (manifest has fewer entries)
            self.assertFalse(sync_ai_memory._check_cache_valid(tmp))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class CacheCorruptFallbackTests(unittest.TestCase):
    def test_cache_corrupt_fallback(self):
        """cache JSON 损坏 → 视为 cache miss (返回 False)."""
        tmp = _make_temp_repo({"lessons/test.md": SAMPLE_LESSON})
        try:
            # Write corrupt cache JSON
            cache_path = sync_ai_memory._cache_path(tmp)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text("{invalid json content", encoding="utf-8")
            # Should fall back to cache miss
            self.assertFalse(sync_ai_memory._check_cache_valid(tmp))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cache_not_dict_fallback(self):
        """cache JSON 是合法 JSON 但不是 dict → 视为 cache miss."""
        tmp = _make_temp_repo({"lessons/test.md": SAMPLE_LESSON})
        try:
            cache_path = sync_ai_memory._cache_path(tmp)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            # Valid JSON but a list, not a dict
            cache_path.write_text('["not", "a", "dict"]', encoding="utf-8")
            self.assertFalse(sync_ai_memory._check_cache_valid(tmp))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DryRunNoCacheWriteTests(unittest.TestCase):
    def test_dry_run_no_cache_write(self):
        """--dry-run 不写 cache (main() use_cache flag 检查).

        This is a behavioral test of main() — we verify that --dry-run
        does not create the cache file.
        """
        tmp = _make_temp_repo({"lessons/test.md": SAMPLE_LESSON})
        try:
            # Run main() with --dry-run
            rc = sync_ai_memory.main(["--root", str(tmp), "--dry-run"])
            self.assertEqual(rc, 0)
            # Cache file should NOT exist after --dry-run
            self.assertFalse(sync_ai_memory._cache_path(tmp).exists())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class NoCountersSyncSkipCacheTests(unittest.TestCase):
    def test_no_counters_sync_skip_cache(self):
        """--no-counters-sync 跳过缓存检查 (仍走全量扫描).

        main() use_cache flag should be False when --no-counters-sync is set,
        so cache is neither checked nor written.
        """
        tmp = _make_temp_repo({"lessons/test.md": SAMPLE_LESSON})
        try:
            # Run main() with --no-counters-sync
            rc = sync_ai_memory.main(["--root", str(tmp), "--no-counters-sync"])
            self.assertEqual(rc, 0)
            # Cache file should NOT exist (use_cache was False, so no write)
            self.assertFalse(sync_ai_memory._cache_path(tmp).exists())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_index_flag_skip_cache(self):
        """--index 标志跳过缓存 (用户想要 per-file 详情)."""
        tmp = _make_temp_repo({"lessons/test.md": SAMPLE_LESSON})
        try:
            rc = sync_ai_memory.main(["--root", str(tmp), "--index"])
            self.assertEqual(rc, 0)
            # Cache should NOT be written because --index skips use_cache
            self.assertFalse(sync_ai_memory._cache_path(tmp).exists())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class EndToEndCacheHitTests(unittest.TestCase):
    def test_end_to_end_cache_hit(self):
        """端到端: 第一次 main() 写 cache, 第二次 main() cache hit."""
        tmp = _make_temp_repo({"lessons/test.md": SAMPLE_LESSON})
        try:
            # First run: full sync, should write cache
            rc1 = sync_ai_memory.main(["--root", str(tmp)])
            self.assertEqual(rc1, 0)
            self.assertTrue(sync_ai_memory._cache_path(tmp).exists())

            # Second run: cache hit, should return 0 quickly
            rc2 = sync_ai_memory.main(["--root", str(tmp)])
            self.assertEqual(rc2, 0)
            # Verify cache file still exists (not deleted)
            self.assertTrue(sync_ai_memory._cache_path(tmp).exists())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class ManifestIncludesExternalDepsTests(unittest.TestCase):
    def test_manifest_includes_project_rules(self):
        """_build_mtime_manifest 包含 .skills/rules/project_rules.md."""
        tmp = _make_temp_repo({"lessons/test.md": SAMPLE_LESSON})
        try:
            manifest = sync_ai_memory._build_mtime_manifest(tmp)
            # Should include .ai-memory/lessons/test.md
            self.assertIn(".ai-memory/lessons/test.md", manifest)
            # Should include .skills/rules/project_rules.md (counter-sync dep)
            self.assertIn(".skills/rules/project_rules.md", manifest)
            # Should include counter-sync dep files
            self.assertIn(".ai-memory/lessons/README.md", manifest)
            self.assertIn(".ai-memory/meta/yn-matrices.md", manifest)
            self.assertIn(".ai-memory/meta/archived-lessons.md", manifest)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


# ===========================================================================
# Wave 4: sync_docs_index cache tests
# ===========================================================================

import sync_docs_index  # noqa: E402


def _make_temp_docs_repo(docs_files: dict | None = None) -> Path:
    """Create a temporary repo with docs/ structure for sync_docs_index tests."""
    tmp = Path(tempfile.mkdtemp(prefix="gaf_test_docs_cache_"))
    docs_dir = tmp / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    # Always create .ai-memory/ for cache file storage
    (tmp / ".ai-memory" / "meta").mkdir(parents=True, exist_ok=True)
    # Add caller-specified docs files
    for rel, content in (docs_files or {}).items():
        p = docs_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp


SAMPLE_DOC = """\
---
summary: Test doc for cache validation
applies_to: [test]
last_updated: 2026-07-26
---

# Test doc
"""

SAMPLE_DOC_2 = """\
---
summary: Second test doc
applies_to: [test]
last_updated: 2026-07-26
---

# Second doc
"""


class DocsCacheMissFirstRunTests(unittest.TestCase):
    def test_docs_cache_miss_first_run(self):
        """sync_docs_index 首次运行无 cache → 全量扫描 → 写 cache."""
        tmp = _make_temp_docs_repo({"test.md": SAMPLE_DOC})
        try:
            # No cache file exists
            self.assertFalse(sync_docs_index._docs_cache_path(tmp).exists())
            # First run: full scan, should write cache
            rc = sync_docs_index.main(["--root", str(tmp), "--check"])
            self.assertEqual(rc, 0)
            # Cache should now exist
            self.assertTrue(sync_docs_index._docs_cache_path(tmp).exists())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DocsCacheHitSecondRunTests(unittest.TestCase):
    def test_docs_cache_hit_second_run(self):
        """sync_docs_index 第二次运行 cache 命中 → 跳过全量扫描."""
        tmp = _make_temp_docs_repo({"test.md": SAMPLE_DOC})
        try:
            # First run: full scan, write cache
            sync_docs_index.main(["--root", str(tmp), "--check"])
            # Second run: should hit cache (same date, no file changes)
            rc = sync_docs_index.main(["--root", str(tmp), "--check"])
            self.assertEqual(rc, 0)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DocsCacheInvalidateOnModifyTests(unittest.TestCase):
    def test_docs_cache_invalidate_on_modify(self):
        """修改 docs/*.md → cache 失效 → 全量扫描 → 更新 cache."""
        tmp = _make_temp_docs_repo({"test.md": SAMPLE_DOC})
        try:
            sync_docs_index.main(["--root", str(tmp), "--check"])
            # Modify a doc file
            (tmp / "docs" / "test.md").write_text(
                SAMPLE_DOC + "\n# modified\n", encoding="utf-8"
            )
            # Cache should be invalid (manifest changed)
            today_str = _dt.date.today().isoformat()
            hit, _, _ = sync_docs_index._check_docs_cache_valid(
                tmp, tmp / "docs", today_str
            )
            self.assertFalse(hit)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DocsCacheInvalidateOnDateChangeTests(unittest.TestCase):
    def test_docs_cache_invalidate_on_date_change(self):
        """日期变化 → cache 失效 (stale 检查依赖 today)."""
        tmp = _make_temp_docs_repo({"test.md": SAMPLE_DOC})
        try:
            sync_docs_index.main(["--root", str(tmp), "--check"])
            # Simulate next-day run by checking with a different date
            tomorrow = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
            hit, _, _ = sync_docs_index._check_docs_cache_valid(
                tmp, tmp / "docs", tomorrow
            )
            self.assertFalse(hit)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DocsCacheCorruptFallbackTests(unittest.TestCase):
    def test_docs_cache_corrupt_fallback(self):
        """sync_docs_index cache JSON 损坏 → 视为 cache miss."""
        tmp = _make_temp_docs_repo({"test.md": SAMPLE_DOC})
        try:
            # Write corrupt cache
            cache_path = sync_docs_index._docs_cache_path(tmp)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text("{invalid json", encoding="utf-8")
            # Should fall back to cache miss, run full scan
            rc = sync_docs_index.main(["--root", str(tmp), "--check"])
            self.assertEqual(rc, 0)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DocsCacheStrictModeSkippedTests(unittest.TestCase):
    def test_docs_cache_strict_mode_skipped(self):
        """--strict 模式跳过缓存 (always full scan for strict checks)."""
        tmp = _make_temp_docs_repo({"test.md": SAMPLE_DOC})
        try:
            # First run with --strict (no cache write for strict mode)
            rc1 = sync_docs_index.main(["--root", str(tmp), "--check", "--strict"])
            self.assertEqual(rc1, 0)
            # Cache should NOT exist (strict mode doesn't write cache)
            self.assertFalse(sync_docs_index._docs_cache_path(tmp).exists())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DocsCacheDeleteFileInvalidatesTests(unittest.TestCase):
    def test_docs_cache_delete_file_invalidates(self):
        """删除一个 docs/*.md → cache 失效 (manifest 集合不同)."""
        tmp = _make_temp_docs_repo({
            "test1.md": SAMPLE_DOC,
            "test2.md": SAMPLE_DOC_2,
        })
        try:
            sync_docs_index.main(["--root", str(tmp), "--check"])
            # Delete a file
            (tmp / "docs" / "test2.md").unlink()
            # Cache should be invalid
            today_str = _dt.date.today().isoformat()
            hit, _, _ = sync_docs_index._check_docs_cache_valid(
                tmp, tmp / "docs", today_str
            )
            self.assertFalse(hit)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DocsCacheExcludesPerformanceBaselineTests(unittest.TestCase):
    """TD-347: docs/reference/performance-baseline.md (auto-generated) 不进入 manifest.

    governance-batch 每次 commit 都会 append 一行到该文件. 若该文件进入 manifest,
    cache 永久失效 (mtime 每次变化). 修复方案 A: _build_docs_manifest 排除该文件.
    """

    def test_performance_baseline_excluded_from_manifest(self):
        """_build_docs_manifest 不包含 reference/performance-baseline.md."""
        tmp = _make_temp_docs_repo({
            "test.md": SAMPLE_DOC,
            "reference/performance-baseline.md": "# auto-generated\n| col | col |\n|---|---|\n| row | row |\n",
        })
        try:
            manifest = sync_docs_index._build_docs_manifest(tmp / "docs")
            # test.md 应在 manifest 中
            self.assertIn("test.md", manifest)
            # performance-baseline.md 应被排除
            self.assertNotIn("reference/performance-baseline.md", manifest)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_performance_baseline_modify_does_not_invalidate_cache(self):
        """修改 performance-baseline.md 不应让 cache 失效 (TD-347 核心验证)."""
        tmp = _make_temp_docs_repo({
            "test.md": SAMPLE_DOC,
            "reference/performance-baseline.md": "# auto-generated\n| col |\n|---|\n| row |\n",
        })
        try:
            # First run: build cache
            sync_docs_index.main(["--root", str(tmp), "--check"])
            today_str = _dt.date.today().isoformat()
            hit_before, _, _ = sync_docs_index._check_docs_cache_valid(
                tmp, tmp / "docs", today_str
            )
            self.assertTrue(hit_before, "cache should hit before modify")

            # Modify performance-baseline.md (simulate governance-batch auto-append)
            baseline = tmp / "docs" / "reference" / "performance-baseline.md"
            baseline.write_text(
                "# auto-generated\n| col |\n|---|\n| row1 |\n| row2 |\n",
                encoding="utf-8",
            )

            # Cache should STILL hit (performance-baseline.md excluded from manifest)
            hit_after, _, _ = sync_docs_index._check_docs_cache_valid(
                tmp, tmp / "docs", today_str
            )
            self.assertTrue(
                hit_after,
                "TD-347: cache must still hit after modifying performance-baseline.md",
            )
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
