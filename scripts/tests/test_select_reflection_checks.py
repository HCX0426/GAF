"""Tests for ``scripts/select_reflection_checks.py`` (TD-166).

Covers PATH_PATTERNS + CONTENT_PATTERNS + DEFAULT_CORE_CHECKS + select_checks()
padding/trimming logic. Git subprocess calls are not exercised here; the
selection logic itself is pure-Python and deterministic.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

pytestmark = pytest.mark.unit

from scripts.select_reflection_checks import (  # noqa: E402
    CONTENT_PATTERNS,
    DEFAULT_CORE_CHECKS,
    MAX_CHECKS,
    MIN_CHECKS,
    PATH_PATTERNS,
    select_checks,
)


class TestPathPatterns(unittest.TestCase):
    """PATH_PATTERNS regex coverage."""

    def test_backend_models_py_matches(self):
        """backend/<app>/models.py triggers N112 + N128."""
        selected = select_checks(["backend/tasks/models.py"], "")
        n_ids = {n for n, _ in selected}
        self.assertIn("N112", n_ids)
        self.assertIn("N128", n_ids)

    def test_backend_serializers_py_matches(self):
        """backend/<app>/serializers.py triggers N112 + N128."""
        selected = select_checks(["backend/tasks/serializers.py"], "")
        n_ids = {n for n, _ in selected}
        self.assertIn("N112", n_ids)
        self.assertIn("N128", n_ids)

    def test_sync_scripts_match_n116_n117(self):
        """scripts/sync_*.py triggers N116 + N117."""
        selected = select_checks(["scripts/bootstrap/sync_ai_memory.py"], "")
        n_ids = {n for n, _ in selected}
        self.assertIn("N116", n_ids)
        self.assertIn("N117", n_ids)

    def test_rules_md_matches_n166_n167(self):
        """.skills/rules/*.md triggers N166 + N167."""
        selected = select_checks([".skills/rules/project_rules.md"], "")
        n_ids = {n for n, _ in selected}
        self.assertIn("N166", n_ids)
        self.assertIn("N167", n_ids)

    def test_skill_md_matches_n117_n124_n166_n167(self):
        """SKILL.md triggers N117 + N124 + N166 + N167."""
        selected = select_checks([".skills/skills/gaf-orchestrator/SKILL.md"], "")
        n_ids = {n for n, _ in selected}
        for expected in ("N117", "N124", "N166", "N167"):
            self.assertIn(expected, n_ids)

    def test_docs_standards_md_matches_n167(self):
        """docs/standards/*.md triggers N167."""
        selected = select_checks(["docs/standards/api-contract.md"], "")
        n_ids = {n for n, _ in selected}
        self.assertIn("N167", n_ids)

    def test_failure_modes_md_matches_n95_n132(self):
        """failure-modes.md triggers N95 + N132."""
        selected = select_checks([".ai-memory/meta/failure-modes.md"], "")
        n_ids = {n for n, _ in selected}
        self.assertIn("N95", n_ids)
        self.assertIn("N132", n_ids)


class TestContentPatterns(unittest.TestCase):
    """CONTENT_PATTERNS regex coverage."""

    def test_pytest_keyword_matches_n111(self):
        """Diff content with 'pytest' triggers N111."""
        selected = select_checks([], "    +    pytest tests/\n")
        n_ids = {n for n, _ in selected}
        self.assertIn("N111", n_ids)

    def test_git_add_keyword_matches_n150_n153(self):
        """Diff content with 'git add' triggers N150 + N153."""
        selected = select_checks([], "    +    git add file.py\n")
        n_ids = {n for n, _ in selected}
        self.assertIn("N150", n_ids)
        self.assertIn("N153", n_ids)

    def test_pre_commit_keyword_matches_n91_n150(self):
        """Diff content with 'pre-commit' triggers N91 + N150."""
        selected = select_checks([], "    +pre-commit run\n")
        n_ids = {n for n, _ in selected}
        self.assertIn("N91", n_ids)
        self.assertIn("N150", n_ids)


class TestDefaultCoreChecks(unittest.TestCase):
    """DEFAULT_CORE_CHECKS padding behavior."""

    def test_empty_diff_pads_to_min_checks(self):
        """No matches → padded to MIN_CHECKS with default core checks."""
        selected = select_checks([], "")
        self.assertEqual(len(selected), MIN_CHECKS)
        n_ids = {n for n, _ in selected}
        for n_id, _ in DEFAULT_CORE_CHECKS[:MIN_CHECKS]:
            self.assertIn(n_id, n_ids)

    def test_default_core_checks_includes_n97_n109_n128(self):
        """Default 3 core checks are N97, N109, N128."""
        n_ids = [n for n, _ in DEFAULT_CORE_CHECKS]
        self.assertIn("N97", n_ids)
        self.assertIn("N109", n_ids)
        self.assertIn("N128", n_ids)


class TestSelectChecksTrimming(unittest.TestCase):
    """MAX_CHECKS trimming behavior."""

    def test_trim_to_max_checks(self):
        """Many matches → trimmed to MAX_CHECKS (6)."""
        # Trigger many path patterns simultaneously
        paths = [
            "backend/tasks/models.py",                  # N112, N128
            "backend/tasks/serializers.py",              # N112, N128 (dup)
            "scripts/bootstrap/sync_ai_memory.py",                 # N116, N117
            "scripts/bootstrap/sync_skills.py",          # N117 (dup)
            "scripts/lessons/promote_lessons.py",        # N95
            "frontend/src/types/models.ts",              # N112 (dup)
            "docs/specs/active/test.md",                 # N160
            ".skills/rules/project_rules.md",              # N166, N167
            ".skills/skills/gaf-orchestrator/SKILL.md",    # N117, N124, N166, N167 (dup)
            "docs/standards/api-contract.md",            # N167 (dup)
            ".ai-memory/meta/failure-modes.md",          # N95 (dup), N132
        ]
        selected = select_checks(paths, "")
        self.assertLessEqual(len(selected), MAX_CHECKS)

    def test_first_match_wins(self):
        """First path pattern match wins per N## (no duplicate N##)."""
        selected = select_checks(
            ["backend/tasks/models.py", "backend/tasks/serializers.py"], ""
        )
        n_ids = [n for n, _ in selected]
        # No duplicate N## in result
        self.assertEqual(len(n_ids), len(set(n_ids)))


class TestPathPatternIntegrity(unittest.TestCase):
    """PATH_PATTERNS structural integrity."""

    def test_all_patterns_have_3_tuple(self):
        """Each PATH_PATTERNS entry is (regex, list[N##], sub_file)."""
        for entry in PATH_PATTERNS:
            self.assertEqual(len(entry), 3)
            pattern, n_ids, sub_file = entry
            self.assertIsInstance(pattern, str)
            self.assertIsInstance(n_ids, list)
            self.assertTrue(len(n_ids) > 0)
            self.assertIsInstance(sub_file, str)
            self.assertTrue(sub_file.endswith(".md"))

    def test_all_content_patterns_have_3_tuple(self):
        """Each CONTENT_PATTERNS entry is (regex, list[N##], sub_file)."""
        for entry in CONTENT_PATTERNS:
            self.assertEqual(len(entry), 3)
            pattern, n_ids, sub_file = entry
            self.assertIsInstance(pattern, str)
            self.assertIsInstance(n_ids, list)
            self.assertTrue(len(n_ids) > 0)
            self.assertIsInstance(sub_file, str)
            self.assertTrue(sub_file.endswith(".md"))


if __name__ == "__main__":
    unittest.main()
