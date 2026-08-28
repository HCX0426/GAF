"""test_check_git_status_after_hook.py — Unit tests for the N105 MM-state guard.

Covers the 5 most relevant scenarios for the post-hook git-status
check:

1. test_clean_working_tree          — no problems; exit 0
2. test_mm_state_detected           — staged+modified file; exit 1
3. test_am_state_detected           — added-in-index+modified; exit 1
4. test_auto_only_filter            — only known auto-maintained paths reported
5. test_parse_porcelain_renamed     — `R  old -> new` collapsed to new path
6. test_find_git_root_walks_up      — _find_git_root locates the .git/ directory

Run with: `python GAF/scripts/tests/test_check_git_status_after_hook.py`
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

import check_git_status_after_hook as check_module  # noqa: E402


def _make_temp_repo() -> Path:
    """Create a temporary git repository with one empty commit.

    The temp dir is a real git repo so `git status --porcelain`
    inside it will return deterministic output. The caller is
    responsible for cleanup.
    """
    tmp = Path(tempfile.mkdtemp(prefix="gaf_test_mm_"))
    # `git init` is required so the script can find `.git/`.
    subprocess.run(
        ["git", "init", "-q", "--initial-branch=main"],
        cwd=str(tmp),
        check=True,
    )
    # Set a user identity so the commit below does not fail.
    subprocess.run(
        ["git", "config", "user.email", "test@gaf.local"],
        cwd=str(tmp),
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "GAF Test"],
        cwd=str(tmp),
        check=True,
    )
    # An initial commit is required so subsequent `git add` has a HEAD.
    (tmp / "README.md").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(tmp), check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"],
        cwd=str(tmp),
        check=True,
    )
    return tmp


class CleanWorkingTreeTests(unittest.TestCase):
    def test_clean_working_tree(self):
        tmp = _make_temp_repo()
        try:
            # Use a script invocation rather than scan_problems()
            # directly so we exercise the real subprocess path.
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "hooks" / "check_git_status_after_hook.py"),
                    "--root", str(tmp),
                ],
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0)
            stdout_text = (result.stdout or b"").decode("utf-8", errors="replace")
            self.assertIn("git-status clean", stdout_text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class MmStateDetectedTests(unittest.TestCase):
    def test_mm_state_detected(self):
        tmp = _make_temp_repo()
        try:
            # To get a true "MM" we need an EXISTING tracked file
            # that is modified in BOTH the index and the work tree.
            # The sequence is: (1) commit a baseline, (2) modify +
            # `git add` to mark the index dirty, (3) modify the
            # working tree again so the two states diverge.
            target = tmp / "tracked.md"
            target.write_text("baseline", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.md"], cwd=str(tmp), check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "add tracked.md"],
                cwd=str(tmp),
                check=True,
            )
            target.write_text("index-edit", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.md"], cwd=str(tmp), check=True)
            target.write_text("worktree-edit", encoding="utf-8")

            problems = check_module.scan_problems(tmp)
            statuses = [p.status for p in problems]
            self.assertIn("MM", statuses)
            self.assertTrue(
                any(p.path == "tracked.md" for p in problems),
                f"expected tracked.md in problems, got {problems!r}",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_am_state_detected(self):
        tmp = _make_temp_repo()
        try:
            # New untracked file: `git add` then modify yields "AM"
            # (added in index, modified in work tree).
            target = tmp / "newfile.md"
            target.write_text("v1", encoding="utf-8")
            subprocess.run(["git", "add", "newfile.md"], cwd=str(tmp), check=True)
            target.write_text("v2", encoding="utf-8")

            problems = check_module.scan_problems(tmp)
            statuses = [p.status for p in problems]
            self.assertIn("AM", statuses)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_am_state_blocks_commit(self):
        # End-to-end: invoke the script and verify it exits non-zero
        # so the pre-commit framework treats it as a failure.
        tmp = _make_temp_repo()
        try:
            target = tmp / "newfile.md"
            target.write_text("v1", encoding="utf-8")
            subprocess.run(["git", "add", "newfile.md"], cwd=str(tmp), check=True)
            target.write_text("v2", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "hooks" / "check_git_status_after_hook.py"),
                    "--root", str(tmp),
                ],
                capture_output=True,
            )
            self.assertEqual(result.returncode, 1)
            stderr_text = (result.stderr or b"").decode("utf-8", errors="replace")
            self.assertIn("N105", stderr_text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class AutoOnlyFilterTests(unittest.TestCase):
    def test_auto_only_filter(self):
        tmp = _make_temp_repo()
        try:
            # Two MM files: one in the auto-maintained set, one not.
            auto = tmp / ".ai-memory" / "meta" / "docs-index.md"
            auto.parent.mkdir(parents=True, exist_ok=True)
            auto.write_text("v1", encoding="utf-8")
            subprocess.run(["git", "add", str(auto.relative_to(tmp))], cwd=str(tmp), check=True)
            auto.write_text("v2", encoding="utf-8")

            # Path mirrors the real repo layout where sync_ai_memory.py lives
            # under scripts/bootstrap/ (not scripts/ directly).
            other = tmp / "scripts" / "bootstrap" / "sync_ai_memory.py"
            other.parent.mkdir(parents=True, exist_ok=True)
            other.write_text("v1", encoding="utf-8")
            subprocess.run(["git", "add", str(other.relative_to(tmp))], cwd=str(tmp), check=True)
            other.write_text("v2", encoding="utf-8")

            # Default scan: should report BOTH.
            all_problems = check_module.scan_problems(tmp)
            all_paths = {p.path for p in all_problems}
            self.assertIn("scripts/bootstrap/sync_ai_memory.py", all_paths)
            self.assertTrue(
                any(".ai-memory" in p for p in all_paths),
                f"expected .ai-memory path in {all_paths!r}",
            )

            # --auto-only: should only report the auto-maintained one.
            auto_problems = check_module.scan_problems(tmp, auto_only=True)
            auto_paths = {p.path for p in auto_problems}
            self.assertNotIn("scripts/bootstrap/sync_ai_memory.py", auto_paths)
            self.assertEqual(len(auto_problems), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class HookMaintainedPathsTests(unittest.TestCase):
    """N190 — files in HOOK_MAINTAINED_PATHS must be skipped in ALL modes.

    Root-cause fix for the governance-batch ↔ N105 infinite loop:
    governance-batch writes docs/reference/performance-baseline.md
    every pre-commit run, which would otherwise create an MM state
    that N105 blocks. The whitelist lets the hook write proceed.
    """

    def test_hook_maintained_path_skipped_in_all_mode(self):
        """Default scan (--all) must skip HOOK_MAINTAINED_PATHS."""
        tmp = _make_temp_repo()
        try:
            # Create docs/reference/performance-baseline.md in MM state.
            baseline = tmp / "docs" / "reference" / "performance-baseline.md"
            baseline.parent.mkdir(parents=True, exist_ok=True)
            baseline.write_text("v1\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "docs/reference/performance-baseline.md"],
                cwd=str(tmp), check=True,
            )
            subprocess.run(
                ["git", "commit", "-q", "-m", "add baseline"],
                cwd=str(tmp), check=True,
            )
            baseline.write_text("v1\nv2\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "docs/reference/performance-baseline.md"],
                cwd=str(tmp), check=True,
            )
            baseline.write_text("v1\nv2\nv3\n", encoding="utf-8")

            # Default scan: performance-baseline.md should NOT be reported.
            problems = check_module.scan_problems(tmp)
            paths = {p.path for p in problems}
            self.assertNotIn(
                "docs/reference/performance-baseline.md", paths,
                f"HOOK_MAINTAINED_PATHS whitelist failed; got {problems!r}",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_hook_maintained_path_skipped_in_auto_only_mode(self):
        """--auto-only mode must also skip HOOK_MAINTAINED_PATHS."""
        tmp = _make_temp_repo()
        try:
            baseline = tmp / "docs" / "reference" / "performance-baseline.md"
            baseline.parent.mkdir(parents=True, exist_ok=True)
            baseline.write_text("v1\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "docs/reference/performance-baseline.md"],
                cwd=str(tmp), check=True,
            )
            baseline.write_text("v1\nv2\n", encoding="utf-8")

            problems = check_module.scan_problems(tmp, auto_only=True)
            paths = {p.path for p in problems}
            self.assertNotIn(
                "docs/reference/performance-baseline.md", paths,
                f"HOOK_MAINTAINED_PATHS whitelist failed in auto_only; "
                f"got {problems!r}",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_non_hook_maintained_mm_still_detected(self):
        """Whitelist must NOT mask MM bugs on other files."""
        tmp = _make_temp_repo()
        try:
            # A regular tracked file in MM state (not in whitelist).
            other = tmp / "src" / "important.py"
            other.parent.mkdir(parents=True, exist_ok=True)
            other.write_text("v1\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "src/important.py"],
                cwd=str(tmp), check=True,
            )
            subprocess.run(
                ["git", "commit", "-q", "-m", "add important"],
                cwd=str(tmp), check=True,
            )
            other.write_text("v2\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "src/important.py"],
                cwd=str(tmp), check=True,
            )
            other.write_text("v3\n", encoding="utf-8")

            problems = check_module.scan_problems(tmp)
            paths = {p.path for p in problems}
            self.assertIn(
                "src/important.py", paths,
                f"Non-whitelisted MM must still be detected; got {problems!r}",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ParsePorcelainLineTests(unittest.TestCase):
    def test_basic_porcelain(self):
        entry = check_module._parse_porcelain_line("MM staged.md")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.status, "MM")
        self.assertEqual(entry.path, "staged.md")

    def test_renamed_porcelain(self):
        # Format from `git status --porcelain` for renames:
        #   "R  old.md -> new.md"
        # The status letters are R, then space (unstaged), so the
        # 2-letter code is "R " (R + space). The script still
        # extracts the destination path.
        entry = check_module._parse_porcelain_line("R  old.md -> new.md")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.path, "new.md")

    def test_short_line_ignored(self):
        self.assertIsNone(check_module._parse_porcelain_line("XY"))


class FindGitRootTests(unittest.TestCase):
    def test_find_git_root_walks_up(self):
        tmp = _make_temp_repo()
        try:
            nested = tmp / "a" / "b" / "c"
            nested.mkdir(parents=True)
            found = check_module._find_git_root(nested)
            self.assertEqual(found.resolve(), tmp.resolve())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_find_git_root_no_repo(self):
        # Use a temp dir with no .git/ — _find_git_root must return None.
        tmp = Path(tempfile.mkdtemp(prefix="gaf_test_norepo_"))
        try:
            found = check_module._find_git_root(tmp)
            self.assertIsNone(found)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
