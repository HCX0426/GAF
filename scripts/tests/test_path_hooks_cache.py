"""test_path_hooks_cache.py — Unit tests for check_doc_path_drift + check_path_consistency mtime cache (TD-348).

spec-2026-07-26-governance-batch-perf-cache 后续 TD-348: 复用 sync_ai_memory.py 的
mtime-based manifest cache 模式, 优化两个全仓扫描 hook 的性能.

Test coverage:
1. check_doc_path_drift cache:
   - test_doc_path_drift_cache_miss_first_run        — 首次运行无 cache → 全量扫描 → 写 cache
   - test_doc_path_drift_cache_hit_second_run        — 第二次运行 cache 命中 → 跳过全量扫描
   - test_doc_path_drift_cache_invalidate_on_modify  — 修改一个 .py → cache 失效
   - test_doc_path_drift_cache_corrupt_fallback      — cache JSON 损坏 → 视为 cache miss
   - test_doc_path_drift_cache_excludes_cache_files  — cache 文件自身不进入 manifest
2. check_path_consistency cache:
   - test_path_consistency_cache_miss_first_run      — 首次运行无 cache → 全量扫描 → 写 cache
   - test_path_consistency_cache_hit_second_run      — 第二次运行 cache 命中 → 跳过全量扫描
   - test_path_consistency_cache_invalidate_on_modify — 修改一个 .py → cache 失效
   - test_path_consistency_cache_corrupt_fallback    — cache JSON 损坏 → 视为 cache miss
   - test_path_consistency_gitignore_in_manifest     — .gitignore mtime 变化 → cache 失效

Note: both hook main() functions use argparse (read from sys.argv, not argv param),
so tests monkey-patch sys.argv via the _run_hook helper.

Run with: `conda run -n gaf python -m pytest scripts/tests/test_path_hooks_cache.py -v`
"""
from __future__ import annotations

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

# Add scripts/hooks to path so we can import the hook modules directly
HOOKS_DIR = SCRIPTS_DIR / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

import check_doc_path_drift  # noqa: E402
import check_path_consistency  # noqa: E402


def _run_doc_path_drift(repo_root: Path) -> int:
    """Run check_doc_path_drift.main() with --root pointing at repo_root."""
    old_argv = sys.argv
    sys.argv = ["check_doc_path_drift", "--root", str(repo_root)]
    try:
        return check_doc_path_drift.main()
    finally:
        sys.argv = old_argv


def _run_path_consistency(repo_root: Path) -> int:
    """Run check_path_consistency.main() with --root pointing at repo_root."""
    old_argv = sys.argv
    sys.argv = ["check_path_consistency", "--root", str(repo_root)]
    try:
        return check_path_consistency.main()
    finally:
        sys.argv = old_argv


def _make_temp_repo(files: dict | None = None) -> Path:
    """Create a temporary repo with .git/ + scripts/gaf_init.sh + .ai-memory/ structure.

    files: {relative_path: content} for files to create.
    """
    tmp = Path(tempfile.mkdtemp(prefix="gaf_test_path_hooks_cache_"))
    # .git/ marker (check_doc_path_drift requires .git/)
    (tmp / ".git").mkdir(parents=True, exist_ok=True)
    # scripts/gaf_init.sh marker (check_path_consistency requires it)
    (tmp / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp / "scripts" / "gaf_init.sh").write_text("#!/bin/bash\n# stub\n", encoding="utf-8")
    # .ai-memory/ for cache file storage
    (tmp / ".ai-memory").mkdir(parents=True, exist_ok=True)
    # .gitignore (check_path_consistency reads it)
    (tmp / ".gitignore").write_text("# stub gitignore\n", encoding="utf-8")
    # Add caller-specified files
    for rel, content in (files or {}).items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp


SAMPLE_PY = """\
# Sample python file
import os

def main():
    print("hello")
"""


SAMPLE_PY_WITH_FORBIDDEN_PATH = """\
# Sample python file with forbidden old path reference
import os

def main():
    path = "docs/general/old.md"
    print(path)
"""


SAMPLE_PY_WITH_ABS_PATH = """\
# Sample python file with absolute path literal
def main():
    config = "C:\\\\Users\\\\developer\\\\app_config.json"
    print(config)
"""


# ===========================================================================
# check_doc_path_drift cache tests (TD-348)
# ===========================================================================


class DocPathDriftCacheMissFirstRunTests(unittest.TestCase):
    def test_doc_path_drift_cache_miss_first_run(self):
        """check_doc_path_drift 首次运行无 cache → 全量扫描 → 写 cache."""
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            # No cache file exists
            self.assertFalse(check_doc_path_drift._cache_path(tmp).exists())
            # First run: full scan, should write cache
            rc = _run_doc_path_drift(tmp)
            self.assertEqual(rc, 0)
            # Cache should now exist
            self.assertTrue(check_doc_path_drift._cache_path(tmp).exists())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DocPathDriftCacheHitSecondRunTests(unittest.TestCase):
    def test_doc_path_drift_cache_hit_second_run(self):
        """check_doc_path_drift 第二次运行 cache 命中 → 跳过全量扫描."""
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            # First run: full scan, write cache
            _run_doc_path_drift(tmp)
            # Second run: should hit cache (no file changes)
            rc = _run_doc_path_drift(tmp)
            self.assertEqual(rc, 0)
            # Verify cache hit by checking _check_cache_valid directly
            hit, _, _, _ = check_doc_path_drift._check_cache_valid(tmp)
            self.assertTrue(hit)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DocPathDriftCacheInvalidateOnModifyTests(unittest.TestCase):
    def test_doc_path_drift_cache_invalidate_on_modify(self):
        """修改一个 .py → cache 失效 → 全量扫描 → 更新 cache."""
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            _run_doc_path_drift(tmp)
            # Modify a file
            (tmp / "backend" / "test.py").write_text("# modified\n", encoding="utf-8")
            # Cache should be invalid
            hit, _, _, _ = check_doc_path_drift._check_cache_valid(tmp)
            self.assertFalse(hit)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DocPathDriftCacheCorruptFallbackTests(unittest.TestCase):
    def test_doc_path_drift_cache_corrupt_fallback(self):
        """check_doc_path_drift cache JSON 损坏 → 视为 cache miss."""
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            _run_doc_path_drift(tmp)
            # Corrupt the cache file
            cache_path = check_doc_path_drift._cache_path(tmp)
            cache_path.write_text("{not valid json", encoding="utf-8")
            # Should be treated as cache miss
            hit, _, _, _ = check_doc_path_drift._check_cache_valid(tmp)
            self.assertFalse(hit)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_doc_path_drift_cache_not_dict_fallback(self):
        """check_doc_path_drift cache JSON 是 list 而非 dict → 视为 cache miss."""
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            _run_doc_path_drift(tmp)
            cache_path = check_doc_path_drift._cache_path(tmp)
            cache_path.write_text("[1, 2, 3]", encoding="utf-8")
            hit, _, _, _ = check_doc_path_drift._check_cache_valid(tmp)
            self.assertFalse(hit)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DocPathDriftCacheExcludesCacheFilesTests(unittest.TestCase):
    """TD-348: cache 文件自身不进入 manifest (避免 N+1 cache miss 循环).

    SCAN_EXTENSIONS 包含 .json, 所以 cache 文件 (.doc-path-drift-cache.json)
    会被 walk_repo 扫到. 但 _build_mtime_manifest 必须排除所有 .-*-cache.json,
    否则每次 cache 写入会改变 cache 文件 mtime → 下次 cache 永久 miss.
    """

    def test_doc_path_drift_cache_file_not_in_manifest(self):
        """_build_mtime_manifest 不包含 .doc-path-drift-cache.json."""
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            # Create the cache file (simulating a previous run)
            cache_path = check_doc_path_drift._cache_path(tmp)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text('{"manifest": {}}', encoding="utf-8")
            # Build manifest
            manifest = check_doc_path_drift._build_mtime_manifest(tmp)
            # Cache file should NOT be in manifest
            cache_rel = f".ai-memory/{check_doc_path_drift.CACHE_FILE_NAME}"
            self.assertNotIn(cache_rel, manifest)
            # But other .py files should be
            self.assertIn("backend/test.py", manifest)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_doc_path_drift_all_cache_files_excluded(self):
        """_build_mtime_manifest 排除所有 5 个 cache/state 文件 (跨 hook 隔离 + runtime state)."""
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            # Create all 5 auto-written files (4 cache + 1 runtime state)
            for name in [
                ".doc-path-drift-cache.json",
                ".sync-cache.json",
                ".docs-index-cache.json",
                ".path-consistency-cache.json",
                "sync-state.json",  # sync_ai_memory runtime state (.gitignored)
            ]:
                p = tmp / ".ai-memory" / name
                p.write_text('{"manifest": {}}', encoding="utf-8")
            manifest = check_doc_path_drift._build_mtime_manifest(tmp)
            # None of the auto-written files should be in manifest
            for name in [
                ".doc-path-drift-cache.json",
                ".sync-cache.json",
                ".docs-index-cache.json",
                ".path-consistency-cache.json",
                "sync-state.json",
            ]:
                self.assertNotIn(f".ai-memory/{name}", manifest)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_doc_path_drift_cache_hit_after_cache_write(self):
        """cache 写入后立即再检查 → 应 cache hit (不是 cache miss).

        这是 TD-348 核心验证: 修复前 cache 写入会改变 cache 文件 mtime →
        下次检查 manifest 不匹配 → cache miss. 修复后 cache 文件被排除,
        manifest 不包含 cache 文件 → cache hit.
        """
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            # First run: full scan, write cache
            _run_doc_path_drift(tmp)
            # Immediately check cache validity (no file changes since write)
            hit, _, _, _ = check_doc_path_drift._check_cache_valid(tmp)
            self.assertTrue(hit, "cache must hit immediately after write (cache file excluded from manifest)")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_doc_path_drift_performance_baseline_excluded(self):
        """_build_mtime_manifest 排除 docs/reference/performance-baseline.md.

        governance-batch 每次 end 都会 _append_performance_baseline 写这个文件,
        不排除会导致下次 batch 的 doc-path-drift 永久 cache miss (N+1 loop).
        """
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            # Create the auto-written performance-baseline.md
            pb = tmp / "docs" / "reference" / "performance-baseline.md"
            pb.parent.mkdir(parents=True, exist_ok=True)
            pb.write_text("| timestamp | batch_pass |\n", encoding="utf-8")
            manifest = check_doc_path_drift._build_mtime_manifest(tmp)
            self.assertNotIn("docs/reference/performance-baseline.md", manifest)
            # But other .md files should be in manifest
            # (backend/test.py is .py, not .md — check docs/reference/ itself isn't fully excluded)
            self.assertIn("backend/test.py", manifest)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DocPathDriftCacheViolationPersistedTests(unittest.TestCase):
    """cache hit 时返回上次扫描的 exit code (违规状态持久化)."""

    def test_doc_path_drift_violation_exit_code_persisted(self):
        """有违规的扫描结果 → cache hit 时返回 exit code 1."""
        tmp = _make_temp_repo({"backend/bad.py": SAMPLE_PY_WITH_FORBIDDEN_PATH})
        try:
            # First run: should find violation, exit 1
            rc1 = _run_doc_path_drift(tmp)
            self.assertEqual(rc1, 1)
            # Second run: cache hit, should return same exit code 1
            rc2 = _run_doc_path_drift(tmp)
            self.assertEqual(rc2, 1)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


# ===========================================================================
# check_path_consistency cache tests (TD-348)
# ===========================================================================


class PathConsistencyCacheMissFirstRunTests(unittest.TestCase):
    def test_path_consistency_cache_miss_first_run(self):
        """check_path_consistency 首次运行无 cache → 全量扫描 → 写 cache."""
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            self.assertFalse(check_path_consistency._cache_path(tmp).exists())
            rc = _run_path_consistency(tmp)
            self.assertEqual(rc, 0)
            self.assertTrue(check_path_consistency._cache_path(tmp).exists())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class PathConsistencyCacheHitSecondRunTests(unittest.TestCase):
    def test_path_consistency_cache_hit_second_run(self):
        """check_path_consistency 第二次运行 cache 命中 → 跳过全量扫描."""
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            _run_path_consistency(tmp)
            rc = _run_path_consistency(tmp)
            self.assertEqual(rc, 0)
            hit, _, _, _ = check_path_consistency._check_cache_valid(tmp)
            self.assertTrue(hit)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class PathConsistencyCacheInvalidateOnModifyTests(unittest.TestCase):
    def test_path_consistency_cache_invalidate_on_modify(self):
        """修改一个 .py → cache 失效."""
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            _run_path_consistency(tmp)
            (tmp / "backend" / "test.py").write_text("# modified\n", encoding="utf-8")
            hit, _, _, _ = check_path_consistency._check_cache_valid(tmp)
            self.assertFalse(hit)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class PathConsistencyCacheCorruptFallbackTests(unittest.TestCase):
    def test_path_consistency_cache_corrupt_fallback(self):
        """check_path_consistency cache JSON 损坏 → 视为 cache miss."""
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            _run_path_consistency(tmp)
            cache_path = check_path_consistency._cache_path(tmp)
            cache_path.write_text("{not valid json", encoding="utf-8")
            hit, _, _, _ = check_path_consistency._check_cache_valid(tmp)
            self.assertFalse(hit)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class PathConsistencyGitignoreInManifestTests(unittest.TestCase):
    """check_path_consistency 的 manifest 包含 .gitignore (severity 依赖 gitignore patterns)."""

    def test_gitignore_in_manifest(self):
        """.gitignore 应在 manifest 中 (修改 .gitignore → cache 失效)."""
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            manifest = check_path_consistency._build_mtime_manifest(tmp)
            self.assertIn(".gitignore", manifest)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_gitignore_modify_invalidates_cache(self):
        """修改 .gitignore → cache 失效 (severity 可能变化)."""
        tmp = _make_temp_repo({"backend/test.py": SAMPLE_PY})
        try:
            _run_path_consistency(tmp)
            # Modify .gitignore
            (tmp / ".gitignore").write_text("# changed gitignore\n*.pyc\n", encoding="utf-8")
            hit, _, _, _ = check_path_consistency._check_cache_valid(tmp)
            self.assertFalse(hit)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class PathConsistencyCacheViolationPersistedTests(unittest.TestCase):
    def test_path_consistency_warning_count_persisted(self):
        """有 warning 的扫描结果 → cache hit 时返回相同的 warning_count."""
        tmp = _make_temp_repo({"backend/abs.py": SAMPLE_PY_WITH_ABS_PATH})
        try:
            # First run: should find absolute path warning
            rc1 = _run_path_consistency(tmp)
            self.assertEqual(rc1, 0)  # warnings don't fail
            # Check cache was written with warning_count > 0
            cache = check_path_consistency._load_cache(tmp)
            self.assertIsNotNone(cache)
            self.assertGreater(cache.get("last_warning_count", 0), 0)
            # Second run: cache hit, should return same exit code
            rc2 = _run_path_consistency(tmp)
            self.assertEqual(rc2, 0)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


# ===========================================================================
# check_doc_path_drift incremental scan tests (TD-390)
# ===========================================================================


class DocPathDriftIncrementalScanTests(unittest.TestCase):
    """cache miss 后增量重扫: 只重扫 mtime changed 文件, 复用其余缓存结果.

    验证三件事:
    - 修一个文件 → 增量路径 (非全量), 且新违规被发现
    - 删除违规文件 → 增量的 violation 记录消失, exit code 归 0
    - 新增违规文件 → 增量能发现 (正确性 == 全量)
    """

    def _assert_scan_mode(self, tmp: Path, expect_incremental: bool) -> None:
        """断言下次运行走 incremental 而非 full (通过捕获 print 输出)."""
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        old_argv = sys.argv
        sys.argv = ["check_doc_path_drift", "--root", str(tmp)]
        try:
            with redirect_stdout(buf):
                check_doc_path_drift.main()
        finally:
            sys.argv = old_argv
        out = buf.getvalue()
        if expect_incremental:
            self.assertIn("incremental scan", out)
        else:
            self.assertIn("full scan", out)

    def test_modify_detects_new_violation_incrementally(self):
        """改一个无违规文件为其含违规 → 增量路径, 返回 exit 1."""
        tmp = _make_temp_repo({"backend/a.py": SAMPLE_PY, "backend/b.py": SAMPLE_PY})
        try:
            self.assertEqual(_run_doc_path_drift(tmp), 0)
            # Insert a forbidden path into b.py → cache miss → incremental
            (tmp / "backend" / "b.py").write_text(SAMPLE_PY_WITH_FORBIDDEN_PATH, encoding="utf-8")
            self._assert_scan_mode(tmp, expect_incremental=True)
            rc = _run_doc_path_drift(tmp)
            self.assertEqual(rc, 1, "新增违规必须在增量扫描中被发现")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_delete_clears_violation_incrementally(self):
        """删除违规文件 → 增量路径, violation 记录消失, exit 归 0."""
        tmp = _make_temp_repo({"backend/bad.py": SAMPLE_PY_WITH_FORBIDDEN_PATH})
        try:
            self.assertEqual(_run_doc_path_drift(tmp), 1)
            # Delete the violating file → cache miss → incremental
            (tmp / "backend" / "bad.py").unlink()
            self._assert_scan_mode(tmp, expect_incremental=True)
            rc = _run_doc_path_drift(tmp)
            self.assertEqual(rc, 0, "删除违规文件后 violation 必须消失")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_incremental_result_persisted_and_cached(self):
        """增量扫描后写 cache, 再次运行 (无改动) 应 cache hit."""
        tmp = _make_temp_repo({"backend/a.py": SAMPLE_PY, "backend/b.py": SAMPLE_PY})
        try:
            _run_doc_path_drift(tmp)
            (tmp / "backend" / "b.py").write_text(SAMPLE_PY_WITH_FORBIDDEN_PATH, encoding="utf-8")
            rc = _run_doc_path_drift(tmp)  # incremental, finds violation
            self.assertEqual(rc, 1)
            hit, _, violation_count, _ = check_doc_path_drift._check_cache_valid(tmp)
            self.assertTrue(hit, "incremental 后应写入 cache")
            self.assertGreater(violation_count, 0, "violation count 应在 cache 中持久化")
            # Third run no change → cache hit → returns persisted exit code 1
            rc2 = _run_doc_path_drift(tmp)
            self.assertEqual(rc2, 1)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


# ===========================================================================
# check_path_consistency incremental scan tests (TD-390)
# ===========================================================================


class PathConsistencyIncrementalScanTests(unittest.TestCase):
    """cache miss 后增量重扫: 只重扫 mtime changed 文件, 复用其余缓存结果."""

    SAMPLE_INLINE = 'import os\nX = os.path.join("a", "b")\n'  # no inline path
    # Split the basename so the checker does not flag THIS test module's source
    # as a real inline path; the written temp file still contains the contiguous
    # literal and is correctly flagged (known canonical → warning).
    _SYNC_NAME = "sync-state"
    SAMPLE_INLINE_HIT = 'Path(x) / "' + _SYNC_NAME + '.json"\n'  # known canonical → warning

    def _run(self, tmp: Path) -> tuple[int, str]:
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        old_argv = sys.argv
        sys.argv = ["check_path_consistency", "--root", str(tmp)]
        try:
            with redirect_stdout(buf):
                rc = check_path_consistency.main()
        finally:
            sys.argv = old_argv
        return rc, buf.getvalue()

    def test_modify_runs_incremental_and_persists(self):
        """改一个文件 → 增量路径; 之后无改动 → cache hit 返回相同结果."""
        tmp = _make_temp_repo({"backend/a.py": self.SAMPLE_INLINE,
                               "backend/b.py": self.SAMPLE_INLINE})
        try:
            rc, _ = self._run(tmp)
            self.assertEqual(rc, 0)
            # Change one file to reference a canonical path → incremental
            (tmp / "backend" / "b.py").write_text(self.SAMPLE_INLINE_HIT, encoding="utf-8")
            rc, out = self._run(tmp)
            self.assertIn("incremental scanning", out, "must take incremental path")
            # Third run with no change → cache hit
            rc2, out2 = self._run(tmp)
            self.assertIn("cache hit", out2)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
